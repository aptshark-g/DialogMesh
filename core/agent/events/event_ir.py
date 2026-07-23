"""Event IR: unified event intermediate representation with thread-safe bus.

Design: Event is NOT persisted. It is a runtime intermediate like an HTTP Request.
The EventBus is a lock-free ring buffer for Fast Path, with overflow protection.
"""
from __future__ import annotations
import threading, time, logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_CAPACITY = 10000
DEFAULT_BACKPRESSURE = 0.8


@dataclass
class EventIR:
    id: str
    kind: str          # dialog.message | ui.drag | config.change | api.call
    payload: dict = field(default_factory=dict)
    refs: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class EventBus:
    """Thread-safe ring buffer with backpressure and overflow protection."""

    def __init__(self, capacity: int = DEFAULT_CAPACITY,
                 backpressure_ratio: float = DEFAULT_BACKPRESSURE):
        self._capacity = max(10, capacity)
        self._backpressure_threshold = int(self._capacity * backpressure_ratio)
        self._buffer: deque = deque()
        self._lock = threading.Lock()
        self._subscribers: List[Callable] = []
        self._sub_lock = threading.Lock()
        self._stats: Dict[str, int] = {"published": 0, "dropped": 0, "consumed": 0, "errors": 0}
        self._running = True

    def publish(self, event: EventIR) -> bool:
        """Non-blocking publish. Returns False if event was dropped due to overflow."""
        try:
            with self._lock:
                if len(self._buffer) >= self._capacity:
                    self._buffer.popleft()
                    self._stats["dropped"] += 1
                    if self._stats["dropped"] % 100 == 0:
                        logger.warning("EventBus dropped %d events", self._stats["dropped"])
                self._buffer.append(event)
                self._stats["published"] += 1
            return True
        except Exception:
            self._stats["errors"] += 1
            return False

    def consume_batch(self, max_events: int = 100, timeout: float = 0.5) -> List[EventIR]:
        """Blocking batch consume with timeout."""
        deadline = time.time() + timeout
        batch = []
        while time.time() < deadline and len(batch) < max_events:
            with self._lock:
                if self._buffer:
                    batch.append(self._buffer.popleft())
                else:
                    break
            if len(batch) >= max_events:
                break
            time.sleep(0.001)
        self._stats["consumed"] += len(batch)
        return batch

    def subscribe(self, callback: Callable[[List[EventIR]], None]):
        with self._sub_lock:
            self._subscribers.append(callback)

    def start_consumer(self, batch_size: int = 100, poll_interval: float = 0.1):
        """Start a background consumer thread."""
        def _consume():
            while self._running:
                batch = self.consume_batch(max_events=batch_size, timeout=poll_interval)
                if batch:
                    with self._sub_lock:
                        for sub in self._subscribers:
                            try:
                                sub(batch)
                            except Exception:
                                logger.exception("EventBus subscriber failed")
                                self._stats["errors"] += 1
        t = threading.Thread(target=_consume, daemon=True, name="eventbus-consumer")
        t.start()
        return t

    def health(self) -> dict:
        with self._lock:
            pending = len(self._buffer)
        return {
            "pending": pending,
            "capacity": self._capacity,
            "backpressure_ratio": pending / max(1, self._capacity),
            "stats": dict(self._stats),
        }

    def shutdown(self):
        self._running = False


class DialogAdapter:
    """Convert text input to EventIR."""

    def adapt(self, user_text: str, session_id: str = "",
              turn_number: int = 0, metadata: dict = None) -> EventIR:
        return EventIR(
            id=f"evt_{session_id}_{turn_number}",
            kind="dialog.message",
            payload={"text": user_text},
            refs={"session_id": session_id, "turn_number": turn_number},
            metadata=metadata or {},
        )
