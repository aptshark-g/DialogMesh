# -*- coding: utf-8 -*-
"""
service/stores/async_sqlite.py
───────────────────────────────
Async SQLite session store with WAL mode, optimistic locking,
and automatic corruption recovery.

Dependency: aiosqlite (optional, listed under [service] extras)
"""

from __future__ import annotations

import json
import os
import shutil
import time
import logging
from typing import List, Optional

from service.stores.base import SessionStore
from service.models import Session, TurnRecord, UserProfile

try:
    import aiosqlite
except ImportError as _exc:  # pragma: no cover
    aiosqlite = None  # type: ignore

logger = logging.getLogger(__name__)


class AsyncSQLiteSessionStore(SessionStore):
    """
    Production-grade async SQLite session store.

    Features:
      - WAL mode for concurrent read/write
      - Lazy connection on first use
      - Optimistic locking via ``version`` field
      - Automatic corruption detection and backup
      - Pure async/await (no blocking I/O)
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        user_id TEXT,
        version INTEGER DEFAULT 1,
        data JSON NOT NULL,
        updated_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_sessions_tenant ON sessions(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);

    CREATE TABLE IF NOT EXISTS turns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        data JSON NOT NULL,
        timestamp REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, sequence DESC);

    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        data JSON NOT NULL,
        updated_at REAL NOT NULL,
        PRIMARY KEY (user_id, tenant_id)
    );
    CREATE INDEX IF NOT EXISTS idx_user_profiles_tenant ON user_profiles(tenant_id);
    """

    def __init__(self, db_path: str = "sessions.db"):
        if aiosqlite is None:
            raise ImportError(
                "aiosqlite is required for AsyncSQLiteSessionStore. "
                "Install it with: pip install aiosqlite"
            )
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._initialized = False

    # ── Connection lifecycle ───────────────────────────────────────

    async def _ensure_db(self) -> aiosqlite.Connection:
        """Lazy connection with corruption recovery."""
        if self._db is not None:
            return self._db

        # Ensure parent directory exists
        dir_path = os.path.dirname(self.db_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        # Integrity check on existing file
        if os.path.exists(self.db_path) and os.path.getsize(self.db_path) > 0:
            conn = None
            try:
                conn = await aiosqlite.connect(self.db_path)
                await conn.execute("PRAGMA integrity_check")
            except Exception as exc:
                logger.warning(
                    "Database corruption detected on %s: %s. "
                    "Backing up and recreating.",
                    self.db_path, exc,
                )
                backup_path = f"{self.db_path}.corrupt.{int(time.time())}"
                try:
                    shutil.move(self.db_path, backup_path)
                except Exception:
                    try:
                        os.rename(self.db_path, backup_path)
                    except Exception:
                        os.remove(self.db_path)
            finally:
                if conn is not None:
                    try:
                        await conn.close()
                    except Exception:
                        pass

        # Open connection and initialize schema
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA synchronous=NORMAL")
        await self._db.executescript(self.SCHEMA)
        await self._db.commit()
        self._initialized = True
        logger.info("AsyncSQLiteSessionStore initialized: %s", self.db_path)
        return self._db

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None
            self._initialized = False
            logger.info("AsyncSQLiteSessionStore closed: %s", self.db_path)

    # ── Session CRUD ─────────────────────────────────────────────

    async def save_session(self, session: Session) -> bool:
        """Persist session with optimistic locking."""
        try:
            db = await self._ensure_db()
            data = json.dumps(session.to_persistent_dict(), ensure_ascii=False)
            now = time.time()

            # Verify existing version for optimistic locking
            cursor = await db.execute(
                "SELECT version FROM sessions WHERE session_id = ?",
                (session.session_id,),
            )
            row = await cursor.fetchone()

            if row is not None:
                db_version = row[0]
                session_version = getattr(session, "version", 1)
                if db_version != session_version:
                    logger.warning(
                        "Optimistic lock conflict on session %s: "
                        "db_version=%d, session_version=%d",
                        session.session_id, db_version, session_version,
                    )
                    return False
                new_version = session_version + 1
                await db.execute(
                    """UPDATE sessions
                       SET tenant_id = ?, user_id = ?, version = ?,
                           data = ?, updated_at = ?
                       WHERE session_id = ?""",
                    (session.tenant_id, session.user_id, new_version,
                     data, now, session.session_id),
                )
                session.version = new_version
            else:
                await db.execute(
                    """INSERT INTO sessions
                       (session_id, tenant_id, user_id, version, data, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (session.session_id, session.tenant_id, session.user_id,
                     1, data, now),
                )
                session.version = 1

            await db.commit()
            return True
        except Exception as exc:
            logger.error("Failed to save session %s: %s", session.session_id, exc)
            return False

    async def load_session(self, session_id: str) -> Optional[Session]:
        """Load session by ID."""
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
        except Exception as exc:
            logger.error("Failed to load session %s: %s", session_id, exc)
            return None

    async def delete_session(self, session_id: str) -> bool:
        """Delete session and all associated turns."""
        try:
            db = await self._ensure_db()
            await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
            await db.commit()
            return True
        except Exception as exc:
            logger.error("Failed to delete session %s: %s", session_id, exc)
            return False

    async def list_active_sessions(self, tenant_id: str, limit: int = 100) -> List[str]:
        """List session IDs ordered by most recent update."""
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
        except Exception as exc:
            logger.error("Failed to list active sessions for tenant %s: %s", tenant_id, exc)
            return []

    # ── Turn history ─────────────────────────────────────────────

    async def save_turn(self, session_id: str, turn: TurnRecord) -> bool:
        """Persist a turn record."""
        try:
            db = await self._ensure_db()
            data = json.dumps(turn.to_dict(), ensure_ascii=False)
            await db.execute(
                """INSERT INTO turns
                   (session_id, sequence, role, content, data, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, turn.sequence, turn.role, turn.content,
                 data, turn.timestamp),
            )
            await db.commit()
            return True
        except Exception as exc:
            logger.error("Failed to save turn for session %s: %s", session_id, exc)
            return False

    async def get_history(
        self,
        session_id: str,
        limit: int = 50,
        before_sequence: Optional[int] = None,
    ) -> List[TurnRecord]:
        """Retrieve turn history for a session."""
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
            turns = [TurnRecord.from_dict(json.loads(row["data"])) for row in rows]
            turns.reverse()
            return turns
        except Exception as exc:
            logger.error("Failed to get history for session %s: %s", session_id, exc)
            return []

    # ── User profiles ────────────────────────────────────────────

    async def save_user_profile(self, user_id: str, tenant_id: str, profile: UserProfile) -> bool:
        """Persist or update a user profile."""
        try:
            db = await self._ensure_db()
            data = json.dumps(profile.to_dict(), ensure_ascii=False)
            now = time.time()
            await db.execute(
                """INSERT INTO user_profiles (user_id, tenant_id, data, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id, tenant_id) DO UPDATE SET
                     data = excluded.data,
                     updated_at = excluded.updated_at""",
                (user_id, tenant_id, data, now),
            )
            await db.commit()
            return True
        except Exception as exc:
            logger.error("Failed to save user profile %s/%s: %s", tenant_id, user_id, exc)
            return False

    async def load_user_profile(self, user_id: str, tenant_id: str) -> Optional[UserProfile]:
        """Load a user profile by user_id and tenant_id."""
        try:
            db = await self._ensure_db()
            async with db.execute(
                "SELECT data FROM user_profiles WHERE user_id = ? AND tenant_id = ?",
                (user_id, tenant_id),
            ) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return None
                data = json.loads(row["data"])
                return UserProfile.from_dict(data)
        except Exception as exc:
            logger.error("Failed to load user profile %s/%s: %s", tenant_id, user_id, exc)
            return None
