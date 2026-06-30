# -*- coding: utf-8 -*-
"""
core/agent/frontend/websocket_events.py
──────────────────────────────────────────
实时推送事件协议（Layer 3，v2.4 新增）。

定义 WebSocket / SSE 实时推送的事件类型和数据格式。
支持事件：
  - intent_result: 意图解析结果
  - clarification: 澄清请求
  - progress: 解析进度（阶段更新）
  - taskgraph_update: 任务图更新
  - error: 错误信息
  - state_change: 澄清 FSM 状态变化
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent.frontend.clarification_ui import ClarificationUISchema
from core.agent.frontend.taskgraph_viz import TaskGraphUpdateEvent


class EventType:
    """事件类型常量。"""
    INTENT_RESULT = "intent_result"             # 意图解析结果
    CLARIFICATION = "clarification"             # 澄清请求
    PROGRESS = "progress"                       # 解析进度
    TASKGRAPH_UPDATE = "taskgraph_update"       # 任务图更新
    ERROR = "error"                             # 错误信息
    STATE_CHANGE = "state_change"               # FSM 状态变化
    PONG = "pong"                               # 心跳响应


class EventTypeRegistry:
    """
    WebSocket 事件类型注册表（P2 修复增强：Schema + 版本 + 第三方扩展）。

    支持第三方插件注册自定义事件类型，运行时校验 payload 完整性。
    """
    # 内置事件 Schema：type -> {"version": str, "required_fields": List[str]}
    _BUILT_IN_SCHEMA: Dict[str, Dict[str, Any]] = {
        EventType.INTENT_RESULT:    {"version": "1.0", "required_fields": ["expectation"]},
        EventType.CLARIFICATION:    {"version": "1.0", "required_fields": ["clarification_id", "ui_schema"]},
        EventType.PROGRESS:         {"version": "1.0", "required_fields": ["stage", "status"]},
        EventType.TASKGRAPH_UPDATE: {"version": "1.0", "required_fields": ["task_graph_id"]},
        EventType.ERROR:            {"version": "1.0", "required_fields": ["code", "message"]},
        EventType.STATE_CHANGE:     {"version": "1.0", "required_fields": ["new_state"]},
        EventType.PONG:             {"version": "1.0", "required_fields": []},
    }
    _custom_schema: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def register(cls, event_type: str, schema: Optional[Dict[str, Any]] = None) -> None:
        """注册自定义事件类型（可选 Schema）。"""
        if not isinstance(event_type, str) or not event_type:
            raise ValueError("event_type must be a non-empty string")
        if event_type in cls._BUILT_IN_SCHEMA:
            raise ValueError(f"Cannot override built-in event type: {event_type}")
        cls._custom_schema[event_type] = schema or {"version": "1.0", "required_fields": []}

    @classmethod
    def is_valid(cls, event_type: str) -> bool:
        """检查事件类型是否合法（内置或已注册）。"""
        return event_type in cls._BUILT_IN_SCHEMA or event_type in cls._custom_schema

    @classmethod
    def validate(cls, event_type: str) -> None:
        """校验事件类型，非法时抛出 ValueError。"""
        if not cls.is_valid(event_type):
            all_types = set(cls._BUILT_IN_SCHEMA.keys()) | set(cls._custom_schema.keys())
            raise ValueError(
                f"Unknown event type '{event_type}'. "
                f"Legal types: {sorted(all_types)}"
            )

    @classmethod
    def validate_payload(cls, event_type: str, payload: Dict[str, Any]) -> List[str]:
        """
        校验 payload 是否包含必需字段。返回错误列表（空列表表示有效）。
        未知事件类型不报错，直接返回 []（由 validate 负责类型检查）。
        """
        schema = cls._BUILT_IN_SCHEMA.get(event_type) or cls._custom_schema.get(event_type)
        if schema is None:
            return [f"Unknown event type: {event_type}"]
        errors: List[str] = []
        for field in schema.get("required_fields", []):
            if field not in payload:
                errors.append(f"Missing required field: {field}")
        return errors

    @classmethod
    def get_schema(cls, event_type: str) -> Optional[Dict[str, Any]]:
        """获取事件 Schema（含版本和必需字段）。"""
        return cls._BUILT_IN_SCHEMA.get(event_type) or cls._custom_schema.get(event_type)

    @classmethod
    def list_all(cls) -> List[str]:
        """返回所有合法事件类型（含版本）。"""
        result = []
        for et, meta in cls._BUILT_IN_SCHEMA.items():
            result.append(f"{et}@v{meta['version']}")
        for et, meta in cls._custom_schema.items():
            result.append(f"{et}@v{meta['version']}(custom)")
        return sorted(result)

    @classmethod
    def unregister(cls, event_type: str) -> None:
        """注销自定义事件类型（不能注销内置类型）。"""
        if event_type in cls._BUILT_IN_SCHEMA:
            raise ValueError(f"Cannot unregister built-in event type '{event_type}'")
        cls._custom_schema.pop(event_type, None)


@dataclass
class WebSocketEvent:
    """WebSocket 事件基类。"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    event_type: str = ""
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> WebSocketEvent:
        return cls(
            event_id=d.get("event_id", str(uuid.uuid4())[:8]),
            event_type=d.get("event_type", ""),
            timestamp=d.get("timestamp", time.time()),
            session_id=d.get("session_id", ""),
            payload=d.get("payload", {}),
        )


# ── 具体事件构造器 ────────────────────────────────────────────────────────

class EventBuilder:
    """便捷的事件构造器。"""

    @staticmethod
    def build(
        event_type: str,
        session_id: str,
        payload: Dict[str, Any],
    ) -> WebSocketEvent:
        """通用构造器：使用注册表验证类型和 payload Schema。"""
        EventTypeRegistry.validate(event_type)
        errors = EventTypeRegistry.validate_payload(event_type, payload)
        if errors:
            import logging
            logging.getLogger("EventBuilder").warning(
                "Payload validation warnings for %s: %s", event_type, errors
            )
        return WebSocketEvent(
            event_type=event_type,
            session_id=session_id,
            payload=payload,
        )

    @staticmethod
    def intent_result(
        session_id: str,
        message_id: str,
        status: str,
        intent_result: Optional[Dict[str, Any]] = None,
        clarification: Optional[Dict[str, Any]] = None,
        latency_ms: float = 0.0,
        trace_log: Optional[List[str]] = None,
    ) -> WebSocketEvent:
        """构建意图结果事件。"""
        return WebSocketEvent(
            event_type=EventType.INTENT_RESULT,
            session_id=session_id,
            payload={
                "message_id": message_id,
                "status": status,
                "intent_result": intent_result,
                "clarification": clarification,
                "latency_ms": latency_ms,
                "trace_log": trace_log or [],
            },
        )

    @staticmethod
    def clarification(
        session_id: str,
        clarification_id: str,
        message: str,
        ui_schema: Dict[str, Any],
        timeout_seconds: int = 60,
    ) -> WebSocketEvent:
        """构建澄清请求事件。"""
        return WebSocketEvent(
            event_type=EventType.CLARIFICATION,
            session_id=session_id,
            payload={
                "clarification_id": clarification_id,
                "message": message,
                "ui_schema": ui_schema,
                "timeout_seconds": timeout_seconds,
                "deadline": time.time() + timeout_seconds,
            },
        )

    @staticmethod
    def progress(
        session_id: str,
        message_id: str,
        stage: str,
        status: str,                              # started | completed | skipped
        detail: Optional[str] = None,
        elapsed_ms: float = 0.0,
        estimated_total_ms: Optional[float] = None,
    ) -> WebSocketEvent:
        """构建解析进度事件。"""
        return WebSocketEvent(
            event_type=EventType.PROGRESS,
            session_id=session_id,
            payload={
                "message_id": message_id,
                "stage": stage,
                "status": status,
                "detail": detail,
                "elapsed_ms": elapsed_ms,
                "estimated_total_ms": estimated_total_ms,
            },
        )

    @staticmethod
    def taskgraph_update(
        session_id: str,
        update: TaskGraphUpdateEvent,
    ) -> WebSocketEvent:
        """构建任务图更新事件。"""
        return WebSocketEvent(
            event_type=EventType.TASKGRAPH_UPDATE,
            session_id=session_id,
            payload=update.to_dict(),
        )

    @staticmethod
    def error(
        session_id: str,
        code: str,
        message: str,
        retryable: bool = False,
        retry_after_ms: Optional[int] = None,
    ) -> WebSocketEvent:
        """构建错误事件。"""
        return WebSocketEvent(
            event_type=EventType.ERROR,
            session_id=session_id,
            payload={
                "code": code,
                "message": message,
                "retryable": retryable,
                "retry_after_ms": retry_after_ms,
            },
        )

    @staticmethod
    def state_change(
        session_id: str,
        old_state: str,
        new_state: str,
        event: str,
        description: str,
    ) -> WebSocketEvent:
        """构建 FSM 状态变化事件。"""
        return WebSocketEvent(
            event_type=EventType.STATE_CHANGE,
            session_id=session_id,
            payload={
                "old_state": old_state,
                "new_state": new_state,
                "trigger_event": event,
                "description": description,
            },
        )

    @staticmethod
    def pong(session_id: str, server_time: Optional[float] = None) -> WebSocketEvent:
        """构建心跳响应事件。"""
        return WebSocketEvent(
            event_type=EventType.PONG,
            session_id=session_id,
            payload={
                "server_time": server_time or time.time(),
            },
        )


# ── 事件序列化辅助 ────────────────────────────────────────────────────────

class EventSerializer:
    """事件序列化/反序列化。"""

    @staticmethod
    def serialize(event: WebSocketEvent) -> str:
        """序列化为 JSON 字符串。"""
        import json
        return json.dumps(event.to_dict(), ensure_ascii=False)

    @staticmethod
    def deserialize(raw: str) -> WebSocketEvent:
        """从 JSON 字符串反序列化。"""
        import json
        d = json.loads(raw)
        return WebSocketEvent.from_dict(d)

    @staticmethod
    def serialize_batch(events: List[WebSocketEvent]) -> str:
        """批量序列化。"""
        import json
        return json.dumps([e.to_dict() for e in events], ensure_ascii=False)
