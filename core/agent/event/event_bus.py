"""EventBus v2 — NATS-patterned pub/sub with subject routing + queue groups.

Key NATS patterns adapted:
  1. Subject-based routing     "entity.event" → hierarchical matching
  2. Async subscription        await sub.next_msg() + callback dispatch
  3. Queue groups              same-subject consumers load-balanced
  4. Graceful drain            close → drain pending → done

G2 升级（双模）:
  - 保留 async API（agent_native / permissions / closure 的 ensure_future 用法）
  - 新增后台事件循环线程 + publish_sync/subscribe_sync/request_sync 同步桥
    （CLI 引擎同步路径 / wire_subscribers / meta_subscriber 使用）
  - 修复 _deliver 重复入队 bug（消息只入队一次，NEVER drop 语义保持）

Python-native: zero external dependencies, asyncio-based.
"""

from __future__ import annotations
import asyncio
import logging
import threading
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
        self._overflow = 0

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

        cb 型订阅：回调即投递（不入队，drain 不等待）；
        无 cb 型订阅：入队供 next_msg() 消费（pending 计数，drain 等待）。
        """
        if not self._active:
            return
        msg.sid = self.sid
        if self._cb is None:
            if self._pending >= self._max_pending:
                # Slow consumer — never drop: try put, count overflow if full.
                # EventLog already persisted this event (immutable); subscriber
                # catches up via replay (G2-P1 水位线语义).
                logger.warning(
                    "Slow consumer %s (%d pending), will catch up via replay",
                    self.subject, self._pending)
                try:
                    self._queue.put_nowait(msg)
                    self._pending += 1
                except asyncio.QueueFull:
                    self._overflow += 1
                    logger.warning(
                        "Queue full for %s, subscriber should replay from %s",
                        self.subject, msg.subject)
            else:
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

    @property
    def overflow(self) -> int:
        return self._overflow

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
    """NATS-patterned pub/sub bus with subject routing（双模：async + sync 桥）。

    Usage (async):
        bus = EventBus()
        sub = await bus.subscribe("pcr.>", cb=my_handler)
        await bus.publish("pcr.completed", {"zone": "MIXED"})
        msg = await sub.next_msg()

    Usage (sync / CLI 引擎):
        bus = EventBus()
        bus.subscribe_sync("pcr.>", handler)
        bus.publish_sync("pcr.completed", {"zone": "MIXED"})

    所有内部操作 marshal 到专属后台事件循环线程，队列绑定一致，
    同步/异步调用方互不冲突（G2-P6 归一）。
    """

    MAX_SUBSCRIPTIONS = 1000
    DRAIN_TIMEOUT = 2.0

    def __init__(self, background_loop: bool = True):
        self._subscriptions: Dict[int, Subscription] = {}
        self._subject_index: Dict[str, List[int]] = defaultdict(list)
        self._queue_groups: Dict[str, Dict[str, int]] = {}  # group→{subject→round-robin idx}
        self._sid_counter = 0
        self._closed = False
        self._stats = {"published": 0, "delivered": 0, "dropped": 0}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        if background_loop:
            self._start_loop()

    # ── 后台事件循环（同步桥底座） ─────────────────────────────── #

    def _start_loop(self):
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._run_loop, daemon=True, name="event-bus-loop")
        self._loop_thread.start()

    def stop(self) -> None:
        """Stop the background event loop (clean shutdown).

        Used by engine.stop() so tests/API shutdowns do not leave a live
        consumer thread issuing gateway calls after the engine is stopped.
        """
        loop = getattr(self, "_loop", None)
        thread = getattr(self, "_loop_thread", None)
        if loop is not None and loop.is_running():
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass
        if thread is not None and thread.is_alive():
            try:
                thread.join(timeout=2.0)
            except Exception:
                pass
        self._loop = None
        self._loop_thread = None

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    def _run_coro(self, coro, timeout: float = DRAIN_TIMEOUT):
        """同步桥：把协程调度到后台循环并等待结果（线程安全）。"""
        if self._loop is None or self._loop_thread is None:
            # 无后台循环 → 调用方必须在 async 上下文（走 async API）
            raise RuntimeError("EventBus background loop disabled; use async API")
        if threading.current_thread() is self._loop_thread:
            # 已在循环线程内（回调中再发布）→ fire-and-forget，避免死锁
            return asyncio.ensure_future(coro)
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

    async def _run_coro_async(self, coro):
        """异步桥：从调用方循环 marshal 到后台循环（保证队列绑定一致）。"""
        if self._loop is None or self._loop_thread is None:
            return await coro
        if threading.current_thread() is self._loop_thread:
            return await coro
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return await asyncio.wrap_future(fut)

    # ── Async API（v6 异步消费方） ──────────────────────────────── #

    async def subscribe(self, subject: str,
                        cb: Callable = None,
                        queue: str = None,
                        max_pending: int = 1024) -> Subscription:
        """Subscribe to a subject pattern."""
        return await self._run_coro_async(
            self._subscribe_impl(subject, cb, queue, max_pending))

    async def _subscribe_impl(self, subject: str, cb: Callable = None,
                              queue: str = None,
                              max_pending: int = 1024) -> Subscription:
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
        return await self._run_coro_async(
            self._publish_impl(subject, data, reply, headers))

    async def _publish_impl(self, subject: str, data: Any = None,
                            reply: str = None, headers: dict = None) -> int:
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
        return await self._run_coro_async(
            self._request_impl(subject, data, timeout))

    async def _request_impl(self, subject: str, data: Any = None,
                            timeout: float = 5.0) -> Optional[Event]:
        inbox = f"_INBOX.{id(self)}.{time.monotonic_ns()}"
        sub = await self._subscribe_impl(inbox, max_pending=1)
        try:
            await self._publish_impl(subject, data, reply=inbox)
            return await sub.next_msg(timeout)
        finally:
            sub.unsubscribe()

    # ── Sync 桥（CLI 引擎 / wire_subscribers / meta_subscriber） ── #

    def subscribe_sync(self, subject: str,
                       cb: Callable = None,
                       queue: str = None,
                       max_pending: int = 1024) -> Subscription:
        """同步订阅（后台循环执行，返回 Subscription）。"""
        return self._run_coro(
            self._subscribe_impl(subject, cb, queue, max_pending))

    def publish_sync(self, subject: str, data: Any = None,
                     reply: str = None, headers: dict = None) -> int:
        """同步发布（后台循环执行，等待投递完成）。"""
        return self._run_coro(
            self._publish_impl(subject, data, reply, headers))

    def request_sync(self, subject: str, data: Any = None,
                     timeout: float = 5.0) -> Optional[Event]:
        """同步 request-reply。"""
        return self._run_coro(
            self._request_impl(subject, data, timeout), timeout=timeout)

    def drain_sync(self):
        """同步排空并停止后台循环线程。"""
        if self._loop is None or self._loop_thread is None:
            self._closed = True
            return
        try:
            self._run_coro(self._drain_impl(), timeout=self.DRAIN_TIMEOUT)
        except Exception as e:
            logger.debug("EventBus drain_sync partial: %s", e)
        self._closed = True
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._loop_thread.join(timeout=1.0)
        self._loop_thread = None

    def unsubscribe(self, sid: int):
        sub = self._subscriptions.get(sid)
        if sub:
            sub.unsubscribe()

    async def drain(self):
        """Drain all subscriptions gracefully (async)."""
        self._closed = True
        for sub in list(self._subscriptions.values()):
            await sub.drain()
        self._subscriptions.clear()
        self._subject_index.clear()

    async def _drain_impl(self):
        self._closed = True
        for sub in list(self._subscriptions.values()):
            await sub.drain()
        self._subscriptions.clear()
        self._subject_index.clear()

    @property
    def stats(self) -> dict:
        overflow = sum(s.overflow for s in self._subscriptions.values())
        return {**self._stats, "overflow": overflow,
                "subscriptions": len(self._subscriptions),
                "active": sum(1 for s in self._subscriptions.values() if s._active)}
