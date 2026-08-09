"""Meta Subscriber — cold path, Event Sourcing.

Subscribes to 8 event types. Runs every 5 ticks.
Produces: META_REVIEWED, ANOMALY_DETECTED.

G2-P6: 迁移到 EventBus v2（core.agent.event.event_bus），
同步桥 subscribe_sync/publish_sync（CLI 引擎同步路径可用）。

M5（2026-08-05）: 写路径接线修复
  - M5-M1: _review_and_publish 现在写回 FeedbackBridge（post_decision）——
    修复「post_decision 零调用方 → FeedbackBridge 恒空」。
  - M5-M2: 新增显式 subscribe()（幂等）；bus 可用时 __init__ 自动订阅，
    cli/engine 延迟接线后也调用 subscribe()——修复「实例存在、从未订阅」。
"""

from __future__ import annotations
from dataclasses import dataclass, field
import logging
from typing import Any, Optional
from core.agent.api.api_event_log import EventLog

logger = logging.getLogger(__name__)

# G2-P6: 订阅主题（v2 subject 单 token，与 engine._publish kind 对齐）
SUBSCRIBED_KINDS = (
    "pcr_computed", "route_generated", "intent_parsed", "reply_generated",
    "profile_updated", "behavior_recorded", "abc_evaluated", "mind_learned",
)


@dataclass
class MetaState:
    behavior_count: int = 0
    last_trust: float = 0.5
    profile_drift: float = 0.0


class MetaSubscriber:
    def __init__(self, event_log: Optional[EventLog] = None, bus: Any = None,
                 feedback_bridge: Any = None):
        self._log = event_log
        self._bus = bus
        self._bridge = feedback_bridge
        self._turn_count = 0
        self._state = MetaState()

        if self._bus is not None:
            self.subscribe()

    # ── 订阅接线（M5-M2）──────────────────────────────────────

    def subscribe(self) -> bool:
        """显式订阅（幂等）。bus 为空或已订阅时安全返回。"""
        if self._bus is None:
            return False
        sub = getattr(self._bus, "subscribe_sync", None)
        if sub is None:
            return False
        for kind in SUBSCRIBED_KINDS:
            sub(kind, self._on_msg)
        return True

    def _on_msg(self, msg: Any):
        """v2 Event(subject, data) → dict 事件。"""
        self._on_event({
            "kind": getattr(msg, "subject", ""),
            "payload": getattr(msg, "data", None) or {},
        })

    def _publish(self, kind: str, payload: dict):
        if self._bus is None:
            return
        pub = getattr(self._bus, "publish_sync", None)
        if pub is not None:
            pub(kind, payload)
        else:
            self._bus.publish(kind, payload)

    def _on_event(self, event: dict):
        kind = event.get("kind", "")
        payload = event.get("payload", {})
        self._turn_count += 1

        if kind == "behavior_recorded":
            self._state.behavior_count += 1
        elif kind == "profile_updated":
            trust = payload.get('trust', 0.5)
            if abs(trust - self._state.last_trust) > 0.3:
                self._state.profile_drift = abs(trust - self._state.last_trust)
            self._state.last_trust = trust

        if self._should_review():
            self._review_and_publish()

    def _should_review(self) -> bool:
        return (self._turn_count > 0 and self._turn_count % 5 == 0 or
                self._state.profile_drift > 0.3 or
                self._state.behavior_count >= 5)

    def _review_and_publish(self):
        findings = {"turn": self._turn_count, "behavior_count": self._state.behavior_count,
                    "profile_drift": self._state.profile_drift, "action": "none"}
        if self._state.profile_drift > 0.3:
            findings["action"] = "recalibrate_profile"
            self._publish("anomaly_detected", {"type": "profile_drift"})
        self._publish("meta_reviewed", findings)

        # M5-M1: 写回 FeedbackBridge（冷→热三层反馈；此前 post_decision 零调用方）
        if self._bridge is not None:
            try:
                from core.agent.meta.feedback_bridge import MetaDecision
                decision = MetaDecision(
                    tick=self._turn_count,
                    confidence=0.6 if self._state.profile_drift > 0.3 else 0.4,
                )
                if self._state.profile_drift > 0.3:
                    decision.urgent_correction = {
                        "type": "profile_drift",
                        "drift": self._state.profile_drift,
                        "action": "recalibrate_profile",
                    }
                elif self._state.behavior_count >= 5:
                    decision.belief_update = {
                        "type": "behavior_pattern",
                        "behavior_count": self._state.behavior_count,
                        "action": "review_patterns",
                    }
                else:
                    decision.parameter_shift = {
                        "type": "periodic_review",
                        "turn": self._turn_count,
                        "action": "none",
                    }
                self._bridge.post_decision(decision)
            except Exception as e:
                logger.debug("FeedbackBridge post failed: %s", e)
