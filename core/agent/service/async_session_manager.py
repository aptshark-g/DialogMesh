# -*- coding: utf-8 -*-
"""
core/agent/service/async_session_manager.py
─────────────────────────────────────────────
异步会话管理器（生产优化）。

真正的 async/await 实现，支持：
  - aiosqlite / Redis 异步存储
  - 后台过期清理任务（asyncio.Task）
  - 并发安全的 asyncio.Lock（替代 threading.RLock）

不依赖 asyncio.run() 在同步方法里强制调用。
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional, Any

from core.agent.service.models import Session, TurnRecord, SessionSummary
from core.agent.service.stores.base import SessionStore


class AsyncSessionManager:
    """
    异步会话管理器。
    
    使用 asyncio.Lock 保证并发安全，适合 FastAPI / ASGI 环境。
    """

    def __init__(
        self,
        store: Optional[SessionStore] = None,
        ttl_seconds: int = 3600,
        max_memory_sessions: int = 10000,
        eviction_interval_seconds: int = 300,  # 5 分钟清理一次
    ):
        self.store = store
        self.ttl_seconds = ttl_seconds
        self.max_memory_sessions = max_memory_sessions
        self.eviction_interval = eviction_interval_seconds

        self._sessions: Dict[str, Session] = {}
        self._lock = asyncio.Lock()
        self._eviction_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """启动后台清理任务。"""
        self._running = True
        self._eviction_task = asyncio.create_task(self._eviction_loop())

    async def stop(self) -> None:
        """停止后台清理任务。"""
        self._running = False
        if self._eviction_task is not None:
            self._eviction_task.cancel()
            try:
                await self._eviction_task
            except asyncio.CancelledError:
                pass
            self._eviction_task = None

    async def create_session(
        self,
        tenant_id: str = "default",
        user_id: Optional[str] = None,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> Session:
        """创建新会话。"""
        async with self._lock:
            sess = Session(
                tenant_id=tenant_id,
                user_id=user_id,
                expires_at=time.time() + self.ttl_seconds,
            )
            if initial_context:
                sess.parse_context = initial_context
            self._sessions[sess.session_id] = sess
            return sess

    async def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话：先查内存，再查持久化，加载后预热回内存。"""
        async with self._lock:
            sess = self._sessions.get(session_id)
            if sess is not None:
                if time.time() > sess.expires_at:
                    del self._sessions[session_id]
                    return None
                sess.touch()
                return sess

        # 内存未命中，查持久化
        if self.store is not None:
            sess = await self.store.load_session(session_id)
            if sess is not None:
                if time.time() > sess.expires_at:
                    return None
                async with self._lock:
                    self._sessions[session_id] = sess
                sess.touch()
                return sess
        return None

    async def update_session(self, session_id: str, turn: TurnRecord) -> Optional[Session]:
        """追加一轮对话。"""
        async with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                return None
            sess.history.append(turn)
            sess.turn_count = max(sess.turn_count, turn.sequence + 1)
            sess.touch()
            sess.expires_at = time.time() + self.ttl_seconds
            return sess

    async def close_session(self, session_id: str) -> Optional[SessionSummary]:
        """关闭会话，持久化摘要，清理内存。"""
        async with self._lock:
            sess = self._sessions.pop(session_id, None)
        if sess is None:
            return None

        sess.state = "closed"
        summary = SessionSummary(
            session_id=session_id,
            closed_at=time.time(),
            total_turns=sess.turn_count,
            final_state=sess.state,
            persisted=False,
        )

        # 异步持久化
        if self.store is not None:
            try:
                await self.store.save_session(sess)
                summary.persisted = True
            except Exception:
                pass
        return summary

    async def list_active_sessions(self, tenant_id: str, limit: int = 100) -> List[str]:
        """列出内存中的活跃会话。"""
        async with self._lock:
            now = time.time()
            result = []
            for sid, sess in self._sessions.items():
                if sess.tenant_id == tenant_id and sess.state == "active" and now < sess.expires_at:
                    result.append(sid)
                    if len(result) >= limit:
                        break
            return result

    async def _eviction_loop(self) -> None:
        """后台过期清理循环。"""
        while self._running:
            try:
                await asyncio.sleep(self.eviction_interval)
                await self._evict_expired()
            except asyncio.CancelledError:
                break
            except Exception:
                # 清理异常不应中断循环
                await asyncio.sleep(1)

    async def _evict_expired(self) -> int:
        """清理过期会话。返回清理数量。"""
        now = time.time()
        evicted = 0
        async with self._lock:
            expired = [
                sid for sid, sess in self._sessions.items()
                if now > sess.expires_at or sess.state == "closed"
            ]
            for sid in expired:
                sess = self._sessions.pop(sid)
                # 持久化冷会话
                if self.store is not None and sess.state != "closed":
                    try:
                        await self.store.save_session(sess)
                    except Exception:
                        pass
                evicted += 1

        # 超限清理：如果内存会话数超过上限，清理最旧的活跃会话
        async with self._lock:
            if len(self._sessions) > self.max_memory_sessions:
                sorted_sessions = sorted(
                    self._sessions.items(),
                    key=lambda x: x[1].last_activity_at,
                )
                overflow = len(self._sessions) - self.max_memory_sessions
                for sid, sess in sorted_sessions[:overflow]:
                    del self._sessions[sid]
                    if self.store is not None and sess.state != "closed":
                        try:
                            await self.store.save_session(sess)
                        except Exception:
                            pass
                    evicted += 1
        return evicted
