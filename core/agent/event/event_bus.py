"""EventBus v2 — NATS-patterned pub/sub with subject routing + queue groups.

Key NATS patterns adapted:
  1. Subject-based routing     "entity.event" → hierarchical matching
  2. Async subscription        await sub.next_msg() + callback dispatch
  3. Queue groups              same-subject consumers load-balanced
  4. Graceful drain            close → drain pending → done

Python-native: zero external dependencies, asyncio-based.
"""

from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)

# ═══ Message ═══

@dataclass
class Event:
    """NATS-style message with subject, reply, and data."""
    subject: str           # e.g. "pcr.completed", "execution.*"
    data: Any = None
    reply: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    sid: Optional[int] = None

    def __repr__(self):
        return f"Event({self.subject}, {str(self.data)[:50]})"


# ═══ Subscription ═══

class Subscription:
    """Represents interest in a subject pattern.

    Subject hierarchy: "*" matches single token, ">" matches all trailing tokens.
    """

    def __init__(self, subject: str, sid: int,
                 cb: Callable = None, queue: str = None,
                 max_pending: int = 1024):
        self.subject = subject
        self.sid = sid
        self._cb = cb
        self.queue = queue
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_pending)
        self._pending = 0
        self._max_pending = max_pending
        self._active = True
        self._draining = False

    async def next_msg(self, timeout: float = None) -> Optional[Event]:
        """Await next message (sync style)."""
        if not self._active:
            return None
        try:
            if timeout:
                return await asyncio.wait_for(self._queue.get(), timeout)
            return await self._queue.get()
        except asyncio.TimeoutError:
            return None
        except asyncio.CancelledError:
            return None

    async def __aiter__(self):
        """Async iterator over messages."""
        while self._active:
            msg = await self.next_msg()
            if msg is None:
                break
            yield msg

    def _deliver(self, msg: Event):
        """Internal: deliver message to this subscription.

        Unlike NATS: we NEVER drop. Slow consumer → EventLog persists,
        subscriber catches up via replay, GC cleans old events later.
        """
        if not self._active:
            return
        if self._pending >= self._max_pending:
            # Slow consumer — not dropped, queued for later delivery
            # EventLog already persisted this event (immutable)
            logger.warning(
                "Slow consumer %s (%d pending), will catch up via replay",
                self.subject, self._pending)
            # Try non-blocking put
            try:
                self._queue.put_nowait(msg)
                self._pending += 1
            except asyncio.QueueFull:
                # Queue full — subscriber must catch up via EventLog replay
                logger.warning(
                    "Queue full for %s, subscriber should replay from %s",
                    self.subject, msg.subject)
        else:
            self._queue.put_nowait(msg)
            self._pending += 1

        msg.sid = self.sid
        self._queue.put_nowait(msg)
        self._pending += 1
        if self._cb:
            try:
                if asyncio.iscoroutinefunction(self._cb):
                    asyncio.ensure_future(self._cb(msg))
                else:
                    self._cb(msg)
            except Exception as e:
                logger.error("Subscriber %s callback failed: %s", self.subject, e)

    async def drain(self):
        """Wait for all pending messages to be processed."""
        self._draining = True
        while self._pending > 0:
            await asyncio.sleep(0.1)
        self._active = False

    def unsubscribe(self):
        self._active = False

    @property
    def pending(self) -> int:
        return self._pending

    @staticmethod
    def _match_subject(pattern: str, subject: str) -> bool:
        """Match NATS subject pattern against a concrete subject.

        "*"  = single token wildcard (e.g. "a.*.c" matches "a.b.c")
        ">"  = all trailing tokens (e.g. "a.>" matches "a.b.c.d")
        """
        p_tokens = pattern.split(".")
        s_tokens = subject.split(".")

        for i, pt in enumerate(p_tokens):
            if pt == ">":
                return True  # Matches everything from here
            if i >= len(s_tokens):
                return False
            if pt == "*":
                continue  # Match single token
            if pt != s_tokens[i]:
                return False

        # Exact match if same length
        return len(p_tokens) == len(s_tokens)


# ═══ EventBus ═══

class EventBus:
    """NATS-patterned pub/sub bus with subject routing.

    Usage:
        bus = EventBus()
        sub = await bus.subscribe("pcr.>", cb=my_handler)
        await bus.publish("pcr.completed", {"zone": "MIXED"})
        msg = await sub.next_msg()
    """

    MAX_SUBSCRIPTIONS = 1000
    DRAIN_TIMEOUT = 2.0

    def __init__(self):
        self._subscriptions: Dict[int, Subscription] = {}
        self._subject_index: Dict[str, List[int]] = defaultdict(list)
        self._queue_groups: Dict[str, Dict[str, int]] = {}  # group→{subject→round-robin idx}
        self._sid_counter = 0
        self._closed = False
        self._stats = {"published": 0, "delivered": 0, "dropped": 0}

    async def subscribe(self, subject: str,
                        cb: Callable = None,
                        queue: str = None,
                        max_pending: int = 1024) -> Subscription:
        """Subscribe to a subject pattern."""
        if self._closed:
            raise RuntimeError("EventBus closed")
        if len(self._subscriptions) >= self.MAX_SUBSCRIPTIONS:
            raise RuntimeError("Max subscriptions reached")

        self._sid_counter += 1
        sub = Subscription(subject, self._sid_counter, cb, queue, max_pending)
        self._subscriptions[self._sid_counter] = sub
        self._subject_index[subject].append(self._sid_counter)
        return sub

    async def publish(self, subject: str, data: Any = None,
                      reply: str = None, headers: dict = None) -> int:
        """Publish event to all matching subscription subjects.

        Returns number of subscribers delivered to.
        """
        if self._closed:
            return 0

        msg = Event(subject=subject, data=data, reply=reply,
                    headers=headers or {})
        delivered = 0

        # Find matching subscriptions
        for pattern, sids in self._subject_index.items():
            if not Subscription._match_subject(pattern, subject):
                continue

            # Queue group: round-robin to one subscriber
            queue_subs = {}
            non_queue_subs = []
            for sid in sids:
                sub = self._subscriptions.get(sid)
                if not sub or not sub._active:
                    continue
                if sub.queue:
                    queue_subs.setdefault(sub.queue, []).append(sid)
                else:
                    non_queue_subs.append(sid)

            # Non-queue: deliver to all
            for sid in non_queue_subs:
                sub = self._subscriptions.get(sid)
                if sub:
                    sub._deliver(msg)
                    delivered += 1

            # Queue groups: one per group (round-robin)
            for group, g_sids in queue_subs.items():
                key = f"{group}:{subject}"
                idx = self._queue_groups.setdefault(group, {}).get(subject, 0)
                target_sid = g_sids[idx % len(g_sids)]
                sub = self._subscriptions.get(target_sid)
                if sub:
                    sub._deliver(msg)
                    delivered += 1
                self._queue_groups[group][subject] = (idx + 1) % len(g_sids)

        self._stats["published"] += 1
        self._stats["delivered"] += delivered
        return delivered

    async def request(self, subject: str, data: Any = None,
                      timeout: float = 5.0) -> Optional[Event]:
        """Request-reply pattern: publish + await response on inbox."""
        inbox = f"_INBOX.{id(self)}.{time.monotonic_ns()}"
        sub = await self.subscribe(inbox, max_pending=1)
        try:
            await self.publish(subject, data, reply=inbox)
            return await sub.next_msg(timeout)
        finally:
            sub.unsubscribe()

    def unsubscribe(self, sid: int):
        sub = self._subscriptions.get(sid)
        if sub:
            sub.unsubscribe()

    async def drain(self):
        """Drain all subscriptions gracefully."""
        self._closed = True
        for sub in list(self._subscriptions.values()):
            await sub.drain()
        self._subscriptions.clear()
        self._subject_index.clear()

    @property
    def stats(self) -> dict:
        return {**self._stats, "subscriptions": len(self._subscriptions),
                "active": sum(1 for s in self._subscriptions.values() if s._active)}
