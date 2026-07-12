# -*- coding: utf-8 -*-
"""
service/api/dependencies.py
──────────────────────────
DialogMesh FastAPI 依赖注入与 AgentService 适配层。

- 全局单例生命周期由 main.py 的 startup/shutdown 管理
- 测试时通过 create_app(override_dependencies={...}) 注入 mock
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Optional, Dict, List, Any, Tuple

from fastapi import Header, Depends, HTTPException

from service.async_session_manager import AsyncSessionManager
from service.models import Session, TurnRecord
from service.protocol.schemas import (
    IntentResult,
    CognitiveProfilePayload,
    ClarificationPayload,
)
from service.protocol.events import EventBuilder, EventSerializer, ErrorPayload
from service.protocol.fsm import (
    ClarificationFSM,
    ClarificationFSMContext,
    ClarificationState,
    ClarificationEvent,
)
from service.protocol.ui_schema import ClarificationUISchema

from core.agent.pcr.rule_based import RuleBasedPCR
from core.agent.v3_common.intent_parser import IntentParser
from core.agent.pcr.datacontract import PCRInput_v1, HistoryEntry
from core.agent.v3_common.models import IntentContext, ParseContext

from service.api.websocket import WebSocketManager

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 全局单例（由 main.py startup 注入）
# ═══════════════════════════════════════════════════════════════════════════════

_pcr_instance: Optional[RuleBasedPCR] = None
_parser_instance: Optional[IntentParser] = None
_session_manager_instance: Optional[AsyncSessionManager] = None
_ws_manager_instance: Optional[WebSocketManager] = None
_agent_service_instance: Optional[AgentService] = None


def init_dependencies(
    pcr: RuleBasedPCR,
    parser: IntentParser,
    session_manager: AsyncSessionManager,
    ws_manager: WebSocketManager,
) -> None:
    """由 main.py startup 调用一次，注入所有单例。"""
    global _pcr_instance, _parser_instance, _session_manager_instance
    global _ws_manager_instance, _agent_service_instance
    _pcr_instance = pcr
    _parser_instance = parser
    _session_manager_instance = session_manager
    _ws_manager_instance = ws_manager
    _agent_service_instance = AgentService(pcr, parser, session_manager, ws_manager)


# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI Depends 依赖注入函数
# ═══════════════════════════════════════════════════════════════════════════════

def get_session_manager() -> AsyncSessionManager:
    if _session_manager_instance is None:
        raise RuntimeError("AsyncSessionManager not initialized")
    return _session_manager_instance


def get_websocket_manager() -> WebSocketManager:
    if _ws_manager_instance is None:
        raise RuntimeError("WebSocketManager not initialized")
    return _ws_manager_instance


def get_agent_service() -> AgentService:
    if _agent_service_instance is None:
        raise RuntimeError("AgentService not initialized")
    return _agent_service_instance


async def get_current_session(
    session_id: str,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
) -> Session:
    """获取会话，不存在时返回 404。"""
    session = await session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": f"Session {session_id} not found or expired",
                    "retryable": False,
                }
            },
        )
    return session


def get_tenant_id(
    x_tenant_id: Optional[str] = Header(default="default", alias="X-Tenant-ID"),
) -> str:
    """从请求头提取 X-Tenant-ID。"""
    return x_tenant_id or "default"


# ═══════════════════════════════════════════════════════════════════════════════
# AgentService — 核心引擎到 API 层的适配器
# ═══════════════════════════════════════════════════════════════════════════════

class AgentService:
    """
    DialogMesh API 层 AgentService。

    桥接 service 层（AsyncSessionManager + WebSocketManager）与核心引擎
    （RuleBasedPCR + IntentParser + ClarificationFSM）。
    """

    def __init__(
        self,
        pcr: RuleBasedPCR,
        parser: IntentParser,
        session_manager: AsyncSessionManager,
        ws_manager: WebSocketManager,
    ) -> None:
        self.pcr = pcr
        self.parser = parser
        self.session_manager = session_manager
        self.ws_manager = ws_manager

        self._parse_contexts: Dict[str, ParseContext] = {}
        self._fsm_map: Dict[str, ClarificationFSM] = {}
        self._fsm_lock = asyncio.Lock()
        self._pending_clarification_ids: Dict[str, str] = {}
        self._request_count = 0
        self._error_count = 0

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _get_fsm(self, session_id: str) -> ClarificationFSM:
        async with self._fsm_lock:
            if session_id not in self._fsm_map:
                ctx = ClarificationFSMContext(session_id=session_id)
                self._fsm_map[session_id] = ClarificationFSM(ctx)
            return self._fsm_map[session_id]

    async def _save_fsm(self, session_id: str, fsm: ClarificationFSM) -> None:
        self._fsm_map[session_id] = fsm

    def _get_parse_context(self, session_id: str) -> ParseContext:
        if session_id not in self._parse_contexts:
            self._parse_contexts[session_id] = ParseContext(session_id=session_id)
        return self._parse_contexts[session_id]

    def _build_history(self, session: Session) -> List[HistoryEntry]:
        entries: List[HistoryEntry] = []
        for turn in session.history[-10:]:
            entries.append(
                HistoryEntry(
                    role=turn.role,
                    content=turn.content,
                    expectation=(
                        turn.intent_result.get("expectation")
                        if turn.intent_result else None
                    ),
                    timestamp=turn.timestamp,
                )
            )
        return entries

    def _cognitive_to_payload(
        self, cog_profile: Any,
    ) -> Optional[CognitiveProfilePayload]:
        if cog_profile is None:
            return None
        d: Dict[str, Any] = {}
        if hasattr(cog_profile, "to_dict"):
            d = cog_profile.to_dict()
        elif isinstance(cog_profile, dict):
            d = cog_profile
        else:
            return None
        return CognitiveProfilePayload(
            metacognition=d.get("metacognition", 0.0),
            divergence=d.get("divergence", 0.0),
            tracking_depth=d.get("tracking_depth", 0.0),
            stability=d.get("stability", 0.0),
            confidence=d.get("confidence", 0.0),
        )

    # ── Public API ───────────────────────────────────────────────────────────

    async def create_session(
        self,
        tenant_id: str = "default",
        user_id: Optional[str] = None,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> Session:
        session = await self.session_manager.create_session(
            tenant_id=tenant_id, user_id=user_id,
        )
        if initial_context:
            session.parse_context = initial_context
            await self.session_manager.update_session(session)
        return session

    async def process_message(
        self,
        session_id: str,
        content: str,
        modality: str = "text",
        message_id: Optional[str] = None,
    ) -> Tuple[str, Optional[IntentResult], Optional[ClarificationPayload],
               Optional[ErrorPayload], List[str], float]:
        """
        处理用户消息。

        返回: (status, intent_result, clarification, error, trace_log, latency_ms)
        """
        session = await self.session_manager.get_session(session_id)
        if session is None:
            return (
                "error", None, None,
                ErrorPayload(
                    code="SESSION_EXPIRED",
                    message="Session not found or expired",
                    retryable=False,
                ),
                [],
                0.0,
            )

        fsm = await self._get_fsm(session_id)

        # 确定 FSM 事件
        if fsm.context.current_state == ClarificationState.CLARIFYING:
            event = ClarificationEvent.USER_CLARIFY
        else:
            event = ClarificationEvent.USER_MESSAGE

        # FSM 转换 -> PARSING / RE_PARSING
        new_state, response = fsm.handle_event(event)
        await self._save_fsm(session_id, fsm)

        # 构建历史
        history = self._build_history(session)

        # PCR 评估
        start_ms = time.time() * 1000
        metadata: Dict[str, Any] = {}
        if session.parse_context and isinstance(session.parse_context, dict):
            user_type_hint = session.parse_context.get("user_type_hint")
            if user_type_hint:
                metadata["user_type_hint"] = user_type_hint

        pcr_input = PCRInput_v1(
            query=content,
            session_id=session_id,
            turn_index=session.turn_count,
            session_history=history,
            timestamp=time.time(),
            metadata=metadata,
        )
        try:
            pcr_output = self.pcr.evaluate(pcr_input)
        except Exception as exc:
            logger.exception("PCR evaluation failed: %s", exc)
            return (
                "error", None, None,
                ErrorPayload(
                    code="PCR_DEGRADED",
                    message="Intent analysis engine failed",
                    retryable=True,
                    retry_after_ms=1000,
                ),
                [f"PCR error: {exc}"],
                0.0,
            )

        # Intent 解析
        intent_context = IntentContext.from_pcr_output(pcr_output)
        parse_context = self._get_parse_context(session_id)

        try:
            parse_result = self.parser.parse(content, intent_context, parse_context)
        except Exception as exc:
            logger.exception("Intent parsing failed: %s", exc)
            return (
                "error", None, None,
                ErrorPayload(
                    code="INTERNAL_ERROR",
                    message="Intent parsing failed",
                    retryable=True,
                    retry_after_ms=1000,
                ),
                [f"Parser error: {exc}"],
                0.0,
            )

        # 判断歧义
        has_ambiguity = (
            not parse_result.is_actionable
            or parse_result.clarification_message is not None
        )

        # FSM 状态转换
        if has_ambiguity:
            new_state, response = fsm.handle_event(
                (
                    ClarificationEvent.PARSE_COMPLETE_HAS_AMBIGUITY
                    if event == ClarificationEvent.USER_MESSAGE
                    else ClarificationEvent.REPARSE_COMPLETE_HAS_AMBIGUITY
                ),
                {"ambiguities": []},
            )
        else:
            new_state, response = fsm.handle_event(
                (
                    ClarificationEvent.PARSE_COMPLETE_NO_AMBIGUITY
                    if event == ClarificationEvent.USER_MESSAGE
                    else ClarificationEvent.REPARSE_COMPLETE_NO_AMBIGUITY
                ),
                {"intent_result": pcr_output.to_dict() if pcr_output else None},
            )

        await self._save_fsm(session_id, fsm)
        latency_ms = (time.time() * 1000) - start_ms

        # 构建结果
        intent_result: Optional[IntentResult] = None
        clarification: Optional[ClarificationPayload] = None
        status = "actionable"
        error: Optional[ErrorPayload] = None
        trace_log = parse_result.trace_log if parse_result else []

        if new_state == ClarificationState.CLARIFYING:
            status = "needs_clarification"
            ambiguities = (
                parse_result.intent.ambiguities
                if parse_result and parse_result.intent else []
            )
            suggestions: List[str] = []
            if ambiguities and ambiguities[0].suggestions:
                suggestions = ambiguities[0].suggestions
            elif parse_result and parse_result.suggestions:
                suggestions = parse_result.suggestions

            clarify_id = f"clarify-{uuid.uuid4().hex[:8]}"
            self._pending_clarification_ids[session_id] = clarify_id

            clarification = ClarificationPayload(
                clarification_id=clarify_id,
                message=parse_result.clarification_message or "需要澄清您的意图",
                suggestions=suggestions,
                timeout_seconds=60,
            )

            # 通过 WebSocket 广播澄清事件
            await self.ws_manager.broadcast(
                session_id,
                EventBuilder.clarification(
                    session_id, clarification.model_dump(),
                ),
            )

        elif new_state == ClarificationState.ACTIONABLE:
            status = "actionable"
            if pcr_output:
                cog_payload = self._cognitive_to_payload(pcr_output.cognitive_profile)
                intent_result = IntentResult(
                    expectation=pcr_output.expectation,
                    cognitive_profile=cog_payload or CognitiveProfilePayload(),
                )

            # 通过 WebSocket 广播意图结果
            await self.ws_manager.broadcast(
                session_id,
                EventBuilder.intent_result(
                    session_id,
                    {
                        "message_id": message_id,
                        "status": status,
                        "intent_result": (
                            intent_result.model_dump() if intent_result else None
                        ),
                        "latency_ms": latency_ms,
                    },
                ),
            )

        # 记录轮次
        turn = TurnRecord(
            sequence=session.turn_count,
            timestamp=time.time(),
            role="user",
            content=content,
            modality=modality,
            intent_result=intent_result.model_dump() if intent_result else None,
            clarification=clarification.model_dump() if clarification else None,
            latency_ms=latency_ms,
        )
        await self.session_manager.save_turn(session_id, turn)

        # 更新会话状态
        if new_state == ClarificationState.CLARIFYING:
            session.state = "clarifying"
            session.pending_clarification = (
                clarification.clarification_id if clarification else None
            )
        elif new_state == ClarificationState.ACTIONABLE:
            session.state = "active"
            session.pending_clarification = None

        await self.session_manager.update_session(session)

        return status, intent_result, clarification, error, trace_log, latency_ms

    async def submit_clarification(
        self,
        session_id: str,
        clarification_id: str,
        selected_option: Optional[int] = None,
        free_text: Optional[str] = None,
    ) -> Tuple[str, Optional[IntentResult], Optional[ClarificationPayload],
               Optional[ErrorPayload]]:
        """提交澄清回复。"""
        session = await self.session_manager.get_session(session_id)
        if session is None:
            return "error", None, None, ErrorPayload(
                code="SESSION_EXPIRED",
                message="Session not found",
                retryable=False,
            )

        fsm = await self._get_fsm(session_id)

        if fsm.context.current_state != ClarificationState.CLARIFYING:
            return "error", None, None, ErrorPayload(
                code="NOT_CLARIFYING",
                message="Session is not in clarification state",
                retryable=False,
            )

        pending_id = self._pending_clarification_ids.get(session_id)
        if pending_id != clarification_id:
            return "error", None, None, ErrorPayload(
                code="CLARIFICATION_MISMATCH",
                message="Clarification ID mismatch or expired",
                retryable=False,
            )

        if fsm.is_expired():
            fsm.handle_event(ClarificationEvent.TIMEOUT)
            await self._save_fsm(session_id, fsm)
            return "error", None, None, ErrorPayload(
                code="CLARIFICATION_EXPIRED",
                message="Clarification request has expired",
                retryable=True,
            )

        clarify_text = free_text or f"[selected_option:{selected_option}]"

        # 复用 process_message 逻辑（FSM 会自动处理 CLARIFYING -> RE_PARSING 转换）
        status, intent_result, clarification, error, trace_log, latency_ms = (
            await self.process_message(
                session_id, clarify_text, modality="text", message_id=None,
            )
        )

        if error is not None and error.code == "NOT_CLARIFYING":
            # 强制重置 FSM 后重试
            ctx = ClarificationFSMContext(session_id=session_id)
            self._fsm_map[session_id] = ClarificationFSM(ctx)
            status, intent_result, clarification, error, trace_log, latency_ms = (
                await self.process_message(
                    session_id, clarify_text, modality="text", message_id=None,
                )
            )

        if error is None:
            session.pending_clarification = None
            if clarification is None:
                session.state = "active"
            await self.session_manager.update_session(session)

        return status, intent_result, clarification, error

    async def get_history(
        self, session_id: str, limit: int = 50, before_seq: Optional[int] = None,
    ) -> List[TurnRecord]:
        """获取会话历史（优先使用 store 分页，否则内存回退）。"""
        store = self.session_manager.store
        if store is not None:
            try:
                return await store.get_history(
                    session_id, limit=limit, before_sequence=before_seq,
                )
            except Exception as exc:
                logger.warning("Store get_history failed, fallback to memory: %s", exc)

        session = await self.session_manager.get_session(session_id)
        if session is None:
            return []
        history = list(session.history)
        if before_seq is not None:
            history = [t for t in history if t.sequence < before_seq]
        return history[-limit:]

    async def get_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话状态（含 FSM、认知画像）。"""
        session = await self.session_manager.get_session(session_id)
        if session is None:
            return None

        fsm = await self._get_fsm(session_id)
        fsm_status = None
        if fsm is not None:
            fsm_status = {
                "state": fsm.context.current_state,
                "clarification_count": fsm.context.clarification_count,
                "max_clarifications": fsm.context.max_clarifications,
                "can_clarify_more": fsm.can_clarify_more(),
                "is_expired": fsm.is_expired(),
            }

        return {
            "session_id": session.session_id,
            "state": session.state,
            "current_turn": session.turn_count,
            "pending_clarification": session.pending_clarification,
            "cognitive_profile": (
                session.cognitive_profile.to_dict()
                if session.cognitive_profile else None
            ),
            "last_activity_at": session.last_activity_at,
            "expires_at": session.expires_at,
            "fsm": fsm_status,
        }

    async def health_check(self) -> Dict[str, Any]:
        """组件健康检查。"""
        pcr_status = "healthy"
        pcr_error = None
        try:
            health = self.pcr.get_health()
            pcr_status = health.value if hasattr(health, "value") else str(health)
        except Exception as exc:
            pcr_status = "unhealthy"
            pcr_error = str(exc)

        parser_status = "healthy"
        parser_error = None
        try:
            _ = self.parser
        except Exception as exc:
            parser_status = "unhealthy"
            parser_error = str(exc)

        sm_status = "healthy"
        sm_error = None
        try:
            active = await self.session_manager.list_sessions("default", limit=1)
        except Exception as exc:
            sm_status = "unhealthy"
            sm_error = str(exc)

        ws_status = "healthy"
        ws_error = None
        try:
            _ = self.ws_manager.get_connection_count("default")
        except Exception as exc:
            ws_status = "unhealthy"
            ws_error = str(exc)

        store_status = "healthy"
        store_error = None
        if self.session_manager.store:
            try:
                _ = await self.session_manager.store.list_active_sessions(
                    "default", limit=1,
                )
            except Exception as exc:
                store_status = "unhealthy"
                store_error = str(exc)
        else:
            store_status = "degraded"
            store_error = "No persistent store configured"

        overall = "healthy"
        if any(s == "unhealthy" for s in [pcr_status, parser_status, sm_status, ws_status, store_status]):
            overall = "unhealthy"
        elif any(s == "degraded" for s in [pcr_status, parser_status, sm_status, ws_status, store_status]):
            overall = "degraded"

        return {
            "status": overall,
            "components": {
                "pcr": {"status": pcr_status, "last_error": pcr_error},
                "intent_parser": {"status": parser_status, "last_error": parser_error},
                "session_manager": {"status": sm_status, "last_error": sm_error},
                "websocket_manager": {"status": ws_status, "last_error": ws_error},
                "store": {"status": store_status, "last_error": store_error},
            },
        }
