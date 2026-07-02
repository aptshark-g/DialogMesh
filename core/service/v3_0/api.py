# -*- coding: utf-8 -*-
"""
core/service/v3_0/api.py
────────────────────────
DialogMesh Service Layer v3.0 — FastAPI 路由与 WebSocket 端点。

用途：
- 定义所有 REST API 路由（/v3/*）。
- 定义 WebSocket 端点（/v3/ws/{session_id}）。
- 所有业务逻辑委托给 AgentService_v3，本层只做参数校验、响应包装、事件桥接。
- 使用 core.service.v3_0.data_models 中的 Pydantic 模型生成 OpenAPI Schema。

设计原则：
- 路由函数保持精简，避免嵌套业务逻辑。
- 异常统一捕获并包装为 ErrorResponse。
- WebSocket 消息统一使用 WebSocketClientMessage 解析。

版本：3.0.0
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

try:
    from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends
    from fastapi.responses import JSONResponse
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    APIRouter = None
    FastAPI = None
    WebSocket = None
    WebSocketDisconnect = Exception
    HTTPException = Exception
    JSONResponse = None
    Request = None
    Depends = None

from core.agent.v3_0.data_models import EventType, WebSocketEvent, WebSocketEventBuilder
from core.service.v3_0.data_models import (
    ClarifyRequest,
    CloseSessionRequest,
    CloseSessionResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    ErrorResponse,
    HistoryResponse,
    SendMessageRequest,
    SendMessageResponse,
    SessionStatusResponse,
    WebSocketClientMessage,
    build_error_response,
)
from core.service.v3_0.agent_service import AgentService_v3
from core.service.v3_0.websocket_manager import WebSocketManager_v3

logger = logging.getLogger(__name__)


class DialogMeshAPI_v3:
    """
    v3.0 API 路由集合。

    将 AgentService_v3 与 WebSocketManager_v3 绑定到 FastAPI Router。
    """

    def __init__(
        self,
        agent_service: AgentService_v3,
        websocket_manager: WebSocketManager_v3,
    ) -> None:
        if not HAS_FASTAPI:
            raise ImportError(
                "FastAPI is required for the service layer. "
                "Install with: pip install fastapi uvicorn"
            )
        self.agent_service = agent_service
        self.websocket_manager = websocket_manager
        self.router = APIRouter(prefix="/v3")
        self._setup_routes()
        self._setup_websocket()
        self._setup_event_bridge()

    # ── 事件桥接 ───────────────────────────────────────────────────────────

    def _setup_event_bridge(self) -> None:
        """将 AgentService 的事件回调绑定到 WebSocketManager。"""
        async def async_event_bridge(session_id: str, event_type: str, payload: Dict[str, Any]) -> None:
            try:
                event = (
                    WebSocketEvent.builder(EventType(event_type), session_id)
                    .with_payload_dict(payload)
                    .build()
                )
                await self.websocket_manager.broadcast_to_session(session_id, event)
            except Exception as exc:
                logger.warning("async_event_bridge failed: %s", exc)

        # 将异步桥接设为回调
        self.agent_service.event_callback = async_event_bridge

    # ── REST 路由 ────────────────────────────────────────────────────────────

    def _setup_routes(self) -> None:
        """注册 REST 路由。"""
        router = self.router

        @router.post("/session", response_model=CreateSessionResponse)
        async def create_session(req: CreateSessionRequest) -> CreateSessionResponse:
            try:
                return await self.agent_service.create_session(req)
            except Exception as exc:
                logger.error(f"POST /session failed: {exc}")
                raise HTTPException(status_code=500, detail=str(exc))

        @router.post("/session/{session_id}/close", response_model=CloseSessionResponse)
        async def close_session(session_id: str, req: Optional[CloseSessionRequest] = None) -> CloseSessionResponse:
            try:
                return await self.agent_service.close_session(session_id, req)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc))
            except Exception as exc:
                logger.error(f"POST /session/{session_id}/close failed: {exc}")
                raise HTTPException(status_code=500, detail=str(exc))

        @router.post("/session/{session_id}/message", response_model=SendMessageResponse)
        async def send_message(session_id: str, req: SendMessageRequest) -> SendMessageResponse:
            try:
                return await self.agent_service.process_message(session_id, req)
            except Exception as exc:
                logger.error(f"POST /session/{session_id}/message failed: {exc}")
                raise HTTPException(status_code=500, detail=str(exc))

        @router.post("/session/{session_id}/clarify", response_model=SendMessageResponse)
        async def submit_clarification(session_id: str, req: ClarifyRequest) -> SendMessageResponse:
            try:
                return await self.agent_service.submit_clarification(session_id, req)
            except Exception as exc:
                logger.error(f"POST /session/{session_id}/clarify failed: {exc}")
                raise HTTPException(status_code=500, detail=str(exc))

        @router.get("/session/{session_id}/history", response_model=HistoryResponse)
        async def get_history(session_id: str, limit: int = 50, offset: int = 0) -> HistoryResponse:
            try:
                history = await self.agent_service.get_history(session_id, limit=limit, offset=offset)
                if history is None:
                    raise HTTPException(status_code=404, detail="Session not found")
                return history
            except HTTPException:
                raise
            except Exception as exc:
                logger.error(f"GET /session/{session_id}/history failed: {exc}")
                raise HTTPException(status_code=500, detail=str(exc))

        @router.get("/session/{session_id}/status", response_model=SessionStatusResponse)
        async def get_status(session_id: str) -> SessionStatusResponse:
            try:
                status = await self.agent_service.get_status(session_id)
                if status is None:
                    raise HTTPException(status_code=404, detail="Session not found")
                return status
            except HTTPException:
                raise
            except Exception as exc:
                logger.error(f"GET /session/{session_id}/status failed: {exc}")
                raise HTTPException(status_code=500, detail=str(exc))

        @router.get("/health")
        async def health() -> Dict[str, Any]:
            try:
                return await self.agent_service.health_check()
            except Exception as exc:
                logger.error(f"GET /health failed: {exc}")
                return {"status": "unhealthy", "error": str(exc)}

        @router.get("/metrics")
        async def metrics() -> JSONResponse:
            try:
                stats = await self.agent_service.get_stats()
                # 简化的 Prometheus 格式
                lines = [
                    '# HELP dm_requests_total Total requests',
                    '# TYPE dm_requests_total counter',
                    f'dm_requests_total {{service="agent_v3"}} {stats["agent_service"]["total_requests"]}',
                    '# HELP dm_errors_total Total errors',
                    '# TYPE dm_errors_total counter',
                    f'dm_errors_total {{service="agent_v3"}} {stats["agent_service"]["total_errors"]}',
                    '# HELP dm_avg_latency_ms Average latency',
                    '# TYPE dm_avg_latency_ms gauge',
                    f'dm_avg_latency_ms {{service="agent_v3"}} {stats["agent_service"]["avg_latency_ms"]}',
                ]
                return JSONResponse(content="\n".join(lines))
            except Exception as exc:
                logger.error(f"GET /metrics failed: {exc}")
                return JSONResponse(content="# Error generating metrics")

    # ── WebSocket 端点 ───────────────────────────────────────────────────────

    def _setup_websocket(self) -> None:
        """注册 WebSocket 端点。"""
        router = self.router

        @router.websocket("/ws/{session_id}")
        async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
            await self.websocket_manager.connect(session_id, websocket)
            try:
                while True:
                    raw_data = await websocket.receive_json()
                    try:
                        client_msg = WebSocketClientMessage.model_validate(raw_data)
                    except Exception as exc:
                        logger.warning("Invalid WebSocket message format: %s", exc)
                        await self.websocket_manager.send_error(
                            session_id, "INVALID_MESSAGE", "Invalid message format"
                        )
                        continue

                    msg_type = client_msg.type
                    payload = client_msg.payload

                    if msg_type == "ping":
                        pong_event = (
                            WebSocketEvent.builder(EventType.HEARTBEAT, session_id)
                            .with_payload("server_time", time.time())
                            .build()
                        )
                        await self.websocket_manager.send_event(websocket, pong_event)

                    elif msg_type == "message":
                        content = payload.get("content", "")
                        modality = payload.get("modality", "text")
                        req = SendMessageRequest(content=content, modality=modality)
                        result = await self.agent_service.process_message(session_id, req)
                        # 通过 event_callback 已广播，这里发送确认
                        confirm_event = (
                            WebSocketEvent.builder(EventType.MESSAGE, session_id)
                            .with_payload_dict({
                                "message_id": result.message_id,
                                "status": result.status.value,
                                "latency_ms": result.latency_ms,
                            })
                            .build()
                        )
                        await self.websocket_manager.send_event(websocket, confirm_event)

                    elif msg_type == "clarify":
                        req = ClarifyRequest(
                            clarification_id=payload.get("clarification_id", ""),
                            selected_option=payload.get("selected_option"),
                            free_text=payload.get("free_text"),
                        )
                        result = await self.agent_service.submit_clarification(session_id, req)
                        confirm_event = (
                            WebSocketEvent.builder(EventType.CLARIFICATION, session_id)
                            .with_payload_dict({
                                "clarification_id": req.clarification_id,
                                "status": result.status.value,
                                "latency_ms": result.latency_ms,
                            })
                            .build()
                        )
                        await self.websocket_manager.send_event(websocket, confirm_event)

                    elif msg_type == "get_status":
                        status = await self.agent_service.get_status(session_id)
                        if status is not None:
                            event = (
                                WebSocketEvent.builder(EventType.SYSTEM_STATUS, session_id)
                                .with_payload_dict({
                                    "state": status.state.value,
                                    "current_turn": status.current_turn,
                                    "pending_clarification": status.pending_clarification,
                                })
                                .build()
                            )
                            await self.websocket_manager.send_event(websocket, event)
                        else:
                            await self.websocket_manager.send_error(
                                session_id, "SESSION_NOT_FOUND", "Session not found"
                            )

                    elif msg_type == "heartbeat":
                        # 客户端心跳，静默处理
                        pass

                    else:
                        await self.websocket_manager.send_error(
                            session_id, "UNKNOWN_MESSAGE_TYPE", f"Unknown type: {msg_type}"
                        )

            except WebSocketDisconnect:
                await self.websocket_manager.disconnect(websocket)
            except Exception as exc:
                logger.error(f"WebSocket error for session {session_id}: {exc}")
                await self.websocket_manager.disconnect(websocket)

    # ── 注册到 FastAPI ───────────────────────────────────────────────────────

    def register(self, app: FastAPI) -> None:
        """将本路由集合注册到 FastAPI 应用。"""
        app.include_router(self.router)
        logger.info("DialogMeshAPI_v3 registered with FastAPI")
