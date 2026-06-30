# -*- coding: utf-8 -*-
"""
core/agent/service/api.py
─────────────────────────
FastAPI 服务层路由（v2.4 服务层新增）。

设计原则：
  - FastAPI 是可选依赖（pip install fastapi uvicorn）
  - 如果 FastAPI 未安装，import 时抛 ImportError 提示
  - 所有业务逻辑在 AgentService 中，API 层只做参数校验和响应包装
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

# 可选导入 FastAPI
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    FastAPI = None
    WebSocket = None
    WebSocketDisconnect = None
    HTTPException = Exception
    JSONResponse = None
    BaseModel = object
    Field = lambda *a, **k: None

from core.agent.frontend import EventBuilder, EventSerializer, WebSocketEvent, EventType

from core.agent.service.agent_service import AgentService
from core.agent.service.models import (
    Session, TurnRecord, IntentResult, ClarificationPayload, ErrorPayload,
    ParseProgressEvent, SessionSummary,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 请求/响应模型（仅在 FastAPI 可用时定义）
# ═══════════════════════════════════════════════════════════════════════════════

if HAS_FASTAPI:

    class CreateSessionRequest(BaseModel):
        tenant_id: str = "default"
        user_id: Optional[str] = None
        initial_context: Optional[Dict[str, Any]] = None
        preferred_language: str = "zh-CN"
        user_type_hint: Optional[str] = None  # "expert" | "novice" | None (P1 冷启动策略)

    class CreateSessionResponse(BaseModel):
        session_id: str
        created_at: float
        ws_url: str
        capabilities: List[str] = ["text", "structured"]
        session_ttl_seconds: int = 3600

    class SendMessageRequest(BaseModel):
        message_id: str = Field(default_factory=lambda: "msg_" + str(int(time.time() * 1000)))
        modality: str = "text"
        content: str
        structured_payload: Optional[Dict[str, Any]] = None
        attachments: Optional[List[Dict[str, Any]]] = None
        timestamp: Optional[float] = None
        client_sequence: int = 0

    class SendMessageResponse(BaseModel):
        message_id: str
        status: str  # "actionable" | "needs_clarification" | "error" | "processing"
        intent_result: Optional[Dict[str, Any]] = None
        clarification: Optional[Dict[str, Any]] = None
        trace_log: List[str] = []
        latency_ms: float = 0.0

    class ClarifyRequest(BaseModel):
        clarification_id: str
        selected_option: Optional[int] = None
        free_text: Optional[str] = None

    class ClarifyResponse(BaseModel):
        status: str
        intent_result: Optional[Dict[str, Any]] = None
        clarification: Optional[Dict[str, Any]] = None
        error: Optional[Dict[str, Any]] = None

    class HistoryResponse(BaseModel):
        session_id: str
        messages: List[Dict[str, Any]]
        has_more: bool = False

    class SessionStatusResponse(BaseModel):
        session_id: str
        state: str
        current_turn: int
        pending_clarification: Optional[str] = None
        last_activity_at: float
        expires_at: float
        fsm: Optional[Dict[str, Any]] = None

    class HealthResponse(BaseModel):
        status: str
        version: str = "2.4.0"
        components: Dict[str, Any]

    class CloseSessionResponse(BaseModel):
        session_id: str
        closed_at: float
        summary: Dict[str, Any]
        persisted: bool

    class ErrorResponse(BaseModel):
        code: str
        message: str
        retryable: bool = False
        retry_after_ms: Optional[int] = None

else:
    # 占位类，防止 NameError（虽然不会实际使用）
    CreateSessionRequest = None
    CreateSessionResponse = None
    SendMessageRequest = None
    SendMessageResponse = None
    ClarifyRequest = None
    ClarifyResponse = None
    HistoryResponse = None
    SessionStatusResponse = None
    HealthResponse = None
    CloseSessionResponse = None
    ErrorResponse = None


# ═══════════════════════════════════════════════════════════════════════════════
# 创建 FastAPI 应用
# ═══════════════════════════════════════════════════════════════════════════════

def create_app(agent_service: AgentService) -> "FastAPI":
    """
    创建 FastAPI 应用实例。
    需要传入已初始化的 AgentService。
    """
    if not HAS_FASTAPI:
        raise ImportError(
            "FastAPI is required for the service layer. "
            "Install with: pip install fastapi uvicorn"
        )

    app = FastAPI(
        title="Cognitive Router Agent Service",
        description="MemoryGraph Intent Recognition & Clarification Service",
        version="2.4.0",
    )

    # 存储 WebSocket 连接（仅内存，session_id -> List[WebSocket]）
    ws_connections: Dict[str, List[WebSocket]] = {}

    async def broadcast_to_session(session_id: str, event: WebSocketEvent) -> None:
        """向会话的所有 WebSocket 连接广播标准事件。"""
        conns = ws_connections.get(session_id, [])
        dead = []
        raw = EventSerializer.serialize(event)
        for ws in conns:
            try:
                await ws.send_text(raw)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conns.remove(ws)

    # 为 AgentService 创建事件回调（同步桥接 -> 主事件循环）
    import asyncio
    _main_loop = asyncio.get_event_loop()

    def event_callback(session_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        """同步回调 -> 异步广播（通过主事件循环线程安全调度）。"""
        try:
            if event_type == "intent_result":
                event = EventBuilder.intent_result(
                    session_id=session_id,
                    message_id=payload.get("message_id", ""),
                    status=payload.get("status", "unknown"),
                    intent_result=payload.get("intent_result"),
                    latency_ms=payload.get("latency_ms", 0.0),
                )
            elif event_type == "clarification":
                event = EventBuilder.clarification(
                    session_id=session_id,
                    clarification_id=payload.get("clarification_id", ""),
                    message=payload.get("message", ""),
                    ui_schema=payload.get("ui_schema"),
                )
            elif event_type == "progress":
                event = EventBuilder.progress(
                    session_id=session_id,
                    message_id=payload.get("message_id", ""),
                    stage=payload.get("stage", "unknown"),
                    status=payload.get("status", "unknown"),
                    detail=payload.get("detail"),
                    elapsed_ms=payload.get("elapsed_ms", 0.0),
                )
            elif event_type == "error":
                event = EventBuilder.error(
                    session_id=session_id,
                    code=payload.get("code", "INTERNAL_ERROR"),
                    message=payload.get("message", ""),
                    retryable=payload.get("retryable", False),
                    retry_after_ms=payload.get("retry_after_ms"),
                )
            elif event_type == "state_change":
                event = EventBuilder.state_change(
                    session_id=session_id,
                    old_state=payload.get("old_state", ""),
                    new_state=payload.get("new_state", ""),
                    event=payload.get("event", ""),
                    description=payload.get("description", ""),
                )
            elif event_type == "taskgraph_update":
                event = EventBuilder.taskgraph_update(
                    session_id=session_id,
                    task_graph_id=payload.get("task_graph_id", ""),
                    update_type=payload.get("update_type", "node_status_change"),
                    node_id=payload.get("node_id"),
                    new_status=payload.get("new_status"),
                    result_summary=payload.get("result_summary"),
                    overall_status=payload.get("overall_status", "running"),
                    overall_progress_pct=payload.get("overall_progress_pct", 0.0),
                )
            else:
                event = WebSocketEvent(
                    event_type=event_type,
                    session_id=session_id,
                    payload=payload,
                    timestamp=time.time(),
                )
            # 线程安全调度到主事件循环
            try:
                asyncio.run_coroutine_threadsafe(
                    broadcast_to_session(session_id, event), _main_loop
                )
            except Exception:
                pass  # 事件循环不可用时静默丢弃
        except Exception as exc:
            logger = logging.getLogger(__name__)
            logger.warning("Event callback failed: %s", exc)

    # 将回调绑定到 AgentService
    agent_service.event_callback = event_callback

    # ── 会话管理 ──────────────────────────────────────────────────────────

    @app.post("/v1/session/create", response_model=CreateSessionResponse)
    async def create_session(req: CreateSessionRequest):
        sess = agent_service.create_session(
            tenant_id=req.tenant_id,
            user_id=req.user_id,
            initial_context=req.initial_context,
            user_type_hint=req.user_type_hint,
        )
        return CreateSessionResponse(
            session_id=sess.session_id,
            created_at=sess.created_at,
            ws_url=f"/v1/ws/{sess.session_id}",
            capabilities=["text", "structured"],
            session_ttl_seconds=3600,
        )

    @app.post("/v1/session/{session_id}/close", response_model=CloseSessionResponse)
    async def close_session(session_id: str):
        summary = agent_service.close_session(session_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return CloseSessionResponse(
            session_id=summary.session_id,
            closed_at=summary.closed_at,
            summary={
                "total_turns": summary.total_turns,
                "final_state": summary.final_state,
            },
            persisted=summary.persisted,
        )

    # ── 消息解析 ──────────────────────────────────────────────────────────

    @app.post("/v1/session/{session_id}/message", response_model=SendMessageResponse)
    async def send_message(session_id: str, req: SendMessageRequest):
        start_ms = time.time() * 1000
        status, intent_result, clarification, error, trace = agent_service.process_message(
            session_id=session_id,
            content=req.content,
            modality=req.modality,
            message_id=req.message_id,
        )
        latency_ms = (time.time() * 1000) - start_ms

        # 补充 HTTP 响应中的 latency（AgentService 的 event_callback 已推送 WebSocket 事件）
        if error is not None:
            return SendMessageResponse(
                message_id=req.message_id,
                status="error",
                error={
                    "code": error.code,
                    "message": error.message,
                    "retryable": error.retryable,
                    "retry_after_ms": error.retry_after_ms,
                },
                trace_log=trace,
                latency_ms=latency_ms,
            )

        return SendMessageResponse(
            message_id=req.message_id,
            status=status,
            intent_result=intent_result.to_dict() if intent_result else None,
            clarification=clarification.to_dict() if clarification else None,
            trace_log=trace,
            latency_ms=latency_ms,
        )

    # ── 澄清回复 ──────────────────────────────────────────────────────────

    @app.post("/v1/session/{session_id}/clarify", response_model=ClarifyResponse)
    async def submit_clarification(session_id: str, req: ClarifyRequest):
        status, intent_result, clarification, error = agent_service.submit_clarification(
            session_id=session_id,
            clarification_id=req.clarification_id,
            selected_option=req.selected_option,
            free_text=req.free_text,
        )
        if error is not None:
            return ClarifyResponse(
                status="error",
                error={
                    "code": error.code,
                    "message": error.message,
                    "retryable": error.retryable,
                },
            )
        return ClarifyResponse(
            status=status,
            intent_result=intent_result.to_dict() if intent_result else None,
            clarification=clarification.to_dict() if clarification else None,
        )

    # ── 历史查询 ──────────────────────────────────────────────────────────

    @app.get("/v1/session/{session_id}/history", response_model=HistoryResponse)
    async def get_history(session_id: str, limit: int = 50):
        history = agent_service.get_history(session_id, limit=limit)
        return HistoryResponse(
            session_id=session_id,
            messages=[h.to_dict() for h in history],
            has_more=len(history) >= limit,
        )

    @app.get("/v1/session/{session_id}/status", response_model=SessionStatusResponse)
    async def get_status(session_id: str):
        status = agent_service.get_status(session_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return SessionStatusResponse(
            session_id=status["session_id"],
            state=status["state"],
            current_turn=status["current_turn"],
            pending_clarification=status.get("pending_clarification"),
            last_activity_at=status["last_activity_at"],
            expires_at=status["expires_at"],
            fsm=status.get("fsm"),
        )

    # ── 健康检查 ──────────────────────────────────────────────────────────

    @app.get("/v1/health", response_model=HealthResponse)
    async def health():
        health = agent_service.health_check()
        return HealthResponse(
            status=health["status"],
            version="2.4.0",
            components=health["components"],
        )

    @app.get("/v1/metrics")
    async def metrics():
        """Prometheus 格式指标（简化）。"""
        lines = [
            '# HELP agent_requests_total Total requests',
            '# TYPE agent_requests_total counter',
            'agent_requests_total{status="success"} 1',
            '# HELP agent_active_sessions Active sessions',
            '# TYPE agent_active_sessions gauge',
            f'agent_active_sessions {{}} {len(agent_service.session_manager._sessions)}',
        ]
        return JSONResponse(content="\n".join(lines))

    # ── WebSocket ─────────────────────────────────────────────────────────

    @app.websocket("/v1/ws/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        await websocket.accept()
        conns = ws_connections.setdefault(session_id, [])
        conns.append(websocket)

        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type")

                if msg_type == "ping":
                    event = EventBuilder.pong(session_id, server_time=time.time())
                    await websocket.send_text(EventSerializer.serialize(event))

                elif msg_type == "message":
                    payload = data.get("payload", {})
                    req = SendMessageRequest(
                        content=payload.get("content", ""),
                        modality=payload.get("modality", "text"),
                    )
                    # 复用 HTTP 逻辑（AgentService 的 event_callback 已推送事件）
                    status, intent_result, clarification, error, trace = (
                        agent_service.process_message(
                            session_id=session_id,
                            content=req.content,
                            modality=req.modality,
                        )
                    )
                    # 发送确认响应（标准事件格式）
                    event = EventBuilder.intent_result(
                        session_id=session_id,
                        status=status,
                        intent_result=intent_result.to_dict() if intent_result else None,
                        clarification=clarification.to_dict() if clarification else None,
                        error=error.to_dict() if error else None,
                        trace_log=trace,
                    )
                    await websocket.send_text(EventSerializer.serialize(event))

                elif msg_type == "clarify":
                    payload = data.get("payload", {})
                    status, intent_result, clarification, error = (
                        agent_service.submit_clarification(
                            session_id=session_id,
                            clarification_id=payload.get("clarification_id", ""),
                            selected_option=payload.get("selected_option"),
                            free_text=payload.get("free_text"),
                        )
                    )
                    event = EventBuilder.intent_result(
                        session_id=session_id,
                        status=status,
                        intent_result=intent_result.to_dict() if intent_result else None,
                        clarification=clarification.to_dict() if clarification else None,
                        error=error.to_dict() if error else None,
                    )
                    await websocket.send_text(EventSerializer.serialize(event))

                elif msg_type == "get_status":
                    status = agent_service.get_status(session_id)
                    if status is not None:
                        event = EventBuilder.state_change(
                            session_id=session_id,
                            old_state=status.get("state", ""),
                            new_state=status.get("state", ""),
                            event="status_query",
                            description=f"Current state: {status.get('state', 'unknown')}",
                        )
                        await websocket.send_text(EventSerializer.serialize(event))
                    else:
                        event = EventBuilder.error(
                            session_id=session_id,
                            code="SESSION_NOT_FOUND",
                            message="Session not found",
                            retryable=False,
                        )
                        await websocket.send_text(EventSerializer.serialize(event))

                else:
                    event = EventBuilder.error(
                        session_id=session_id,
                        code="UNKNOWN_MESSAGE_TYPE",
                        message=f"Unknown message type: {msg_type}",
                        retryable=False,
                    )
                    await websocket.send_text(EventSerializer.serialize(event))

        except WebSocketDisconnect:
            conns.remove(websocket)
            if not conns:
                ws_connections.pop(session_id, None)

    return app
