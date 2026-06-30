# -*- coding: utf-8 -*-
"""
core/agent/persistence/sqlite_store.py
────────────────────────────────────
SQLite-backed session store.
使用标准库 sqlite3（同步），线程安全通过 threading.Lock 保证。

设计要点：
  - WAL 模式支持并发读写
  - 懒加载连接（首次使用时创建）
  - JSON 字段存储 dict/list
  - 批量写入优化（事务包裹）
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

from core.agent.persistence.base import SessionStore
from core.agent.persistence.models import Session, TurnRecord


class SQLiteSessionStore(SessionStore):
    """
    SQLite 会话存储实现。
    线程安全：通过 threading.Lock 保护连接操作。
    """

    def __init__(self, db_path: str = "~/.memorygraph/sessions.db"):
        # 路径健壮性：展开 ~ 并创建目录
        self._db_path = os.path.expanduser(db_path)
        Path(os.path.dirname(self._db_path)).mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._initialized = False

    def _ensure_connection(self) -> sqlite3.Connection:
        """懒加载连接，线程安全。"""
        if self._conn is not None:
            return self._conn

        with self._lock:
            if self._conn is not None:
                return self._conn

            self._conn = sqlite3.connect(
                self._db_path,
                check_same_thread=False,  # 我们自己管理线程安全
                timeout=30.0,
            )
            # WAL 模式：支持并发读写，避免写锁阻塞
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.row_factory = sqlite3.Row

            if not self._initialized:
                self._create_tables()
                self._initialized = True

            return self._conn

    def _create_tables(self) -> None:
        """创建表和索引。"""
        conn = self._conn
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                tenant_id TEXT DEFAULT 'default',
                user_id TEXT,
                version INTEGER DEFAULT 1,
                data JSON,
                updated_at REAL
            );

            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                data JSON,
                timestamp REAL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_tenant
                ON sessions(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_updated
                ON sessions(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_turns_session
                ON turns(session_id, sequence DESC);
        """)
        conn.commit()

    # ── SessionStore API ─────────────────────────────────────────

    def save_session(self, session: Session) -> bool:
        """保存或更新会话（UPSERT）。"""
        conn = self._ensure_connection()
        data = session.to_persistent_dict()

        with self._lock:
            try:
                conn.execute(
                    """
                    INSERT INTO sessions (session_id, tenant_id, user_id, version, data, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        tenant_id = excluded.tenant_id,
                        user_id = excluded.user_id,
                        version = excluded.version,
                        data = excluded.data,
                        updated_at = excluded.updated_at
                    """,
                    (
                        session.session_id,
                        session.tenant_id,
                        session.user_id,
                        session.version,
                        json.dumps(data, ensure_ascii=False, default=str),
                        session.last_activity_at,
                    ),
                )
                conn.commit()
                return True
            except sqlite3.Error as e:
                conn.rollback()
                print(f"[SQLiteSessionStore] save_session failed: {e}")
                return False

    def load_session(self, session_id: str) -> Optional[Session]:
        """加载会话（不含 history）。"""
        conn = self._ensure_connection()

        with self._lock:
            row = conn.execute(
                "SELECT data FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()

            if row is None:
                return None

            try:
                data = json.loads(row["data"])
                return Session.from_persistent_dict(data)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[SQLiteSessionStore] load_session decode failed: {e}")
                return None

    def save_turn(self, session_id: str, turn: TurnRecord) -> bool:
        """保存单轮对话记录。"""
        conn = self._ensure_connection()
        data = turn.to_dict()

        with self._lock:
            try:
                conn.execute(
                    """
                    INSERT INTO turns (session_id, sequence, role, content, data, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        turn.sequence,
                        turn.role,
                        turn.content,
                        json.dumps(data, ensure_ascii=False, default=str),
                        turn.timestamp,
                    ),
                )
                conn.commit()
                return True
            except sqlite3.Error as e:
                conn.rollback()
                print(f"[SQLiteSessionStore] save_turn failed: {e}")
                return False

    def load_turns(self, session_id: str, limit: int = 50) -> List[TurnRecord]:
        """加载最近 N 轮对话记录。"""
        conn = self._ensure_connection()

        with self._lock:
            rows = conn.execute(
                """
                SELECT data FROM turns
                WHERE session_id = ?
                ORDER BY sequence DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

            turns = []
            for row in rows:
                try:
                    data = json.loads(row["data"])
                    turns.append(TurnRecord.from_dict(data))
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"[SQLiteSessionStore] load_turns decode failed: {e}")
                    continue

            # 按 sequence 升序排列（老 → 新）
            turns.sort(key=lambda t: t.sequence)
            return turns

    def list_active_sessions(self, limit: int = 20, tenant_id: str = "default") -> List[str]:
        """列出最近活跃的会话 ID。"""
        conn = self._ensure_connection()

        with self._lock:
            rows = conn.execute(
                """
                SELECT session_id FROM sessions
                WHERE tenant_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (tenant_id, limit),
            ).fetchall()

            return [row["session_id"] for row in rows]

    def delete_session(self, session_id: str) -> bool:
        """删除会话及其所有轮次（CASCADE）。"""
        conn = self._ensure_connection()

        with self._lock:
            try:
                conn.execute(
                    "DELETE FROM sessions WHERE session_id = ?",
                    (session_id,),
                )
                conn.commit()
                return True
            except sqlite3.Error as e:
                conn.rollback()
                print(f"[SQLiteSessionStore] delete_session failed: {e}")
                return False

    def close(self) -> None:
        """关闭连接。"""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except sqlite3.Error:
                    pass
                self._conn = None

    # ── 批量写入优化 ───────────────────────────────────────────

    def save_turns_batch(self, session_id: str, turns: List[TurnRecord]) -> bool:
        """批量保存轮次（事务包裹）。"""
        conn = self._ensure_connection()

        with self._lock:
            try:
                conn.execute("BEGIN")
                for turn in turns:
                    conn.execute(
                        """
                        INSERT INTO turns (session_id, sequence, role, content, data, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            session_id,
                            turn.sequence,
                            turn.role,
                            turn.content,
                            json.dumps(turn.to_dict(), ensure_ascii=False, default=str),
                            turn.timestamp,
                        ),
                    )
                conn.commit()
                return True
            except sqlite3.Error as e:
                conn.rollback()
                print(f"[SQLiteSessionStore] save_turns_batch failed: {e}")
                return False

    # ── 维护 ───────────────────────────────────────────────

    def cleanup_expired(self, ttl_seconds: float, dry_run: bool = False) -> int:
        """
        清理过期会话。
        :param ttl_seconds: 过期时间（秒）
        :param dry_run: 如果 True，只返回计数不删除
        :return: 删除的会话数
        """
        conn = self._ensure_connection()
        cutoff = time.time() - ttl_seconds

        with self._lock:
            if dry_run:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM sessions WHERE updated_at < ?",
                    (cutoff,),
                ).fetchone()
                return row["cnt"] if row else 0

            # 先查询计数
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM sessions WHERE updated_at < ?",
                (cutoff,),
            ).fetchone()
            count = row["cnt"] if row else 0

            try:
                conn.execute(
                    "DELETE FROM sessions WHERE updated_at < ?",
                    (cutoff,),
                )
                conn.commit()
                return count
            except sqlite3.Error as e:
                conn.rollback()
                print(f"[SQLiteSessionStore] cleanup_expired failed: {e}")
                return 0
