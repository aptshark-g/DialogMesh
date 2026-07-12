# -*- coding: utf-8 -*-
"""
core/agent/service/agent_service.py
─────────────────────────────────────
Agent 服务核心逻辑（v2.4 服务层新增）。

集成编排门控（DualTrackOrchestrator）与会话管理，
处理消息解析、澄清、历史查询等核心业务逻辑。
"""

from __future__ import annotations

import time
import threading
from typing import Any, Dict, List, Optional, Tuple

from core.agent.frontend import (
    ClarificationFSM, ClarificationFSMContext, ClarificationState, ClarificationEvent,
    ClarificationUIFactory, EventBuilder, EventSerializer,
)
from core.agent.service.models import (
    Session, TurnRecord, IntentResult, ClarificationPayload,
    ParseProgressEvent, ErrorPayload, SessionSummary,
)
from core.agent.service.session_manager import SessionManager
from core.agent.service.rate_limiter import RateLimiter
from core.agent.service.distributed_lock import DistributedLock, ThreadingLockAdapter

from core.agent.pcr.rule_based import RuleBasedPCR
from core.agent.v3_common.intent_parser import IntentParser
from core.agent.v3_common.gates import DualTrackOrchestrator, GateResult, AdaptiveThresholds
from core.agent.llm_providers.base import LLMProvider

import logging
logger = logging.getLogger(__name__)


class AgentService:
    """
    Agent 服务：封装核心引擎 + 会话管理 + 限流。
    线程安全：核心引擎（PCR/Parser）是复用的单例，会话数据由 SessionManager 保护。
    """

    def __init__(
        self,
        pcr: RuleBasedPCR,
        parser: IntentParser,
        session_manager: SessionManager,
        rate_limiter: RateLimiter,
        llm_provider: Optional[LLMProvider] = None,
        event_callback: Optional[Any] = None,
        lock: Optional[DistributedLock] = None,
    ):
        self.pcr = pcr
        self.parser = parser
        self.session_manager = session_manager
        self.rate_limiter = rate_limiter
        self.llm_provider = llm_provider
        self.event_callback = event_callback

        # 编排器：可选 LLM Provider
        self.orchestrator = DualTrackOrchestrator(
            pcr, parser,
            router_llm_fn=self._llm_router_fn if llm_provider else None,
        )

        self._lock = lock or ThreadingLockAdapter()
        self._fsm_lock = threading.Lock()
        self._message_counter = 0

    def _get_or_create_fsm(self, session_id: str) -> Optional[ClarificationFSM]:
        """获取或恢复会话的 FSM。"""
        sess = self.session_manager.get_session(session_id)
        if sess is None:
            return None
        with self._fsm_lock:
            if sess.clarification_fsm_state is not None:
                try:
                    fsm = ClarificationFSM.from_dict(sess.clarification_fsm_state)
                except Exception as exc:
                    logger.warning("FSM deserialization failed: %s, creating new", exc)
                    fsm = ClarificationFSM(ClarificationFSMContext(session_id=session_id))
            else:
                fsm = ClarificationFSM(ClarificationFSMContext(session_id=session_id))
            return fsm

    def _save_fsm(self, session_id: str, fsm: ClarificationFSM) -> None:
        """保存 FSM 状态到会话。"""
        sess = self.session_manager.get_session(session_id)
        if sess is not None:
            sess.clarification_fsm_state = fsm.to_dict()

    def _emit_event(self, session_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        """发送事件（通过回调）。"""
        if self.event_callback is not None:
            try:
                self.event_callback(session_id, event_type, payload)
            except Exception as exc:
                logger.warning("Event callback failed: %s", exc)

    def _build_history(self, sess: Session, limit: int = 10) -> List[Dict[str, Any]]:
        """构建历史上下文（最近 limit 轮）。"""
        history = []
        for turn in sess.history[-limit:]:
            history.append({
                "role": turn.role,
                "content": turn.content,
                "expectation": turn.intent_result.get("expectation") if turn.intent_result else None,
            })
        return history

    def _check_ambiguity(self, gate_result: GateResult) -> Tuple[bool, List[Dict[str, Any]]]:
        """检查 gate_result 是否包含歧义。"""
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
        """从歧义列表生成 UI Schema。"""
        if not ambiguities:
            return ClarificationUIFactory.create_tutorial_hint(
                "需要澄清您的意图",
                ["请提供更多信息"]
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

    def _llm_router_fn(self, pcr_output: Dict[str, Any]) -> str:
        """包装 LLM Provider 为 Router LLM 函数。"""
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
        res = self.llm_provider.generate(req)
        return res.text if res.metrics.success else ""

    def create_session(
        self,
        tenant_id: str = "default",
        user_id: Optional[str] = None,
        initial_context: Optional[Dict[str, Any]] = None,
        user_type_hint: Optional[str] = None,
    ) -> Session:
        """创建新会话。"""
        if initial_context is None:
            initial_context = {}
        if user_type_hint is not None:
            initial_context["user_type_hint"] = user_type_hint
        return self.session_manager.create_session(
            tenant_id=tenant_id, user_id=user_id, initial_context=initial_context
        )

    def close_session(self, session_id: str) -> Optional[SessionSummary]:
        """关闭会话。"""
        self.rate_limiter.release_session(session_id)
        return self.session_manager.close_session(session_id)

    def process_message(
        self,
        session_id: str,
        content: str,
        modality: str = "text",
        message_id: Optional[str] = None,
    ) -> Tuple[str, Optional[IntentResult], Optional[ClarificationPayload],
               Optional[ErrorPayload], List[str]]:
        """
        处理用户消息（集成 FSM 多轮澄清流程）。

        返回: (status, intent_result, clarification, error, trace_log)
        - status: "actionable" | "needs_clarification" | "error" | "processing"
        """
        # 1. 获取会话和 FSM
        sess = self.session_manager.get_session(session_id)
        if sess is None:
            return (
                "error", None, None,
                ErrorPayload(
                    code="SESSION_EXPIRED", message="Session not found or expired",
                    retryable=False,
                ),
                [],
            )

        fsm = self._get_or_create_fsm(session_id)
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

        # 3. 处理 FSM 状态：如果当前在 CLARIFYING，自动转为重新解析（用户直接发消息）
        if fsm.current_state == ClarificationState.CLARIFYING:
            # 自动将消息视为澄清回复
            event = ClarificationEvent.USER_CLARIFY
        else:
            event = ClarificationEvent.USER_MESSAGE

        # 4. FSM 状态转换 -> PARSING / RE_PARSING
        new_state, response = fsm.handle_event(event)
        self._save_fsm(session_id, fsm)
        self._emit_event(session_id, "progress", response)

        # 5. 构建历史上下文
        history = self._build_history(sess)

        # P1 修复：获取 user_type_hint
        user_type_hint = None
        if sess.parse_context and isinstance(sess.parse_context, dict):
            user_type_hint = sess.parse_context.get("user_type_hint")

        # P0 修复：获取或创建自适应阈值
        adaptive = None
        if sess.adaptive_thresholds is not None:
            adaptive = AdaptiveThresholds.from_dict(sess.adaptive_thresholds)
        else:
            adaptive = AdaptiveThresholds()

        # 6. 调用编排器（传入自适应阈值和 metadata）
        self._emit_event(session_id, "progress", {
            "stage": "orchestrator", "status": "started", "detail": "意图解析中"
        })
        metadata = {"user_type_hint": user_type_hint} if user_type_hint else None
        gate_result = self.orchestrator.process(
            content, history=history, adaptive=adaptive, metadata=metadata
        )
        trace_log = gate_result.trace
        self._emit_event(session_id, "progress", {
            "stage": "orchestrator", "status": "completed", "detail": f"结果: {gate_result.track}"
        })

        # 7. 检查歧义
        has_ambiguity, ambiguities = self._check_ambiguity(gate_result)

        # 8. FSM 状态转换 -> ACTIONABLE / CLARIFYING
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

        self._save_fsm(session_id, fsm)
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

            # 发送澄清事件
            self._emit_event(session_id, "clarification", {
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

            # 发送意图结果事件
            self._emit_event(session_id, "intent_result", {
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
            # 重置 FSM
            fsm = ClarificationFSM(ClarificationFSMContext(session_id=session_id))
            self._save_fsm(session_id, fsm)

        elif new_state == ClarificationState.ERROR:
            status = "error"
            error = ErrorPayload(
                code="INTERNAL_ERROR",
                message=response.get("error", "处理失败"),
                retryable=False,
            )

        # 10. 记录轮次
        with self._lock:
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
        self.session_manager.update_session(session_id, turn)

        # 11. 更新会话状态
        if new_state == ClarificationState.CLARIFYING:
            sess.state = "clarifying"
            sess.pending_clarification = clarification.clarification_id if clarification else None
        elif new_state == ClarificationState.ACTIONABLE:
            sess.state = "active"
            sess.pending_clarification = None

        # P0 修复：反馈闭环 — 根据结果调整自适应阈值
        required_clarification = (new_state == ClarificationState.CLARIFYING)
        adaptive.feedback(required_clarification=required_clarification, was_accurate=None)
        sess.adaptive_thresholds = adaptive.to_dict()

        return status, intent_result, clarification, error, trace_log

    def submit_clarification(
        self,
        session_id: str,
        clarification_id: str,
        selected_option: Optional[int] = None,
        free_text: Optional[str] = None,
    ) -> Tuple[str, Optional[IntentResult], Optional[ClarificationPayload],
               Optional[ErrorPayload]]:
        """
        提交澄清回复（集成 FSM 多轮澄清流程）。
        """
        sess = self.session_manager.get_session(session_id)
        if sess is None:
            return "error", None, None, ErrorPayload(
                code="SESSION_EXPIRED", message="Session not found",
                retryable=False,
            )

        fsm = self._get_or_create_fsm(session_id)
        if fsm is None:
            return "error", None, None, ErrorPayload(
                code="INTERNAL_ERROR", message="FSM initialization failed",
            )

        # 验证 FSM 状态
        if fsm.current_state != ClarificationState.CLARIFYING:
            return "error", None, None, ErrorPayload(
                code="NOT_CLARIFYING",
                message="Session is not in clarification state",
                retryable=False,
            )

        # 验证 clarification_id
        if fsm.context.last_clarification_id != clarification_id:
            return "error", None, None, ErrorPayload(
                code="CLARIFICATION_MISMATCH",
                message="Clarification ID mismatch or expired",
                retryable=False,
            )

        # 检查超时
        if fsm.check_timeout() == ClarificationEvent.TIMEOUT:
            new_state, response = fsm.handle_event(ClarificationEvent.TIMEOUT)
            self._save_fsm(session_id, fsm)
            return "error", None, None, ErrorPayload(
                code="CLARIFICATION_EXPIRED",
                message="Clarification request has expired",
                retryable=True,
            )

        # 构建澄清文本
        clarify_text = free_text or f"[selected_option:{selected_option}]"

        # 复用 process_message 逻辑（FSM 会自动处理 CLARIFYING -> RE_PARSING 转换）
        status, intent_result, clarification, error, trace = self.process_message(
            session_id, clarify_text, modality="text",
        )

        if error is not None and error.code == "NOT_CLARIFYING":
            # 如果 process_message 返回 NOT_CLARIFYING，说明 FSM 状态异常
            # 强制重置并重新处理
            fsm = ClarificationFSM(ClarificationFSMContext(session_id=session_id))
            self._save_fsm(session_id, fsm)
            status, intent_result, clarification, error, trace = self.process_message(
                session_id, clarify_text, modality="text",
            )

        if error is None:
            sess.pending_clarification = None
            if clarification is None:
                sess.state = "active"

        return status, intent_result, clarification, error

    def get_history(self, session_id: str, limit: int = 50) -> List[TurnRecord]:
        """获取会话历史。"""
        sess = self.session_manager.get_session(session_id)
        if sess is None:
            return []
        return sess.history[-limit:]

    def get_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话状态（包含 FSM 状态）。"""
        sess = self.session_manager.get_session(session_id)
        if sess is None:
            return None
        fsm = self._get_or_create_fsm(session_id)
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

    def health_check(self) -> Dict[str, Any]:
        """健康检查。"""
        return {
            "status": "healthy",
            "components": {
                "pcr": {"status": "ok"},
                "parser": {"status": "ok"},
                "session_manager": {
                    "status": "ok",
                    "active_sessions": len(self.session_manager._sessions),
                },
                "rate_limiter": {"status": "ok"},
            },
        }
