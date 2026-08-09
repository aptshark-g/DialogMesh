# -*- coding: utf-8 -*-
"""
service/protocol/fsm.py
───────────────────────
多轮澄清有限状态机（§13.4）。

管理用户从发消息到澄清、重新解析、执行、超时的完整交互状态流转。
防止无限澄清循环，支持超时检测和状态持久化。
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel, Field, ConfigDict


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举定义
# ═══════════════════════════════════════════════════════════════════════════════

class ClarificationState(str, Enum):
    """Clarification FSM 状态。"""

    START = "START"
    """初始状态：用户发送新消息，尚未开始解析"""
    PARSING = "PARSING"
    """正在解析：前端可展示'思考中'动画"""
    ACTIONABLE = "ACTIONABLE"
    """解析完成且无歧义，可直接执行"""
    CLARIFYING = "CLARIFYING"
    """解析有歧义，等待用户澄清"""
    RE_PARSING = "RE_PARSING"
    """收到澄清回复，正在重新解析"""
    EXPIRED = "EXPIRED"
    """澄清超时，使用默认/保守策略继续"""
    CLOSED = "CLOSED"
    """会话关闭，状态机终止"""


class ClarificationEvent(str, Enum):
    """触发状态转换的事件。"""

    USER_MESSAGE = "user_message"
    """用户发送新消息"""
    PARSE_COMPLETE_NO_AMBIGUITY = "parse_complete_no_ambiguity"
    """解析完成，无歧义"""
    PARSE_COMPLETE_HAS_AMBIGUITY = "parse_complete_has_ambiguity"
    """解析完成，存在歧义"""
    USER_CLARIFY = "user_clarify"
    """用户在超时前提交澄清回复"""
    TIMEOUT = "timeout"
    """澄清等待超时"""
    REPARSE_COMPLETE_NO_AMBIGUITY = "reparse_complete_no_ambiguity"
    """重新解析完成，无歧义"""
    REPARSE_COMPLETE_HAS_AMBIGUITY = "reparse_complete_has_ambiguity"
    """重新解析完成，仍有歧义"""
    FALLBACK_COMPLETE = "fallback_complete"
    """超时后使用默认策略生成结果"""
    CLOSE = "close"
    """会话关闭"""


# ═══════════════════════════════════════════════════════════════════════════════
# 状态转换表
# ═══════════════════════════════════════════════════════════════════════════════

TRANSITIONS: Dict[Tuple[str, str], str] = {
    (ClarificationState.START, ClarificationEvent.USER_MESSAGE): ClarificationState.PARSING,
    (ClarificationState.PARSING, ClarificationEvent.PARSE_COMPLETE_NO_AMBIGUITY): ClarificationState.ACTIONABLE,
    (ClarificationState.PARSING, ClarificationEvent.PARSE_COMPLETE_HAS_AMBIGUITY): ClarificationState.CLARIFYING,
    (ClarificationState.CLARIFYING, ClarificationEvent.USER_CLARIFY): ClarificationState.RE_PARSING,
    (ClarificationState.CLARIFYING, ClarificationEvent.TIMEOUT): ClarificationState.EXPIRED,
    (ClarificationState.RE_PARSING, ClarificationEvent.REPARSE_COMPLETE_NO_AMBIGUITY): ClarificationState.ACTIONABLE,
    (ClarificationState.RE_PARSING, ClarificationEvent.REPARSE_COMPLETE_HAS_AMBIGUITY): ClarificationState.CLARIFYING,
    (ClarificationState.EXPIRED, ClarificationEvent.FALLBACK_COMPLETE): ClarificationState.ACTIONABLE,
    (ClarificationState.ACTIONABLE, ClarificationEvent.USER_MESSAGE): ClarificationState.PARSING,
    (ClarificationState.START, ClarificationEvent.CLOSE): ClarificationState.CLOSED,
    (ClarificationState.PARSING, ClarificationEvent.CLOSE): ClarificationState.CLOSED,
    (ClarificationState.ACTIONABLE, ClarificationEvent.CLOSE): ClarificationState.CLOSED,
    (ClarificationState.CLARIFYING, ClarificationEvent.CLOSE): ClarificationState.CLOSED,
    (ClarificationState.RE_PARSING, ClarificationEvent.CLOSE): ClarificationState.CLOSED,
    (ClarificationState.EXPIRED, ClarificationEvent.CLOSE): ClarificationState.CLOSED,
}


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
# FSM 上下文
# ═══════════════════════════════════════════════════════════════════════════════

class ClarificationFSMContext(_CompatModel):
    """Clarification FSM 的持久化上下文，保存于会话存储中。"""

    session_id: str = Field(..., description="所属会话 ID")
    current_state: str = Field(
        default=ClarificationState.START,
        description="当前 FSM 状态",
    )
    clarification_count: int = Field(
        0,
        description="已进行的澄清轮次（防止无限循环）",
        ge=0,
    )
    max_clarifications: int = Field(
        5,
        description="最大允许澄清轮次",
        ge=1,
    )
    created_at: float = Field(
        default_factory=time.time,
        description="状态机创建时间（Unix 时间戳）",
    )
    last_transition_at: float = Field(
        default_factory=time.time,
        description="上次状态转换时间（Unix 时间戳）",
    )
    timeout_seconds: int = Field(
        60,
        description="澄清等待超时时间（秒）",
        ge=1,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FSM 主类
# ═══════════════════════════════════════════════════════════════════════════════

class ClarificationFSM:
    """多轮澄清有限状态机。

    用法：
        ctx = ClarificationFSMContext(session_id="sess-123")
        fsm = ClarificationFSM(ctx)
        new_state, payload = fsm.handle_event("user_message", {})
    """

    DEFAULT_MAX_CLARIFICATIONS: int = 5
    DEFAULT_TIMEOUT_SECONDS: int = 60

    def __init__(self, context: Optional[ClarificationFSMContext] = None) -> None:
        """初始化 FSM。

        Args:
            context: 持久化上下文。为 None 时自动创建新上下文。
        """
        self.context = context or ClarificationFSMContext(
            session_id=str(uuid.uuid4())[:12]
        )

    # ── 核心 API ─────────────────────────────────────────────────────────────

    def handle_event(
        self,
        event: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """处理状态转换事件。

        Args:
            event: 事件名称，如 "user_message"、"timeout" 等。
            payload: 事件附带的任意数据，透传给响应。

        Returns:
            (new_state, response_payload): 新状态（字符串）与可选的响应负载。
        """
        payload = payload or {}
        current = self.context.current_state

        # 检查是否允许转换
        if not self.can_transition(event):
            # 不合法的转换：保持当前状态，返回错误提示
            return current, {
                "error": f"非法状态转换：{current} --{event}--> ?",
                "allowed_events": self.get_allowed_events(),
            }

        # 执行转换
        new_state = TRANSITIONS[(current, event)]
        self.context.current_state = new_state
        self.context.last_transition_at = time.time()

        # 澄清计数逻辑
        if new_state == ClarificationState.CLARIFYING:
            self.context.clarification_count += 1

        # 构建响应 payload
        response_payload: Dict[str, Any] = {
            "previous_state": current,
            "new_state": new_state,
            "clarification_count": self.context.clarification_count,
            "max_clarifications": self.context.max_clarifications,
            **payload,
        }

        # 超时/上限特殊处理
        if new_state == ClarificationState.EXPIRED:
            response_payload["reason"] = "clarification_timeout"
            response_payload["timeout_seconds"] = self.context.timeout_seconds

        if self.context.clarification_count >= self.context.max_clarifications:
            if new_state == ClarificationState.CLARIFYING:
                # 达到最大澄清次数，强制转为 EXPIRED
                self.context.current_state = ClarificationState.EXPIRED
                response_payload["previous_state"] = new_state
                response_payload["new_state"] = ClarificationState.EXPIRED
                response_payload["reason"] = "max_clarifications_reached"

        return self.context.current_state, response_payload

    def can_transition(self, event: str) -> bool:
        """检查在当前状态下是否可以处理给定事件。

        Args:
            event: 事件名称。

        Returns:
            True 如果转换合法，否则 False。
        """
        return (self.context.current_state, event) in TRANSITIONS

    def get_allowed_events(self) -> list[str]:
        """获取当前状态下允许的所有事件列表。"""
        return [
            evt for (st, evt) in TRANSITIONS.keys() if st == self.context.current_state
        ]

    def is_expired(self) -> bool:
        """检查当前 CLARIFYING 状态是否已超时。

        Returns:
            True 如果当前状态为 CLARIFYING 且已超过 timeout_seconds。
        """
        if self.context.current_state != ClarificationState.CLARIFYING:
            return False
        elapsed = time.time() - self.context.last_transition_at
        return elapsed > self.context.timeout_seconds

    def can_clarify_more(self) -> bool:
        """检查是否还能继续澄清（未达上限）。"""
        return self.context.clarification_count < self.context.max_clarifications

    # ── 序列化 ───────────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """将 FSM 状态序列化为字典，用于持久化存储。"""
        return {
            "context": self.context.dict(),
            "current_state": self.context.current_state,
            "clarification_count": self.context.clarification_count,
            "max_clarifications": self.context.max_clarifications,
            "timeout_seconds": self.context.timeout_seconds,
            "created_at": self.context.created_at,
            "last_transition_at": self.context.last_transition_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClarificationFSM":
        """从字典恢复 FSM 状态。

        Args:
            data: 由 `to_dict()` 生成的字典。

        Returns:
            恢复后的 ClarificationFSM 实例。
        """
        ctx_data = data.get("context", {})
        if isinstance(ctx_data, dict):
            context = ClarificationFSMContext.model_validate(ctx_data)
        else:
            context = ClarificationFSMContext()
        # 覆盖可能存储在顶层的历史字段
        context.current_state = data.get("current_state", context.current_state)
        context.clarification_count = data.get(
            "clarification_count", context.clarification_count
        )
        context.max_clarifications = data.get(
            "max_clarifications", context.max_clarifications
        )
        context.timeout_seconds = data.get(
            "timeout_seconds", context.timeout_seconds
        )
        context.created_at = data.get("created_at", context.created_at)
        context.last_transition_at = data.get(
            "last_transition_at", context.last_transition_at
        )
        return cls(context)

    def __repr__(self) -> str:
        return (
            f"ClarificationFSM(state={self.context.current_state}, "
            f"clarifications={self.context.clarification_count}/{self.context.max_clarifications}, "
            f"session={self.context.session_id})"
        )
