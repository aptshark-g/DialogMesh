# -*- coding: utf-8 -*-
"""
service/protocol/schemas.py
───────────────────────────
FastAPI 请求/响应 Pydantic 模型（§12.3 / §13.5 / §13.6）。

定义 REST API 所有端点的输入输出契约，以及内部使用的 Payload 模型。
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict

from .ui_schema import ClarificationUISchema
from .task_graph import TaskGraphPayload


# ═══════════════════════════════════════════════════════════════════════════════
# 兼容基类
# ═══════════════════════════════════════════════════════════════════════════════

class _CompatModel(BaseModel):
    """兼容基类：为 Pydantic v2 模型提供 V1 风格的 `.dict()` 方法。"""

    def dict(self, **kwargs) -> Dict[str, Any]:
        return self.model_dump(**kwargs)

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 会话管理
# ═══════════════════════════════════════════════════════════════════════════════

class CreateSessionRequest(_CompatModel):
    """POST /v1/session/create 请求体。"""

    tenant_id: str = Field("default", description="多租户标识")
    user_id: Optional[str] = Field(None, description="用户标识（可选，匿名会话）")
    initial_context: Optional[Dict[str, Any]] = Field(
        None,
        description="初始进程上下文等附加数据",
    )
    preferred_language: str = Field(
        "zh-CN",
        description="语言偏好（影响同义词扩展词典）",
    )


class CreateSessionResponse(_CompatModel):
    """POST /v1/session/create 响应体。"""

    session_id: str = Field(..., description="会话唯一标识（uuid）")
    created_at: float = Field(
        default_factory=time.time,
        description="会话创建时间（Unix 时间戳）",
    )
    ws_url: str = Field(..., description="WebSocket 连接地址")
    capabilities: List[str] = Field(
        default_factory=lambda: ["text", "structured"],
        description="支持的模态列表",
    )
    session_ttl_seconds: int = Field(
        3600,
        description="会话超时时间（秒）",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 消息解析
# ═══════════════════════════════════════════════════════════════════════════════

class SendMessageRequest(_CompatModel):
    """POST /v1/session/{id}/message 请求体。"""

    message_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8],
        description="消息唯一标识（客户端可生成，用于去重）",
    )
    modality: str = Field(
        "text",
        description="输入模态：text / structured / image / audio / multimodal",
    )
    content: str = Field(..., description="文本内容（TEXT 模态时必填）")
    structured_payload: Optional[Dict[str, Any]] = Field(
        None,
        description="STRUCTURED 模态的原始负载",
    )
    attachments: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="多模态附件列表（图片/音频 URL 等）",
    )
    timestamp: Optional[float] = Field(
        None,
        description="客户端时间戳（可选，服务端默认使用 time.time()）",
    )
    client_sequence: int = Field(
        0,
        description="客户端序列号（用于去重和排序）",
        ge=0,
    )


class EntityPayload(_CompatModel):
    """意图解析中提取的实体。"""

    type: str = Field(..., description="实体类型，如 memory_address / process_name / numeric_value")
    value: Any = Field(..., description="提取的值")
    raw_text: str = Field("", description="原始文本片段")
    confidence: float = Field(1.0, description="置信度 0.0-1.0", ge=0.0, le=1.0)


class CognitiveProfilePayload(_CompatModel):
    """认知画像快照。"""

    metacognition: float = Field(0.0, description="元认知得分")
    divergence: float = Field(0.0, description="发散性得分")
    tracking_depth: float = Field(0.0, description="追踪深度得分")
    stability: float = Field(0.0, description="稳定性得分")
    confidence: float = Field(0.0, description="综合置信度")


class IntentResult(_CompatModel):
    """可直接执行时的意图解析结果。"""

    expectation: str = Field(
        ...,
        description="用户期望模式：TOOL / ADVISOR / COMPANION / UNKNOWN",
    )
    task_graph: Optional[TaskGraphPayload] = Field(
        None,
        description="任务依赖图（如需可视化）",
    )
    entities: List[EntityPayload] = Field(
        default_factory=list,
        description="提取的实体列表",
    )
    cognitive_profile: CognitiveProfilePayload = Field(
        default_factory=CognitiveProfilePayload,
        description="当前认知画像快照",
    )


class ClarificationPayload(_CompatModel):
    """需要澄清时返回的负载（包含 UI 渲染协议）。"""

    clarification_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8],
        description="本次澄清请求唯一 ID",
    )
    message: str = Field(..., description="给用户的自然语言提示")
    ui_schema: Optional[ClarificationUISchema] = Field(
        None,
        description="前端渲染协议（组件定义）",
    )
    suggestions: List[str] = Field(
        default_factory=list,
        description="快速回复选项（纯文本 fallback）",
    )
    timeout_seconds: int = Field(
        60,
        description="澄清超时时间（秒）",
    )
    required: bool = Field(
        True,
        description="是否必须回答（false = 可忽略）",
    )


class SendMessageResponse(_CompatModel):
    """POST /v1/session/{id}/message 响应体。"""

    message_id: str = Field(..., description="消息唯一标识")
    status: str = Field(
        ...,
        description="处理状态：actionable / needs_clarification / error / processing",
    )
    intent_result: Optional[IntentResult] = Field(
        None,
        description="可直接执行时返回的解析结果",
    )
    clarification: Optional[ClarificationPayload] = Field(
        None,
        description="需要澄清时返回的澄清负载",
    )
    trace_log: List[str] = Field(
        default_factory=list,
        description="调试用的 trace_log（生产环境可脱敏）",
    )
    latency_ms: float = Field(
        0.0,
        description="服务端处理耗时（毫秒）",
        ge=0.0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 澄清回复
# ═══════════════════════════════════════════════════════════════════════════════

class ClarifyRequest(_CompatModel):
    """POST /v1/session/{id}/clarify 请求体。"""

    clarification_id: str = Field(
        ...,
        description="对应 SendMessageResponse 中的 clarification_id",
    )
    selected_option: Optional[int] = Field(
        None,
        description="选择了第几个 suggestion（0-based）",
        ge=0,
    )
    free_text: Optional[str] = Field(
        None,
        description="自由文本回复（当 selected_option=None 时）",
    )


class ClarifyResponse(_CompatModel):
    """POST /v1/session/{id}/clarify 响应体。"""

    status: str = Field(
        ...,
        description="澄清状态：resolved / needs_more_clarification / expired",
    )
    intent_result: Optional[IntentResult] = Field(
        None,
        description="澄清消解后重新解析的结果",
    )
    next_clarification: Optional[ClarificationPayload] = Field(
        None,
        description="仍有歧义时，继续发起下一轮澄清",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 历史与状态查询
# ═══════════════════════════════════════════════════════════════════════════════

class MessageRecord(_CompatModel):
    """单条对话历史记录。"""

    sequence: int = Field(..., description="序列号，递增")
    role: str = Field(
        ...,
        description="角色：user / system / assistant / tool",
    )
    content: str = Field(..., description="消息内容")
    intent_result: Optional[IntentResult] = Field(
        None,
        description="解析结果（用户消息）或系统响应",
    )
    clarification: Optional[ClarificationPayload] = Field(
        None,
        description="澄清请求（如适用）",
    )
    latency_ms: float = Field(0.0, description="处理耗时（毫秒）", ge=0.0)
    timestamp: float = Field(
        default_factory=time.time,
        description="记录时间（Unix 时间戳）",
    )


class HistoryResponse(_CompatModel):
    """GET /v1/session/{id}/history 响应体。"""

    session_id: str = Field(..., description="会话 ID")
    messages: List[MessageRecord] = Field(
        default_factory=list,
        description="对话历史记录列表",
    )
    has_more: bool = Field(
        False,
        description="是否还有更多历史记录",
    )


class SessionStatusResponse(_CompatModel):
    """GET /v1/session/{id}/status 响应体。"""

    session_id: str = Field(..., description="会话 ID")
    state: str = Field(
        ...,
        description="会话状态：active / idle / clarifying / closed / expired",
    )
    current_turn: int = Field(0, description="当前轮次", ge=0)
    pending_clarification: Optional[str] = Field(
        None,
        description="待澄清的 clarification_id",
    )
    cognitive_profile: Optional[CognitiveProfilePayload] = Field(
        None,
        description="当前认知画像",
    )
    last_activity_at: float = Field(
        default_factory=time.time,
        description="最后活动时间（Unix 时间戳）",
    )
    expires_at: float = Field(
        default_factory=lambda: time.time() + 3600,
        description="会话过期时间（Unix 时间戳）",
    )
    fsm: Optional[Dict[str, Any]] = Field(
        None,
        description="ClarificationFSM 状态快照（state, clarification_count, can_clarify_more 等）",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 健康检查
# ═══════════════════════════════════════════════════════════════════════════════

class ComponentHealth(_CompatModel):
    """单个组件健康状态。"""

    status: str = Field(
        ...,
        description="状态：healthy / degraded / unhealthy",
    )
    latency_ms: Optional[float] = Field(
        None,
        description="最近一次检查耗时（毫秒）",
        ge=0.0,
    )
    last_error: Optional[str] = Field(
        None,
        description="最近一次错误信息",
    )


class HealthResponse(_CompatModel):
    """GET /v1/health 响应体。"""

    status: str = Field(
        ...,
        description="整体状态：healthy / degraded / unhealthy",
    )
    version: str = Field("2.3.0", description="服务版本号")
    components: Dict[str, ComponentHealth] = Field(
        default_factory=dict,
        description="各组件健康状态字典（pcr, intent_parser, session_manager, websocket_manager, store）",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 错误/降级 UI 协议
# ═══════════════════════════════════════════════════════════════════════════════

class ErrorAction(_CompatModel):
    """错误场景下用户可执行的操作。"""

    action_type: str = Field(
        ...,
        description="操作类型：retry / fallback / contact_support / ignore",
    )
    label: str = Field(..., description="按钮文案")
    payload: Optional[Dict[str, Any]] = Field(
        None,
        description="触发时携带的数据",
    )


class ErrorUIPayload(_CompatModel):
    """PCR 降级或 LLM 超时时的前端展示协议。"""

    severity: str = Field(
        ...,
        description="严重程度：info / warning / error / critical",
    )
    title: str = Field(..., description="错误标题")
    message: str = Field(..., description="详细说明")
    actions: List[ErrorAction] = Field(
        default_factory=list,
        description="用户可执行的操作列表",
    )
    technical_detail: Optional[str] = Field(
        None,
        description="技术详情（可折叠，仅高级用户可见）",
    )
    auto_recover: bool = Field(
        False,
        description="是否自动恢复",
    )
    recover_in_seconds: Optional[int] = Field(
        None,
        description="预计自动恢复时间（秒）",
        ge=0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 多模态输入
# ═══════════════════════════════════════════════════════════════════════════════

class MultimodalInputRequest(_CompatModel):
    """多模态输入请求（扩展预留）。

    当前 TEXT / STRUCTURED 生产可用，其余 IMAGE / AUDIO / MULTIMODAL 为预留。
    """

    message_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8],
        description="消息唯一标识",
    )
    modality: str = Field(
        ...,
        description="输入模态：text / structured / image / audio / multimodal",
    )
    text_content: Optional[str] = Field(
        None,
        description="文本内容（TEXT 模态）",
    )
    structured_payload: Optional[Dict[str, Any]] = Field(
        None,
        description="结构化内容（STRUCTURED 模态）",
    )
    image_url: Optional[str] = Field(
        None,
        description="图片 URL（IMAGE 模态，服务端已上传）",
    )
    image_base64: Optional[str] = Field(
        None,
        description="Base64 编码图片（小图）",
    )
    audio_url: Optional[str] = Field(
        None,
        description="音频 URL（AUDIO 模态）",
    )
    audio_duration_ms: Optional[int] = Field(
        None,
        description="音频时长（毫秒）",
        ge=0,
    )
    client_timestamp: Optional[float] = Field(
        None,
        description="客户端时间戳",
    )
    client_sequence: int = Field(
        ...,
        description="客户端序列号（用于去重和排序）",
        ge=0,
    )
