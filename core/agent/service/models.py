# -*- coding: utf-8 -*-
"""
core/agent/service/models.py
────────────────────────────
服务层数据模型（v2.4 服务层新增）。

定义 Session、TurnRecord、请求/响应模型等数据契约。
设计原则：
  - 所有模型可序列化为 JSON（用于持久化和 API 响应）
  - 与核心引擎模型解耦，服务层做转换适配
  - 支持多租户隔离（tenant_id）
"""

from __future__ import annotations

import uuid
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class Session:
    """
    用户会话对象。
    活跃会话驻留内存，非活跃后异步持久化。
    """
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    tenant_id: str = "default"
    user_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_activity_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 3600)

    # 核心引擎状态（序列化后可恢复）
    parse_context: Optional[Dict[str, Any]] = None
    cognitive_profile: Optional[Dict[str, Any]] = None
    turn_count: int = 0

    # 对话历史
    history: List[TurnRecord] = field(default_factory=list)

    # 当前状态
    state: str = "active"  # "active" | "idle" | "clarifying" | "closed" | "expired"
    pending_clarification: Optional[str] = None
    clarification_fsm_state: Optional[Dict[str, Any]] = None  # 前端 FSM 状态（序列化）

    # 新增：PCR 阈值自适应（P0 修复：反馈闭环）
    adaptive_thresholds: Optional[Dict[str, float]] = None

    # 前端连接状态（仅内存，不持久化）
    ws_connections: List[str] = field(default_factory=list)

    def touch(self) -> None:
        """更新活动时间。"""
        self.last_activity_at = time.time()

    def to_persistent_dict(self) -> Dict[str, Any]:
        """序列化为持久化格式（不含 ws_connections）。"""
        return {
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "last_activity_at": self.last_activity_at,
            "expires_at": self.expires_at,
            "parse_context": self.parse_context,
            "cognitive_profile": self.cognitive_profile,
            "turn_count": self.turn_count,
            "history": [t.to_dict() for t in self.history],
            "state": self.state,
            "pending_clarification": self.pending_clarification,
            "clarification_fsm_state": self.clarification_fsm_state,
            "adaptive_thresholds": self.adaptive_thresholds,
        }

    @classmethod
    def from_persistent_dict(cls, data: Dict[str, Any]) -> Session:
        """从持久化数据恢复。"""
        sess = cls(
            session_id=data["session_id"],
            tenant_id=data.get("tenant_id", "default"),
            user_id=data.get("user_id"),
            created_at=data.get("created_at", time.time()),
            last_activity_at=data.get("last_activity_at", time.time()),
            expires_at=data.get("expires_at", time.time() + 3600),
            parse_context=data.get("parse_context"),
            cognitive_profile=data.get("cognitive_profile"),
            turn_count=data.get("turn_count", 0),
            state=data.get("state", "active"),
            pending_clarification=data.get("pending_clarification"),
            clarification_fsm_state=data.get("clarification_fsm_state"),
            adaptive_thresholds=data.get("adaptive_thresholds"),
        )
        # 恢复历史记录
        for t_data in data.get("history", []):
            sess.history.append(TurnRecord.from_dict(t_data))
        return sess


@dataclass
class TurnRecord:
    """单轮对话记录。"""
    sequence: int
    timestamp: float
    role: str = "user"  # "user" | "system" | "assistant" | "tool"
    content: str = ""
    modality: str = "text"
    intent_result: Optional[Dict[str, Any]] = None
    clarification: Optional[Dict[str, Any]] = None
    latency_ms: float = 0.0
    pcr_latency_ms: float = 0.0
    parser_latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TurnRecord:
        return cls(
            sequence=data["sequence"],
            timestamp=data["timestamp"],
            role=data.get("role", "user"),
            content=data.get("content", ""),
            modality=data.get("modality", "text"),
            intent_result=data.get("intent_result"),
            clarification=data.get("clarification"),
            latency_ms=data.get("latency_ms", 0.0),
            pcr_latency_ms=data.get("pcr_latency_ms", 0.0),
            parser_latency_ms=data.get("parser_latency_ms", 0.0),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SessionSummary:
    """会话关闭时的摘要。"""
    session_id: str
    closed_at: float
    total_turns: int
    final_state: str
    persisted: bool


@dataclass
class IntentResult:
    """意图解析结果（API 响应用）。"""
    expectation: str = "UNKNOWN"
    task_graph: Optional[Dict[str, Any]] = None
    entities: List[Dict[str, Any]] = field(default_factory=list)
    cognitive_profile: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClarificationPayload:
    """澄清请求负载（包含 UI Schema）。"""
    clarification_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    message: str = ""
    suggestions: List[str] = field(default_factory=list)
    timeout_seconds: int = 60
    required: bool = True
    ui_schema: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clarification_id": self.clarification_id,
            "message": self.message,
            "suggestions": self.suggestions,
            "timeout_seconds": self.timeout_seconds,
            "required": self.required,
            "ui_schema": self.ui_schema,
        }


@dataclass
class ParseProgressEvent:
    """解析进度事件（WebSocket 推送用）。"""
    message_id: str = ""
    stage: str = ""
    status: str = ""
    detail: Optional[str] = None
    elapsed_ms: float = 0.0
    estimated_total_ms: Optional[float] = None


@dataclass
class ErrorPayload:
    """错误响应。"""
    code: str = "INTERNAL_ERROR"
    message: str = ""
    retryable: bool = False
    retry_after_ms: Optional[int] = None
