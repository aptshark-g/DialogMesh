"""Week 5: Production hardening — SLA enforcement + Circuit breaker + Parallel dispatch + Graceful shutdown.

All transparent to existing code — wraps engine and scheduler with monitoring."""
import time, signal, threading, logging
from typing import Dict, Callable, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  SLA Watchdog
# ═══════════════════════════════════════════════════════════

SLA_LIMITS = {"P0": 10, "P1": 100, "P2": 1000, "P3": 5000}  # ms

@dataclass
class SLARecord:
    phase: str
    count: int = 0
    violations: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0


class SLAWatchdog:
    """Monitor P0/P1 latency, record violations, emit alerts."""

    def __init__(self):
        self._records: Dict[str, SLARecord] = {}
        self._lock = threading.Lock()
        self._alert_hooks: list = []

    def record(self, phase: str, level: str, latency_ms: float):
        with self._lock:
            rec = self._records.get(phase)
            if rec is None:
                rec = SLARecord(phase=phase)
                self._records[phase] = rec
            rec.count += 1
            rec.total_ms += latency_ms
            if latency_ms > rec.max_ms:
                rec.max_ms = latency_ms
            limit = SLA_LIMITS.get(level, 1000)
            if latency_ms > limit:
                rec.violations += 1
                self._alert(phase, level, latency_ms, limit)

    def _alert(self, phase: str, level: str, actual: float, limit: int):
        msg = f"SLA VIOLATION: {phase}({level}) {actual:.0f}ms > {limit}ms"
        logger.warning(msg)
        for hook in self._alert_hooks:
            try: hook(phase, level, actual, limit)
            except: pass

    def add_alert_hook(self, hook: Callable):
        self._alert_hooks.append(hook)

    def stats(self) -> dict:
        with self._lock:
            return {
                phase: {
                    "count": r.count, "violations": r.violations,
                    "avg_ms": round(r.total_ms / max(r.count, 1), 1),
                    "max_ms": round(r.max_ms, 1),
                    "violation_rate": round(r.violations / max(r.count, 1) * 100, 1),
                }
                for phase, r in self._records.items()
            }


# ═══════════════════════════════════════════════════════════
#  Circuit Breaker
# ═══════════════════════════════════════════════════════════

class CircuitBreaker:
    """After N consecutive failures, open circuit for cooldown_sec."""

    def __init__(self, failure_threshold: int = 3, cooldown_sec: float = 60.0):
        self._threshold = failure_threshold
        self._cooldown = cooldown_sec
        self._failures: Dict[str, int] = {}
        self._open_at: Dict[str, float] = {}
        self._lock = threading.Lock()

    def allow(self, name: str) -> bool:
        with self._lock:
            opened = self._open_at.get(name)
            if opened and time.time() < opened + self._cooldown:
                return False  # circuit open
            if opened:  # cooldown expired
                self._open_at.pop(name, None)
                self._failures[name] = 0
            return True

    def record_success(self, name: str):
        with self._lock:
            self._failures[name] = 0

    def record_failure(self, name: str):
        with self._lock:
            f = self._failures.get(name, 0) + 1
            self._failures[name] = f
            if f >= self._threshold:
                self._open_at[name] = time.time()
                logger.warning("Circuit BREAKER OPEN: %s (%d failures)", name, f)

    def stats(self) -> dict:
        with self._lock:
            return {
                name: {"failures": self._failures.get(name, 0),
                        "open": name in self._open_at}
                for name in set(self._failures) | set(self._open_at)
            }


# ═══════════════════════════════════════════════════════════
#  Parallel Subscriber Dispatch
# ═══════════════════════════════════════════════════════════

class ParallelDispatcher:
    """Replace serial subscriber iteration with threaded parallel dispatch.

    P0/P1 still fire synchronously (must complete before returning).
    P2/P3 fire in parallel threads (non-blocking)."""

    def __init__(self, engine, sla_watchdog: SLAWatchdog = None,
                 circuit_breaker: CircuitBreaker = None):
        self._engine = engine
        self._sla = sla_watchdog or SLAWatchdog()
        self._cb = circuit_breaker or CircuitBreaker()
        self._threads: list = []

    def dispatch(self, kind: str, payload: dict,
                 subscriber_priorities: dict = None) -> dict:
        """Dispatch to all subscribers with SLA tracking + circuit breaker."""
        subs = getattr(self._engine, '_event_subscribers', {})
        if not subs: return {"dispatched": 0}

        priorities = subscriber_priorities or {
            "meta": "P1", "association": "P1",
            "discourse": "P2", "behavior": "P2", "profile": "P2",
            "persistence": "P3",
        }
        results = {}

        for name, sub in subs.items():
            if not self._cb.allow(name):
                results[name] = "circuit_open"
                continue

            level = priorities.get(name, "P2")

            if level in ("P0", "P1"):
                # Synchronous
                results[name] = self._run_one(name, sub, kind, payload, level)
            else:
                # Parallel
                t = threading.Thread(
                    target=self._thread_runner,
                    args=(name, sub, kind, payload, level),
                    daemon=True
                )
                t.start()
                self._clean_threads()
                self._threads.append(t)

        results["total"] = len(subs)
        return results

    def _run_one(self, name: str, sub, kind: str, payload: dict, level: str) -> str:
        t0 = time.time()
        try:
            sub.handle(kind, payload)
            latency = (time.time() - t0) * 1000
            self._sla.record(name, level, latency)
            self._cb.record_success(name)
            return f"ok_{latency:.0f}ms"
        except Exception as e:
            latency = (time.time() - t0) * 1000
            self._sla.record(name, level, latency)
            self._cb.record_failure(name)
            return f"error:{e}"

    def _thread_runner(self, name: str, sub, kind: str, payload: dict, level: str):
        self._run_one(name, sub, kind, payload, level)

    def _clean_threads(self):
        self._threads = [t for t in self._threads if t.is_alive()]

    def stats(self) -> dict:
        return {
            "sla": self._sla.stats(),
            "circuit_breaker": self._cb.stats(),
            "active_threads": len([t for t in self._threads if t.is_alive()]),
        }


# ═══════════════════════════════════════════════════════════
#  Graceful Shutdown
# ═══════════════════════════════════════════════════════════

class GracefulShutdown:
    """Signal handler for clean shutdown: drain queues, close connections, save state."""

    def __init__(self, engine):
        self._engine = engine
        self._hooks: list = []
        self._shutting_down = False
        self._install_handlers()

    @property
    def is_shutting_down(self) -> bool:
        return self._shutting_down

    def _install_handlers(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._handle)
            except (ValueError, OSError):
                pass  # Not in main thread

    def _handle(self, signum, frame):
        logger.info("Shutdown signal received: %s", signum)
        self._shutting_down = True
        self.drain()

    def add_hook(self, hook: Callable):
        self._hooks.append(hook)

    def drain(self):
        """Drain: persist state → close storages → close pub/sub → goodbye."""
        logger.info("Draining...")
        for hook in self._hooks:
            try: hook()
            except: pass
        # Persist
        if hasattr(self._engine, '_persist_state'):
            try: self._engine._persist_state()
            except: pass
        # Close NATS
        bus = getattr(self._engine, '_hybrid_bus', None)
        if bus and hasattr(bus, 'close'):
            try: bus.close()
            except: pass
        # Close Redis
        redis = getattr(self._engine, '_redis', None)
        if redis and hasattr(redis, 'close'):
            try: redis.close()
            except: pass
        # Close PG
        store = getattr(self._engine, '_storage', None)
        if store and hasattr(store, 'pg') and store.pg:
            try: store.pg.close()
            except: pass
        # Close EventLog
        el = getattr(self._engine, '_event_log', None)
        if el and hasattr(el, 'close'):
            try: el.close()
            except: pass
        logger.info("Drain complete. Goodbye.")


def wire_production(engine) -> dict:
    """Wire SLAWatchdog + CircuitBreaker + ParallelDispatcher + GracefulShutdown."""
    status = {}
    try:
        engine._sla_watchdog = SLAWatchdog()
        engine._circuit_breaker = CircuitBreaker()
        engine._parallel_dispatch = ParallelDispatcher(
            engine, engine._sla_watchdog, engine._circuit_breaker
        )
        engine._shutdown = GracefulShutdown(engine)
        status["sla"] = "active"
        status["circuit_breaker"] = "active"
        status["parallel"] = "active"
        logger.info("Production hardening wired: SLA + CB + Parallel + Shutdown")
    except Exception as e:
        logger.debug("Production wiring skipped: %s", e)
        status["error"] = str(e)[:100]
    return status
