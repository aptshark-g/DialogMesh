# -*- coding: utf-8 -*-
"""
core/agent/service/stores/sqlite.py
───────────────────────────────────
SQLite 会话存储实现（v2.4 服务层新增）。

适合单机部署，零外部依赖。
表结构：
  sessions: 会话主表（JSON 数据）
  turns: 对话轮次表
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import List, Optional

from core.agent.service.stores.base import SessionStore
from core.agent.service.models import Session, TurnRecord


class SQLiteSessionStore(SessionStore):
    """
    SQLite 会话存储。
    线程安全：通过 check_same_thread=False + 外部锁保证（生产环境建议用 aiosqlite）。
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        user_id TEXT,
        data TEXT NOT NULL,
        updated_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_sessions_tenant ON sessions(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at);

    CREATE TABLE IF NOT EXISTS turns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT,
        data TEXT NOT NULL,
        timestamp REAL NOT NULL,
        UNIQUE(session_id, sequence)
    );
    CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
    """

    def __init__(self, db_path: str = "sessions.db"):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库表。"""
        self._conn.executescript(self.SCHEMA)
        self._conn.commit()

    async def save_session(self, session: Session) -> bool:
        try:
            data = json.dumps(session.to_persistent_dict(), ensure_ascii=False)
            self._conn.execute(
                """INSERT INTO sessions (session_id, tenant_id, user_id, data, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET
                     tenant_id=excluded.tenant_id,
                     user_id=excluded.user_id,
                     data=excluded.data,
                     updated_at=excluded.updated_at""",
                (session.session_id, session.tenant_id, session.user_id,
                 data, time.time()),
            )
            self._conn.commit()
            return True
        except Exception:
            return False

    async def load_session(self, session_id: str) -> Optional[Session]:
        try:
            row = self._conn.execute(
                "SELECT data FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            data = json.loads(row["data"])
            return Session.from_persistent_dict(data)
        except Exception:
            return None

    async def save_turn(self, session_id: str, turn: TurnRecord) -> bool:
        try:
            data = json.dumps(turn.to_dict(), ensure_ascii=False)
            self._conn.execute(
                """INSERT INTO turns (session_id, sequence, role, content, data, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(session_id, sequence) DO UPDATE SET
                     role=excluded.role,
                     content=excluded.content,
                     data=excluded.data,
                     timestamp=excluded.timestamp""",
                (session_id, turn.sequence, turn.role, turn.content,
                 data, turn.timestamp),
            )
            self._conn.commit()
            return True
        except Exception:
            return False

    async def get_history(
        self, session_id: str, limit: int = 50,
        before_sequence: Optional[int] = None,
    ) -> List[TurnRecord]:
        try:
            if before_sequence is not None:
                rows = self._conn.execute(
                    """SELECT data FROM turns
                       WHERE session_id = ? AND sequence < ?
                       ORDER BY sequence DESC LIMIT ?""",
                    (session_id, before_sequence, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT data FROM turns
                       WHERE session_id = ?
                       ORDER BY sequence DESC LIMIT ?""",
                    (session_id, limit),
                ).fetchall()
            turns = []
            for row in rows:
                data = json.loads(row["data"])
                turns.append(TurnRecord.from_dict(data))
            turns.reverse()  # 按 sequence 升序
            return turns
        except Exception:
            return []

    async def delete_session(self, session_id: str) -> bool:
        try:
            self._conn.execute(
                "DELETE FROM sessions WHERE session_id = ?", (session_id,)
            )
            self._conn.execute(
                "DELETE FROM turns WHERE session_id = ?", (session_id,)
            )
            self._conn.commit()
            return True
        except Exception:
            return False

    async def list_active_sessions(self, tenant_id: str, limit: int = 100) -> List[str]:
        try:
            rows = self._conn.execute(
                """SELECT session_id FROM sessions
                   WHERE tenant_id = ?
                   ORDER BY updated_at DESC LIMIT ?""",
                (tenant_id, limit),
            ).fetchall()
            return [row["session_id"] for row in rows]
        except Exception:
            return []

    async def health_check(self) -> bool:
        try:
            self._conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False
