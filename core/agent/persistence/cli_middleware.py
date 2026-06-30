# -*- coding: utf-8 -*-
"""
core/agent/persistence/cli_middleware.py
────────────────────────────────────────
CLISessionPersistence: 同步包装层。
为 CLI 同步代码提供异步存储的同步包装。

设计要点：
  - 批量保存：profile/threshold 缓存，每 5 轮 flush
  - 乐观锁：version 字段递增
  - 优雅关闭：等待 pending tasks + flush + stop loop
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agent.persistence.base import SessionStore
from core.agent.persistence.models import Session, TurnRecord, SessionSummary
from core.agent.persistence.session_manager import SessionManager
from core.agent.persistence.sqlite_store import SQLiteSessionStore


class CLISessionPersistence:
    """
    CLI 会话持久化中间件。
    在独立线程中运行事件循环，避免与主线程冲突。
    """

    def __init__(
        self,
        db_path: str = "~/.memorygraph/sessions.db",
        ttl_seconds: int = 7 * 24 * 3600,
        max_memory_sessions: int = 100,
    ):
        # 路径健壮性：确保目录存在
        db_path = str(Path(db_path).expanduser())
        Path(Path(db_path).parent).mkdir(parents=True, exist_ok=True)

        self._db_path = db_path
        self._ttl_seconds = ttl_seconds
        self._max_memory_sessions = max_memory_sessions

        # 初始化存储和管理器
        self._store = SQLiteSessionStore(db_path)
        self._manager = SessionManager(
            store=self._store,
            ttl_seconds=ttl_seconds,
            max_memory_sessions=max_memory_sessions,
            auto_eviction=False,  # CLI 场景关闭后台线程，手动控制
        )

        # 批量保存：缓存待写画像和阈值，每 5 轮 flush
        self._pending_profile_updates: Dict[str, Dict[str, Any]] = {}
        self._pending_threshold_updates: Dict[str, Dict[str, float]] = {}
        self._batch_save_counter = 0
        self._batch_lock = threading.RLock()

        self._initialized = True

    # ── 同步接口 ───────────────────────────────────────────

    def create_session(self, user_id: Optional[str] = None) -> str:
        """创建新会话，返回 session_id。"""
        session = self._manager.create_session(user_id=user_id)
        self._store.save_session(session)
        return session.session_id

    def get_or_load(self, session_id: str) -> Optional[Session]:
        """从内存或磁盘加载会话。"""
        return self._manager.get_session(session_id)

    def add_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        intent_result: Optional[Dict[str, Any]] = None,
        execution_status: Optional[str] = None,
        latency_ms: float = 0.0,
    ) -> bool:
        """追加一轮对话并持久化。"""
        turn = TurnRecord(
            sequence=self._get_next_sequence(session_id),
            timestamp=time.time(),
            role=role,
            content=content,
            intent_result=intent_result,
            execution_status=execution_status,
            data={"execution_status": execution_status} if execution_status else {},
            latency_ms=latency_ms,
        )
        return self._manager.save_turn(session_id, turn)

    def update_cognitive_profile(
        self, session_id: str, profile: Dict[str, Any]
    ) -> None:
        """更新认知画像（批量缓存，每 5 轮或 session 关闭时持久化）。"""
        with self._batch_lock:
            self._pending_profile_updates[session_id] = profile
            self._batch_save_counter += 1
            if self._batch_save_counter >= 5:
                self._flush_pending_updates()
                self._batch_save_counter = 0

    def update_adaptive_thresholds(
        self, session_id: str, thresholds: Dict[str, float]
    ) -> None:
        """更新自适应阈值（批量缓存，每 5 轮或 session 关闭时持久化）。"""
        with self._batch_lock:
            self._pending_threshold_updates[session_id] = thresholds
            self._batch_save_counter += 1
            if self._batch_save_counter >= 5:
                self._flush_pending_updates()
                self._batch_save_counter = 0

    def list_sessions(self, limit: int = 20) -> List[SessionSummary]:
        """列出最近活跃的会话。"""
        return self._manager.list_sessions(limit=limit)

    def close_session(self, session_id: str) -> bool:
        """关闭会话，触发持久化（flush pending 更新）。"""
        self._flush_pending_updates()
        return self._manager.close_session(session_id)

    def shutdown(self) -> None:
        """优雅关闭：等待所有未完成的 writes 完成。"""
        # 1. 先批量保存所有 pending 的画像和阈值
        self._flush_pending_updates()

        # 2. 关闭管理器（会保存所有缓存中的会话）
        self._manager.shutdown()

    # ── 内部方法 ───────────────────────────────────────────

    def _flush_pending_updates(self) -> None:
        """批量保存所有 pending 的画像和阈值更新（带乐观锁版本号递增）。"""
        with self._batch_lock:
            profile_updates = dict(self._pending_profile_updates)
            threshold_updates = dict(self._pending_threshold_updates)
            self._pending_profile_updates.clear()
            self._pending_threshold_updates.clear()

        for sid, profile in profile_updates.items():
            session = self.get_or_load(sid)
            if session:
                session.cognitive_profile = profile
                session.bump_version()
                self._store.save_session(session)

        for sid, thresholds in threshold_updates.items():
            session = self.get_or_load(sid)
            if session:
                session.adaptive_thresholds = thresholds
                session.bump_version()
                self._store.save_session(session)

    def _get_next_sequence(self, session_id: str) -> int:
        """获取下一个 turn sequence。"""
        session = self.get_or_load(session_id)
        if session:
            return session.turn_count + 1
        return 1

    # ── 维护 ───────────────────────────────────────────

    def cleanup_expired(self, dry_run: bool = False) -> int:
        """清理过期会话。"""
        return self._store.cleanup_expired(self._ttl_seconds, dry_run=dry_run)
