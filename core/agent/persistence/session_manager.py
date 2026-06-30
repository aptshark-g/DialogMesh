# -*- coding: utf-8 -*-
"""
core/agent/persistence/session_manager.py
────────────────────────────────────────
Session manager: in-memory cache + persistent store.
负责会话的创建、缓存、驱逐和 TTL 管理。

设计要点：
  - 内存缓存：Dict[str, Session] 加速热会话访问
  - 后台驱逐：每 5 分钟清理过期会话（可选，CLI 场景可关闭）
  - 上限清理：超过 max_memory_sessions 时按 LRU 淘汰
  - 写回策略：save_turn 立即持久化，profile/threshold 批量写入
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Any

from core.agent.persistence.base import SessionStore
from core.agent.persistence.models import Session, TurnRecord, SessionState, SessionSummary


class SessionManager:
    """
    会话管理器：内存缓存 + 持久化存储。
    线程安全：通过 threading.Lock 保护缓存操作。
    """

    def __init__(
        self,
        store: SessionStore,
        ttl_seconds: float = 7 * 24 * 3600,       # 7 天默认 TTL
        max_memory_sessions: int = 100,           # 内存中保留的会话数
        eviction_interval_seconds: float = 300,   # 5 分钟清理一次
        auto_eviction: bool = False,              # CLI 场景建议关闭后台线程
    ):
        self._store = store
        self._ttl_seconds = ttl_seconds
        self._max_memory_sessions = max_memory_sessions
        self._eviction_interval = eviction_interval_seconds
        self._auto_eviction = auto_eviction

        # 内存缓存：OrderedDict 用于 LRU 淘汰
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._lock = threading.Lock()

        # 后台驱逐线程
        self._eviction_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()

        if self._auto_eviction:
            self._start_eviction_thread()

    # ── 生命周期 ───────────────────────────────────────────────

    def _start_eviction_thread(self) -> None:
        """启动后台驱逐线程。"""
        def _run():
            while not self._shutdown_event.wait(self._eviction_interval):
                self._evict_expired()
                self._evict_lru_if_needed()

        self._eviction_thread = threading.Thread(target=_run, daemon=True, name="session-eviction")
        self._eviction_thread.start()

    def shutdown(self) -> None:
        """优雅关闭：停止后台线程，flush 所有缓存。"""
        self._shutdown_event.set()

        if self._eviction_thread and self._eviction_thread.is_alive():
            self._eviction_thread.join(timeout=5.0)

        # 关闭前保存所有缓存中的会话
        with self._lock:
            for session in self._sessions.values():
                self._store.save_session(session)

        self._store.close()

    # ── 会话管理 ───────────────────────────────────────────

    def create_session(self, user_id: Optional[str] = None) -> Session:
        """创建新会话并持久化。"""
        session = Session(user_id=user_id)
        self._store.save_session(session)

        with self._lock:
            self._sessions[session.session_id] = session
            self._move_to_end(session.session_id)
            self._evict_lru_if_needed()

        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """
        获取会话：先查内存缓存，再查持久化存储。
        命中缓存时更新 LRU 顺序。
        """
        with self._lock:
            if session_id in self._sessions:
                self._move_to_end(session_id)
                return self._sessions[session_id]

        # 缓存未命中，从持久化加载
        session = self._store.load_session(session_id)
        if session is not None:
            # 加载历史
            session.history = self._store.load_turns(session_id, limit=1000)
            session.turn_count = len(session.history)

            with self._lock:
                self._sessions[session_id] = session
                self._move_to_end(session_id)
                self._evict_lru_if_needed()

        return session

    def save_turn(self, session_id: str, turn: TurnRecord) -> bool:
        """保存轮次：立即持久化 + 更新内存缓存。"""
        session = self.get_session(session_id)
        if session is None:
            return False

        # 确保 sequence 正确
        if turn.sequence == 0:
            turn.sequence = session.turn_count + 1

        turn.timestamp = time.time()

        # 立即持久化轮次
        ok = self._store.save_turn(session_id, turn)
        if not ok:
            return False

        # 更新内存缓存
        with self._lock:
            session.history.append(turn)
            session.turn_count = len(session.history)
            session.last_activity_at = time.time()
            self._move_to_end(session_id)

        # 更新持久化会话（不含 history，history 已单独保存）
        self._store.save_session(session)
        return True

    def close_session(self, session_id: str) -> bool:
        """关闭会话：更新状态，保存，从缓存移除。"""
        session = self.get_session(session_id)
        if session is None:
            return False

        session.state = SessionState.CLOSED
        session.last_activity_at = time.time()
        self._store.save_session(session)

        with self._lock:
            self._sessions.pop(session_id, None)

        return True

    def list_sessions(self, limit: int = 20, tenant_id: str = "default") -> List[SessionSummary]:
        """列出最近活跃的会话摘要。"""
        sids = self._store.list_active_sessions(limit=limit, tenant_id=tenant_id)
        summaries = []

        for sid in sids:
            session = self.get_session(sid)
            if session is None:
                continue

            summaries.append(SessionSummary(
                session_id=sid,
                last_active=session.last_activity_at,
                turn_count=session.turn_count,
                state=session.state.value,
                health_score=0.0,  # 占位，由 observability 模块计算
            ))

        return summaries

    # ── 缓存管理 ───────────────────────────────────────────

    def _move_to_end(self, session_id: str) -> None:
        """将会话移到 OrderedDict 末尾（最新使用）。"""
        if session_id in self._sessions:
            self._sessions.move_to_end(session_id)

    def _evict_lru_if_needed(self) -> None:
        """如果缓存超过上限，淘汰最久未使用的会话。"""
        while len(self._sessions) > self._max_memory_sessions:
            oldest_id, oldest_session = self._sessions.popitem(last=False)
            # 保存后再移除
            self._store.save_session(oldest_session)

    def _evict_expired(self) -> None:
        """驱逐过期会话（TTL 检查）。"""
        cutoff = time.time() - self._ttl_seconds
        expired = []

        with self._lock:
            for sid, session in self._sessions.items():
                if session.last_activity_at < cutoff:
                    expired.append(sid)

        for sid in expired:
            with self._lock:
                session = self._sessions.pop(sid, None)
            if session:
                self._store.save_session(session)

    # ── 批量操作 ───────────────────────────────────────────

    def save_profile(self, session_id: str, profile: Dict[str, Any]) -> bool:
        """保存认知画像（更新会话但不立即保存历史）。"""
        session = self.get_session(session_id)
        if session is None:
            return False

        session.cognitive_profile = profile
        session.bump_version()
        return self._store.save_session(session)

    def save_thresholds(self, session_id: str, thresholds: Dict[str, float]) -> bool:
        """保存自适应阈值。"""
        session = self.get_session(session_id)
        if session is None:
            return False

        session.adaptive_thresholds = thresholds
        session.bump_version()
        return self._store.save_session(session)
