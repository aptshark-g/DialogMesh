# -*- coding: utf-8 -*-
"""
service/api/routes.py
─────────────────────
DialogMesh REST API 路由（FastAPI Router）。

所有端点挂载到 /v1/ 前缀下。
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import PlainTextResponse

from service.protocol.schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    SendMessageRequest,
    SendMessageResponse,
    ClarifyRequest,
    ClarifyResponse,
    HistoryResponse,
    MessageRecord,
    SessionStatusResponse,
    HealthResponse,
    ComponentHealth,
    CognitiveProfilePayload,
    ErrorUIPayload,
    ErrorAction,
)
from service.protocol.events import ErrorPayload
from service.models import Session, SessionSummary
from service.async_session_manager import AsyncSessionManager
from service.api.dependencies import (
    get_agent_service,
    get_current_session,
    get_session_manager,
    get_websocket_manager,
    get_tenant_id,
    AgentService,
)
from service.api.websocket import WebSocketManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")


# ═══════════════════════════════════════════════════════════════════════════════
# 会话管理
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/session/create",
    response_model=CreateSessionResponse,
    responses={
        429: {"description": "Rate limited"},
        500: {"description": "Internal error"},
    },
)
async def create_session(
    req: CreateSessionRequest,
    agent_service: AgentService = Depends(get_agent_service),
    tenant_id: str = Depends(get_tenant_id),
):
    """创建新会话，返回 session_id 与 WebSocket 连接地址。"""
    try:
        session = await agent_service.create_session(
            tenant_id=tenant_id,
            user_id=req.user_id,
            initial_context=req.initial_context,
        )
        ws_url = f"/ws/{session.session_id}"
        return CreateSessionResponse(
            session_id=session.session_id,
            created_at=session.created_at,
            ws_url=ws_url,
            session_ttl_seconds=3600,
        )
    except Exception as exc:
        logger.exception("Failed to create session: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to create session",
                    "retryable": True,
                }
            },
        )


@router.post(
    "/session/{session_id}/message",
    response_model=SendMessageResponse,
    responses={
        404: {"description": "Session not found"},
        429: {"description": "Rate limited"},
        500: {"description": "Internal error"},
    },
)
async def send_message(
    session_id: str,
    req: SendMessageRequest,
    agent_service: AgentService = Depends(get_agent_service),
    session: Session = Depends(get_current_session),
):
    """发送消息（核心接口），调用 AgentService.process_message。"""
    try:
        status, intent_result, clarification, error, trace_log, latency_ms = (
            await agent_service.process_message(
                session_id=session_id,
                content=req.content,
                modality=req.modality,
                message_id=req.message_id,
            )
        )

        if error:
            # 业务错误仍以 SendMessageResponse 返回，status="error"
            trace_log = trace_log + [f"Error: {error.code} - {error.message}"]
            return SendMessageResponse(
                message_id=req.message_id,
                status="error",
                intent_result=None,
                clarification=None,
                trace_log=trace_log,
                latency_ms=latency_ms,
            )

        return SendMessageResponse(
            message_id=req.message_id,
            status=status,
            intent_result=intent_result,
            clarification=clarification,
            trace_log=trace_log,
            latency_ms=latency_ms,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to process message: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(exc),
                    "retryable": True,
                }
            },
        )


@router.post(
    "/session/{session_id}/clarify",
    response_model=ClarifyResponse,
    responses={
        404: {"description": "Session not found"},
        400: {"description": "Invalid clarification"},
        500: {"description": "Internal error"},
    },
)
async def submit_clarification(
    session_id: str,
    req: ClarifyRequest,
    agent_service: AgentService = Depends(get_agent_service),
    session: Session = Depends(get_current_session),
):
    """提交澄清回复。"""
    try:
        status, intent_result, clarification, error = (
            await agent_service.submit_clarification(
                session_id=session_id,
                clarification_id=req.clarification_id,
                selected_option=req.selected_option,
                free_text=req.free_text,
            )
        )

        if error:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": error.code,
                        "message": error.message,
                        "retryable": error.retryable,
                    }
                },
            )

        return ClarifyResponse(
            status=status,
            intent_result=intent_result,
            next_clarification=clarification,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to submit clarification: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(exc),
                    "retryable": True,
                }
            },
        )


@router.get(
    "/session/{session_id}/history",
    response_model=HistoryResponse,
    responses={404: {"description": "Session not found"}},
)
async def get_history(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    before_seq: Optional[int] = Query(default=None, ge=0),
    agent_service: AgentService = Depends(get_agent_service),
    session: Session = Depends(get_current_session),
):
    """获取对话历史（支持 limit + before_seq 分页）。"""
    try:
        turns = await agent_service.get_history(
            session_id, limit=limit, before_seq=before_seq,
        )
        messages = [
            MessageRecord(
                sequence=turn.sequence,
                role=turn.role,
                content=turn.content,
                latency_ms=turn.latency_ms,
                timestamp=turn.timestamp,
            )
            for turn in turns
        ]
        has_more = len(turns) >= limit
        return HistoryResponse(
            session_id=session_id,
            messages=messages,
            has_more=has_more,
        )
    except Exception as exc:
        logger.exception("Failed to get history: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(exc),
                    "retryable": True,
                }
            },
        )


@router.get(
    "/session/{session_id}/status",
    response_model=SessionStatusResponse,
    responses={404: {"description": "Session not found"}},
)
async def get_session_status(
    session_id: str,
    agent_service: AgentService = Depends(get_agent_service),
    session: Session = Depends(get_current_session),
):
    """获取会话状态（含 FSM 状态、待澄清 ID、认知画像）。"""
    try:
        status_data = await agent_service.get_status(session_id)
        if status_data is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "SESSION_NOT_FOUND",
                        "message": "Session not found",
                        "retryable": False,
                    }
                },
            )

        cog_profile = None
        raw_cog = status_data.get("cognitive_profile")
        if raw_cog:
            cog_profile = CognitiveProfilePayload(
                metacognition=raw_cog.get("metacognition", 0.0),
                divergence=raw_cog.get("divergence", 0.0),
                tracking_depth=raw_cog.get("tracking_depth", 0.0),
                stability=raw_cog.get("stability", 0.0),
                confidence=raw_cog.get("confidence", 0.0),
            )

        return SessionStatusResponse(
            session_id=status_data["session_id"],
            state=status_data["state"],
            current_turn=status_data["current_turn"],
            pending_clarification=status_data.get("pending_clarification"),
            cognitive_profile=cog_profile,
            last_activity_at=status_data["last_activity_at"],
            expires_at=status_data["expires_at"],
            fsm=status_data.get("fsm"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get session status: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(exc),
                    "retryable": True,
                }
            },
        )


@router.post(
    "/session/{session_id}/close",
    response_model=SessionSummary,
    responses={404: {"description": "Session not found"}},
)
async def close_session(
    session_id: str,
    session_manager: AsyncSessionManager = Depends(get_session_manager),
    session: Session = Depends(get_current_session),
):
    """关闭会话，返回 SessionSummary。"""
    try:
        summary = await session_manager.close_session(session_id)
        if summary is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "SESSION_NOT_FOUND",
                        "message": "Session not found or already closed",
                        "retryable": False,
                    }
                },
            )
        return summary
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to close session: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(exc),
                    "retryable": True,
                }
            },
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 健康与监控
# ═══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/health",
    response_model=HealthResponse,
)
async def health(
    agent_service: AgentService = Depends(get_agent_service),
):
    """健康检查（检查 PCR、IntentParser、SessionManager、WebSocketManager、Store）。"""
    try:
        raw = await agent_service.health_check()
        components = raw.get("components", {})
        return HealthResponse(
            status=raw.get("status", "unknown"),
            version="2.4.0",
            components={
                name: ComponentHealth(
                    status=comp.get("status", "unknown"),
                    latency_ms=comp.get("latency_ms"),
                    last_error=comp.get("last_error"),
                )
                for name, comp in components.items()
            },
        )
    except Exception as exc:
        logger.exception("Health check failed: %s", exc)
        return HealthResponse(
            status="unhealthy",
            version="2.4.0",
            components={
                "api": ComponentHealth(
                    status="unhealthy",
                    last_error=str(exc),
                ),
            },
        )


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    """Prometheus 格式遥测数据。"""
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, REGISTRY
        data = generate_latest(REGISTRY)
        return PlainTextResponse(
            content=data.decode("utf-8"), media_type=CONTENT_TYPE_LATEST
        )
    except ImportError:
        # Fallback: 返回基础指标文本
        lines = [
            "# HELP dialogmesh_requests_total Total requests",
            "# TYPE dialogmesh_requests_total counter",
            "dialogmesh_requests_total 0",
            "# HELP dialogmesh_errors_total Total errors",
            "# TYPE dialogmesh_errors_total counter",
            "dialogmesh_errors_total 0",
        ]
        return PlainTextResponse(content="\n".join(lines), media_type="text/plain")


# ═══════════════════════════════════════════════════════════════════════════════
# 多模态输入
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    tenant_id: str = Depends(get_tenant_id),
):
    """文件上传（多模态预留），返回 file_url。"""
    try:
        import os
        upload_dir = f"uploads/{tenant_id}"
        os.makedirs(upload_dir, exist_ok=True)
        file_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
        file_path = os.path.join(upload_dir, file_name)
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        file_url = f"/uploads/{tenant_id}/{file_name}"
        return {
            "file_id": file_name,
            "file_name": file.filename,
            "file_url": file_url,
            "size": len(content),
            "content_type": file.content_type,
        }
    except Exception as exc:
        logger.exception("Upload failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "UPLOAD_FAILED",
                    "message": str(exc),
                    "retryable": True,
                }
            },
        )
