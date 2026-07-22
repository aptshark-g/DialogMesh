"""Association Subscriber — cold path, Event Sourcing.

Subscribes to 6 event types. Triggered on topic switch or behavior pattern.
Produces: ASSOCIATION_DISCOVERED, CAUSAL_CLOSURE.
"""

from __future__ import annotations
from dataclasses import dataclass
import logging
from .api_event_log import EventLog
from .event_bus import EventBus, EventType

logger = logging.getLogger(__name__)


@dataclass
class AssociationState:
    current_intent: str = "UNKNOWN"
    topic_shift_count: int = 0
    behavior_count: int = 0
    cohesion: float = 1.0


class AssociationSubscriber:
    """Subscribes to: PCR, Route, Intent, Discourse, Topic, Behavior. Triggered on topic switch."""

    def __init__(self, event_log: EventLog, bus: EventBus):
        self._log = event_log
        self._bus = bus
        self._last_seq = 0
        self._state = AssociationState()

        for et in (EventType.PCR_COMPUTED, EventType.ROUTE_GENERATED,
                   EventType.INTENT_PARSED, EventType.REPLY_GENERATED,
                   EventType.BEHAVIOR_RECORDED):
            self._bus.subscribe(et, "assoc", self._on_event)

    def _on_event(self, event: dict):
        kind = event.get("kind", "")
        payload = event.get("payload", {})

        if kind == "intent_parsed":
            self._state.current_intent = payload.get("category", "UNKNOWN")
        elif kind == "behavior_recorded":
            self._state.behavior_count += 1

        if self._should_discover():
            self._discover_and_publish()

    def _should_discover(self) -> bool:
        return self._state.topic_shift_count >= 2 or self._state.behavior_count >= 10

    def _discover_and_publish(self):
        self._bus.publish("association_discovered", {
            "intent": self._state.current_intent,
            "behavior_count": self._state.behavior_count,
        })
