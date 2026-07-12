# -*- coding: utf-8 -*-
"""
core/service/v3_0/agent_service.py
──────────────────────────────────
DialogMesh Service Layer v3.0 — Agent 核心服务。

用途：
- 封装业务逻辑：意图解析 → 任务图生成 → 澄清管理 → 结果返回。
- 集成 v3.0 组件：ContextManager、LLMProviderManager、CognitiveTree。
- 提供事件回调机制，供 WebSocketManager 推送实时事件。
- 支持限流、错误处理、Trace 日志、性能统计。

设计原则：
- 所有公共方法为 async def，纯 asyncio 实现。
- 不直接依赖 FastAPI，仅通过回调函数与外部通信。
- 使用 try/except 包裹所有业务逻辑，确保不抛未捕获异常。

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.agent.v3_common.models import IntentCategory, TaskStatus
from core.agent.v3_0.data_models import (
    Ambiguity_v3,
    EventType,
    Intent_v3,
    MessageRole,
    ParseResult_v3,
    SessionState_v3,
    TaskGraph_v3,
    TaskNode_v3,
    UserMessage_v3,
    WebSocketEvent,
    WebSocketEventBuilder,
)
from core.agent.v3_0.llm_providers.base import GenerateRequest_v3, LLMProvider_v3
from core.agent.v3_0.llm_providers.models import ProviderResult
from core.agent.v3_0.llm_providers.provider_manager import ProviderManager
from core.service.v3_0.data_models import (
    ClarifyRequest,
    CloseSessionRequest,
    CloseSessionResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    ErrorResponse,
    HistoryResponse,
    MessageStatus,
    ModalityType,
    SendMessageRequest,
    SendMessageResponse,
    SessionStatus,
    SessionStatusResponse,
    build_error_response,
)
from core.service.v3_0.session_manager import SessionManager_v3

logger = logging.getLogger(__name__)

EventCallback = Callable[[str, str, Dict[str, Any]], None]


class AgentService_v3:
    """
    v3.0 Agent 服务核心。

    职责：
    1. 会话管理：创建/关闭/查询会话。
    2. 消息处理：解析用户输入 → 生成意图 → 构建任务图 → 返回结果。
    3. 澄清处理：管理多轮澄清 FSM 状态。
    4. 事件推送：通过 event_callback 向 WebSocketManager 推送事件。
    5. 统计与监控：记录延迟、成功率、错误率。
    """

    def __init__(
        self,
        session_manager: SessionManager_v3,
        provider_manager: Optional[ProviderManager] = None,
        event_callback: Optional[EventCallback] = None,
    ) -> None:
        self.session_manager = session_manager
        self.provider_manager = provider_manager
        self.event_callback = event_callback

        # 响应编排器（SL-S-06 修复）
        from core.service.v3_0.response_composer import ResponseComposer
        self._response_composer = ResponseComposer()

        self._lock = asyncio.Lock()
        self._request_counter = 0
        self._error_counter = 0
        self._total_latency_ms = 0.0

    # ── 内部辅助 ───────────────────────────────────────────────────────────

    async def _emit_event(self, session_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        """触发事件回调。"""
        if self.event_callback is not None:
            try:
                if asyncio.iscoroutinefunction(self.event_callback):
                    await self.event_callback(session_id, event_type, payload)
                else:
                    self.event_callback(session_id, event_type, payload)
            except Exception as exc:
                logger.warning("Event callback failed: %s", exc)

    async def _build_intent_from_text(self, content: str) -> Intent_v3:
        """基于文本构建基础意图（简化版，实际应由 IntentParser 完成）。"""
        # 简易规则匹配：关键词 -> IntentCategory
        category = IntentCategory.UNKNOWN
        lower = content.lower()
        if "scan" in lower or "扫描" in lower:
            category = IntentCategory.SCAN_MEMORY
        elif "read" in lower or "读取" in lower:
            category = IntentCategory.READ_MEMORY
        elif "write" in lower or "写入" in lower:
            category = IntentCategory.WRITE_MEMORY
        elif "resolve" in lower or "指针" in lower:
            category = IntentCategory.RESOLVE_POINTER
        elif "decompile" in lower or "反编译" in lower:
            category = IntentCategory.DECOMPILE
        elif "disassemble" in lower or "反汇编" in lower:
            category = IntentCategory.DISASSEMBLE
        elif "breakpoint" in lower or "断点" in lower:
            category = IntentCategory.SET_BREAKPOINT
        elif "trace" in lower or "追踪" in lower:
            category = IntentCategory.TRACE_EXECUTION

        return Intent_v3(
            category=category,
            raw_input=content,
            normalized_input=content.strip().lower(),
            confidence=0.7 if category != IntentCategory.UNKNOWN else 0.3,
        )

    async def _build_task_graph(self, intent: Intent_v3) -> Optional[TaskGraph_v3]:
        """根据意图构建任务图（简化版）。"""
        if intent.category == IntentCategory.UNKNOWN:
            return None

        graph = TaskGraph_v3(intent_id=intent.id)
        # 根据意图类别创建概念层节点
        node1 = TaskNode_v3(
            name=f"plan_{intent.category.value}",
            description=f"Plan execution for {intent.category.value}",
            intent_id=intent.id,
            layer=1,
            goal=f"Achieve intent: {intent.category.value}",
            strategy="rule-based planning",
        )
        node2 = TaskNode_v3(
            name=f"execute_{intent.category.value}",
            description=f"Execute {intent.category.value}",
            intent_id=intent.id,
            layer=3,
            goal="Complete execution",
            strategy="direct tool invocation",
            tool_name=intent.category.value,
        )
        graph.add_node(node1)
        graph.add_node(node2)
        # 添加顺序依赖
        from core.agent.v3_0.data_models import TaskEdge_v3
        from core.agent.v3_common.models import DependencyType
        graph.add_edge(TaskEdge_v3(source_id=node1.id, target_id=node2.id, dep_type=DependencyType.SEQUENTIAL))
        return graph

    async def _check_clarification(self, intent: Intent_v3) -> Tuple[bool, List[Ambiguity_v3]]:
        """检查是否需要澄清（简化版：低置信度或未知意图）。"""
        if intent.confidence < 0.5 or intent.category == IntentCategory.UNKNOWN:
            from core.agent.v3_common.models import AmbiguityType
            ambiguity = Ambiguity_v3(
                type=AmbiguityType.MISSING_ENTITY,
                description="意图置信度较低，请确认具体操作。",
                suggestions=["扫描内存", "读取内存", "写入内存", "设置断点"],
                auto_resolvable=False,
            )
            return True, [ambiguity]
        return False, []

    async def _llm_fallback(self, content: str) -> Optional[str]:
        """LLM 回退：当规则解析不足时，调用 ProviderManager。"""
        if self.provider_manager is None:
            return None
        try:
            req = GenerateRequest_v3(
                prompt=f"Classify the following user intent into a structured JSON: '{content}'",
                max_tokens=256,
                temperature=0.3,
                response_format="json",
            )
            result = await self.provider_manager.generate_async(req)
            if result and result.success:
                return result.text
            return None
        except Exception as exc:
            logger.warning(f"LLM fallback failed: {exc}")
            return None

    async def _build_cognitive_profile(self, session_id: str) -> Optional[Dict[str, Any]]:
        """从会话上下文中构建简化的认知画像，供 ResponseComposer 使用。

        Returns:
            包含 user_type_hint 的字典，若上下文不存在则返回 None。
        """
        try:
            session_ctx = await self.session_manager.context_manager.get_session(session_id)
            if not session_ctx:
                return None
            profile: Dict[str, Any] = {}
            if session_ctx.metadata.get("user_type_hint"):
                profile["user_type_hint"] = session_ctx.metadata["user_type_hint"]
            # 若已有认知画像字段，直接透传
            if session_ctx.metadata.get("cognitive_profile"):
                profile.update(session_ctx.metadata["cognitive_profile"])
            return profile if profile else None
        except Exception as exc:
            logger.warning(f"_build_cognitive_profile failed: {exc}")
            return None

    # ── 公共 API ───────────────────────────────────────────────────────────

    async def create_session(self, req: CreateSessionRequest) -> CreateSessionResponse:
        """创建新会话。"""
        try:
            state = await self.session_manager.create_session(
                user_id=req.user_id,
                process_name=req.process_name,
                pid=req.pid,
                initial_context=req.initial_context,
                window_config=req.window_config,
            )
            # 保存用户类型提示到 metadata，供 ResponseComposer 使用
            if req.user_type_hint:
                session_ctx = await self.session_manager.context_manager.get_session(state.session_id)
                if session_ctx:
                    session_ctx.metadata["user_type_hint"] = req.user_type_hint
            return CreateSessionResponse(
                session_id=state.session_id,
                created_at=state.created_at,
                ws_url=f"/v3/ws/{state.session_id}",
                status=SessionStatus.ACTIVE,
            )
        except Exception as exc:
            logger.error(f"create_session failed: {exc}")
            raise

    async def close_session(self, session_id: str, req: Optional[CloseSessionRequest] = None) -> CloseSessionResponse:
        """关闭会话。"""
        try:
            summary = await self.session_manager.close_session(session_id)
            if summary is None:
                raise ValueError(f"Session not found: {session_id}")
            return CloseSessionResponse(
                session_id=session_id,
                closed_at=summary["closed_at"],
                summary=summary,
                persisted=summary.get("persisted", False),
            )
        except Exception as exc:
            logger.error(f"close_session failed for {session_id}: {exc}")
            raise

    async def process_message(
        self, session_id: str, req: SendMessageRequest
    ) -> SendMessageResponse:
        """处理用户消息：解析 → 任务图 → 澄清检测 → 响应编排。"""
        start_ms = time.time() * 1000
        try:
            # 1. 添加用户消息到上下文
            await self.session_manager.add_user_message(session_id, req.content, metadata=req.structured_payload)

            await self._emit_event(session_id, "progress", {
                "stage": "parsing", "status": "started", "message_id": req.message_id,
            })

            # 2. 意图解析（规则 + LLM 回退）
            intent = await self._build_intent_from_text(req.content)
            # 尝试 LLM 回退提升低置信度
            if intent.confidence < 0.6 and self.provider_manager is not None:
                llm_result = await self._llm_fallback(req.content)
                if llm_result:
                    intent.metadata["llm_fallback"] = llm_result
                    intent.confidence = min(0.75, intent.confidence + 0.2)

            await self._emit_event(session_id, "progress", {
                "stage": "parsing", "status": "completed", "intent": intent.category.value,
            })

            # 3. 添加意图到上下文
            await self.session_manager.add_intent(session_id, intent)

            # 4. 构建任务图
            task_graph = await self._build_task_graph(intent)

            # 5. 检查澄清
            needs_clarification, ambiguities = await self._check_clarification(intent)

            latency_ms = (time.time() * 1000) - start_ms
            async with self._lock:
                self._request_counter += 1
                self._total_latency_ms += latency_ms

            # 获取会话状态，用于响应编排（历史长度、用户画像）
            session_status = await self.session_manager.get_status(session_id)
            history_length = session_status.current_turn if session_status else 0
            cognitive_profile = await self._build_cognitive_profile(session_id)

            if needs_clarification:
                # 澄清响应编排
                clarification_text = (
                    ambiguities[0].description if ambiguities else "需要澄清"
                )
                composed = self._response_composer.compose(
                    result_summary=clarification_text,
                    intent=intent,
                    session_history_length=history_length,
                    cognitive_profile=cognitive_profile,
                )
                await self._emit_event(session_id, "clarification", {
                    "clarification_id": ambiguities[0].description if ambiguities else "clarify-1",
                    "message": ambiguities[0].description if ambiguities else "需要澄清",
                    "suggestions": ambiguities[0].suggestions if ambiguities else [],
                })
                return SendMessageResponse(
                    message_id=req.message_id,
                    session_id=session_id,
                    status=MessageStatus.NEEDS_CLARIFICATION,
                    content=composed,
                    response_format=self._response_composer._select_format(
                        intent=intent,
                        session_history_length=history_length,
                        cognitive_profile=cognitive_profile,
                    ),
                    intent=intent,
                    task_graph=task_graph,
                    clarifications=ambiguities,
                    suggestions=ambiguities[0].suggestions if ambiguities else [],
                    latency_ms=latency_ms,
                )

            # 6. 返回 actionable 结果（经响应编排）
            result_summary = f"已识别意图：{intent.category.value}。"
            if task_graph:
                result_summary += f" 任务图包含 {len(task_graph.nodes)} 个节点。"
            composed = self._response_composer.compose(
                result_summary=result_summary,
                intent=intent,
                session_history_length=history_length,
                cognitive_profile=cognitive_profile,
            )
            await self._emit_event(session_id, "intent_result", {
                "message_id": req.message_id,
                "status": "actionable",
                "intent": intent.category.value,
                "latency_ms": latency_ms,
            })
            return SendMessageResponse(
                message_id=req.message_id,
                session_id=session_id,
                status=MessageStatus.ACTIONABLE,
                content=composed,
                response_format=self._response_composer._select_format(
                    intent=intent,
                    session_history_length=history_length,
                    cognitive_profile=cognitive_profile,
                ),
                intent=intent,
                task_graph=task_graph,
                latency_ms=latency_ms,
            )

        except Exception as exc:
            async with self._lock:
                self._error_counter += 1
            latency_ms = (time.time() * 1000) - start_ms
            logger.error(f"process_message failed for {session_id}: {exc}")
            await self._emit_event(session_id, "error", {
                "code": "INTERNAL_ERROR", "message": str(exc), "message_id": req.message_id,
            })
            return SendMessageResponse(
                message_id=req.message_id,
                session_id=session_id,
                status=MessageStatus.ERROR,
                content=f"处理失败: {exc}",
                response_format=ResponseFormat.BALANCED,
                latency_ms=latency_ms,
                error={"code": "INTERNAL_ERROR", "message": str(exc)},
            )

    async def submit_clarification(
        self, session_id: str, req: ClarifyRequest
    ) -> SendMessageResponse:
        """提交澄清回复，重新处理。"""
        start_ms = time.time() * 1000
        try:
            # 简化处理：将澄清文本作为新消息处理
            clarify_text = req.free_text or f"[option:{req.selected_option}]"
            # 构造新的 SendMessageRequest
            inner_req = SendMessageRequest(content=clarify_text)
            return await self.process_message(session_id, inner_req)
        except Exception as exc:
            latency_ms = (time.time() * 1000) - start_ms
            logger.error(f"submit_clarification failed for {session_id}: {exc}")
            return SendMessageResponse(
                message_id=req.clarification_id,
                session_id=session_id,
                status=MessageStatus.ERROR,
                latency_ms=latency_ms,
                error={"code": "CLARIFICATION_ERROR", "message": str(exc)},
            )

    async def get_history(self, session_id: str, limit: int = 50, offset: int = 0) -> Optional[HistoryResponse]:
        """获取会话历史。"""
        try:
            return await self.session_manager.get_history(session_id, limit=limit, offset=offset)
        except Exception as exc:
            logger.error(f"get_history failed for {session_id}: {exc}")
            raise

    async def get_status(self, session_id: str) -> Optional[SessionStatusResponse]:
        """获取会话状态。"""
        try:
            return await self.session_manager.get_status(session_id)
        except Exception as exc:
            logger.error(f"get_status failed for {session_id}: {exc}")
            raise

    async def health_check(self) -> Dict[str, Any]:
        """健康检查。"""
        try:
            active_sessions = await self.session_manager.list_active_sessions()
            avg_latency = (
                self._total_latency_ms / self._request_counter
                if self._request_counter > 0 else 0.0
            )
            return {
                "status": "healthy",
                "version": "3.0.0",
                "components": {
                    "session_manager": {"status": "ok", "active_sessions": len(active_sessions)},
                    "provider_manager": {
                        "status": "ok" if self.provider_manager is not None else "disabled",
                    },
                    "agent_service": {
                        "status": "ok",
                        "total_requests": self._request_counter,
                        "total_errors": self._error_counter,
                        "avg_latency_ms": round(avg_latency, 2),
                    },
                },
            }
        except Exception as exc:
            logger.error(f"health_check failed: {exc}")
            return {"status": "unhealthy", "error": str(exc)}

    async def get_stats(self) -> Dict[str, Any]:
        """获取服务统计。"""
        try:
            global_stats = await self.session_manager.get_global_stats()
            avg_latency = (
                self._total_latency_ms / self._request_counter
                if self._request_counter > 0 else 0.0
            )
            return {
                "agent_service": {
                    "total_requests": self._request_counter,
                    "total_errors": self._error_counter,
                    "avg_latency_ms": round(avg_latency, 2),
                    "error_rate": round(self._error_counter / max(self._request_counter, 1), 4),
                },
                "session_manager": global_stats,
            }
        except Exception as exc:
            logger.error(f"get_stats failed: {exc}")
            raise

    async def start(self) -> None:
        """启动服务。"""
        await self.session_manager.start()
        logger.info("AgentService_v3 started")

    async def stop(self) -> None:
        """停止服务。"""
        await self.session_manager.stop()
        logger.info("AgentService_v3 stopped")
