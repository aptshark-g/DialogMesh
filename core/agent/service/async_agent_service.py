# -*- coding: utf-8 -*-
"""
core/agent/service/async_agent_service.py
─────────────────────────────────────────
AsyncAgentService（v2.4 生产调优）。

与 AgentService 完全对等的异步版本，使用 AsyncSessionManager（aiosqlite / Redis）
替代同步 SessionManager，适配 FastAPI 等 ASGI 框架的 async 上下文。

所有业务逻辑与 AgentService 保持一致（复制-粘贴后添加 await），
确保同步 / 异步版本行为一致。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from core.agent.frontend import (
    ClarificationFSM, ClarificationFSMContext, ClarificationState, ClarificationEvent,
    ClarificationUIFactory, EventBuilder, EventSerializer,
)
from core.agent.frontend.multimodal import MultimodalPipeline, MediaAttachment
from core.agent.service.models import (
    Session, TurnRecord, IntentResult, ClarificationPayload,
    ParseProgressEvent, ErrorPayload, SessionSummary,
)
from core.agent.service.async_session_manager import AsyncSessionManager
from core.agent.service.rate_limiter import RateLimiter
from core.agent.service.distributed_lock import DistributedLock, AsyncLockAdapter

from core.agent.pcr.rule_based import RuleBasedPCR
from core.agent.intent_parser import IntentParser
from core.agent.gates import DualTrackOrchestrator, GateResult
from core.agent.llm_providers.base import LLMProvider

import logging
logger = logging.getLogger(__name__)


class AsyncAgentService:
    """
    Agent 服务（异步版本）：封装核心引擎 + 异步会话管理 + 限流。
    
    与 AgentService 的区别：
      - 所有方法为 async def
      - session_manager 为 AsyncSessionManager（aiosqlite / Redis 后端）
      - 使用 asyncio.Lock 替代 threading.RLock
      - 集成 MultimodalPipeline 支持多模态输入（图片/音频）
    """

    def __init__(
        self,
        pcr: RuleBasedPCR,
        parser: IntentParser,
        session_manager: AsyncSessionManager,
        rate_limiter: RateLimiter,
        llm_provider: Optional[LLMProvider] = None,
        event_callback: Optional[Any] = None,
        multimodal_pipeline: Optional[MultimodalPipeline] = None,
        lock: Optional[DistributedLock] = None,
    ):
        self.pcr = pcr
        self.parser = parser
        self.session_manager = session_manager
        self.rate_limiter = rate_limiter
        self.llm_provider = llm_provider
        self.event_callback = event_callback
        self.multimodal = multimodal_pipeline or MultimodalPipeline()

        self.orchestrator = DualTrackOrchestrator(
            pcr, parser,
            router_llm_fn=self._llm_router_fn if llm_provider else None,
        )

        self._lock = lock or AsyncLockAdapter()
        self._fsm_lock = asyncio.Lock()
        self._message_counter = 0

    # ───────────────────────────────────────────────────────────────────────
    # 内部辅助方法（与 AgentService 一致，仅加 async）
    # ───────────────────────────────────────────────────────────────────────

    async def _get_or_create_fsm(self, session_id: str) -> Optional[ClarificationFSM]:
        sess = await self.session_manager.get_session(session_id)
        if sess is None:
            return None
        async with self._fsm_lock:
            if sess.clarification_fsm_state is not None:
                try:
                    fsm = ClarificationFSM.from_dict(sess.clarification_fsm_state)
                except Exception as exc:
                    logger.warning("FSM deserialization failed: %s, creating new", exc)
                    fsm = ClarificationFSM(ClarificationFSMContext(session_id=session_id))
            else:
                fsm = ClarificationFSM(ClarificationFSMContext(session_id=session_id))
            return fsm

    async def _save_fsm(self, session_id: str, fsm: ClarificationFSM) -> None:
        sess = await self.session_manager.get_session(session_id)
        if sess is not None:
            sess.clarification_fsm_state = fsm.to_dict()

    async def _emit_event(self, session_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        if self.event_callback is not None:
            try:
                await self.event_callback(session_id, event_type, payload)
            except Exception as exc:
                logger.warning("Event callback failed: %s", exc)

    async def _build_history(self, sess: Session, limit: int = 10) -> List[Dict[str, Any]]:
        history = []
        for turn in sess.history[-limit:]:
            history.append({
                "role": turn.role,
                "content": turn.content,
                "expectation": turn.intent_result.get("expectation") if turn.intent_result else None,
            })
        return history

    def _check_ambiguity(self, gate_result: GateResult) -> Tuple[bool, List[Dict[str, Any]]]:
        ambiguities = []
        if gate_result.execution_result is not None:
            exec_res = gate_result.execution_result
            if exec_res.status == "clarifying":
                ambiguities = exec_res.clarification.get("ambiguities", [
                    {"type": "unknown_intent", "hint": exec_res.message or "需要澄清"}
                ])
                return True, ambiguities
        return False, []

    def _ui_schema_from_ambiguities(self, ambiguities: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not ambiguities:
            return ClarificationUIFactory.create_tutorial_hint(
                "需要澄清您的意图", ["请提供更多信息"]
            ).to_dict()

        amb = ambiguities[0]
        amb_type = amb.get("type", "unknown")

        if amb_type == "ambiguous_process":
            schema = ClarificationUIFactory.create_process_selector(
                candidates=amb.get("candidates", []),
                recommended_idx=amb.get("recommended_idx", 0),
            )
        elif amb_type == "ambiguous_address":
            schema = ClarificationUIFactory.create_address_selector(
                addresses=amb.get("candidates", []),
                recommended_idx=amb.get("recommended_idx", 0),
            )
        elif amb_type == "missing_value":
            schema = ClarificationUIFactory.create_value_input(
                field_name=amb.get("field", "值"),
                expected_type=amb.get("expected_type", "text"),
                default=amb.get("default", None),
            )
        elif amb_type == "destructive_action":
            schema = ClarificationUIFactory.create_dangerous_confirm(
                action_description=amb.get("description", "危险操作"),
            )
        elif amb_type == "unknown_intent":
            schema = ClarificationUIFactory.create_tutorial_hint(
                hint_text=amb.get("hint", "您的意图不明确，请确认："),
                suggestions=amb.get("suggestions", ["扫描", "读取", "写入"]),
            )
        else:
            schema = ClarificationUIFactory.create_tutorial_hint(
                f"需要澄清: {amb.get('message', '提供更多信息')}",
                amb.get("suggestions", ["确认", "取消"]),
            )
        return schema.to_dict()

    async def _llm_router_fn(self, pcr_output: Dict[str, Any]) -> str:
        if self.llm_provider is None:
            return ""
        from core.agent.llm_providers.base import GenerateRequest
        import json
        req = GenerateRequest(
            prompt=json.dumps(pcr_output, ensure_ascii=False),
            response_format="json",
            max_tokens=256,
            temperature=0.3,
        )
        res = await self.llm_provider.generate_async(req)
        return res.text if res.metrics.success else ""

    # ───────────────────────────────────────────────────────────────────────
    # 公共 API（async 版本）
    # ───────────────────────────────────────────────────────────────────────

    async def create_session(
        self,
        tenant_id: str = "default",
        user_id: Optional[str] = None,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> Session:
        return await self.session_manager.create_session(
            tenant_id=tenant_id, user_id=user_id, initial_context=initial_context
        )

    async def close_session(self, session_id: str) -> Optional[SessionSummary]:
        self.rate_limiter.release_session(session_id)
        return await self.session_manager.close_session(session_id)

    async def process_message(
        self,
        session_id: str,
        content: str,
        modality: str = "text",
        message_id: Optional[str] = None,
        attachments: Optional[List[MediaAttachment]] = None,
    ) -> Tuple[str, Optional[IntentResult], Optional[ClarificationPayload],
               Optional[ErrorPayload], List[str]]:
        """
        处理用户消息（async 版本，支持多模态附件）。
        
        attachments: 多模态附件列表（图片/音频），会自动通过 MultimodalPipeline 预处理。
        """
        # 1. 获取会话
        sess = await self.session_manager.get_session(session_id)
        if sess is None:
            return (
                "error", None, None,
                ErrorPayload(
                    code="SESSION_EXPIRED", message="Session not found or expired",
                    retryable=False,
                ),
                [],
            )

        fsm = await self._get_or_create_fsm(session_id)
        if fsm is None:
            return (
                "error", None, None,
                ErrorPayload(code="INTERNAL_ERROR", message="FSM initialization failed"),
                [],
            )

        # 2. 限流检查
        allowed, retry_after, reason = self.rate_limiter.check(
            sess.tenant_id, session_id, priority="normal"
        )
        if not allowed:
            return (
                "error", None, None,
                ErrorPayload(
                    code="RATE_LIMITED",
                    message=f"Rate limited: {reason}",
                    retryable=True,
                    retry_after_ms=int((retry_after or 1.0) * 1000),
                ),
                [],
            )

        start_ms = time.time() * 1000

        # 3. 多模态预处理（如果提供了附件）
        processed_text = content
        if attachments:
            preprocessed = await self.multimodal.process(content, attachments)
            processed_text = preprocessed.text
            if preprocessed.warnings:
                logger.warning("Multimodal preprocessing warnings: %s", preprocessed.warnings)

        # 4. FSM 状态转换
        if fsm.current_state == ClarificationState.CLARIFYING:
            event = ClarificationEvent.USER_CLARIFY
        else:
            event = ClarificationEvent.USER_MESSAGE

        new_state, response = fsm.handle_event(event)
        await self._save_fsm(session_id, fsm)
        await self._emit_event(session_id, "progress", response)

        # 5. 构建历史
        history = await self._build_history(sess)

        # 6. 调用编排器
        await self._emit_event(session_id, "progress", {
            "stage": "orchestrator", "status": "started", "detail": "意图解析中"
        })
        gate_result = self.orchestrator.process(processed_text, history=history)
        trace_log = gate_result.trace
        await self._emit_event(session_id, "progress", {
            "stage": "orchestrator", "status": "completed", "detail": f"结果: {gate_result.track}"
        })

        # 7. 检查歧义
        has_ambiguity, ambiguities = self._check_ambiguity(gate_result)

        # 8. FSM 状态转换
        if has_ambiguity:
            new_state, response = fsm.handle_event(
                ClarificationEvent.PARSE_COMPLETE_HAS_AMBIGUITY if event == ClarificationEvent.USER_MESSAGE
                else ClarificationEvent.REPARSE_COMPLETE_HAS_AMBIGUITY,
                {"ambiguities": ambiguities},
            )
        else:
            new_state, response = fsm.handle_event(
                ClarificationEvent.PARSE_COMPLETE_NO_AMBIGUITY if event == ClarificationEvent.USER_MESSAGE
                else ClarificationEvent.REPARSE_COMPLETE_NO_AMBIGUITY,
                {"intent_result": gate_result.pcr_output},
            )

        await self._save_fsm(session_id, fsm)
        latency_ms = (time.time() * 1000) - start_ms

        # 9. 构建结果
        intent_result = None
        clarification = None
        status = "actionable"
        error = None

        if new_state == ClarificationState.CLARIFYING:
            status = "needs_clarification"
            ui_schema = self._ui_schema_from_ambiguities(ambiguities)
            clarification = ClarificationPayload(
                clarification_id=response.get("clarification_id", ""),
                message=response.get("message", "需要澄清"),
                suggestions=ambiguities[0].get("suggestions", []) if ambiguities else [],
                timeout_seconds=60,
                ui_schema=ui_schema,
            )
            await self._emit_event(session_id, "clarification", {
                "clarification_id": clarification.clarification_id,
                "message": clarification.message,
                "ui_schema": ui_schema,
                "deadline": response.get("deadline", time.time() + 60),
            })

        elif new_state == ClarificationState.ACTIONABLE:
            status = "actionable"
            if gate_result.pcr_output is not None:
                pcr_out = gate_result.pcr_output
                intent_result = IntentResult(
                    expectation=pcr_out.expectation,
                    cognitive_profile=pcr_out.cognitive_profile.to_dict() if hasattr(pcr_out.cognitive_profile, "to_dict") else None,
                )
                if gate_result.execution_result and gate_result.execution_result.task_graph is not None:
                    tg = gate_result.execution_result.task_graph
                    if hasattr(tg, "to_dict"):
                        intent_result.task_graph = tg.to_dict()

            await self._emit_event(session_id, "intent_result", {
                "message_id": message_id,
                "status": status,
                "intent_result": intent_result.to_dict() if intent_result else None,
                "latency_ms": latency_ms,
            })

        elif new_state == ClarificationState.EXPIRED:
            status = "error"
            error = ErrorPayload(
                code="CLARIFICATION_EXPIRED",
                message="澄清请求已超时，请重新发送消息",
                retryable=True,
            )
            fsm = ClarificationFSM(ClarificationFSMContext(session_id=session_id))
            await self._save_fsm(session_id, fsm)

        elif new_state == ClarificationState.ERROR:
            status = "error"
            error = ErrorPayload(
                code="INTERNAL_ERROR",
                message=response.get("error", "处理失败"),
                retryable=False,
            )

        # 10. 记录轮次
        async with self._lock:
            self._message_counter += 1
        turn = TurnRecord(
            sequence=sess.turn_count,
            timestamp=time.time(),
            role="user",
            content=content,
            modality=modality,
            intent_result=intent_result.to_dict() if intent_result else None,
            clarification=clarification.to_dict() if clarification else None,
            latency_ms=latency_ms,
        )
        await self.session_manager.update_session(session_id, turn)

        # 11. 更新会话状态
        if new_state == ClarificationState.CLARIFYING:
            sess.state = "clarifying"
            sess.pending_clarification = clarification.clarification_id if clarification else None
        elif new_state == ClarificationState.ACTIONABLE:
            sess.state = "active"
            sess.pending_clarification = None

        return status, intent_result, clarification, error, trace_log

    async def submit_clarification(
        self,
        session_id: str,
        clarification_id: str,
        selected_option: Optional[int] = None,
        free_text: Optional[str] = None,
    ) -> Tuple[str, Optional[IntentResult], Optional[ClarificationPayload],
               Optional[ErrorPayload]]:
        """提交澄清回复（async 版本）。"""
        sess = await self.session_manager.get_session(session_id)
        if sess is None:
            return "error", None, None, ErrorPayload(
                code="SESSION_EXPIRED", message="Session not found",
                retryable=False,
            )

        fsm = await self._get_or_create_fsm(session_id)
        if fsm is None:
            return "error", None, None, ErrorPayload(
                code="INTERNAL_ERROR", message="FSM initialization failed",
            )

        if fsm.current_state != ClarificationState.CLARIFYING:
            return "error", None, None, ErrorPayload(
                code="NOT_CLARIFYING",
                message="Session is not in clarification state",
                retryable=False,
            )

        if fsm.context.last_clarification_id != clarification_id:
            return "error", None, None, ErrorPayload(
                code="CLARIFICATION_MISMATCH",
                message="Clarification ID mismatch or expired",
                retryable=False,
            )

        if fsm.check_timeout() == ClarificationEvent.TIMEOUT:
            new_state, response = fsm.handle_event(ClarificationEvent.TIMEOUT)
            await self._save_fsm(session_id, fsm)
            return "error", None, None, ErrorPayload(
                code="CLARIFICATION_EXPIRED",
                message="Clarification request has expired",
                retryable=True,
            )

        clarify_text = free_text or f"[selected_option:{selected_option}]"
        status, intent_result, clarification, error, trace = await self.process_message(
            session_id, clarify_text, modality="text",
        )

        if error is not None and error.code == "NOT_CLARIFYING":
            fsm = ClarificationFSM(ClarificationFSMContext(session_id=session_id))
            await self._save_fsm(session_id, fsm)
            status, intent_result, clarification, error, trace = await self.process_message(
                session_id, clarify_text, modality="text",
            )

        if error is None:
            sess.pending_clarification = None
            if clarification is None:
                sess.state = "active"

        return status, intent_result, clarification, error

    async def get_history(self, session_id: str, limit: int = 50) -> List[TurnRecord]:
        """获取会话历史（async 版本）。"""
        sess = await self.session_manager.get_session(session_id)
        if sess is None:
            return []
        return sess.history[-limit:]

    async def get_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话状态（async 版本，包含 FSM 状态）。"""
        sess = await self.session_manager.get_session(session_id)
        if sess is None:
            return None
        fsm = await self._get_or_create_fsm(session_id)
        fsm_status = None
        if fsm is not None:
            fsm_status = {
                "state": fsm.current_state,
                "state_description": fsm.get_state_description(),
                "clarification_count": fsm.context.clarification_count,
                "max_clarifications": fsm.context.max_clarifications,
                "can_clarify_more": fsm.can_clarify_more(),
                "current_clarification_id": fsm.context.last_clarification_id,
            }
        return {
            "session_id": sess.session_id,
            "state": sess.state,
            "current_turn": sess.turn_count,
            "pending_clarification": sess.pending_clarification,
            "last_activity_at": sess.last_activity_at,
            "expires_at": sess.expires_at,
            "fsm": fsm_status,
        }

    async def health_check(self) -> Dict[str, Any]:
        """健康检查（async 版本）。"""
        active_count = await self.session_manager.list_active_sessions("default", limit=10000)
        return {
            "status": "healthy",
            "components": {
                "pcr": {"status": "ok"},
                "parser": {"status": "ok"},
                "session_manager": {
                    "status": "ok",
                    "active_sessions": len(active_count),
                },
                "rate_limiter": {"status": "ok"},
            },
        }

    async def start(self) -> None:
        """启动服务（启动 AsyncSessionManager 的后台任务）。"""
        await self.session_manager.start()

    async def stop(self) -> None:
        """停止服务（优雅关闭）。"""
        await self.session_manager.stop()
