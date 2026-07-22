"""EventBus — in-process ring buffer + pub/sub.

Design: docs/v5/DESIGN_HYBRID_ARCHITECTURE.md
Events are dicts from api_event_log.EventLog.
"""

from __future__ import annotations
import collections, logging
from enum import Enum
from typing import Callable, Dict, List, Tuple, Any

logger = logging.getLogger(__name__)


class EventType(Enum):
    MESSAGE_RECEIVED = "message_received"
    PCR_COMPUTED = "pcr_computed"
    ROUTE_GENERATED = "route_generated"
    INTENT_PARSED = "intent_parsed"
    PLAN_GENERATED = "plan_generated"
    CONTEXT_COMPILED = "context_compiled"
    REPLY_GENERATED = "reply_generated"
    PROFILE_UPDATED = "profile_updated"
    BEHAVIOR_RECORDED = "behavior_recorded"
    ABC_EVALUATED = "abc_evaluated"
    MIND_LEARNED = "mind_learned"
    META_REVIEWED = "meta_reviewed"
    ASSOCIATION_DISCOVERED = "association_discovered"
    ANOMALY_DETECTED = "anomaly_detected"


class EventBus:
    """Ring buffer + subscriber dispatch. Zero network, in-process only."""

    def __init__(self, buffer_size: int = 1024):
        self._buffer = collections.deque(maxlen=buffer_size)
        self._subscribers: Dict[EventType, List[Tuple[str, Callable]]] = (
            collections.defaultdict(list)
        )
        self._dropped_count = 0

    def publish(self, kind: str, payload: Dict[str, Any] = None):
        """Publish event dict to subscribers."""
        event = {"kind": kind, "payload": payload or {}}
        if len(self._buffer) >= self._buffer.maxlen:
            self._dropped_count += 1
        self._buffer.append(event)

        try:
            etype = EventType(kind)
        except ValueError:
            return

        for name, handler in self._subscribers.get(etype, []):
            try:
                handler(event)
            except Exception as e:
                logger.error("Subscriber '%s' failed on %s: %s", name, kind, e)

    def subscribe(self, event_type: EventType, name: str, handler: Callable):
        self._subscribers[event_type].append((name, handler))

    @property
    def dropped(self) -> int:
        return self._dropped_count

    @property
    def subscriber_count(self) -> int:
        return sum(len(v) for v in self._subscribers.values())
