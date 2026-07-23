"""DialogMesh v6 — GlobalDecider · 全局状态机

设计: DESIGN_GLOBAL_STATE_MACHINE.md + DESIGN_SYSTEM_SCHEDULER.md
模式: Command → Decider → Event → evolve → State

防止广播风暴: 每次只产生 1 个 Event。链间通信通过 Event Log 串行化。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import time
import logging

logger = logging.getLogger(__name__)


class EventType(Enum):
    MESSAGE_RECEIVED = "message_received"
    PCR_COMPUTED = "pcr_computed"
    INTENT_PARSED = "intent_parsed"
    PLAN_GENERATED = "plan_generated"
    CONTEXT_COMPILED = "context_compiled"
    REPLY_GENERATED = "reply_generated"
    PROFILE_UPDATED = "profile_updated"
    BEHAVIOR_RECORDED = "behavior_recorded"
    META_REVIEWED = "meta_reviewed"
    ABC_EVALUATED = "abc_evaluated"
    MIND_LEARNED = "mind_learned"
    NODE_EDITED = "node_edited"
    PATTERN_DISCOVERED = "pattern_discovered"
    PROFILE_DRIFTED = "profile_drifted"
    CONSTRAINT_VIOLATED = "constraint_violated"


@dataclass
class Event:
    type: EventType
    timestamp: float = field(default_factory=time.time)
    payload: Dict[str, Any] = field(default_factory=dict)
    source_chain: str = ""
    trace_id: str = ""


@dataclass
class Command:
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class StateSnapshot:
    """Snapshot of current system state across all chains."""
    pcr_expectation: str = "UNKNOWN"
    intent_category: str = "UNKNOWN"
    plan_task_count: int = 0
    context_entries: int = 0
    profile_trust: float = 0.5
    behavior_actions: int = 0
    meta_signals: int = 0
    abc_rules_fired: int = 0
    mind_relations: int = 0
    tick: int = 0


class GlobalDecider:
    """唯一决策入口 — 防止广播风暴。

    Temporal Workflow 映射:
      decide = Workflow.logic (产生 Event)
      evolve = apply Event → update State
      Activity = LLM call (外部操作, 可重试)

    关键: 每次只产生 1 个 Event。
    链间通信通过 Event Log → next tick 读取，不直接 push。
    """

    def __init__(self):
        self._event_log: List[Event] = []
        self._state = StateSnapshot()
        self._tick = 0

    @property
    def state(self) -> StateSnapshot:
        return self._state

    @property
    def event_log(self) -> List[Event]:
        return self._event_log

    def decide(self, command: Command) -> Event:
        """从当前状态+命令 → 产生事件。

        返回: 1个 Event。调用方执行 Activity (LLM call)，
              完成后调用 evolve() 更新状态。
        """
        event_type = self._map_command_to_event(command)
        event = Event(
            type=event_type,
            payload=command.payload,
            source_chain=command.type,
            trace_id=f"tick_{self._tick}",
        )
        return event

    def evolve(self, event: Event) -> StateSnapshot:
        """应用事件到状态 — 纯函数, 可重放。

        每个事件更新一个维度的状态, 不连锁触发其他链。
        多链联动由下一个 Tick 的 decide() 基于新状态决定。
        """
        self._event_log.append(event)
        self._tick += 1
        self._state.tick = self._tick

        if event.type == EventType.PCR_COMPUTED:
            self._state.pcr_expectation = event.payload.get("expectation", "UNKNOWN")

        elif event.type == EventType.INTENT_PARSED:
            self._state.intent_category = event.payload.get("category", "UNKNOWN")

        elif event.type == EventType.PLAN_GENERATED:
            self._state.plan_task_count = event.payload.get("task_count", 0)

        elif event.type == EventType.CONTEXT_COMPILED:
            self._state.context_entries = event.payload.get("entries", 0)

        elif event.type == EventType.REPLY_GENERATED:
            pass  # reply itself is the output, no state change needed here

        elif event.type == EventType.PROFILE_UPDATED:
            self._state.profile_trust = event.payload.get("trust", self._state.profile_trust)

        elif event.type == EventType.BEHAVIOR_RECORDED:
            self._state.behavior_actions += 1

        elif event.type == EventType.META_REVIEWED:
            self._state.meta_signals += 1

        elif event.type == EventType.ABC_EVALUATED:
            self._state.abc_rules_fired = event.payload.get("rules_fired", 0)

        elif event.type == EventType.MIND_LEARNED:
            self._state.mind_relations = event.payload.get("relations", 0)

        return self._state

    def _map_command_to_event(self, command: Command) -> EventType:
        """Map command type to the SINGLE event it produces."""
        mapping = {
            "user_message": EventType.MESSAGE_RECEIVED,
            "pcr": EventType.PCR_COMPUTED,
            "intent": EventType.INTENT_PARSED,
            "planning": EventType.PLAN_GENERATED,
            "context": EventType.CONTEXT_COMPILED,
            "llm": EventType.REPLY_GENERATED,
            "profile": EventType.PROFILE_UPDATED,
            "behavior": EventType.BEHAVIOR_RECORDED,
            "meta": EventType.META_REVIEWED,
            "abc": EventType.ABC_EVALUATED,
            "mind": EventType.MIND_LEARNED,
            "node_edit": EventType.NODE_EDITED,
        }
        return mapping.get(command.type, EventType.MESSAGE_RECEIVED)

    def stats(self) -> dict:
        return {
            "tick": self._tick,
            "events_logged": len(self._event_log),
            "state": self._state.__dict__,
        }
