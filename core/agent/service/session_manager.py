# -*- coding: utf-8 -*-
"""
core/agent/service/session_manager.py
─────────────────────────────────────
会话管理器（v2.4 服务层新增）。

内存缓存（LRU）+ 持久化双写架构。
- 活跃会话驻留内存
- 非活跃会话（idle > 5min）异步写入持久化
- 会话到期（TTL 1h）后从内存驱逐，保留在持久化中可恢复
"""

from __future__ import annotations

import time
import threading
from typing import Dict, List, Optional, Any

from core.agent.service.models import Session, TurnRecord, SessionSummary, IntentResult, ClarificationPayload, ParseProgressEvent, ErrorPayload
from core.agent.service.stores.base import SessionStore
from core.agent.service.distributed_lock import DistributedLock, ThreadingLockAdapter


class SessionManager:
    """
    会话管理器。
    简单实现：内存 Dict + 持久化 Store。
    生产环境可替换为 cachetools.LRUCache + 后台持久化线程。
    """

    def __init__(
        self,
        store: Optional[SessionStore] = None,
        ttl_seconds: int = 3600,
        max_memory_sessions: int = 10000,
        lock: Optional[DistributedLock] = None,
    ):
        self.store = store
        self.ttl_seconds = ttl_seconds
        self.max_memory_sessions = max_memory_sessions
        self._sessions: Dict[str, Session] = {}
        self._lock = lock or ThreadingLockAdapter()

    def create_session(
        self,
        tenant_id: str = "default",
        user_id: Optional[str] = None,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> Session:
        """创建新会话。"""
        with self._lock:
            sess = Session(
                tenant_id=tenant_id,
                user_id=user_id,
                expires_at=time.time() + self.ttl_seconds,
            )
            if initial_context:
                sess.parse_context = initial_context
            self._sessions[sess.session_id] = sess
            return sess

    def get_session(self, session_id: str) -> Optional[Session]:
        """
        获取会话：先查内存，再查持久化，加载后预热回内存。
        """
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess is not None:
                if time.time() > sess.expires_at:
                    # 已过期，驱逐
                    del self._sessions[session_id]
                    return None
                sess.touch()
                return sess

        # 内存未命中，查持久化
        if self.store is not None:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                # 在异步上下文
                import asyncio
                sess = asyncio.run(self.store.load_session(session_id))
            else:
                # 同步上下文（测试）
                import asyncio
                sess = asyncio.run(self.store.load_session(session_id))
            if sess is not None:
                with self._lock:
                    self._sessions[session_id] = sess
                sess.touch()
                return sess
        return None

    def update_session(self, session_id: str, turn: TurnRecord) -> Optional[Session]:
        """追加一轮对话，更新会话状态。"""
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                return None
            sess.history.append(turn)
            sess.turn_count = max(sess.turn_count, turn.sequence + 1)
            sess.touch()
            sess.expires_at = time.time() + self.ttl_seconds
            return sess

    def close_session(self, session_id: str) -> Optional[SessionSummary]:
        """关闭会话，持久化摘要，清理内存。"""
        with self._lock:
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
            import asyncio
            try:
                asyncio.run(self.store.save_session(sess))
                summary.persisted = True
            except Exception:
                pass
        return summary

    def list_active_sessions(self, tenant_id: str, limit: int = 100) -> List[str]:
        """列出内存中的活跃会话。"""
        with self._lock:
            now = time.time()
            result = []
            for sid, sess in self._sessions.items():
                if sess.tenant_id == tenant_id and sess.state == "active" and now < sess.expires_at:
                    result.append(sid)
                    if len(result) >= limit:
                        break
            return result

    def evict_expired(self) -> int:
        """清理过期会话。返回清理数量。"""
        now = time.time()
        evicted = 0
        with self._lock:
            expired = [
                sid for sid, sess in self._sessions.items()
                if now > sess.expires_at or sess.state == "closed"
            ]
            for sid in expired:
                sess = self._sessions.pop(sid)
                # 持久化冷会话
                if self.store is not None and sess.state != "closed":
                    import asyncio
                    try:
                        asyncio.run(self.store.save_session(sess))
                    except Exception:
                        pass
                evicted += 1
        return evicted
