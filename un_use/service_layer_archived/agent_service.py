# -*- coding: utf-8 -*-
"""
service/agent_service.py
────────────────────────
AgentService：DialogMesh 核心服务类。

管理会话生命周期、消息处理、澄清提交、历史查询、状态查询、会话关闭。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict

from service.models import Session, TurnRecord
from service.async_session_manager import AsyncSessionManager
from service.orchestrator import DialogMeshOrchestrator
from service.protocol.fsm import (
    ClarificationFSM,
    ClarificationFSMContext,
    ClarificationEvent,
    ClarificationState,
)
from service.protocol.events import EventBuilder
from service.protocol.schemas import (
    CreateSessionResponse,
    SendMessageRequest,
    SendMessageResponse,
    ClarifyRequest,
    ClarifyResponse,
    HistoryResponse,
    MessageRecord,
    SessionStatusResponse,
    IntentResult,
    ClarificationPayload,
    CognitiveProfilePayload,
    EntityPayload,
)
from service.protocol.ui_schema import (
    ClarificationUISchema,
    UIComponent,
    UIOption,
    UIValidation,
    TEXT_INPUT,
    SINGLE_SELECT,
    MULTI_SELECT,
    SHOW_INFO,
)
from service.protocol.task_graph import (
    TaskGraphPayload,
    TaskNodePayload,
    TaskEdgePayload,
    NodeStatus,
    EdgeType,
    NodeType,
)
from core.agent.v3_common.models import AmbiguityType, TaskStatus, DependencyType

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 补充模型（schemas.py 中未定义）
# ═══════════════════════════════════════════════════════════════════════════════

class _CompatModel(BaseModel):
    def dict(self, **kwargs) -> Dict[str, Any]:
        return self.model_dump(**kwargs)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class CloseSessionResponse(_CompatModel):
    """POST /v1/session/{id}/close 响应体。"""

    session_id: str = Field(..., description="会话 ID")
    closed_at: float = Field(default_factory=time.time, description="关闭时间")
    final_turn_count: int = Field(0, description="最终轮次", ge=0)


# ═══════════════════════════════════════════════════════════════════════════════
# AgentService
# ═══════════════════════════════════════════════════════════════════════════════

class DialogMeshAgentService:
    """
    DialogMesh AgentService。

    管理会话的完整生命周期：
      - 创建会话（create_session）
      - 处理消息（process_message）
      - 提交澄清（submit_clarification）
      - 查询历史（get_session_history）
      - 查询状态（get_session_status）
      - 关闭会话（close_session）
    """

    def __init__(
        self,
        session_manager: AsyncSessionManager,
        orchestrator: DialogMeshOrchestrator,
        event_callback: Optional[Callable[[str, Any], None]] = None,
    ):
        self._session_manager = session_manager
        self._orchestrator = orchestrator
        self._event_callback = event_callback
        self._logger = logging.getLogger(self.__class__.__name__)

        # 每个 session 的串行处理锁
        self._session_locks: Dict[str, asyncio.Lock] = {}
        # FSM 内存缓存
        self._fsm_cache: Dict[str, ClarificationFSM] = {}

    # ── 锁管理 ─────────────────────────────────────────────────────────

    def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        """获取或创建 session 的串行锁。"""
        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
        return self._session_locks[session_id]

    # ── FSM 管理 ───────────────────────────────────────────────────────

    def _get_or_create_fsm(self, session: Session) -> ClarificationFSM:
        """获取或创建 session 的 FSM。"""
        fsm = self._fsm_cache.get(session.session_id)
        if fsm is None:
            if session.parse_context and "fsm" in session.parse_context:
                try:
                    fsm_data = session.parse_context["fsm"]
                    fsm = ClarificationFSM.from_dict(fsm_data)
                except Exception as exc:
                    self._logger.warning(
                        "Failed to restore FSM for session=%s: %s", session.session_id, exc
                    )
                    fsm = ClarificationFSM(
                        ClarificationFSMContext(session_id=session.session_id)
                    )
            else:
                fsm = ClarificationFSM(
                    ClarificationFSMContext(session_id=session.session_id)
                )
            self._fsm_cache[session.session_id] = fsm
        return fsm

    def _save_fsm(self, session: Session, fsm: ClarificationFSM) -> None:
        """保存 FSM 状态到 session。"""
        self._fsm_cache[session.session_id] = fsm
        if session.parse_context is None:
            session.parse_context = {}
        session.parse_context["fsm"] = fsm.to_dict()

    # ── 公共 API ───────────────────────────────────────────────────────

    async def create_session(
        self,
        tenant_id: str = "default",
        user_id: Optional[str] = None,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> CreateSessionResponse:
        """
        创建新会话。

        1. 调用 session_manager.create_session()
        2. 初始化 FSM
        3. 返回 session_id + ws_url
        """
        try:
            session = await self._session_manager.create_session(
                tenant_id=tenant_id,
                user_id=user_id,
            )

            # 初始化 FSM
            fsm = ClarificationFSM(
                ClarificationFSMContext(session_id=session.session_id)
            )
            self._fsm_cache[session.session_id] = fsm
            self._save_fsm(session, fsm)

            # 保存 initial_context
            if initial_context:
                if session.parse_context is None:
                    session.parse_context = {}
                session.parse_context["initial_context"] = initial_context

            await self._session_manager.update_session(session)

            self._logger.info("Session created: %s", session.session_id)

            # 构建 WebSocket URL
            ws_url = f"/ws/v1/session/{session.session_id}"

            return CreateSessionResponse(
                session_id=session.session_id,
                created_at=session.created_at,
                ws_url=ws_url,
                capabilities=["text", "structured"],
                session_ttl_seconds=3600,
            )

        except Exception as exc:
            self._logger.exception("Failed to create session")
            raise

    async def process_message(
        self,
        session_id: str,
        request: SendMessageRequest,
    ) -> SendMessageResponse:
        """
        处理用户消息。

        1. 获取会话
        2. 获取/恢复 FSM
        3. 根据 FSM 状态决定行为
        4. 保存 TurnRecord
        5. 返回 SendMessageResponse
        """
        async with self._get_session_lock(session_id):
            start_time = time.time()

            try:
                # 获取会话
                session = await self._session_manager.get_session(session_id)
                if session is None:
                    self._logger.warning("Session not found: %s", session_id)
                    return SendMessageResponse(
                        message_id=request.message_id,
                        status="error",
                        trace_log=["Session not found"],
                        latency_ms=0.0,
                    )

                session.touch()

                # 获取 FSM
                fsm = self._get_or_create_fsm(session)

                # 检查 FSM 是否超时
                if fsm.is_expired():
                    old_state = fsm.context.current_state
                    fsm.handle_event(ClarificationEvent.TIMEOUT.value)
                    self._logger.info(
                        "FSM timeout for session=%s: %s -> %s",
                        session_id, old_state, fsm.context.current_state,
                    )

                current_state = fsm.context.current_state

                # 状态转换：START / RE_PARSING / ACTIONABLE -> PARSING
                if current_state in (
                    ClarificationState.START,
                    ClarificationState.RE_PARSING,
                    ClarificationState.ACTIONABLE,
                ):
                    fsm.handle_event(ClarificationEvent.USER_MESSAGE.value)

                # 记录用户输入 TurnRecord
                turn_record = TurnRecord(
                    sequence=session.turn_count,
                    timestamp=time.time(),
                    role="user",
                    content=request.content or "",
                    modality=request.modality,
                )

                # 调用编排器
                self._logger.info("Processing message for session=%s", session_id)
                orchestrator_result = await self._orchestrator.process(request, session)

                parse_result = orchestrator_result["parse_result"]
                pcr_latency = orchestrator_result.get("pcr_latency_ms", 0.0)
                parser_latency = orchestrator_result.get("parser_latency_ms", 0.0)

                # 更新 turn_record
                turn_record.intent_result = parse_result.intent.to_dict()
                turn_record.pcr_latency_ms = pcr_latency
                turn_record.parser_latency_ms = parser_latency

                # 检查歧义
                has_ambiguity = parse_result and not parse_result.is_actionable

                if has_ambiguity:
                    # 有歧义 → CLARIFYING
                    fsm.handle_event(ClarificationEvent.PARSE_COMPLETE_HAS_AMBIGUITY.value)
                    self._save_fsm(session, fsm)

                    # 构建 ClarificationPayload
                    ui_schema = self._build_ui_schema_from_ambiguities(parse_result.intent.ambiguities)
                    clarification_payload = ClarificationPayload(
                        message=parse_result.clarification_message or "需要更多信息",
                        ui_schema=ui_schema,
                        suggestions=parse_result.suggestions,
                        timeout_seconds=fsm.context.timeout_seconds,
                        required=True,
                    )

                    # 保存 pending clarification
                    session.pending_clarification = clarification_payload.clarification_id
                    session.state = "clarifying"

                    # 保存 turn record
                    turn_record.clarification = clarification_payload.dict()
                    await self._session_manager.save_turn(session_id, turn_record)
                    await self._session_manager.update_session(session)

                    # 推送事件
                    self._emit_event(
                        session_id,
                        "clarification",
                        clarification_payload.dict(),
                    )
                    self._emit_event(
                        session_id,
                        "state_change",
                        {"old_state": current_state, "new_state": fsm.context.current_state},
                    )

                    latency = (time.time() - start_time) * 1000
                    return SendMessageResponse(
                        message_id=request.message_id,
                        status="needs_clarification",
                        clarification=clarification_payload,
                        trace_log=parse_result.trace_log,
                        latency_ms=latency,
                    )

                else:
                    # 无歧义 → ACTIONABLE
                    fsm.handle_event(ClarificationEvent.PARSE_COMPLETE_NO_AMBIGUITY.value)
                    self._save_fsm(session, fsm)

                    # 构建 IntentResult
                    pcr_output = orchestrator_result.get("pcr_output")
                    expectation = pcr_output.expectation if pcr_output else "UNKNOWN"
                    intent_result = self._build_intent_result_payload(parse_result, expectation)

                    # 保存 turn record
                    await self._session_manager.save_turn(session_id, turn_record)

                    # 更新 session
                    session.state = "active"
                    session.pending_clarification = None
                    await self._session_manager.update_session(session)

                    # 推送事件
                    self._emit_event(
                        session_id,
                        "intent_result",
                        intent_result.dict(),
                    )
                    self._emit_event(
                        session_id,
                        "state_change",
                        {"old_state": current_state, "new_state": fsm.context.current_state},
                    )

                    latency = (time.time() - start_time) * 1000
                    return SendMessageResponse(
                        message_id=request.message_id,
                        status="actionable",
                        intent_result=intent_result,
                        trace_log=parse_result.trace_log,
                        latency_ms=latency,
                    )

            except Exception as exc:
                self._logger.exception("process_message failed for session=%s", session_id)
                self._emit_event(
                    session_id,
                    "error",
                    {"code": "INTERNAL_ERROR", "message": str(exc)},
                )
                return SendMessageResponse(
                    message_id=request.message_id,
                    status="error",
                    trace_log=[f"Internal error: {exc}"],
                    latency_ms=(time.time() - start_time) * 1000,
                )

    async def submit_clarification(
        self,
        session_id: str,
        request: ClarifyRequest,
    ) -> ClarifyResponse:
        """
        提交澄清回复。

        1. 获取会话和 FSM
        2. FSM 转换：CLARIFYING → RE_PARSING
        3. 将澄清回复合并到原查询，重新调用 orchestrator.process()
        4. 检查是否还有歧义
        5. 返回 ClarifyResponse
        """
        async with self._get_session_lock(session_id):
            start_time = time.time()

            try:
                # 获取会话
                session = await self._session_manager.get_session(session_id)
                if session is None:
                    return ClarifyResponse(
                        status="expired",
                        trace_log=["Session not found"],
                    )

                session.touch()

                # 获取 FSM
                fsm = self._get_or_create_fsm(session)

                # 检查状态
                if fsm.context.current_state != ClarificationState.CLARIFYING:
                    self._logger.warning(
                        "submit_clarification called but state=%s", fsm.context.current_state
                    )
                    return ClarifyResponse(
                        status="expired",
                        trace_log=[f"Invalid state: {fsm.context.current_state}"],
                    )

                # 检查是否还能继续澄清
                if not fsm.can_clarify_more():
                    fsm.handle_event(ClarificationEvent.TIMEOUT.value)
                    self._save_fsm(session, fsm)
                    return ClarifyResponse(
                        status="expired",
                        trace_log=["Max clarifications reached"],
                    )

                # FSM 转换：CLARIFYING → RE_PARSING
                fsm.handle_event(ClarificationEvent.USER_CLARIFY.value)
                self._save_fsm(session, fsm)

                # 获取原查询
                original_query = ""
                if session.history:
                    for turn in reversed(session.history):
                        if turn.role == "user":
                            original_query = turn.content
                            break

                # 构建澄清回复
                clarification_text = ""
                if request.free_text:
                    clarification_text = request.free_text
                elif request.selected_option is not None:
                    # 从最近一条 clarification 中获取选项
                    for turn in reversed(session.history):
                        if turn.clarification and turn.clarification.get("suggestions"):
                            suggestions = turn.clarification["suggestions"]
                            if 0 <= request.selected_option < len(suggestions):
                                clarification_text = suggestions[request.selected_option]
                            break

                # 合并查询
                merged_query = f"{original_query} [{clarification_text}]"

                # 构建重新解析请求
                reparse_request = SendMessageRequest(
                    message_id=request.clarification_id,
                    content=merged_query,
                    modality="text",
                )

                # 重新调用 orchestrator
                self._logger.info("Re-parsing clarification for session=%s", session_id)
                orchestrator_result = await self._orchestrator.process(reparse_request, session)

                parse_result = orchestrator_result["parse_result"]
                pcr_output = orchestrator_result.get("pcr_output")
                expectation = pcr_output.expectation if pcr_output else "UNKNOWN"

                # 检查是否还有歧义
                has_ambiguity = parse_result and not parse_result.is_actionable

                if has_ambiguity:
                    # 仍有歧义
                    fsm.handle_event(ClarificationEvent.REPARSE_COMPLETE_HAS_AMBIGUITY.value)
                    self._save_fsm(session, fsm)

                    ui_schema = self._build_ui_schema_from_ambiguities(parse_result.intent.ambiguities)
                    next_clarification = ClarificationPayload(
                        message=parse_result.clarification_message or "仍需要更多信息",
                        ui_schema=ui_schema,
                        suggestions=parse_result.suggestions,
                        timeout_seconds=fsm.context.timeout_seconds,
                        required=True,
                    )

                    session.pending_clarification = next_clarification.clarification_id
                    session.state = "clarifying"
                    await self._session_manager.update_session(session)

                    # 推送事件
                    self._emit_event(
                        session_id,
                        "clarification",
                        next_clarification.dict(),
                    )

                    latency = (time.time() - start_time) * 1000
                    return ClarifyResponse(
                        status="needs_more_clarification",
                        next_clarification=next_clarification,
                        trace_log=parse_result.trace_log,
                    )

                else:
                    # 已消解
                    fsm.handle_event(ClarificationEvent.REPARSE_COMPLETE_NO_AMBIGUITY.value)
                    self._save_fsm(session, fsm)

                    intent_result = self._build_intent_result_payload(parse_result, expectation)

                    session.pending_clarification = None
                    session.state = "active"
                    await self._session_manager.update_session(session)

                    # 推送事件
                    self._emit_event(
                        session_id,
                        "intent_result",
                        intent_result.dict(),
                    )

                    latency = (time.time() - start_time) * 1000
                    return ClarifyResponse(
                        status="resolved",
                        intent_result=intent_result,
                        trace_log=parse_result.trace_log,
                    )

            except Exception as exc:
                self._logger.exception("submit_clarification failed for session=%s", session_id)
                return ClarifyResponse(
                    status="expired",
                    trace_log=[f"Error: {exc}"],
                )

    async def get_session_history(
        self,
        session_id: str,
        limit: int = 50,
        before_seq: Optional[int] = None,
    ) -> HistoryResponse:
        """获取会话历史。"""
        try:
            session = await self._session_manager.get_session(session_id)
            if session is None:
                return HistoryResponse(
                    session_id=session_id,
                    messages=[],
                    has_more=False,
                )

            messages: List[MessageRecord] = []
            history = session.history

            # 过滤
            if before_seq is not None:
                history = [h for h in history if h.sequence < before_seq]

            # 取最近 limit 条
            selected = history[-limit:] if len(history) > limit else history

            for turn in selected:
                msg = MessageRecord(
                    sequence=turn.sequence,
                    role=turn.role,
                    content=turn.content,
                    latency_ms=turn.latency_ms,
                    timestamp=turn.timestamp,
                )
                # 尝试设置 intent_result（跳过不兼容的 dict）
                if turn.intent_result:
                    try:
                        msg.intent_result = turn.intent_result
                    except Exception:
                        pass
                if turn.clarification:
                    try:
                        msg.clarification = turn.clarification
                    except Exception:
                        pass
                messages.append(msg)

            has_more = len(history) > limit

            return HistoryResponse(
                session_id=session_id,
                messages=messages,
                has_more=has_more,
            )

        except Exception as exc:
            self._logger.exception("get_session_history failed for session=%s", session_id)
            return HistoryResponse(
                session_id=session_id,
                messages=[],
                has_more=False,
            )

    async def get_session_status(self, session_id: str) -> SessionStatusResponse:
        """获取会话状态 + FSM 状态 + 认知画像。"""
        try:
            session = await self._session_manager.get_session(session_id)
            if session is None:
                return SessionStatusResponse(
                    session_id=session_id,
                    state="expired",
                    current_turn=0,
                )

            fsm = self._get_or_create_fsm(session)

            # 认知画像
            cog_payload = None
            if session.cognitive_profile:
                cog_payload = CognitiveProfilePayload(
                    metacognition=session.cognitive_profile.metacognition,
                    divergence=session.cognitive_profile.divergence,
                    tracking_depth=session.cognitive_profile.tracking_depth,
                    stability=session.cognitive_profile.stability,
                    confidence=session.cognitive_profile.confidence,
                )

            # FSM 状态快照
            fsm_snapshot = {
                "state": fsm.context.current_state,
                "clarification_count": fsm.context.clarification_count,
                "max_clarifications": fsm.context.max_clarifications,
                "can_clarify_more": fsm.can_clarify_more(),
                "is_expired": fsm.is_expired(),
            }

            return SessionStatusResponse(
                session_id=session_id,
                state=session.state,
                current_turn=session.turn_count,
                pending_clarification=session.pending_clarification,
                cognitive_profile=cog_payload,
                last_activity_at=session.last_activity_at,
                expires_at=session.expires_at,
                fsm=fsm_snapshot,
            )

        except Exception as exc:
            self._logger.exception("get_session_status failed for session=%s", session_id)
            return SessionStatusResponse(
                session_id=session_id,
                state="error",
                current_turn=0,
            )

    async def close_session(self, session_id: str) -> CloseSessionResponse:
        """关闭会话，持久化，推送 session_close 事件。"""
        async with self._get_session_lock(session_id):
            try:
                # 获取会话以记录最终轮次
                session = await self._session_manager.get_session(session_id)
                final_turn_count = session.turn_count if session else 0

                # 清理 FSM 缓存和锁
                self._fsm_cache.pop(session_id, None)
                self._session_locks.pop(session_id, None)

                # 关闭会话
                summary = await self._session_manager.close_session(session_id)

                # 推送 session_close 事件
                self._emit_event(
                    session_id,
                    "session_close",
                    {"session_id": session_id, "reason": "user_closed"},
                )

                return CloseSessionResponse(
                    session_id=session_id,
                    closed_at=time.time(),
                    final_turn_count=summary.turn_count if summary else final_turn_count,
                )

            except Exception as exc:
                self._logger.exception("close_session failed for session=%s", session_id)
                return CloseSessionResponse(
                    session_id=session_id,
                    closed_at=time.time(),
                    final_turn_count=0,
                )

    # ── 内部方法 ───────────────────────────────────────────────────────

    def _emit_event(
        self,
        session_id: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> None:
        """通过 event_callback 推送 WebSocket 事件。"""
        if self._event_callback is not None:
            try:
                event = EventBuilder._build(event_type, session_id, payload)
                self._event_callback(session_id, event)
            except Exception as exc:
                self._logger.warning("Event callback failed: %s", exc)

    def _build_ui_schema_from_ambiguities(
        self,
        ambiguities,
    ) -> ClarificationUISchema:
        """
        根据歧义类型自动生成 UI 组件：

        - MISSING_ENTITY → text_input
        - AMBIGUOUS_ENTITY → single_select
        - CONFLICTING_ENTITIES → multi_select
        - VAGUE_SCOPE → text_input
        - UNSUPPORTED_OPERATION → show_info
        - MULTIPLE_INTENTS → single_select
        """
        components: List[UIComponent] = []

        for amb in ambiguities:
            amb_type = amb.type

            if amb_type == AmbiguityType.MISSING_ENTITY:
                components.append(UIComponent(
                    type=TEXT_INPUT,
                    id=f"amb_{amb_type.value}_input",
                    label=amb.description,
                    placeholder="请输入缺失的信息",
                    validation=UIValidation(
                        type="required",
                        error_message="此项为必填",
                    ),
                ))

            elif amb_type == AmbiguityType.AMBIGUOUS_ENTITY:
                options = [
                    UIOption(value=sug, display_text=sug)
                    for sug in amb.suggestions
                ] if amb.suggestions else []
                components.append(UIComponent(
                    type=SINGLE_SELECT,
                    id=f"amb_{amb_type.value}_select",
                    label=amb.description,
                    options=options,
                ))

            elif amb_type == AmbiguityType.CONFLICTING_ENTITIES:
                options = [
                    UIOption(value=sug, display_text=sug)
                    for sug in amb.suggestions
                ] if amb.suggestions else []
                components.append(UIComponent(
                    type=MULTI_SELECT,
                    id=f"amb_{amb_type.value}_multi",
                    label=amb.description,
                    options=options,
                ))

            elif amb_type == AmbiguityType.VAGUE_SCOPE:
                components.append(UIComponent(
                    type=TEXT_INPUT,
                    id=f"amb_{amb_type.value}_scope",
                    label=amb.description,
                    placeholder="请明确范围",
                ))

            elif amb_type == AmbiguityType.UNSUPPORTED_OPERATION:
                components.append(UIComponent(
                    type=SHOW_INFO,
                    id=f"amb_{amb_type.value}_info",
                    label=amb.description,
                ))

            elif amb_type == AmbiguityType.MULTIPLE_INTENTS:
                options = [
                    UIOption(value=sug, display_text=sug)
                    for sug in amb.suggestions
                ] if amb.suggestions else []
                components.append(UIComponent(
                    type=SINGLE_SELECT,
                    id=f"amb_{amb_type.value}_intent",
                    label=amb.description,
                    options=options,
                ))

        return ClarificationUISchema(
            components=components,
            allow_free_text=True,
            allow_skip=False,
        )

    def _build_intent_result_payload(
        self,
        parse_result,
        expectation: str = "UNKNOWN",
    ) -> IntentResult:
        """构建 IntentResult Pydantic 模型。"""
        # 实体
        entities = [
            EntityPayload(
                type=e.type.value,
                value=e.value,
                raw_text=e.raw_text,
                confidence=e.confidence,
            )
            for e in parse_result.intent.entities
        ]

        # TaskGraph
        task_graph_payload = None
        if parse_result.task_graph:
            nodes = []
            for node_id, node in parse_result.task_graph.nodes.items():
                status_map = {
                    TaskStatus.PENDING: NodeStatus.PENDING,
                    TaskStatus.RUNNING: NodeStatus.RUNNING,
                    TaskStatus.SUCCESS: NodeStatus.SUCCESS,
                    TaskStatus.FAILED: NodeStatus.FAILED,
                    TaskStatus.BLOCKED: NodeStatus.BLOCKED,
                    TaskStatus.CANCELLED: NodeStatus.SKIPPED,
                    TaskStatus.SKIPPED: NodeStatus.SKIPPED,
                    TaskStatus.NEEDS_CLARIFICATION: NodeStatus.PENDING,
                }
                node_type_map = {
                    "first_scan": NodeType.SCAN,
                    "next_scan": NodeType.SCAN,
                    "read_memory": NodeType.READ,
                    "write_memory": NodeType.WRITE,
                    "disassemble": NodeType.ANALYZE,
                    "decompile": NodeType.ANALYZE,
                    "analyze_protection": NodeType.ANALYZE,
                    "set_breakpoint": NodeType.ANALYZE,
                    "ask_user": NodeType.ASK_USER,
                    "finish": NodeType.ASK_USER,
                }
                nodes.append(TaskNodePayload(
                    node_id=node.id,
                    name=node.name or node_id,
                    description=node.description,
                    status=status_map.get(node.status, NodeStatus.PENDING),
                    node_type=node_type_map.get(node.tool_name or "", NodeType.ANALYZE),
                    is_destructive=bool(node.tags and "destructive" in node.tags),
                    metadata=node.metadata,
                ))

            edges = []
            for edge in parse_result.task_graph.edges:
                edge_type_map = {
                    DependencyType.SEQUENTIAL: EdgeType.SEQUENTIAL,
                    DependencyType.CONDITIONAL: EdgeType.CONDITIONAL,
                    DependencyType.ITERATIVE: EdgeType.SEQUENTIAL,
                    DependencyType.PARALLEL: EdgeType.SEQUENTIAL,
                    DependencyType.FALLBACK: EdgeType.FALLBACK,
                }
                edges.append(TaskEdgePayload(
                    source_id=edge.source_id,
                    target_id=edge.target_id,
                    edge_type=edge_type_map.get(edge.dep_type, EdgeType.SEQUENTIAL),
                    label=edge.condition,
                ))

            task_graph_payload = TaskGraphPayload(
                task_graph_id=parse_result.task_graph.intent_id or "unknown",
                nodes=nodes,
                edges=edges,
                overall_status="pending",
            )

        # 认知画像
        cog = CognitiveProfilePayload(
            metacognition=0.0,
            divergence=0.0,
            tracking_depth=0.0,
            stability=0.0,
            confidence=parse_result.intent.confidence,
        )

        return IntentResult(
            expectation=expectation,
            task_graph=task_graph_payload,
            entities=entities,
            cognitive_profile=cog,
        )

    def _build_task_graph_payload(self, task_graph) -> TaskGraphPayload:
        """构建 TaskGraphPayload Pydantic 模型（从 TaskGraph 对象）。"""
        if not task_graph:
            return TaskGraphPayload(task_graph_id="empty")

        nodes = []
        for node_id, node in task_graph.nodes.items():
            status_map = {
                TaskStatus.PENDING: NodeStatus.PENDING,
                TaskStatus.RUNNING: NodeStatus.RUNNING,
                TaskStatus.SUCCESS: NodeStatus.SUCCESS,
                TaskStatus.FAILED: NodeStatus.FAILED,
                TaskStatus.BLOCKED: NodeStatus.BLOCKED,
                TaskStatus.CANCELLED: NodeStatus.SKIPPED,
                TaskStatus.SKIPPED: NodeStatus.SKIPPED,
                TaskStatus.NEEDS_CLARIFICATION: NodeStatus.PENDING,
            }
            node_type_map = {
                "first_scan": NodeType.SCAN,
                "next_scan": NodeType.SCAN,
                "read_memory": NodeType.READ,
                "write_memory": NodeType.WRITE,
                "disassemble": NodeType.ANALYZE,
                "ask_user": NodeType.ASK_USER,
                "finish": NodeType.ASK_USER,
            }
            nodes.append(TaskNodePayload(
                node_id=node.id,
                name=node.name or node_id,
                description=node.description,
                status=status_map.get(node.status, NodeStatus.PENDING),
                node_type=node_type_map.get(node.tool_name or "", NodeType.ANALYZE),
                is_destructive=bool(node.tags and "destructive" in node.tags),
                metadata=node.metadata,
            ))

        edges = []
        for edge in task_graph.edges:
            edge_type_map = {
                DependencyType.SEQUENTIAL: EdgeType.SEQUENTIAL,
                DependencyType.CONDITIONAL: EdgeType.CONDITIONAL,
                DependencyType.ITERATIVE: EdgeType.SEQUENTIAL,
                DependencyType.PARALLEL: EdgeType.SEQUENTIAL,
                DependencyType.FALLBACK: EdgeType.FALLBACK,
            }
            edges.append(TaskEdgePayload(
                source_id=edge.source_id,
                target_id=edge.target_id,
                edge_type=edge_type_map.get(edge.dep_type, EdgeType.SEQUENTIAL),
                label=edge.condition,
            ))

        return TaskGraphPayload(
            task_graph_id=task_graph.intent_id or "unknown",
            nodes=nodes,
            edges=edges,
            overall_status="pending",
        )
