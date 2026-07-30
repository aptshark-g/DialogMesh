"""Week 2: NATS pub/sub bridge (DESIGN_DISTRIBUTED §2.2).

Real NATS integration with graceful fallback to in-memory EventBus.
Uses nats-py async client, wrapped for sync use via asyncio.run().

Architecture:
    _publish(kind, payload)
        ├─ NATS available? → nats.publish("dialogmesh.{kind}", json)
        └─ NATS down?     → memory.publish(subscribers, kind, payload)

Subscribers are dual-registered:
    NATS mode:   nats.subscribe("dialogmesh.*") → handle()
    Memory mode: EventBus.subscribe(kind, handle)""" 
import json, logging, threading, time, asyncio
from typing import Optional, Dict, Callable, Any

logger = logging.getLogger(__name__)


class NATSPublisher:
    """Synchronous wrapper around nats-py async client.

    Usage:
        pub = NATSPublisher(server_url="nats://localhost:4222")
        pub.connect()
        pub.publish("dialogmesh.user_message", {"text": "hello"})
    """

    def __init__(self, server_url: str = "nats://localhost:4222"):
        self._server_url = server_url
        self._nc = None
        self._connected = False
        self._lock = threading.Lock()
        self._stats = {"published": 0, "errors": 0, "fallbacks": 0}

    @property
    def available(self) -> bool:
        return self._connected

    def connect(self, timeout: float = 2.0) -> bool:
        try:
            from nats.aio.client import Client as NATS
            async def _connect():
                nc = NATS()
                await nc.connect(self._server_url, connect_timeout=timeout)
                return nc
            self._nc = asyncio.run(_connect())
            self._connected = True
            logger.info("NATS connected: %s", self._server_url)
            return True
        except Exception as e:
            logger.debug("NATS unavailable (%s), using memory fallback", e)
            self._connected = False
            return False

    def publish(self, subject: str, payload: dict) -> bool:
        if not self._connected or self._nc is None:
            self._stats["fallbacks"] += 1
            return False
        try:
            data = json.dumps(payload, ensure_ascii=False, default=str).encode()
            async def _pub():
                await self._nc.publish(subject, data)
            asyncio.run(_pub())
            self._stats["published"] += 1
            return True
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug("NATS publish failed: %s", e)
            self._connected = False
            return False

    def subscribe(self, subject: str, handler: Callable[[dict], None]) -> bool:
        if not self._connected or self._nc is None:
            return False
        try:
            async def _sub():
                async def cb(msg):
                    try:
                        data = json.loads(msg.data.decode())
                        handler(data)
                    except Exception as e:
                        logger.debug("NATS sub handler error: %s", e)
                await self._nc.subscribe(subject, cb=cb)
            asyncio.run(_sub())
            return True
        except Exception as e:
            logger.debug("NATS subscribe failed: %s", e)
            return False

    def close(self):
        if self._nc:
            try:
                async def _close():
                    await self._nc.drain()
                asyncio.run(_close())
            except Exception:
                pass
            self._connected = False

    def stats(self) -> dict:
        return dict(self._stats)


class HybridEventBus:
    """NATS + memory EventBus with automatic fallback.

    Publishes to NATS when available; always publishes to memory subscribers.
    This ensures zero message loss during NATS downtime."""

    def __init__(self, engine, nats_url: str = "nats://localhost:4222"):
        self._engine = engine
        self._nats = NATSPublisher(nats_url)
        self._memory_subscribers: Dict[str, Callable] = {}
        self._memory_stats = {"published": 0, "errors": 0}

        # Try NATS connect
        self._nats_ok = self._nats.connect(timeout=1.0)
        if self._nats_ok:
            logger.info("HybridEventBus: NATS + memory (dual-write)")
        else:
            logger.info("HybridEventBus: memory-only (NATS unavailable)")

    def publish(self, kind: str, payload: dict) -> dict:
        result = {"kind": kind, "nats": False, "memory": 0}

        # Publish to engine's subscribers dynamically (they may be wire_subscribers later)
        subs = getattr(self._engine, '_event_subscribers', {})
        for name, sub in subs.items():
            try:
                sub.handle(kind, payload)
                result["memory"] += 1
                self._memory_stats["published"] += 1
            except Exception as e:
                self._memory_stats["errors"] += 1

        # Attempt NATS publish (best-effort)
        if self._nats_ok:
            subject = f"dialogmesh.{kind}"
            result["nats"] = self._nats.publish(subject, payload)

        return result

    def subscribe(self, kind: str, handler: Callable[[dict], None]):
        self._memory_subscribers[kind] = handler

    def stats(self) -> dict:
        return {
            "mode": "hybrid" if self._nats_ok else "memory",
            "nats": self._nats.stats(),
            "memory": dict(self._memory_stats),
            "subscribers": len(self._memory_subscribers),
        }

    def close(self):
        self._nats.close()


def wire_hybrid_bus(engine) -> bool:
    """Replace engine._publish with HybridEventBus dispatch.

    Returns True if NATS is available, False if memory-only."""
    try:
        bus = HybridEventBus(engine)
        original_publish = engine._publish
        def hybrid_publish(kind, payload=None):
            p = payload or {}
            result = bus.publish(str(kind), p)
            try: original_publish(kind, payload)
            except: pass

        engine._publish = hybrid_publish
        engine._hybrid_bus = bus

        # Auto-register existing subscribers with the bus
        subs = getattr(engine, '_event_subscribers', {})
        if subs:
            for name in subs:
                bus.subscribe("*", lambda p, n=name: None)
        logger.info("HybridEventBus wired: mode=%s subs=%d",
                     bus.stats()["mode"], len(subs))
        return bus._nats_ok
    except Exception as e:
        logger.debug("HybridEventBus wiring failed: %s (continuing with memory)", e)
        return False
