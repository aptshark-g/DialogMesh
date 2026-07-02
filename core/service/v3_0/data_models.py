# -*- coding: utf-8 -*-
"""
core/service/v3_0/data_models.py
────────────────────────────────
DialogMesh Service Layer v3.0 数据模型。

用途：
- 定义服务层专用的 Pydantic v2 请求/响应模型。
- 复用 core.agent.v3_0.data_models 中的核心模型（SessionState_v3、Intent_v3 等）。
- 提供 FastAPI 的 Schema 生成、JSON 序列化与异步验证支持。

设计原则：
- 所有请求/响应模型使用 Pydantic v2 BaseModel，严格类型校验。
- 枚举复用 core.agent.models 中的工业级定义，避免版本漂移。
- 服务层模型与业务模型分离，服务层只做适配和包装。

版本：3.0.0
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.agent.v3_0.data_models import (
    Ambiguity_v3,
    APIResponse,
    EventType,
    HealthStatus,
    Intent_v3,
    MessageRole,
    PaginatedResponse,
    SessionState_v3,
    TaskGraph_v3,
    WebSocketEvent,
    WebSocketEventBuilder,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 服务层枚举
# ═══════════════════════════════════════════════════════════════════════════════

class SessionStatus(str, Enum):
    """会话状态——服务层对会话生命周期的简化视图。"""
    ACTIVE = "active"
    IDLE = "idle"
    CLARIFYING = "clarifying"
    CLOSED = "closed"
    EXPIRED = "expired"
    ERROR = "error"


class MessageStatus(str, Enum):
    """消息处理状态——表示单条消息的处理结果。"""
    PROCESSING = "processing"
    ACTIONABLE = "actionable"
    NEEDS_CLARIFICATION = "needs_clarification"
    ERROR = "error"


class ModalityType(str, Enum):
    """输入模态类型——支持多模态输入。"""
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    STRUCTURED = "structured"
    MULTIMODAL = "multimodal"


class ResponseFormat(str, Enum):
    """响应格式层级——基于认知画像动态选择。

    设计文档 §6.3 要求：
    - BRIEF: 仅结果（1-2 句话）— 高元认知、专家用户
    - BALANCED: 结果 + 简要解释 — 普通用户（默认）
    - EXPLANATORY: 结果 + 详细解释 + 步骤说明 — 低元认知、新手用户
    - TUTORIAL: 结果 + 教学式解释 + 练习建议 — 极低元认知、学习场景
    """
    BRIEF = "brief"
    BALANCED = "balanced"
    EXPLANATORY = "explanatory"
    TUTORIAL = "tutorial"


# ═══════════════════════════════════════════════════════════════════════════════
# 请求模型
# ═══════════════════════════════════════════════════════════════════════════════

class CreateSessionRequest(BaseModel):
    """创建会话请求——POST /v3/session"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    tenant_id: str = "default"
    user_id: Optional[str] = None
    process_name: Optional[str] = None
    pid: Optional[int] = None
    initial_context: Optional[Dict[str, Any]] = None
    preferred_language: str = "zh-CN"
    user_type_hint: Optional[str] = None  # "expert" | "novice" | None
    window_config: Optional[Dict[str, Any]] = None


class SendMessageRequest(BaseModel):
    """发送消息请求——POST /v3/session/{sid}/message"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    message_id: str = Field(
        default_factory=lambda: f"msg_{int(time.time() * 1000)}"
    )
    modality: ModalityType = ModalityType.TEXT
    content: str = Field(..., min_length=0)
    structured_payload: Optional[Dict[str, Any]] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    client_sequence: int = 0
    timestamp: Optional[float] = None

    @field_validator("content", mode="before")
    @classmethod
    def _strip_content(cls, v: str) -> str:
        """去除首尾空白，异常输入回退空字符串。"""
        try:
            return str(v).strip()
        except Exception as exc:
            logger.warning(f"Content validation error ({exc}), defaulting to ''")
            return ""


class ClarifyRequest(BaseModel):
    """提交澄清请求——POST /v3/session/{sid}/clarify"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    clarification_id: str
    selected_option: Optional[int] = None
    free_text: Optional[str] = None


class CloseSessionRequest(BaseModel):
    """关闭会话请求——POST /v3/session/{sid}/close"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    persist_summary: bool = True
    reason: Optional[str] = None


class WebSocketClientMessage(BaseModel):
    """WebSocket 客户端消息标准格式——所有 WebSocket 上行消息的包装。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    type: str  # "ping" | "message" | "clarify" | "get_status" | "heartbeat"
    payload: Dict[str, Any] = Field(default_factory=dict)
    client_timestamp: Optional[float] = None
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])


# ═══════════════════════════════════════════════════════════════════════════════
# 响应模型
# ═══════════════════════════════════════════════════════════════════════════════

class CreateSessionResponse(BaseModel):
    """创建会话响应。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    session_id: str
    created_at: float
    ws_url: str
    status: SessionStatus = SessionStatus.ACTIVE
    capabilities: List[str] = Field(default_factory=lambda: ["text", "structured"])
    session_ttl_seconds: int = 3600


class SendMessageResponse(BaseModel):
    """发送消息响应。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    message_id: str
    session_id: str
    status: MessageStatus
    content: Optional[str] = None  # 经 ResponseComposer 编排后的响应文本
    response_format: ResponseFormat = ResponseFormat.BALANCED
    intent: Optional[Intent_v3] = None
    task_graph: Optional[TaskGraph_v3] = None
    clarifications: List[Ambiguity_v3] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    trace_log: List[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    error: Optional[Dict[str, Any]] = None


class ClarifyResponse(BaseModel):
    """澄清响应。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    status: MessageStatus
    clarification_id: str
    intent: Optional[Intent_v3] = None
    clarifications: List[Ambiguity_v3] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    error: Optional[Dict[str, Any]] = None


class HistoryRecord(BaseModel):
    """单条历史记录——用于历史查询响应。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    sequence: int
    timestamp: float
    role: MessageRole
    content: str
    modality: ModalityType = ModalityType.TEXT
    intent_summary: Optional[Dict[str, Any]] = None
    latency_ms: float = 0.0


class HistoryResponse(BaseModel):
    """历史查询响应。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    session_id: str
    messages: List[HistoryRecord] = Field(default_factory=list)
    has_more: bool = False
    total_turns: int = 0


class SessionStatusResponse(BaseModel):
    """会话状态查询响应。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    session_id: str
    state: SessionStatus
    current_turn: int = 0
    pending_clarification: Optional[str] = None
    last_activity_at: float = 0.0
    expires_at: float = 0.0
    resolved_entities: Dict[str, Any] = Field(default_factory=dict)
    cognitive_profile: Optional[Dict[str, Any]] = None
    fsm: Optional[Dict[str, Any]] = None


class CloseSessionResponse(BaseModel):
    """关闭会话响应。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    session_id: str
    closed_at: float
    summary: Dict[str, Any] = Field(default_factory=dict)
    persisted: bool = False


class ErrorResponse(BaseModel):
    """标准错误响应。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    code: str = "INTERNAL_ERROR"
    message: str = ""
    retryable: bool = False
    retry_after_ms: Optional[int] = None
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = Field(default_factory=time.time)


# ═══════════════════════════════════════════════════════════════════════════════
# 服务配置模型
# ═══════════════════════════════════════════════════════════════════════════════

class ServiceConfig(BaseModel):
    """服务层运行时配置——控制 API 行为、限流、会话 TTL 等。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    log_level: str = "info"
    enable_cors: bool = True
    cors_origins: List[str] = Field(default_factory=lambda: ["*"])
    max_request_size_mb: int = 10
    request_timeout_seconds: float = 30.0

    # 会话管理
    session_ttl_seconds: int = 3600
    max_memory_sessions: int = 10000
    eviction_interval_seconds: int = 300

    # 限流
    rate_limit_requests_per_minute: int = 60
    rate_limit_burst: int = 10
    enable_rate_limiter: bool = True

    # WebSocket
    ws_heartbeat_interval_seconds: float = 30.0
    ws_max_connections_per_session: int = 5
    enable_ws_compression: bool = True

    # 遥测
    enable_metrics: bool = True
    metrics_path: str = "/v3/metrics"
    enable_tracing: bool = False

    # LLM Provider
    default_provider: str = "openai"
    fallback_provider: Optional[str] = None
    provider_timeout_ms: int = 30000

    @field_validator("port", mode="before")
    @classmethod
    def _validate_port(cls, v: int) -> int:
        try:
            p = int(v)
            if not (1 <= p <= 65535):
                raise ValueError("port out of range")
            return p
        except Exception as exc:
            logger.warning(f"Port validation error ({exc}), defaulting to 8000")
            return 8000

    @field_validator("workers", mode="before")
    @classmethod
    def _validate_workers(cls, v: int) -> int:
        try:
            w = int(v)
            return max(1, w)
        except Exception as exc:
            logger.warning(f"Workers validation error ({exc}), defaulting to 1")
            return 1


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

def build_error_response(
    code: str,
    message: str,
    retryable: bool = False,
    retry_after_ms: Optional[int] = None,
) -> ErrorResponse:
    """构造标准错误响应。"""
    return ErrorResponse(
        code=code,
        message=message,
        retryable=retryable,
        retry_after_ms=retry_after_ms,
    )


def build_api_response(
    data: Any,
    success: bool = True,
    code: str = "ok",
    message: str = "success",
) -> APIResponse[Any]:
    """构造标准 API 响应。"""
    return APIResponse(
        success=success,
        code=code,
        message=message,
        data=data,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 简单自检
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio

    async def _self_test() -> None:
        logger.info("=== Service v3.0 data_models self-test ===")

        # 1. 请求模型
        req = CreateSessionRequest(user_id="u123", process_name="test.exe")
        assert req.tenant_id == "default"
        print(f"[PASS] CreateSessionRequest: tenant={req.tenant_id}")

        # 2. 消息请求
        msg_req = SendMessageRequest(content="  hello  ")
        assert msg_req.content == "hello"
        print(f"[PASS] SendMessageRequest stripped: '{msg_req.content}'")

        # 3. 响应模型
        resp = SendMessageResponse(
            message_id="msg_1", session_id="sess-123", status=MessageStatus.ACTIONABLE
        )
        assert resp.status == MessageStatus.ACTIONABLE
        print(f"[PASS] SendMessageResponse: {resp.status.value}")

        # 4. 错误响应
        err = build_error_response("RATE_LIMITED", "Too many requests", retryable=True, retry_after_ms=1000)
        assert err.retryable is True
        print(f"[PASS] ErrorResponse: {err.code}")

        # 5. 服务配置
        cfg = ServiceConfig(port=99999, workers=-1)
        assert cfg.port == 8000  # 超出范围回退
        assert cfg.workers == 1
        print(f"[PASS] ServiceConfig: port={cfg.port}, workers={cfg.workers}")

        # 6. WebSocket 客户端消息
        ws_msg = WebSocketClientMessage(type="message", payload={"content": "hi"})
        assert ws_msg.type == "message"
        print(f"[PASS] WebSocketClientMessage: {ws_msg.type}")

        logger.info("=== All Service v3.0 data_models self-tests passed ===")

    asyncio.run(_self_test())
