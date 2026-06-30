# core/infrastructure/sqlite_store.py
"""SQLiteStore — 轻量级持久化存储（会话、话题树、用户画像、语义向量）。

设计原则：
- 零依赖：Python 内置 sqlite3，无需安装 PostgreSQL
- 单例模式：进程级共享连接池
- 自动迁移：启动时检查 schema，自动创建表
- 事务安全：所有写操作封装在事务中
- 序列化：JSON 存储复杂结构（dict/list/set）

表结构：
    sessions      — 会话元数据
    turns         — 轮次记录（原始查询、话题归属、路由模式）
    topics        — 话题树节点（聚合、语义摘要、父话题）
    user_profiles — 用户画像（技术水平、领域、自适应阈值）
    index_vectors — 语义索引向量（block_id → 512-dim blob）

使用方式：
    from core.infrastructure.sqlite_store import get_sqlite_store

    store = get_sqlite_store()
    store.save_turn(session_id="s1", turn_index=0, raw_query="...", topic_id=0)
    store.save_topic(session_id="s1", topic_id=0, name="Python", turns=[0,1])
    store.save_user_profile(user_id="u1", profile={"tech_level": "advanced", "domains": ["Python"]})

    # 加载
    turns = store.load_turns(session_id="s1")
    profile = store.load_user_profile(user_id="u1")
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "data/memorygraph.db"


class _SQLiteStoreSingleton:
    """进程级单例。"""

    _instance: Optional["SQLiteStore"] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, db_path: Optional[str] = None) -> "SQLiteStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = SQLiteStore(db_path or DEFAULT_DB_PATH)
        return cls._instance


class SQLiteStore:
    """SQLite 持久化存储。"""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._local = threading.local()
        self._ensure_dir()
        self._init_schema()

    # ── 连接管理 ──────────────────────────────────────────────

    def _ensure_dir(self):
        """确保数据目录存在。"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def _get_conn(self) -> sqlite3.Connection:
        """获取线程本地连接。"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
            # WAL 模式：提高并发性能
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _execute(self, sql: str, params: Tuple = ()) -> sqlite3.Cursor:
        """执行 SQL（自动事务）。"""
        conn = self._get_conn()
        return conn.execute(sql, params)

    def _execute_many(self, sql: str, params_list: List[Tuple]) -> sqlite3.Cursor:
        """批量执行。"""
        conn = self._get_conn()
        return conn.executemany(sql, params_list)

    def _commit(self):
        """提交事务。"""
        self._get_conn().commit()

    def close(self):
        """关闭连接。"""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    # ── Schema 初始化 ─────────────────────────────────────────

    def _init_schema(self):
        """自动创建表（如果不存在）。"""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.executescript(
            """
            -- 会话元数据
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            -- 轮次记录
            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_index INTEGER NOT NULL,
                raw_query TEXT NOT NULL,
                topic_id INTEGER DEFAULT 0,
                intent TEXT,
                router_mode TEXT,
                latency_ms REAL,
                created_at REAL NOT NULL,
                UNIQUE(session_id, turn_index)
            );
            CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
            CREATE INDEX IF NOT EXISTS idx_turns_topic ON turns(session_id, topic_id);

            -- 话题树节点
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                topic_id INTEGER NOT NULL,
                name TEXT,
                domains TEXT,           -- JSON list
                intent TEXT,
                start_idx INTEGER,
                end_idx INTEGER,
                parent_topic INTEGER,
                semantic_summary TEXT,
                audit_status TEXT DEFAULT 'pending',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(session_id, topic_id)
            );
            CREATE INDEX IF NOT EXISTS idx_topics_session ON topics(session_id);

            -- 用户画像
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                tech_level TEXT,
                domains TEXT,           -- JSON list
                style TEXT,
                threshold_profile TEXT, -- JSON dict
                turn_count INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            -- 语义索引向量
            CREATE TABLE IF NOT EXISTS index_vectors (
                block_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                vector BLOB NOT NULL,   -- 512 * 4 bytes = 2048 bytes
                text TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_vectors_session ON index_vectors(session_id);
            """
        )
        conn.commit()
        logger.info(f"SQLiteStore initialized: {self.db_path}")

    # ── 会话 ───────────────────────────────────────────────────

    def save_session(self, session_id: str, user_id: str) -> bool:
        """保存/更新会话。"""
        now = time.time()
        try:
            self._execute(
                """INSERT INTO sessions (session_id, user_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET
                   updated_at=excluded.updated_at""",
                (session_id, user_id, now, now),
            )
            self._commit()
            return True
        except Exception as e:
            logger.warning(f"save_session failed: {e}")
            return False

    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """加载会话元数据。"""
        row = self._execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row:
            return dict(row)
        return None

    def list_sessions(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出会话（可选按用户过滤）。"""
        if user_id:
            rows = self._execute(
                "SELECT * FROM sessions WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        else:
            rows = self._execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_session(self, session_id: str) -> bool:
        """删除会话及其所有数据（级联）。"""
        try:
            self._execute("DELETE FROM index_vectors WHERE session_id = ?", (session_id,))
            self._execute("DELETE FROM topics WHERE session_id = ?", (session_id,))
            self._execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
            self._execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            self._commit()
            return True
        except Exception as e:
            logger.warning(f"delete_session failed: {e}")
            return False

    # ── 轮次 ───────────────────────────────────────────────────

    def save_turn(self, session_id: str, turn_index: int, raw_query: str,
                  topic_id: int = 0, intent: Optional[str] = None,
                  router_mode: Optional[str] = None, latency_ms: Optional[float] = None) -> bool:
        """保存轮次。"""
        try:
            self._execute(
                """INSERT INTO turns (session_id, turn_index, raw_query, topic_id, intent, router_mode, latency_ms, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(session_id, turn_index) DO UPDATE SET
                   raw_query=excluded.raw_query,
                   topic_id=excluded.topic_id,
                   intent=excluded.intent,
                   router_mode=excluded.router_mode,
                   latency_ms=excluded.latency_ms""",
                (session_id, turn_index, raw_query, topic_id, intent, router_mode, latency_ms, time.time()),
            )
            self._commit()
            return True
        except Exception as e:
            logger.warning(f"save_turn failed: {e}")
            return False

    def save_turns(self, session_id: str, turns: List[Dict[str, Any]]) -> int:
        """批量保存轮次。"""
        now = time.time()
        params = []
        for t in turns:
            params.append((
                session_id,
                t.get("turn_index", 0),
                t.get("raw_query", ""),
                t.get("topic_id", 0),
                t.get("intent"),
                t.get("router_mode"),
                t.get("latency_ms"),
                now,
            ))
        try:
            self._execute_many(
                """INSERT INTO turns (session_id, turn_index, raw_query, topic_id, intent, router_mode, latency_ms, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(session_id, turn_index) DO UPDATE SET
                   raw_query=excluded.raw_query,
                   topic_id=excluded.topic_id""",
                params,
            )
            self._commit()
            return len(params)
        except Exception as e:
            logger.warning(f"save_turns failed: {e}")
            return 0

    def load_turns(self, session_id: str) -> List[Dict[str, Any]]:
        """加载会话的所有轮次（按 turn_index 排序）。"""
        rows = self._execute(
            "SELECT * FROM turns WHERE session_id = ? ORDER BY turn_index",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def load_turns_by_topic(self, session_id: str, topic_id: int) -> List[Dict[str, Any]]:
        """加载指定话题的所有轮次。"""
        rows = self._execute(
            "SELECT * FROM turns WHERE session_id = ? AND topic_id = ? ORDER BY turn_index",
            (session_id, topic_id),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── 话题树 ─────────────────────────────────────────────────

    def save_topic(self, session_id: str, topic_id: int, name: str,
                   turns: Optional[List[int]] = None, domains: Optional[List[str]] = None,
                   intent: Optional[str] = None, start_idx: Optional[int] = None,
                   end_idx: Optional[int] = None, parent_topic: Optional[int] = None,
                   semantic_summary: Optional[str] = None, audit_status: str = "pending") -> bool:
        """保存/更新话题节点。"""
        now = time.time()
        try:
            self._execute(
                """INSERT INTO topics (session_id, topic_id, name, domains, intent, start_idx, end_idx, parent_topic, semantic_summary, audit_status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(session_id, topic_id) DO UPDATE SET
                   name=excluded.name,
                   domains=excluded.domains,
                   intent=excluded.intent,
                   start_idx=excluded.start_idx,
                   end_idx=excluded.end_idx,
                   parent_topic=excluded.parent_topic,
                   semantic_summary=excluded.semantic_summary,
                   audit_status=excluded.audit_status,
                   updated_at=excluded.updated_at""",
                (session_id, topic_id, name, json.dumps(domains or [], ensure_ascii=False),
                 intent, start_idx, end_idx, parent_topic, semantic_summary, audit_status, now, now),
            )
            self._commit()
            return True
        except Exception as e:
            logger.warning(f"save_topic failed: {e}")
            return False

    def save_topics(self, session_id: str, topics: List[Dict[str, Any]]) -> int:
        """批量保存话题。"""
        now = time.time()
        params = []
        for t in topics:
            params.append((
                session_id,
                t.get("topic_id", 0),
                t.get("name", ""),
                json.dumps(t.get("domains", []), ensure_ascii=False),
                t.get("intent"),
                t.get("start_idx"),
                t.get("end_idx"),
                t.get("parent_topic"),
                t.get("semantic_summary"),
                t.get("audit_status", "pending"),
                now,
                now,
            ))
        try:
            self._execute_many(
                """INSERT INTO topics (session_id, topic_id, name, domains, intent, start_idx, end_idx, parent_topic, semantic_summary, audit_status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(session_id, topic_id) DO UPDATE SET
                   name=excluded.name,
                   domains=excluded.domains,
                   updated_at=excluded.updated_at""",
                params,
            )
            self._commit()
            return len(params)
        except Exception as e:
            logger.warning(f"save_topics failed: {e}")
            return 0

    def load_topics(self, session_id: str) -> List[Dict[str, Any]]:
        """加载会话的所有话题。"""
        rows = self._execute(
            "SELECT * FROM topics WHERE session_id = ? ORDER BY topic_id",
            (session_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["domains"] = json.loads(d.get("domains") or "[]")
            result.append(d)
        return result

    # ── 用户画像 ───────────────────────────────────────────────

    def save_user_profile(self, user_id: str, profile: Dict[str, Any]) -> bool:
        """保存/更新用户画像。"""
        now = time.time()
        try:
            self._execute(
                """INSERT INTO user_profiles (user_id, tech_level, domains, style, threshold_profile, turn_count, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                   tech_level=excluded.tech_level,
                   domains=excluded.domains,
                   style=excluded.style,
                   threshold_profile=excluded.threshold_profile,
                   turn_count=excluded.turn_count,
                   updated_at=excluded.updated_at""",
                (user_id,
                 profile.get("tech_level"),
                 json.dumps(profile.get("domains", []), ensure_ascii=False),
                 profile.get("style"),
                 json.dumps(profile.get("threshold_profile", {}), ensure_ascii=False),
                 profile.get("turn_count", 0),
                 now, now),
            )
            self._commit()
            return True
        except Exception as e:
            logger.warning(f"save_user_profile failed: {e}")
            return False

    def load_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """加载用户画像。"""
        row = self._execute(
            "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["domains"] = json.loads(d.get("domains") or "[]")
        d["threshold_profile"] = json.loads(d.get("threshold_profile") or "{}")
        return d

    def list_users(self) -> List[Dict[str, Any]]:
        """列出所有用户。"""
        rows = self._execute(
            "SELECT * FROM user_profiles ORDER BY updated_at DESC"
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["domains"] = json.loads(d.get("domains") or "[]")
            d["threshold_profile"] = json.loads(d.get("threshold_profile") or "{}")
            result.append(d)
        return result

    # ── 语义向量 ───────────────────────────────────────────────

    def save_vector(self, block_id: str, session_id: str, vector: np.ndarray, text: str) -> bool:
        """保存语义向量（512-dim float32 → bytes）。"""
        try:
            blob = vector.astype(np.float32).tobytes()
            self._execute(
                """INSERT INTO index_vectors (block_id, session_id, vector, text, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(block_id) DO UPDATE SET
                   vector=excluded.vector,
                   text=excluded.text""",
                (block_id, session_id, blob, text, time.time()),
            )
            self._commit()
            return True
        except Exception as e:
            logger.warning(f"save_vector failed: {e}")
            return False

    def save_vectors(self, session_id: str, vectors: List[Tuple[str, np.ndarray, str]]) -> int:
        """批量保存向量。"""
        now = time.time()
        params = []
        for block_id, vec, text in vectors:
            blob = vec.astype(np.float32).tobytes()
            params.append((block_id, session_id, blob, text, now))
        try:
            self._execute_many(
                """INSERT INTO index_vectors (block_id, session_id, vector, text, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(block_id) DO UPDATE SET
                   vector=excluded.vector""",
                params,
            )
            self._commit()
            return len(params)
        except Exception as e:
            logger.warning(f"save_vectors failed: {e}")
            return 0

    def load_vectors(self, session_id: str) -> List[Dict[str, Any]]:
        """加载会话的所有向量。"""
        rows = self._execute(
            "SELECT * FROM index_vectors WHERE session_id = ?", (session_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            blob = d["vector"]
            vec = np.frombuffer(blob, dtype=np.float32)
            d["vector"] = vec
            result.append(d)
        return result

    def load_vector(self, block_id: str) -> Optional[np.ndarray]:
        """加载单个向量。"""
        row = self._execute(
            "SELECT vector FROM index_vectors WHERE block_id = ?", (block_id,)
        ).fetchone()
        if row:
            return np.frombuffer(row["vector"], dtype=np.float32)
        return None

    def delete_vectors(self, session_id: str) -> int:
        """删除会话的所有向量。"""
        try:
            c = self._execute("DELETE FROM index_vectors WHERE session_id = ?", (session_id,))
            self._commit()
            return c.rowcount
        except Exception as e:
            logger.warning(f"delete_vectors failed: {e}")
            return 0

    # ── 统计 ───────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """获取数据库统计。"""
        conn = self._get_conn()
        cursor = conn.cursor()

        tables = ["sessions", "turns", "topics", "user_profiles", "index_vectors"]
        stats = {}
        for t in tables:
            row = cursor.execute(f"SELECT COUNT(*) FROM {t}").fetchone()
            stats[t] = row[0] if row else 0

        # DB 文件大小
        stats["db_size_kb"] = Path(self.db_path).stat().st_size / 1024
        return stats


def get_sqlite_store(db_path: Optional[str] = None) -> SQLiteStore:
    """获取全局 SQLiteStore 单例。"""
    return _SQLiteStoreSingleton.get_instance(db_path)
