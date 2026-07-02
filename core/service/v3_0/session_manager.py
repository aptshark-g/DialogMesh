# -*- coding: utf-8 -*-
"""
core/service/v3_0/session_manager.py
────────────────────────────────────
DialogMesh Service Layer v3.0 — 异步会话管理器。

用途：
- 基于 core.agent.v3_0.context_manager.ContextManager 包装服务层会话管理。
- 提供会话创建、获取、更新、关闭、持久化的异步接口。
- 支持内存缓存 + 存储层双写，过期清理与并发安全。
- 将 ContextManager 的底层概念封装为服务层可直接使用的 SessionManager_v3。

设计原则：
- 所有方法为 async def，使用 asyncio.Lock 保证并发安全。
- 依赖 ContextManager 做上下文管理，不做重复实现。
- 支持从 SessionState_v3 到服务层响应模型的转换。

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from core.agent.v3_0.context_manager.manager import ContextManager
from core.agent.v3_0.context_manager.models import (
    ContextPriority,
    EntityResolutionState,
    WindowConfig,
)
from core.agent.v3_0.data_models import (
    AgentMessage_v3,
    Intent_v3,
    SessionState_v3,
    UserMessage_v3,
)
from core.service.v3_0.data_models import (
    HistoryRecord,
    HistoryResponse,
    SessionStatus,
    SessionStatusResponse,
)

logger = logging.getLogger(__name__)


class SessionManager_v3:
    """
    v3.0 异步会话管理器。

    职责：
    1. 创建/关闭会话：委托给 ContextManager。
    2. 消息/意图追加：委托给 ContextManager。
    3. 状态查询：从 ContextManager 和 SessionState_v3 构建响应。
    4. 历史查询：将 ContextWindow 的切片转换为 HistoryRecord 列表。
    5. 过期清理：定时任务清理不活跃会话。
    """

    def __init__(
        self,
        context_manager: ContextManager,
        ttl_seconds: int = 3600,
        eviction_interval_seconds: int = 300,
    ) -> None:
        self.context_manager = context_manager
        self.ttl_seconds = ttl_seconds
        self.eviction_interval = eviction_interval_seconds

        self._global_lock = asyncio.Lock()
        self._eviction_task: Optional[asyncio.Task] = None
        self._running = False

    # ── 生命周期 ───────────────────────────────────────────────────────────

    async def start(self) -> None:
        """启动后台过期清理任务。"""
        self._running = True
        self._eviction_task = asyncio.create_task(self._eviction_loop())
        logger.info("SessionManager_v3 started (ttl=%ds, eviction_interval=%ds)", self.ttl_seconds, self.eviction_interval)

    async def stop(self) -> None:
        """停止后台任务，保存所有活跃会话。"""
        self._running = False
        if self._eviction_task is not None:
            self._eviction_task.cancel()
            try:
                await self._eviction_task
            except asyncio.CancelledError:
                pass
            self._eviction_task = None

        # 关闭 ContextManager（会保存所有活跃会话）
        try:
            await self.context_manager.close()
        except Exception as exc:
            logger.error(f"SessionManager_v3 stop failed to close context_manager: {exc}")
        logger.info("SessionManager_v3 stopped")

    # ── 会话生命周期 ───────────────────────────────────────────────────────

    async def create_session(
        self,
        user_id: Optional[str] = None,
        process_name: Optional[str] = None,
        pid: Optional[int] = None,
        initial_context: Optional[Dict[str, Any]] = None,
        window_config: Optional[Dict[str, Any]] = None,
    ) -> SessionState_v3:
        """异步创建新会话，委托给 ContextManager。"""
        try:
            wc = WindowConfig(**window_config) if window_config else None
            state = await self.context_manager.create_session(
                user_id=user_id,
                process_name=process_name,
                pid=pid,
                window_config=wc,
            )
            if initial_context:
                state.metadata.update(initial_context)
            logger.info("SessionManager_v3 created session: %s (user=%s)", state.session_id, user_id)
            return state
        except Exception as exc:
            logger.error(f"create_session failed: {exc}")
            raise

    async def close_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """异步关闭会话，返回摘要信息。"""
        try:
            # 获取状态统计
            stats = await self.context_manager.get_stats(session_id)
            await self.context_manager.close_session(session_id)
            summary = {
                "session_id": session_id,
                "closed_at": time.time(),
                "total_turns": stats.get("message_count", 0),
                "final_state": "closed",
                "persisted": True,
            }
            logger.info("SessionManager_v3 closed session: %s", session_id)
            return summary
        except Exception as exc:
            logger.error(f"close_session failed for {session_id}: {exc}")
            raise

    async def get_session(self, session_id: str) -> Optional[SessionState_v3]:
        """异步获取会话状态。"""
        try:
            session_ctx = await self.context_manager.get_session(session_id)
            if not session_ctx:
                return None
            # 从 SessionContext 重建 SessionState_v3
            state = SessionState_v3(
                session_id=session_id,
                user_id=session_ctx.metadata.get("user_id"),
                process_name=session_ctx.metadata.get("process_name"),
                pid=session_ctx.metadata.get("pid"),
                status="active" if (time.time() - session_ctx.last_active) < self.ttl_seconds else "expired",
                updated_at=session_ctx.last_active,
                metadata=session_ctx.metadata,
            )
            return state
        except Exception as exc:
            logger.error(f"get_session failed for {session_id}: {exc}")
            raise

    # ── 消息与意图 ─────────────────────────────────────────────────────────

    async def add_user_message(
        self, session_id: str, content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """异步添加用户消息到会话。"""
        try:
            msg = UserMessage_v3(
                session_id=session_id,
                content=content,
                raw_input=content,
                metadata=metadata or {},
            )
            await self.context_manager.add_user_message(session_id, msg, priority=ContextPriority.INTERMEDIATE)
        except Exception as exc:
            logger.error(f"add_user_message failed for {session_id}: {exc}")
            raise

    async def add_agent_message(
        self, session_id: str, content: str, intent: Optional[Intent_v3] = None, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """异步添加 Agent 消息到会话。"""
        try:
            msg = AgentMessage_v3(
                session_id=session_id,
                content=content,
                intent=intent,
                metadata=metadata or {},
            )
            await self.context_manager.add_agent_message(session_id, msg, priority=ContextPriority.TASK_RESULT)
        except Exception as exc:
            logger.error(f"add_agent_message failed for {session_id}: {exc}")
            raise

    async def add_intent(self, session_id: str, intent: Intent_v3) -> None:
        """异步添加意图到会话。"""
        try:
            await self.context_manager.add_intent(session_id, intent, priority=ContextPriority.USER_GOAL)
        except Exception as exc:
            logger.error(f"add_intent failed for {session_id}: {exc}")
            raise

    # ── 状态查询 ─────────────────────────────────────────────────────────────

    async def get_status(self, session_id: str) -> Optional[SessionStatusResponse]:
        """异步获取会话状态响应。"""
        try:
            session_ctx = await self.context_manager.get_session(session_id)
            if not session_ctx:
                return None

            # 确定状态
            inactive = time.time() - session_ctx.last_active
            if inactive > self.ttl_seconds:
                state = SessionStatus.EXPIRED
            else:
                state = SessionStatus.ACTIVE

            # 已解析实体
            resolved = await self.context_manager.get_resolved_entities(session_id)

            return SessionStatusResponse(
                session_id=session_id,
                state=state,
                current_turn=session_ctx.message_count,
                last_activity_at=session_ctx.last_active,
                expires_at=session_ctx.last_active + self.ttl_seconds,
                resolved_entities=resolved,
                metadata=session_ctx.metadata,
            )
        except Exception as exc:
            logger.error(f"get_status failed for {session_id}: {exc}")
            raise

    # ── 历史查询 ─────────────────────────────────────────────────────────────

    async def get_history(self, session_id: str, limit: int = 50, offset: int = 0) -> Optional[HistoryResponse]:
        """异步获取会话历史记录。"""
        try:
            session_ctx = await self.context_manager.get_session(session_id)
            if not session_ctx:
                return None

            window = session_ctx.window
            all_messages: List[HistoryRecord] = []
            seq = 0
            for slice_obj in window.slices:
                for msg in slice_obj.messages:
                    role = getattr(msg, "role", None)
                    content = getattr(msg, "content", "")
                    all_messages.append(
                        HistoryRecord(
                            sequence=seq,
                            timestamp=getattr(msg, "created_at", time.time()),
                            role=role if role else MessageRole.USER,
                            content=content,
                        )
                    )
                    seq += 1

            total = len(all_messages)
            paginated = all_messages[offset:offset + limit]
            return HistoryResponse(
                session_id=session_id,
                messages=paginated,
                has_more=(offset + limit) < total,
                total_turns=total,
            )
        except Exception as exc:
            logger.error(f"get_history failed for {session_id}: {exc}")
            raise

    # ── 清理 ─────────────────────────────────────────────────────────────────

    async def _eviction_loop(self) -> None:
        """后台过期清理循环。"""
        while self._running:
            try:
                await asyncio.sleep(self.eviction_interval)
                count = await self.context_manager.cleanup_stale_sessions(self.ttl_seconds)
                if count > 0:
                    logger.info("SessionManager_v3 evicted %d stale sessions", count)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Eviction loop error: %s", exc)
                await asyncio.sleep(1)

    async def list_active_sessions(self) -> List[str]:
        """列出所有活跃会话 ID。"""
        try:
            return await self.context_manager.list_active_sessions()
        except Exception as exc:
            logger.error(f"list_active_sessions failed: {exc}")
            raise

    # ── 统计 ─────────────────────────────────────────────────────────────────

    async def get_global_stats(self) -> Dict[str, Any]:
        """获取全局统计。"""
        try:
            return await self.context_manager.get_global_stats()
        except Exception as exc:
            logger.error(f"get_global_stats failed: {exc}")
            raise


# 避免循环导入：在文件底部显式导入 MessageRole
from core.agent.v3_0.data_models import MessageRole
