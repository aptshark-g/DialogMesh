# -*- coding: utf-8 -*-
"""
core/agent/persistence/models.py
──────────────────────────────
Data models for session persistence.
Mirror of design_persistence.md §7.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from core.agent.pcr.datacontract import HistoryEntry


class SessionState(Enum):
    """会话生命周期状态。"""
    ACTIVE = "active"
    IDLE = "idle"
    CLARIFYING = "clarifying"
    CLOSED = "closed"
    EXPIRED = "expired"


@dataclass(frozen=False)
class Session:
    """会话数据模型 — 持久化核心。"""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:16])
    tenant_id: str = "default"
    user_id: Optional[str] = None
    version: int = 1  # 乐观锁版本号
    state: SessionState = SessionState.ACTIVE
    turn_count: int = 0
    history: List[TurnRecord] = field(default_factory=list)
    cognitive_profile: Dict[str, Any] = field(default_factory=dict)
    adaptive_thresholds: Dict[str, float] = field(default_factory=dict)
    fsm_state: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_activity_at: float = field(default_factory=time.time)

    def to_persistent_dict(self) -> Dict[str, Any]:
        """导出为持久化字典（不包含 history，history 单独存储）。"""
        return {
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "version": self.version,
            "state": self.state.value,
            "turn_count": self.turn_count,
            "cognitive_profile": self.cognitive_profile,
            "adaptive_thresholds": self.adaptive_thresholds,
            "fsm_state": self.fsm_state,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "last_activity_at": self.last_activity_at,
        }

    @classmethod
    def from_persistent_dict(cls, data: Dict[str, Any]) -> "Session":
        """从持久化字典恢复。"""
        return cls(
            session_id=data.get("session_id", str(uuid.uuid4())[:16]),
            tenant_id=data.get("tenant_id", "default"),
            user_id=data.get("user_id"),
            version=data.get("version", 1),
            state=SessionState(data.get("state", "active")),
            turn_count=data.get("turn_count", 0),
            history=[],  # history 单独加载
            cognitive_profile=data.get("cognitive_profile", {}),
            adaptive_thresholds=data.get("adaptive_thresholds", {}),
            fsm_state=data.get("fsm_state"),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", time.time()),
            last_activity_at=data.get("last_activity_at", time.time()),
        )

    def bump_version(self) -> None:
        """乐观锁版本递增。"""
        self.version += 1
        self.last_activity_at = time.time()

    def __repr__(self) -> str:
        return f"Session({self.session_id[:8]}..., turns={self.turn_count}, state={self.state.value})"


@dataclass(frozen=False)
class TurnRecord:
    """单轮对话记录。"""
    sequence: int = 0
    role: str = ""          # "user" | "assistant" | "system" | "tool"
    content: str = ""
    intent_result: Optional[Dict[str, Any]] = None
    execution_status: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sequence": self.sequence,
            "role": self.role,
            "content": self.content,
            "intent_result": self.intent_result,
            "execution_status": self.execution_status,
            "data": self.data,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TurnRecord":
        return cls(
            sequence=d.get("sequence", 0),
            role=d.get("role", ""),
            content=d.get("content", ""),
            intent_result=d.get("intent_result"),
            execution_status=d.get("execution_status"),
            data=d.get("data", {}),
            latency_ms=d.get("latency_ms", 0.0),
            timestamp=d.get("timestamp", time.time()),
            metadata=d.get("metadata", {}),
        )

    def to_history_entry(self) -> HistoryEntry:
        """转换为 PCR 所需的 HistoryEntry。"""
        return HistoryEntry(
            role=self.role,
            content=self.content,
            expectation=self.intent_result.get("expectation", "") if self.intent_result else "",
            timestamp=self.timestamp,
            metadata=self.metadata,
        )

    def __repr__(self) -> str:
        return f"TurnRecord(seq={self.sequence}, role={self.role}, content={self.content[:30]!r}...)"


@dataclass(frozen=False)
class SessionSummary:
    """会话列表展示用摘要。"""
    session_id: str
    last_active: float
    turn_count: int
    state: str
    health_score: float = 0.0

    def __repr__(self) -> str:
        return f"SessionSummary({self.session_id[:8]}..., turns={self.turn_count}, state={self.state})"
