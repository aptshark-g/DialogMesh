"""EnginePool — per-request leasing for multi-worker (DESIGN_DISTRIBUTED §2.1)."""
import threading, time, logging
from typing import Optional, List

logger = logging.getLogger(__name__)


class EngineLease:
    """Context-managed engine handle with auto-return."""

    def __init__(self, pool, engine, slot_id: int):
        self._pool = pool
        self._engine = engine
        self._slot = slot_id
        self._leased_at = time.time()

    @property
    def engine(self):
        return self._engine

    def __enter__(self):
        return self._engine

    def __exit__(self, *args):
        self._pool._return(self._slot, self._leased_at)


class EnginePool:
    """Pool of CognitiveRuntimeEngine instances with lease/return/health.

    Usage:
        pool = EnginePool(size=4)
        with pool.lease() as engine:
            engine.on_event(...)
    """

    def __init__(self, size: int = 4, provider_type: str = "mock", timeout_sec: float = 30.0):
        self._size = size
        self._provider_type = provider_type
        self._timeout = timeout_sec
        self._lock = threading.Lock()
        self._slots: List[Optional[object]] = [None] * size
        self._leased: List[bool] = [False] * size
        self._leased_at: List[float] = [0.0] * size
        self._stats = {"leases": 0, "returns": 0, "timeouts": 0, "created": 0}

    def _create_engine(self, slot_id: int):
        from core.agent.cli.engine import _create_engine_instance
        engine = _create_engine_instance(self._provider_type)
        # B1: bootstrap already assembled StateMachine + handlers via
        # _create_engine_instance -> engine.bootstrap(). Pool only needs the
        # EventBus subscribers (not part of the unified assembly).
        from core.agent.event.subscribers import wire_subscribers
        wire_subscribers(engine)
        sm = getattr(engine, '_state_machine', None)
        self._slots[slot_id] = engine
        self._stats["created"] += 1
        logger.info("EnginePool[%d] created: %s subs, %s handlers",
                     slot_id,
                     len(getattr(engine, '_event_subscribers', {})),
                     len(getattr(sm, '_phase_handlers', {})) if sm else 0)
        return engine

    def _find_free_slot(self) -> Optional[int]:
        now = time.time()
        for i in range(self._size):
            if not self._leased[i]:
                return i
            # Reclaim timed-out leases
            if now - self._leased_at[i] > self._timeout:
                logger.warning("EnginePool[%d] lease timeout, auto-reclaim", i)
                self._leased[i] = False
                self._stats["timeouts"] += 1
                return i
        return None

    def _return(self, slot_id: int, leased_at: float):
        with self._lock:
            if self._leased[slot_id] and self._leased_at[slot_id] == leased_at:
                self._leased[slot_id] = False
                self._stats["returns"] += 1

    def lease(self, timeout: float = 5.0) -> Optional[EngineLease]:
        """Lease an engine from the pool. Returns None if all busy."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                slot = self._find_free_slot()
                if slot is not None:
                    if self._slots[slot] is None or not self._healthy(slot):
                        self._create_engine(slot)
                    self._leased[slot] = True
                    self._leased_at[slot] = time.time()
                    self._stats["leases"] += 1
                    return EngineLease(self, self._slots[slot], slot)
            time.sleep(0.05)
        return None

    def _healthy(self, slot_id: int) -> bool:
        engine = self._slots[slot_id]
        if engine is None:
            return False
        try:
            # Basic liveness check
            return hasattr(engine, '_running') and engine._running
        except Exception:
            return False

    def stats(self) -> dict:
        with self._lock:
            return {
                **self._stats,
                "active_leases": sum(self._leased),
                "free_slots": sum(1 for l in self._leased if not l),
                "pool_size": self._size,
            }

    def shutdown(self):
        with self._lock:
            for i in range(self._size):
                self._leased[i] = False
                eng = self._slots[i]
                if eng and hasattr(eng, 'stop'):
                    try:
                        eng.stop()
                    except Exception:
                        pass
                self._slots[i] = None


# Global pool (lazy init)
_pool: Optional[EnginePool] = None
_pool_lock = threading.Lock()


def get_pool(size: int = 4, provider: str = "mock") -> EnginePool:
    global _pool
    with _pool_lock:
        if _pool is None or _pool._provider_type != provider:
            if _pool:
                _pool.shutdown()
            _pool = EnginePool(size=size, provider_type=provider)
        return _pool


def get_engine():
    """Drop-in replacement for cli.engine.get_engine() using pool."""
    pool = get_pool()
    lease = pool.lease()
    if lease:
        return lease.engine
    return None
