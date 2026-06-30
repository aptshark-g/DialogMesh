# -*- coding: utf-8 -*-
"""
core/agent/service/stores/async_sqlite.py
───────────────────────────────────────────
异步 SQLite 存储实现（生产优化）。

使用 aiosqlite 实现非阻塞 I/O，适合 FastAPI / ASGI 环境。

依赖: pip install aiosqlite
"""

from __future__ import annotations

import aiosqlite
import json
import time
from typing import List, Optional

from core.agent.service.stores.base import SessionStore
from core.agent.service.models import Session, TurnRecord


class AsyncSQLiteSessionStore(SessionStore):
    """
    异步 SQLite 会话存储。
    使用 aiosqlite 实现非阻塞 I/O。
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
        self._db: Optional[aiosqlite.Connection] = None

    async def _ensure_db(self) -> aiosqlite.Connection:
        if self._db is None:
            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row
            await self._db.executescript(self.SCHEMA)
            await self._db.commit()
        return self._db

    async def save_session(self, session: Session) -> bool:
        try:
            db = await self._ensure_db()
            data = json.dumps(session.to_persistent_dict(), ensure_ascii=False)
            await db.execute(
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
            await db.commit()
            return True
        except Exception:
            return False

    async def load_session(self, session_id: str) -> Optional[Session]:
        try:
            db = await self._ensure_db()
            async with db.execute(
                "SELECT data FROM sessions WHERE session_id = ?",
                (session_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return None
                data = json.loads(row["data"])
                return Session.from_persistent_dict(data)
        except Exception:
            return None

    async def save_turn(self, session_id: str, turn: TurnRecord) -> bool:
        try:
            db = await self._ensure_db()
            data = json.dumps(turn.to_dict(), ensure_ascii=False)
            await db.execute(
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
            await db.commit()
            return True
        except Exception:
            return False

    async def get_history(
        self, session_id: str, limit: int = 50,
        before_sequence: Optional[int] = None,
    ) -> List[TurnRecord]:
        try:
            db = await self._ensure_db()
            if before_sequence is not None:
                async with db.execute(
                    """SELECT data FROM turns
                       WHERE session_id = ? AND sequence < ?
                       ORDER BY sequence DESC LIMIT ?""",
                    (session_id, before_sequence, limit),
                ) as cursor:
                    rows = await cursor.fetchall()
            else:
                async with db.execute(
                    """SELECT data FROM turns
                       WHERE session_id = ?
                       ORDER BY sequence DESC LIMIT ?""",
                    (session_id, limit),
                ) as cursor:
                    rows = await cursor.fetchall()
            turns = []
            for row in rows:
                data = json.loads(row["data"])
                turns.append(TurnRecord.from_dict(data))
            turns.reverse()
            return turns
        except Exception:
            return []

    async def delete_session(self, session_id: str) -> bool:
        try:
            db = await self._ensure_db()
            await db.execute(
                "DELETE FROM sessions WHERE session_id = ?", (session_id,)
            )
            await db.execute(
                "DELETE FROM turns WHERE session_id = ?", (session_id,)
            )
            await db.commit()
            return True
        except Exception:
            return False

    async def list_active_sessions(self, tenant_id: str, limit: int = 100) -> List[str]:
        try:
            db = await self._ensure_db()
            async with db.execute(
                """SELECT session_id FROM sessions
                   WHERE tenant_id = ?
                   ORDER BY updated_at DESC LIMIT ?""",
                (tenant_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
            return [row["session_id"] for row in rows]
        except Exception:
            return []

    async def health_check(self) -> bool:
        try:
            db = await self._ensure_db()
            await db.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
