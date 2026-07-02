# -*- coding: utf-8 -*-
"""
service/protocol/events.py
──────────────────────────
WebSocket 事件标准格式（§12.4 / §13.5）。

定义服务端 ↔ 前端之间所有实时事件的数据结构，包括事件构造器、序列化器、
进度事件、错误负载等。
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


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
# 核心事件模型
# ═══════════════════════════════════════════════════════════════════════════════

class WebSocketEvent(_CompatModel):
    """WebSocket 标准事件格式。

    所有服务端推送和客户端发送的消息都封装为此结构。
    """

    event_type: str = Field(
        ...,
        description="事件类型：intent_result / clarification / progress / taskgraph_update / error / state_change / ping / pong / message / get_status",
    )
    session_id: Optional[str] = Field(
        None,
        description="关联会话 ID（全局事件如 ping 可为 None）",
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="事件具体负载，按 event_type 解析",
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="事件发生时间（Unix 时间戳）",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# EventBuilder
# ═══════════════════════════════════════════════════════════════════════════════

class EventBuilder:
    """构造标准 WebSocketEvent 的工厂类。

    所有服务端推送事件应通过此工厂生成，确保字段一致性。
    """

    @staticmethod
    def _build(event_type: str, session_id: Optional[str], payload: Dict[str, Any]) -> WebSocketEvent:
        return WebSocketEvent(
            event_type=event_type,
            session_id=session_id,
            payload=payload,
            timestamp=time.time(),
        )

    @classmethod
    def intent_result(cls, session_id: str, payload: Dict[str, Any]) -> WebSocketEvent:
        """意图解析完成事件（可直接执行）。"""
        return cls._build("intent_result", session_id, payload)

    @classmethod
    def clarification(cls, session_id: str, payload: Dict[str, Any]) -> WebSocketEvent:
        """需要用户澄清事件（包含 ClarificationUISchema）。"""
        return cls._build("clarification", session_id, payload)

    @classmethod
    def progress(cls, session_id: str, payload: Dict[str, Any]) -> WebSocketEvent:
        """解析进度推送事件（如 PCR、entity_extract 阶段进度）。"""
        return cls._build("progress", session_id, payload)

    @classmethod
    def taskgraph_update(cls, session_id: str, payload: Dict[str, Any]) -> WebSocketEvent:
        """TaskGraph 状态更新事件（节点/边/整体进度变化）。"""
        return cls._build("taskgraph_update", session_id, payload)

    @classmethod
    def error(cls, session_id: str, payload: Dict[str, Any]) -> WebSocketEvent:
        """错误事件（如会话过期、限流、引擎降级）。"""
        return cls._build("error", session_id, payload)

    @classmethod
    def state_change(cls, session_id: str, old_state: str, new_state: str) -> WebSocketEvent:
        """FSM 状态变更事件（如 PARSING → CLARIFYING）。"""
        return cls._build(
            "state_change",
            session_id,
            {"old_state": old_state, "new_state": new_state},
        )

    @classmethod
    def ping(cls) -> WebSocketEvent:
        """客户端心跳 ping。"""
        return cls._build("ping", None, {})

    @classmethod
    def pong(cls, server_time: Optional[float] = None) -> WebSocketEvent:
        """服务端心跳 pong（携带服务端时间戳）。"""
        return cls._build(
            "pong",
            None,
            {"server_time": server_time or time.time()},
        )


# ═══════════════════════════════════════════════════════════════════════════════
# EventSerializer
# ═══════════════════════════════════════════════════════════════════════════════

class EventSerializer:
    """WebSocketEvent 序列化/反序列化工具。

    WebSocket 传输使用 JSON 字符串（send_text），而非 send_json。
    """

    @staticmethod
    def serialize(event: WebSocketEvent) -> str:
        """将 WebSocketEvent 序列化为 JSON 字符串。

        Args:
            event: 待序列化的事件对象。

        Returns:
            JSON 字符串。
        """
        return json.dumps(event.dict(), ensure_ascii=False, default=str)

    @staticmethod
    def deserialize(raw: str) -> WebSocketEvent:
        """将 JSON 字符串反序列化为 WebSocketEvent。

        Args:
            raw: JSON 字符串。

        Returns:
            WebSocketEvent 实例。
        """
        data = json.loads(raw)
        return WebSocketEvent.model_validate(data)


# ═══════════════════════════════════════════════════════════════════════════════
# 具体事件负载模型
# ═══════════════════════════════════════════════════════════════════════════════

class ParseProgressEvent(_CompatModel):
    """解析进度事件，用于实时展示处理阶段。"""

    message_id: str = Field(..., description="关联消息 ID")
    stage: str = Field(
        ...,
        description="当前阶段：pcr / preprocess / entity_extract / classify / plan / execute",
    )
    status: str = Field(
        ...,
        description="阶段状态：started / completed / skipped",
    )
    detail: Optional[str] = Field(
        None,
        description="人类可读描述，如'正在提取实体...'",
    )
    elapsed_ms: float = Field(
        0.0,
        description="当前已耗时（毫秒）",
        ge=0,
    )
    estimated_total_ms: Optional[float] = Field(
        None,
        description="预估总耗时（毫秒）",
        ge=0,
    )


class ErrorPayload(_CompatModel):
    """标准错误负载，用于 WebSocket 和 HTTP 响应。"""

    code: str = Field(
        ...,
        description="错误码：SESSION_EXPIRED / RATE_LIMITED / PCR_DEGRADED / INTERNAL_ERROR / VALIDATION_ERROR",
    )
    message: str = Field(..., description="人类可读错误描述")
    retryable: bool = Field(
        False,
        description="是否可重试",
    )
    retry_after_ms: Optional[int] = Field(
        None,
        description="建议重试等待时间（毫秒），retryable=true 时有效",
        ge=0,
    )
