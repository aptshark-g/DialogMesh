"""Meta Subscriber — cold path, Event Sourcing.

Subscribes to 8 event types. Runs every 5 ticks.
Produces: META_REVIEWED, ANOMALY_DETECTED.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import logging
from .api_event_log import EventLog
from .event_bus import EventBus, EventType

logger = logging.getLogger(__name__)


@dataclass
class MetaState:
    behavior_count: int = 0
    last_trust: float = 0.5
    profile_drift: float = 0.0


class MetaSubscriber:
    def __init__(self, event_log: EventLog, bus: EventBus):
        self._log = event_log
        self._bus = bus
        self._turn_count = 0
        self._state = MetaState()

        for et in (EventType.PCR_COMPUTED, EventType.ROUTE_GENERATED,
                   EventType.INTENT_PARSED, EventType.REPLY_GENERATED,
                   EventType.PROFILE_UPDATED, EventType.BEHAVIOR_RECORDED,
                   EventType.ABC_EVALUATED, EventType.MIND_LEARNED):
            self._bus.subscribe(et, "meta", self._on_event)

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
            self._bus.publish("anomaly_detected", {"type": "profile_drift"})
        self._bus.publish("meta_reviewed", findings)
