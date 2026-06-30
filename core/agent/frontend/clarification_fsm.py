# -*- coding: utf-8 -*-
"""
core/agent/frontend/clarification_fsm.py
─────────────────────────────────────────
多轮澄清有限状态机（Layer 3，v2.4 新增）。

管理多轮澄清交互状态：
  START → PARSING → ACTIONABLE/CLARIFYING → RE_PARSING → ... → EXPIRED/CLOSED

状态转换触发：
  - START → PARSING: 收到用户消息
  - PARSING → ACTIONABLE: 解析无歧义
  - PARSING → CLARIFYING: 解析有歧义
  - CLARIFYING → RE_PARSING: 收到用户澄清回复
  - CLARIFYING → EXPIRED: 超时
  - RE_PARSING → ACTIONABLE: 重新解析无歧义
  - RE_PARSING → CLARIFYING: 重新解析仍有歧义（下一轮）
  - EXPIRED → ACTIONABLE: 使用默认策略继续
  - ACTIONABLE → START: 用户发送新消息（下一轮）
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.agent.frontend.clarification_ui import (
    ClarificationUISchema, UIComponent, UIOption, UIValidation,
    ClarificationUIFactory,
)


class ClarificationState:
    """状态常量。"""
    START = "START"                          # 初始状态（用户发送新消息）
    PARSING = "PARSING"                       # 正在解析（前端展示"思考中"）
    ACTIONABLE = "ACTIONABLE"                 # 解析无歧义，可直接执行
    CLARIFYING = "CLARIFYING"                 # 解析有歧义，等待用户澄清
    RE_PARSING = "RE_PARSING"                 # 收到澄清回复，重新解析
    EXPIRED = "EXPIRED"                       # 澄清超时，使用默认策略
    CLOSED = "CLOSED"                         # 会话关闭

    # ── 外部状态映射（P3 修复增强：状态分层 + 双向映射 + 历史追溯）────────────
    # 7 个内部状态 → 5 个外部状态（前端/监控只关心 5 个外部状态）
    EXTERNAL_STATE_MAP: Dict[str, str] = {
        START: "idle",
        PARSING: "processing",
        RE_PARSING: "processing",
        ACTIONABLE: "idle",
        CLARIFYING: "clarifying",
        EXPIRED: "error",
        CLOSED: "closed",
    }

    # 反向映射：外部状态 → 可能对应的内部状态列表
    REVERSE_STATE_MAP: Dict[str, List[str]] = {}
    for _int, _ext in EXTERNAL_STATE_MAP.items():
        REVERSE_STATE_MAP.setdefault(_ext, []).append(_int)

    # 状态描述（前端展示用）
    STATE_DESCRIPTIONS: Dict[str, str] = {
        START: "等待用户输入...",
        PARSING: "正在分析意图...",
        ACTIONABLE: "意图已明确，可执行。",
        CLARIFYING: "需要更多信息，请澄清。",
        RE_PARSING: "收到澄清，重新分析...",
        EXPIRED: "澄清超时，使用默认策略。",
        CLOSED: "会话已关闭。",
    }

    # 外部状态描述
    EXTERNAL_DESCRIPTIONS: Dict[str, str] = {
        "idle": "空闲（等待用户新消息）",
        "processing": "处理中（解析或重新解析）",
        "clarifying": "需要用户澄清",
        "error": "超时/错误（使用默认策略）",
        "closed": "会话已关闭",
    }

    @classmethod
    def to_external_state(cls, internal_state: str) -> str:
        """将内部状态映射为外部状态（供前端/监控使用）。"""
        return cls.EXTERNAL_STATE_MAP.get(internal_state, "unknown")

    @classmethod
    def from_external_state(cls, external_state: str) -> List[str]:
        """将外部状态反向映射为可能的内部状态列表（供调试/诊断使用）。"""
        return cls.REVERSE_STATE_MAP.get(external_state, [])

    @classmethod
    def list_external_states(cls) -> List[str]:
        """返回所有合法外部状态。"""
        return list(dict.fromkeys(cls.EXTERNAL_STATE_MAP.values()))

    @classmethod
    def describe_internal(cls, state: str) -> str:
        """获取内部状态描述。"""
        return cls.STATE_DESCRIPTIONS.get(state, f"未知状态: {state}")

    @classmethod
    def describe_external(cls, state: str) -> str:
        """获取外部状态描述。"""
        return cls.EXTERNAL_DESCRIPTIONS.get(state, f"未知状态: {state}")


class StateTransitionLog:
    """状态转换历史记录（增强版）。"""

    def __init__(self):
        self._entries: List[Dict[str, Any]] = []

    def record(self, from_state: str, to_state: str, event: str,
               payload_summary: Optional[str] = None, *, debug_mode: bool = False) -> None:
        """记录一次状态转换。"""
        entry: Dict[str, Any] = {
            "timestamp": time.time(),
            "from_state": from_state,
            "to_state": to_state,
            "from_external": ClarificationState.to_external_state(from_state),
            "to_external": ClarificationState.to_external_state(to_state),
            "event": event,
            "payload_summary": payload_summary,
        }
        if debug_mode:
            entry["from_description"] = ClarificationState.describe_internal(from_state)
            entry["to_description"] = ClarificationState.describe_internal(to_state)
        self._entries.append(entry)

    def entries(self) -> List[Dict[str, Any]]:
        return list(self._entries)

    def to_dict(self) -> List[Dict[str, Any]]:
        return self.entries()

    def last_transition(self) -> Optional[Dict[str, Any]]:
        return self._entries[-1] if self._entries else None

    def transitions_by_external(self, external_state: str) -> List[Dict[str, Any]]:
        """获取所有转换到指定外部状态的历史记录。"""
        return [e for e in self._entries if e.get("to_external") == external_state]

    def summary(self) -> Dict[str, Any]:
        """返回转换历史摘要。"""
        from collections import Counter
        states = Counter(e["to_state"] for e in self._entries)
        ext_states = Counter(e["to_external"] for e in self._entries)
        return {
            "total_transitions": len(self._entries),
            "state_counts": dict(states),
            "external_state_counts": dict(ext_states),
            "first_at": self._entries[0]["timestamp"] if self._entries else None,
            "last_at": self._entries[-1]["timestamp"] if self._entries else None,
        }


class ClarificationEvent:
    """事件常量。"""
    USER_MESSAGE = "user_message"              # 用户发送新消息
    PARSE_COMPLETE_NO_AMBIGUITY = "parse_complete_no_ambiguity"  # 解析无歧义
    PARSE_COMPLETE_HAS_AMBIGUITY = "parse_complete_has_ambiguity"  # 解析有歧义
    USER_CLARIFY = "user_clarify"             # 用户提交澄清回复
    TIMEOUT = "timeout"                        # 澄清超时
    REPARSE_COMPLETE_NO_AMBIGUITY = "reparse_complete_no_ambiguity"  # 重新解析无歧义
    REPARSE_COMPLETE_HAS_AMBIGUITY = "reparse_complete_has_ambiguity"  # 重新解析仍有歧义
    FALLBACK_COMPLETE = "fallback_complete"    # 默认策略生成结果


# ── 状态转换表 ──────────────────────────────────────────────────────────

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
}


# ── 状态机 ──────────────────────────────────────────────────────────────

@dataclass
class ClarificationFSMContext:
    """状态机上下文。"""
    session_id: str
    state: str = ClarificationState.START
    clarification_count: int = 0           # 当前澄清轮次
    last_clarification_id: Optional[str] = None
    clarification_deadline: float = 0.0    # 澄清超时截止时间
    max_clarifications: int = 5            # 最大澄清轮次（防止死循环）
    history: List[Dict[str, Any]] = field(default_factory=list)  # 状态转换历史

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "state": self.state,
            "clarification_count": self.clarification_count,
            "last_clarification_id": self.last_clarification_id,
            "clarification_deadline": self.clarification_deadline,
            "max_clarifications": self.max_clarifications,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ClarificationFSMContext:
        return cls(
            session_id=d["session_id"],
            state=d.get("state", ClarificationState.START),
            clarification_count=d.get("clarification_count", 0),
            last_clarification_id=d.get("last_clarification_id"),
            clarification_deadline=d.get("clarification_deadline", 0.0),
            max_clarifications=d.get("max_clarifications", 5),
            history=d.get("history", []),
        )


class ClarificationFSM:
    """多轮澄清有限状态机。"""

    # 各状态对应的前端展示信息
    STATE_DESCRIPTIONS = {
        ClarificationState.START: "等待用户输入...",
        ClarificationState.PARSING: "正在分析意图...",
        ClarificationState.ACTIONABLE: "意图已明确，可执行。",
        ClarificationState.CLARIFYING: "需要更多信息，请澄清。",
        ClarificationState.RE_PARSING: "收到澄清，重新分析...",
        ClarificationState.EXPIRED: "澄清超时，使用默认策略。",
        ClarificationState.CLOSED: "会话已关闭。",
    }

    # 超时时间（秒）
    CLARIFICATION_TIMEOUT = 60.0

    def __init__(self, context: Optional[ClarificationFSMContext] = None):
        self.context = context or ClarificationFSMContext(session_id="")
        self._transitions = TRANSITIONS

    @property
    def current_state(self) -> str:
        return self.context.state

    def can_transition(self, event: str) -> bool:
        """检查当前状态下是否允许给定事件。"""
        return (self.current_state, event) in self._transitions

    def handle_event(self, event: str,
                     payload: Optional[Dict[str, Any]] = None) -> Tuple[str, Optional[Any]]:
        """
        处理状态转换事件。

        返回: (new_state, response_payload)
        - response_payload: 前端需要的响应数据（ClarificationUISchema 或 None）
        """
        payload = payload or {}
        key = (self.current_state, event)

        if key not in self._transitions:
            # 无效转换：保持在当前状态，返回错误信息
            return self.current_state, {
                "error": f"Invalid transition: {self.current_state} + {event}",
                "state_description": self.STATE_DESCRIPTIONS.get(self.current_state, ""),
            }

        new_state = self._transitions[key]
        old_state = self.current_state
        self.context.state = new_state

        # 特殊处理：进入 CLARIFYING 状态前生成 clarification_id
        if new_state == ClarificationState.CLARIFYING:
            self.context.clarification_count += 1
            self.context.clarification_deadline = time.time() + self.CLARIFICATION_TIMEOUT
            import uuid
            self.context.last_clarification_id = f"clarify-{uuid.uuid4().hex[:8]}"

        # 记录历史
        self.context.history.append({
            "timestamp": time.time(),
            "from_state": old_state,
            "to_state": new_state,
            "event": event,
            "payload_summary": str(payload.keys()) if payload else None,
        })

        # 根据新状态生成响应
        response = self._generate_response(new_state, payload)

        # 特殊处理：ACTIONABLE 或 EXPIRED 重置澄清状态
        if new_state in (ClarificationState.ACTIONABLE, ClarificationState.EXPIRED):
            self.context.clarification_deadline = 0.0

        return new_state, response

    def _generate_response(self, state: str, payload: Dict[str, Any]) -> Optional[Any]:
        """根据状态生成前端响应。"""
        if state == ClarificationState.PARSING:
            # 前端展示"思考中"动画
            return {
                "type": "progress",
                "message": "正在分析您的意图...",
                "ui_schema": ClarificationUIFactory.create_progress_indicator(
                    "正在分析...",
                ).to_dict(),
            }

        elif state == ClarificationState.CLARIFYING:
            # 生成澄清 UI
            ambiguities = payload.get("ambiguities", [])
            if not ambiguities:
                # 没有具体歧义信息，返回通用澄清
                return {
                    "type": "clarification",
                    "clarification_id": self.context.last_clarification_id,
                    "ui_schema": ClarificationUIFactory.create_value_input(
                        "补充信息",
                        expected_type="text",
                    ).to_dict(),
                }

            # 根据第一个歧义类型生成特定 UI
            first_ambiguity = ambiguities[0]
            ambiguity_type = first_ambiguity.get("type", "unknown")
            ui_schema = None

            if ambiguity_type == "ambiguous_process":
                candidates = first_ambiguity.get("candidates", [])
                ui_schema = ClarificationUIFactory.create_process_selector(candidates)
            elif ambiguity_type == "ambiguous_address":
                addresses = first_ambiguity.get("addresses", [])
                ui_schema = ClarificationUIFactory.create_address_selector(addresses)
            elif ambiguity_type == "missing_value":
                field = first_ambiguity.get("field", "信息")
                expected_type = first_ambiguity.get("expected_type", "text")
                ui_schema = ClarificationUIFactory.create_value_input(field, expected_type)
            elif ambiguity_type == "destructive_action":
                desc = first_ambiguity.get("description", "该操作")
                ui_schema = ClarificationUIFactory.create_dangerous_confirm(desc)
            elif ambiguity_type == "unknown_intent":
                suggestions = first_ambiguity.get("suggestions", [])
                hint = first_ambiguity.get("hint", "请明确您的意图")
                ui_schema = ClarificationUIFactory.create_tutorial_hint(hint, suggestions)
            else:
                ui_schema = ClarificationUIFactory.create_value_input("补充信息")

            return {
                "type": "clarification",
                "clarification_id": self.context.last_clarification_id,
                "ui_schema": ui_schema.to_dict() if ui_schema else None,
            }

        elif state == ClarificationState.RE_PARSING:
            # 重新解析中，展示进度
            return {
                "type": "progress",
                "message": "正在根据您的回复重新分析...",
                "ui_schema": ClarificationUIFactory.create_progress_indicator(
                    "重新分析中...",
                ).to_dict(),
            }

        elif state == ClarificationState.EXPIRED:
            # 超时，返回默认结果
            return {
                "type": "expired",
                "message": "澄清超时，已使用默认策略继续。",
                "fallback_result": payload.get("fallback_result"),
            }

        elif state == ClarificationState.ACTIONABLE:
            # 可执行，返回意图结果
            return {
                "type": "actionable",
                "message": "意图已明确。",
                "intent_result": payload.get("intent_result"),
            }

        elif state == ClarificationState.START:
            return {
                "type": "ready",
                "message": "等待输入...",
            }

        return None

    def check_timeout(self) -> Optional[str]:
        """
        检查是否超时。如果超时，返回 TIMEOUT 事件。
        应在定期心跳/轮询中调用。
        """
        if self.current_state == ClarificationState.CLARIFYING:
            if time.time() > self.context.clarification_deadline:
                return ClarificationEvent.TIMEOUT
        return None

    def is_clarification_deadline_reached(self) -> bool:
        """检查澄清是否已超时。"""
        if self.current_state != ClarificationState.CLARIFYING:
            return False
        return time.time() > self.context.clarification_deadline

    def can_clarify_more(self) -> bool:
        """检查是否还能继续澄清（防止死循环）。"""
        return self.context.clarification_count < self.context.max_clarifications

    def get_state_description(self) -> str:
        """获取当前状态的人类可读描述。"""
        return self.STATE_DESCRIPTIONS.get(self.current_state, f"未知状态: {self.current_state}")

    def to_dict(self) -> Dict[str, Any]:
        return self.context.to_dict()

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ClarificationFSM:
        context = ClarificationFSMContext.from_dict(d)
        return cls(context)
