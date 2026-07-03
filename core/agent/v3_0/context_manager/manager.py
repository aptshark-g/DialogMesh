# -*- coding: utf-8 -*-
"""
core/agent/v3_0/context_manager/manager.py
──────────────────────────────────────────
DialogMesh Agent v3.0 — 上下文管理器主入口

用途：
- 统一管理会话生命周期（创建、获取、更新、关闭）。
- 维护会话 → ContextWindow → ContextStore 的映射。
- 集成 CognitiveTree，将意图与决策作为认知节点写入共享心智空间。
- 提供上下文注入接口（build_prompt_context），供 LLM 调用层使用。
- 支持异步操作与并发锁，避免多会话竞争。

版本: 3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from core.agent.v3_0.cognitive_tree import (
    CognitiveTree,
    CognitiveTreeNode,
    CogNodeStatus,
    CogType,
)
from core.agent.v3_0.context_manager.models import (
    ContextPriority,
    ContextSlice,
    ContextSnapshot,
    ContextSummary,
    EntityResolutionState,
    WindowConfig,
)
from core.agent.v3_0.context_manager.store import (
    ContextStore,
    EntityCache,
    InMemoryContextStore,
)
from core.agent.v3_0.context_manager.window import (
    ContextCompressor,
    ContextWindow,
    RelevanceScorer,
    TokenEstimator,
    TruncationStrategy,
)
from core.agent.v3_0.data_models import (
    AgentMessage_v3,
    CognitiveProfile_v3,
    Intent_v3,
    MessageRole,
    SessionState_v3,
    UserMessage_v3,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 会话上下文封装
# ═══════════════════════════════════════════════════════════════════════════

class SessionContext:
    """单个会话的上下文封装 — 包含窗口、状态、认知树引用。

    不直接暴露给外部，仅由 ContextManager 内部使用。
    """

    def __init__(
        self,
        session_id: str,
        window: ContextWindow,
        cognitive_tree: Optional[CognitiveTree] = None,
    ) -> None:
        self.session_id = session_id
        self.window = window
        self.cognitive_tree = cognitive_tree
        self.entity_states: Dict[str, EntityResolutionState] = {}
        self.message_count: int = 0
        self.last_active: float = time.time()
        self.metadata: Dict[str, Any] = {}

    def touch(self) -> None:
        """更新最后活跃时间。"""
        self.last_active = time.time()

    def to_snapshot(self) -> ContextSnapshot:
        """导出为 ContextSnapshot（供持久化）。"""
        return ContextSnapshot(
            session_id=self.session_id,
            slices=list(self.window.slices),
            summaries=list(self.window.summaries),
            entity_states=list(self.entity_states.values()),
            window_config=self.window.config,
            metadata=self.metadata,
        )

    @classmethod
    def from_snapshot(
        cls,
        snapshot: ContextSnapshot,
        cognitive_tree: Optional[CognitiveTree] = None,
    ) -> "SessionContext":
        """从快照恢复会话上下文。"""
        window = ContextWindow(config=snapshot.window_config)
        for s in snapshot.slices:
            window.add_slice(s)
        for summary in snapshot.summaries:
            window.add_summary(summary)
        ctx = cls(session_id=snapshot.session_id, window=window, cognitive_tree=cognitive_tree)
        for es in snapshot.entity_states:
            ctx.entity_states[es.entity_type] = es
        ctx.metadata = dict(snapshot.metadata)
        return ctx


# ═══════════════════════════════════════════════════════════════════════════
# 上下文管理器主类
# ═══════════════════════════════════════════════════════════════════════════

class ContextManager:
    """上下文管理器 — DialogMesh v3.0 的核心上下文协调组件。

    职责：
    1. 会话管理：创建、获取、关闭、持久化。
    2. 窗口管理：追加消息、意图，触发截断/压缩。
    3. 认知树集成：将意图、决策写入 CognitiveTree。
    4. 实体解析：追踪已解析实体，支持澄清状态。
    5. Prompt 构建：为 LLM 调用层提供格式化的上下文文本。

    使用示例：

    .. code-block:: python

        manager = ContextManager(store=SQLiteContextStore("ctx.db"))
        session = await manager.create_session()
        await manager.add_user_message(session.session_id, user_msg)
        await manager.add_intent(session.session_id, intent)
        prompt = await manager.build_prompt_context(session.session_id)
    """

    def __init__(
        self,
        store: Optional[ContextStore] = None,
        default_window_config: Optional[WindowConfig] = None,
        enable_cognitive_tree: bool = True,
    ) -> None:
        self.store = store or InMemoryContextStore()
        self.default_window_config = default_window_config or WindowConfig()
        self.enable_cognitive_tree = enable_cognitive_tree

        # 会话映射
        self._sessions: Dict[str, SessionContext] = {}
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

        # 统计
        self._total_sessions_created: int = 0
        self._total_messages_processed: int = 0

        # 跨轮次实体缓存（供参照消解使用）
        self._entity_cache = EntityCache(max_rounds=5, max_entities_per_round=20)

    # ── 内部锁管理 ─────────────────────────────────────────

    def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        """获取会话级锁（不存在则创建）。"""
        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
        return self._session_locks[session_id]

    # ── 会话生命周期 ─────────────────────────────────────────

    async def create_session(
        self,
        user_id: Optional[str] = None,
        process_name: Optional[str] = None,
        pid: Optional[int] = None,
        window_config: Optional[WindowConfig] = None,
        session_id: Optional[str] = None,
    ) -> SessionState_v3:
        """异步创建新会话。

        Returns:
            新创建的 SessionState_v3。
        """
        try:
            await asyncio.sleep(0)
            session_id = session_id or str(uuid.uuid4())
            config = window_config or self.default_window_config

            window = ContextWindow(config=config)
            cognitive_tree = CognitiveTree(session_id=session_id) if self.enable_cognitive_tree else None

            session_ctx = SessionContext(
                session_id=session_id,
                window=window,
                cognitive_tree=cognitive_tree,
            )

            async with self._global_lock:
                self._sessions[session_id] = session_ctx
                self._total_sessions_created += 1

            state = SessionState_v3(
                session_id=session_id,
                user_id=user_id,
                process_name=process_name,
                pid=pid,
            )

            logger.info("Session created: %s (user=%s)", session_id, user_id)
            return state

        except Exception as exc:
            logger.error(f"create_session failed: {exc}")
            raise

    async def get_session(self, session_id: str) -> Optional[SessionContext]:
        """异步获取会话上下文（内存中）。"""
        try:
            await asyncio.sleep(0)
            async with self._global_lock:
                return self._sessions.get(session_id)
        except Exception as exc:
            logger.error(f"get_session failed: {exc}")
            raise

    async def load_session(self, session_id: str) -> Optional[SessionContext]:
        """异步从存储层加载会话到内存。"""
        try:
            await asyncio.sleep(0)
            snapshot = await self.store.load(session_id)
            if not snapshot:
                return None

            cognitive_tree = CognitiveTree(session_id=session_id) if self.enable_cognitive_tree else None
            session_ctx = SessionContext.from_snapshot(snapshot, cognitive_tree=cognitive_tree)

            async with self._global_lock:
                self._sessions[session_id] = session_ctx
                self._session_locks[session_id] = asyncio.Lock()

            logger.info("Session loaded from store: %s", session_id)
            return session_ctx
        except Exception as exc:
            logger.error(f"load_session failed: {exc}")
            raise

    async def save_session(self, session_id: str) -> bool:
        """异步将会话快照写入存储层。"""
        try:
            await asyncio.sleep(0)
            session_ctx = await self.get_session(session_id)
            if not session_ctx:
                logger.warning("save_session: session %s not found", session_id)
                return False

            snapshot = session_ctx.to_snapshot()
            await self.store.save(snapshot)
            logger.debug("Session saved: %s", session_id)
            return True
        except Exception as exc:
            logger.error(f"save_session failed: {exc}")
            raise

    async def close_session(self, session_id: str) -> bool:
        """异步关闭会话：保存快照、清理内存、释放锁。"""
        try:
            await asyncio.sleep(0)
            await self.save_session(session_id)

            async with self._global_lock:
                self._sessions.pop(session_id, None)
                self._session_locks.pop(session_id, None)

            logger.info("Session closed: %s", session_id)
            return True
        except Exception as exc:
            logger.error(f"close_session failed: {exc}")
            raise

    async def list_active_sessions(self) -> List[str]:
        """列出当前内存中所有活跃会话 ID。"""
        try:
            await asyncio.sleep(0)
            async with self._global_lock:
                return list(self._sessions.keys())
        except Exception as exc:
            logger.error(f"list_active_sessions failed: {exc}")
            raise

    # ── 消息与意图管理 ─────────────────────────────────────

    async def add_user_message(
        self,
        session_id: str,
        message: UserMessage_v3,
        priority: ContextPriority = ContextPriority.INTERMEDIATE,
    ) -> None:
        """异步添加用户消息到会话上下文。"""
        try:
            await asyncio.sleep(0)
            lock = self._get_session_lock(session_id)
            async with lock:
                session_ctx = self._sessions.get(session_id)
                if not session_ctx:
                    raise KeyError(f"Session {session_id} not found")

                # 创建或获取当前切片
                slice_obj = self._ensure_current_slice(session_ctx, priority)
                slice_obj.append_message(message)
                session_ctx.message_count += 1
                session_ctx.touch()

            self._total_messages_processed += 1
            logger.debug("User message added to session %s", session_id)
        except Exception as exc:
            logger.error(f"add_user_message failed: {exc}")
            raise

    async def add_agent_message(
        self,
        session_id: str,
        message: AgentMessage_v3,
        priority: ContextPriority = ContextPriority.TASK_RESULT,
    ) -> None:
        """异步添加 Agent 消息到会话上下文。"""
        try:
            await asyncio.sleep(0)
            lock = self._get_session_lock(session_id)
            async with lock:
                session_ctx = self._sessions.get(session_id)
                if not session_ctx:
                    raise KeyError(f"Session {session_id} not found")

                slice_obj = self._ensure_current_slice(session_ctx, priority)
                slice_obj.append_message(message)
                session_ctx.message_count += 1
                session_ctx.touch()

            logger.debug("Agent message added to session %s", session_id)
        except Exception as exc:
            logger.error(f"add_agent_message failed: {exc}")
            raise

    async def add_intent(
        self,
        session_id: str,
        intent: Intent_v3,
        priority: ContextPriority = ContextPriority.USER_GOAL,
    ) -> None:
        """异步添加意图到会话上下文，并可选写入认知树与实体缓存。"""
        try:
            await asyncio.sleep(0)
            lock = self._get_session_lock(session_id)
            async with lock:
                session_ctx = self._sessions.get(session_id)
                if not session_ctx:
                    raise KeyError(f"Session {session_id} not found")

                slice_obj = self._ensure_current_slice(session_ctx, priority)
                slice_obj.append_intent(intent)
                session_ctx.window.set_current_intent(intent)
                session_ctx.touch()

                # 合并上下文（实体解析 + 认知树 + 实体缓存更新）
                await self._merge_context(session_ctx, intent)

            logger.debug("Intent added to session %s: %s", session_id, intent.category.value)
        except Exception as exc:
            logger.error(f"add_intent failed: {exc}")
            raise

    async def _merge_context(
        self,
        session_ctx: SessionContext,
        intent: Intent_v3,
    ) -> None:
        """合并上下文 — 更新实体解析状态、写入认知树、更新跨轮实体缓存。

        对应设计文档 §3.3.7 的 Stage 6: Context Merger。
        在返回最终 Intent 之前，将当前轮次的高置信度实体写入 EntityCache，
        供下一轮 Pre-Stage 3.5 参照消解使用。
        """
        try:
            # 1. 更新实体解析状态（已解析实体字典）
            for entity in intent.entities:
                if entity.confidence >= 0.7:
                    existing = session_ctx.entity_states.get(entity.type.value)
                    if existing:
                        existing.update_value(entity.value, entity.confidence, intent.id)
                    else:
                        session_ctx.entity_states[entity.type.value] = EntityResolutionState(
                            entity_type=entity.type.value,
                            value=entity.value,
                            confidence=entity.confidence,
                            source_intent_id=intent.id,
                        )

            # 2. 写入认知树
            if session_ctx.cognitive_tree and self.enable_cognitive_tree:
                self._write_intent_to_cognitive_tree(session_ctx, intent)

            # 3. 更新跨轮次实体缓存（IP-S-07 修复）
            await self._update_entity_cache(session_ctx.session_id, intent)
        except Exception as exc:
            logger.error(f"_merge_context failed: {exc}")
            raise

    async def _update_entity_cache(
        self,
        session_id: str,
        intent: Intent_v3,
    ) -> None:
        """将当前轮次的高置信度实体写入 EntityCache。

        写入策略：
        - 筛选条件：confidence >= 0.8 的实体（排除 inherited 标记）
        - 淘汰策略：超过 max_rounds（默认 5）时移除最旧实体
        """
        try:
            await self._entity_cache.add(session_id, intent.entities)
            logger.debug("EntityCache updated for session %s", session_id)
        except Exception as exc:
            logger.error(f"_update_entity_cache failed: {exc}")
            raise

    def _ensure_current_slice(
        self,
        session_ctx: SessionContext,
        priority: ContextPriority,
    ) -> ContextSlice:
        """获取或创建当前活跃的 ContextSlice。

        若当前无切片，或切片消息数超过阈值，则创建新切片。
        """
        try:
            if session_ctx.window.slices:
                last_slice = session_ctx.window.slices[-1]
                if len(last_slice.messages) < 5 and last_slice.priority == priority:
                    return last_slice

            new_slice = ContextSlice(
                session_id=session_ctx.session_id,
                priority=priority,
            )
            session_ctx.window.add_slice(new_slice)
            return new_slice
        except Exception as exc:
            logger.error(f"_ensure_current_slice failed: {exc}")
            raise

    def _write_intent_to_cognitive_tree(
        self,
        session_ctx: SessionContext,
        intent: Intent_v3,
    ) -> None:
        """将意图作为认知节点写入 CognitiveTree（同步内部操作）。"""
        try:
            tree = session_ctx.cognitive_tree
            if not tree:
                return

            node = CognitiveTreeNode(
                cog_type=CogType.PERCEPTION,
                source_llm="Intent-LLM",
                content=f"Intent: {intent.category.value} | raw={intent.raw_input}",
                confidence=intent.confidence,
                metadata={
                    "intent_id": intent.id,
                    "entities": [
                        {"type": e.type.value, "value": str(e.value), "confidence": e.confidence}
                        for e in intent.entities
                    ],
                },
            )
            tree.add_node(node, check_permission=False)
            logger.debug("Intent written to cognitive tree: node=%s", node.node_id)
        except Exception as exc:
            logger.warning(f"_write_intent_to_cognitive_tree failed: {exc}")

    # ── 上下文构建与压缩 ─────────────────────────────────────

    async def build_prompt_context(self, session_id: str) -> str:
        """异步构建注入 LLM prompt 的上下文文本。

        流程：
        1. 触窗口 fit（截断 / 压缩）。
        2. 拼接 summaries + slices 为文本。
        3. 附加已解析实体信息。
        """
        try:
            await asyncio.sleep(0)
            lock = self._get_session_lock(session_id)
            async with lock:
                session_ctx = self._sessions.get(session_id)
                if not session_ctx:
                    raise KeyError(f"Session {session_id} not found")

                # 触发窗口调整
                await session_ctx.window.fit()
                session_ctx.touch()

                # 构建文本
                parts: List[str] = [session_ctx.window.to_prompt_text()]

                # 附加已解析实体
                if session_ctx.entity_states:
                    entity_lines = ["[RESOLVED ENTITIES]"]
                    for es in session_ctx.entity_states.values():
                        if es.status == "resolved":
                            entity_lines.append(f"- {es.entity_type}: {es.value} (conf={es.confidence:.2f})")
                    if len(entity_lines) > 1:
                        parts.append("\n".join(entity_lines))

                return "\n\n".join(parts)
        except Exception as exc:
            logger.error(f"build_prompt_context failed: {exc}")
            raise

    async def compress_session(self, session_id: str) -> Optional[ContextSummary]:
        """异步对会话的旧切片进行强制压缩，生成摘要。"""
        try:
            await asyncio.sleep(0)
            lock = self._get_session_lock(session_id)
            async with lock:
                session_ctx = self._sessions.get(session_id)
                if not session_ctx:
                    raise KeyError(f"Session {session_id} not found")

                window = session_ctx.window
                if len(window.slices) < 2:
                    return None

                # 压缩除最近一条外的所有切片
                to_compress = window.slices[:-1]
                if not to_compress:
                    return None

                summary = await window.compressor.compress(to_compress, session_id)
                window.summaries.append(summary)
                for s in to_compress:
                    window.slices.remove(s)

                session_ctx.touch()
                logger.info(
                    "Session compressed: %s (%d slices -> summary %s)",
                    session_id, len(to_compress), summary.summary_id,
                )
                return summary
        except Exception as exc:
            logger.error(f"compress_session failed: {exc}")
            raise

    # ── 实体与澄清管理 ───────────────────────────────────────

    async def get_resolved_entities(self, session_id: str) -> Dict[str, Any]:
        """异步获取会话中已解析的实体字典。"""
        try:
            await asyncio.sleep(0)
            lock = self._get_session_lock(session_id)
            async with lock:
                session_ctx = self._sessions.get(session_id)
                if not session_ctx:
                    return {}
                return {
                    k: v.value
                    for k, v in session_ctx.entity_states.items()
                    if v.status == "resolved"
                }
        except Exception as exc:
            logger.error(f"get_resolved_entities failed: {exc}")
            raise

    async def update_entity_status(
        self,
        session_id: str,
        entity_type: str,
        status: str,
    ) -> bool:
        """异步更新实体状态（如 resolved -> ambiguous -> clarified）。"""
        try:
            await asyncio.sleep(0)
            lock = self._get_session_lock(session_id)
            async with lock:
                session_ctx = self._sessions.get(session_id)
                if not session_ctx:
                    return False
                state = session_ctx.entity_states.get(entity_type)
                if not state:
                    return False
                state.status = status
                state.updated_at = time.time()
                session_ctx.touch()
                logger.debug("Entity %s status updated to %s in session %s", entity_type, status, session_id)
                return True
        except Exception as exc:
            logger.error(f"update_entity_status failed: {exc}")
            raise

    async def get_entity_cache(self, session_id: str) -> List[Dict[str, Any]]:
        """异步获取指定会话的跨轮次实体缓存（供参照消解使用）。

        Returns:
            按置信度降序排列的高置信度实体列表。
        """
        try:
            await asyncio.sleep(0)
            return await self._entity_cache.get(session_id)
        except Exception as exc:
            logger.error(f"get_entity_cache failed: {exc}")
            raise

    async def clear_entity_cache(self, session_id: str) -> None:
        """异步清空指定会话的实体缓存（话题切换时调用）。"""
        try:
            await asyncio.sleep(0)
            await self._entity_cache.clear(session_id)
            logger.debug("EntityCache cleared for session %s", session_id)
        except Exception as exc:
            logger.error(f"clear_entity_cache failed: {exc}")
            raise

    # ── 认知树查询 ───────────────────────────────────────────

    async def get_cognitive_tree(self, session_id: str) -> Optional[CognitiveTree]:
        """异步获取会话关联的认知树。"""
        try:
            await asyncio.sleep(0)
            session_ctx = await self.get_session(session_id)
            return session_ctx.cognitive_tree if session_ctx else None
        except Exception as exc:
            logger.error(f"get_cognitive_tree failed: {exc}")
            raise

    # ── 统计与诊断 ───────────────────────────────────────────

    async def get_stats(self, session_id: str) -> Dict[str, Any]:
        """异步获取会话统计信息。"""
        try:
            await asyncio.sleep(0)
            session_ctx = await self.get_session(session_id)
            if not session_ctx:
                return {"error": "session not found"}

            return {
                "session_id": session_id,
                "message_count": session_ctx.message_count,
                "last_active": session_ctx.last_active,
                "entity_count": len(session_ctx.entity_states),
                **session_ctx.window.get_stats(),
            }
        except Exception as exc:
            logger.error(f"get_stats failed: {exc}")
            raise

    async def get_global_stats(self) -> Dict[str, Any]:
        """获取全局统计信息。"""
        try:
            await asyncio.sleep(0)
            async with self._global_lock:
                return {
                    "total_sessions_created": self._total_sessions_created,
                    "active_sessions": len(self._sessions),
                    "total_messages_processed": self._total_messages_processed,
                }
        except Exception as exc:
            logger.error(f"get_global_stats failed: {exc}")
            raise

    # ── 清理 ─────────────────────────────────────────────────

    async def cleanup_stale_sessions(self, max_inactive_seconds: float = 3600.0) -> int:
        """异步清理超过指定时间不活跃的会话。

        Returns:
            被清理的会话数。
        """
        try:
            await asyncio.sleep(0)
            now = time.time()
            to_close: List[str] = []

            async with self._global_lock:
                for sid, ctx in self._sessions.items():
                    if now - ctx.last_active > max_inactive_seconds:
                        to_close.append(sid)

            count = 0
            for sid in to_close:
                try:
                    await self.close_session(sid)
                    count += 1
                except Exception as exc:
                    logger.warning(f"cleanup_stale_sessions: failed to close {sid}: {exc}")

            if count > 0:
                logger.info("cleanup_stale_sessions: closed %d stale sessions", count)
            return count
        except Exception as exc:
            logger.error(f"cleanup_stale_sessions failed: {exc}")
            raise

    async def close(self) -> None:
        """异步关闭管理器：保存所有活跃会话，释放存储连接。"""
        try:
            await asyncio.sleep(0)
            active = list(self._sessions.keys())
            for sid in active:
                try:
                    await self.close_session(sid)
                except Exception as exc:
                    logger.warning(f"close: failed to close session {sid}: {exc}")

            await self.store.close()
            logger.info("ContextManager closed")
        except Exception as exc:
            logger.error(f"ContextManager.close failed: {exc}")
            raise
