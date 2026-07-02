# -*- coding: utf-8 -*-
"""
service/async_session_manager.py
────────────────────────────────
Async session manager with LRU memory cache + persistent dual-write,
background eviction, and asyncio.Lock concurrency safety.
"""

from __future__ import annotations

import asyncio
import time
import logging
from collections import OrderedDict
from typing import List, Optional

from service.stores.base import SessionStore
from service.models import Session, TurnRecord, SessionSummary

logger = logging.getLogger(__name__)


class AsyncSessionManager:
    """
    Manages active sessions in memory with async persistence.

    - LRU cache (OrderedDict) with configurable max size
    - Background eviction every ``eviction_interval_seconds``
    - TTL-based expiration (default 1 hour)
    - Dual-write: memory + persistent store
    - Pure ``asyncio.Lock`` (no threading)
    """

    def __init__(
        self,
        store: Optional[SessionStore] = None,
        ttl_seconds: int = 3600,
        max_memory_sessions: int = 10000,
        eviction_interval_seconds: int = 300,
    ):
        self.store = store
        self.ttl_seconds = ttl_seconds
        self.max_memory_sessions = max_memory_sessions
        self.eviction_interval = eviction_interval_seconds

        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._lock = asyncio.Lock()
        self._eviction_task: Optional[asyncio.Task] = None
        self._running = False

    # ── Lifecycle ────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background eviction loop."""
        self._running = True
        self._eviction_task = asyncio.create_task(self._eviction_loop())
        logger.info(
            "AsyncSessionManager started (ttl=%ds, max_memory=%d, interval=%ds)",
            self.ttl_seconds, self.max_memory_sessions, self.eviction_interval,
        )

    async def stop(self) -> None:
        """Stop background eviction and flush all in-memory sessions."""
        self._running = False
        if self._eviction_task is not None:
            self._eviction_task.cancel()
            try:
                await self._eviction_task
            except asyncio.CancelledError:
                pass
            self._eviction_task = None

        # Final flush of active sessions to persistent store
        if self.store is not None:
            async with self._lock:
                sessions_to_flush = list(self._sessions.values())
            for session in sessions_to_flush:
                if session.state != "closed":
                    try:
                        await self.store.save_session(session)
                    except Exception as exc:
                        logger.warning(
                            "Failed to flush session %s on stop: %s",
                            session.session_id, exc,
                        )

        logger.info("AsyncSessionManager stopped")

    # ── Session operations ───────────────────────────────────────

    async def create_session(
        self,
        tenant_id: str = "default",
        user_id: Optional[str] = None,
    ) -> Session:
        """Create a new session, add to memory cache, and persist."""
        session = Session(
            tenant_id=tenant_id,
            user_id=user_id,
            expires_at=time.time() + self.ttl_seconds,
        )
        async with self._lock:
            self._sessions[session.session_id] = session
            self._sessions.move_to_end(session.session_id)

        if self.store is not None:
            try:
                await self.store.save_session(session)
            except Exception as exc:
                logger.warning(
                    "Failed to persist new session %s: %s",
                    session.session_id, exc,
                )

        logger.info(
            "Session created: %s (tenant=%s, user=%s)",
            session.session_id, tenant_id, user_id,
        )
        return session

    async def get_session(self, session_id: str) -> Optional[Session]:
        """
        Get session by ID.

        1. Check memory cache (LRU hit → move to end)
        2. On miss, load from persistent store and warm back to memory
        3. On hit from store, check TTL before returning
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                if time.time() > session.expires_at:
                    del self._sessions[session_id]
                    logger.debug("Session expired in memory: %s", session_id)
                    return None
                session.touch()
                self._sessions.move_to_end(session_id)
                return session

        # Memory miss → load from persistent store
        if self.store is not None:
            try:
                session = await self.store.load_session(session_id)
                if session is not None:
                    if time.time() > session.expires_at:
                        logger.debug("Session expired in store: %s", session_id)
                        return None
                    session.touch()
                    async with self._lock:
                        self._sessions[session_id] = session
                        self._sessions.move_to_end(session_id)
                    return session
            except Exception as exc:
                logger.error(
                    "Failed to load session %s from store: %s",
                    session_id, exc,
                )

        return None

    async def save_turn(self, session_id: str, turn: TurnRecord) -> bool:
        """
        Append a turn to an in-memory session and persist it.
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                logger.warning("save_turn called for unknown session: %s", session_id)
                return False

            session.history.append(turn)
            session.turn_count = max(session.turn_count, turn.sequence + 1)
            session.touch()
            session.expires_at = time.time() + self.ttl_seconds
            self._sessions.move_to_end(session_id)

        # Persist turn to store
        if self.store is not None:
            try:
                await self.store.save_turn(session_id, turn)
            except Exception as exc:
                logger.warning(
                    "Failed to persist turn for session %s: %s",
                    session_id, exc,
                )
                return False

        return True

    async def update_session(self, session: Session) -> bool:
        """Replace session in memory cache and persist."""
        session.touch()
        session.expires_at = time.time() + self.ttl_seconds

        async with self._lock:
            self._sessions[session.session_id] = session
            self._sessions.move_to_end(session.session_id)

        if self.store is not None:
            try:
                return await self.store.save_session(session)
            except Exception as exc:
                logger.warning(
                    "Failed to persist updated session %s: %s",
                    session.session_id, exc,
                )
                return False

        return True

    async def close_session(self, session_id: str) -> Optional[SessionSummary]:
        """
        Close a session: mark as closed, persist final state, remove from memory.
        """
        async with self._lock:
            session = self._sessions.pop(session_id, None)

        if session is None and self.store is not None:
            try:
                session = await self.store.load_session(session_id)
            except Exception as exc:
                logger.error(
                    "Failed to load session %s for closing: %s",
                    session_id, exc,
                )

        if session is None:
            return None

        session.state = "closed"
        session.touch()

        summary = SessionSummary(
            session_id=session_id,
            last_active=session.last_activity_at,
            turn_count=session.turn_count,
            state=session.state,
            health_score=1.0,
        )

        if self.store is not None:
            try:
                await self.store.save_session(session)
            except Exception as exc:
                logger.warning(
                    "Failed to persist closed session %s: %s",
                    session_id, exc,
                )

        logger.info(
            "Session closed: %s (turns=%d, state=%s)",
            session_id, session.turn_count, session.state,
        )
        return summary

    async def list_sessions(self, tenant_id: str, limit: int = 100) -> List[str]:
        """List active session IDs from persistent store (with memory fallback)."""
        if self.store is not None:
            try:
                return await self.store.list_active_sessions(tenant_id, limit)
            except Exception as exc:
                logger.error("Failed to list sessions from store: %s", exc)

        # Fallback: scan memory only
        async with self._lock:
            now = time.time()
            result = []
            for sid, session in self._sessions.items():
                if (
                    session.tenant_id == tenant_id
                    and session.state != "closed"
                    and now < session.expires_at
                ):
                    result.append(sid)
                    if len(result) >= limit:
                        break
            return result

    # ── Background eviction ──────────────────────────────────────

    async def _eviction_loop(self) -> None:
        """Background loop that periodically evicts stale sessions."""
        while self._running:
            try:
                await asyncio.sleep(self.eviction_interval)
                evicted = await self._evict_expired()
                if evicted > 0:
                    logger.debug("Evicted %d session(s)", evicted)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Eviction loop error: %s", exc)
                await asyncio.sleep(1)

    async def _evict_expired(self) -> int:
        """
        Evict expired and closed sessions.
        If still over ``max_memory_sessions``, evict oldest by LRU.
        """
        now = time.time()
        evicted = 0

        # Phase 1: TTL and closed-state eviction
        async with self._lock:
            expired = [
                sid for sid, session in self._sessions.items()
                if now > session.expires_at or session.state == "closed"
            ]
            for sid in expired:
                session = self._sessions.pop(sid)
                if self.store is not None and session.state != "closed":
                    try:
                        await self.store.save_session(session)
                    except Exception as exc:
                        logger.warning(
                            "Failed to persist evicted session %s: %s",
                            sid, exc,
                        )
                evicted += 1

        # Phase 2: LRU cap eviction
        async with self._lock:
            while len(self._sessions) > self.max_memory_sessions:
                sid, session = self._sessions.popitem(last=False)
                if self.store is not None and session.state != "closed":
                    try:
                        await self.store.save_session(session)
                    except Exception as exc:
                        logger.warning(
                            "Failed to persist LRU-evicted session %s: %s",
                            sid, exc,
                        )
                evicted += 1

        return evicted
