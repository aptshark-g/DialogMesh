"""Guard System — backpressure control + cascade detection + circuit breaking.

Protects DialogMesh pipeline from overload:
  RequestGuard    — per-stage rate limiting, token bucket
  CascadeDetector — detect failure cascades (A fails→B fails→C fails)
  CircuitBreaker  — trip when stage repeatedly fails, auto-recover
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import logging
import time

logger = logging.getLogger(__name__)


# ═══ Token Bucket Rate Limiter ═══

class TokenBucket:
    """Simple token bucket rate limiter. Refills at constant rate."""

    def __init__(self, rate: float = 100, burst: int = 10, name: str = ""):
        self._rate = rate          # Tokens per second
        self._burst = burst        # Max burst size
        self._tokens = float(burst)  # Current tokens
        self._last_refill = time.time()
        self.name = name
        self._total_requests = 0
        self._throttled = 0

    def acquire(self, tokens: int = 1) -> bool:
        """Try to acquire N tokens. Returns True if allowed."""
        self._refill()
        self._total_requests += 1
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        self._throttled += 1
        return False

    def _refill(self):
        now = time.time()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now

    @property
    def stats(self) -> dict:
        return {
            "name": self.name, "tokens": round(self._tokens, 1),
            "total": self._total_requests, "throttled": self._throttled,
            "rate": self._rate, "burst": self._burst,
        }


# ═══ Cascade Detector ═══

class FailureLevel(Enum):
    OK = "ok"; SLOW = "slow"; DEGRADED = "degraded"; FAILING = "failing"; CRITICAL = "critical"


@dataclass
class StageHealth:
    stage: str
    total_requests: int = 0
    failures: int = 0
    avg_latency_ms: float = 0.0
    current_level: FailureLevel = FailureLevel.OK
    last_success: float = 0.0
    last_failure: float = 0.0
    consecutive_failures: int = 0


class CascadeDetector:
    """Detect failure cascades: stage A fails→stage B starts failing→downstream impact.

    Pattern:
      - Stage A degrades (latency spikes)
      - Stage B starts timing out (waiting on A's garbage)
      - Stage C gets starved (no new requests pass B)
    """

    def __init__(self, window_seconds: float = 30):
        self._stages: Dict[str, StageHealth] = {}
        self._window = window_seconds

    def register_stage(self, stage: str):
        if stage not in self._stages:
            self._stages[stage] = StageHealth(stage=stage)

    def record(self, stage: str, success: bool, latency_ms: float):
        """Record stage execution result."""
        h = self._stages.get(stage)
        if not h:
            self.register_stage(stage)
            h = self._stages[stage]

        h.total_requests += 1
        now = time.time()

        if success:
            h.last_success = now
            h.consecutive_failures = 0
        else:
            h.failures += 1
            h.last_failure = now
            h.consecutive_failures += 1

        # EMA latency
        h.avg_latency_ms = 0.2 * latency_ms + 0.8 * h.avg_latency_ms

        # Classify health
        h.current_level = self._classify(h)

    def _classify(self, h: StageHealth) -> FailureLevel:
        if h.consecutive_failures >= 10:
            return FailureLevel.CRITICAL
        if h.consecutive_failures >= 5:
            return FailureLevel.FAILING
        if h.avg_latency_ms > 5000:
            return FailureLevel.DEGRADED
        if h.avg_latency_ms > 2000:
            return FailureLevel.SLOW
        return FailureLevel.OK

    def detect_cascade(self) -> Optional[Dict[str, Any]]:
        """Detect if a cascade is in progress. Returns cascade chain or None."""
        failures = []
        for stage, h in self._stages.items():
            if h.current_level in (FailureLevel.FAILING, FailureLevel.CRITICAL):
                failures.append((stage, h))

        if not failures:
            return None

        # Sort by failure count — deepest failure is likely root cause
        failures.sort(key=lambda x: x[1].consecutive_failures, reverse=True)

        cascade_chain = [f[0] for f in failures]
        return {
            "detected": True,
            "root_cause": cascade_chain[0] if cascade_chain else None,
            "chain": cascade_chain,
            "stages": {s: h.current_level.value for s, h in self._stages.items()},
        }

    def stats(self) -> dict:
        return {s: {"level": h.current_level.value,
                    "total": h.total_requests, "failures": h.failures,
                    "avg_ms": round(h.avg_latency_ms, 1),
                    "consecutive": h.consecutive_failures}
                for s, h in self._stages.items()}


# ═══ Circuit Breaker ═══

class CircuitState(Enum):
    CLOSED = "closed"        # Normal — requests flow
    OPEN = "open"            # Tripped — requests rejected
    HALF_OPEN = "half_open"  # Testing — limited requests allowed


class CircuitBreaker:
    """Circuit breaker: trip on repeated failures, auto-recover.

    States:
      CLOSED → (failures > threshold) → OPEN
      OPEN   → (cooldown elapsed)     → HALF_OPEN
      HALF_OPEN → (success)           → CLOSED
      HALF_OPEN → (failure)           → OPEN"""

    def __init__(self, name: str, failure_threshold: int = 5,
                 cooldown_seconds: float = 30.0,
                 half_open_max: int = 2):
        self.name = name
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._half_open_max = half_open_max
        self._half_open_requests = 0
        self._last_failure_time = 0.0
        self._last_state_change = time.time()

    def allow_request(self) -> bool:
        """Check if request should be allowed through."""
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_state_change >= self._cooldown:
                self._state = CircuitState.HALF_OPEN
                self._half_open_requests = 0
                self._last_state_change = time.time()
                logger.info("Circuit %s: OPEN→HALF_OPEN (cooldown elapsed)", self.name)
                return True
            return False
        if self._state == CircuitState.HALF_OPEN:
            if self._half_open_requests < self._half_open_max:
                self._half_open_requests += 1
                return True
            return False
        return False

    def record_success(self):
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_state_change = time.time()
            logger.info("Circuit %s: HALF_OPEN→CLOSED (success)", self.name)
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._state == CircuitState.CLOSED and self._failure_count >= self._threshold:
            self._state = CircuitState.OPEN
            self._last_state_change = time.time()
            logger.warning("Circuit %s: CLOSED→OPEN (%d failures)", self.name, self._failure_count)
        elif self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._last_state_change = time.time()
            logger.warning("Circuit %s: HALF_OPEN→OPEN (test failed)", self.name)

    @property
    def state(self) -> str:
        return self._state.value

    @property
    def stats(self) -> dict:
        return {"name": self.name, "state": self._state.value,
                "failures": self._failure_count,
                "last_failure": round(self._last_failure_time, 1)}


# ═══ Unified Guard ═══

class RequestGuard:
    """Unified guard: rate limit + cascade detect + circuit break for all stages.

    Usage:
        guard = RequestGuard()
        await guard.enter("compass")
        # ... do compass work ...
        guard.exit("compass", True, latency_ms=12.5)
    """

    DEFAULT_RATES = {
        "compass": 200, "pcr": 200, "intent": 150, "l4": 150,
        "context": 100, "llm_plan": 10, "plan_gate": 50,
        "execution": 20, "llm_answer": 10,
    }

    def __init__(self):
        self._buckets = {}
        self._cascade = CascadeDetector()
        self._circuits = {}

        for stage, rate in self.DEFAULT_RATES.items():
            self._buckets[stage] = TokenBucket(rate=rate, burst=rate // 5,
                                                name=stage)
            self._circuits[stage] = CircuitBreaker(name=stage)

    def enter(self, stage: str) -> bool:
        """Try to enter a pipeline stage. Returns True if allowed."""
        bucket = self._buckets.get(stage)
        if bucket and not bucket.acquire():
            logger.debug("Guard: %s throttled", stage)
            return False

        circuit = self._circuits.get(stage)
        if circuit and not circuit.allow_request():
            logger.debug("Guard: %s circuit open", stage)
            return False

        return True

    def exit(self, stage: str, success: bool, latency_ms: float):
        """Exit a pipeline stage, recording result."""
        circuit = self._circuits.get(stage)
        if circuit:
            if success:
                circuit.record_success()
            else:
                circuit.record_failure()

        self._cascade.record(stage, success, latency_ms)

    def check_cascade(self) -> Optional[dict]:
        return self._cascade.detect_cascade()

    def stats(self) -> dict:
        return {
            "buckets": {s: b.stats for s, b in self._buckets.items()},
            "circuits": {s: c.stats for s, c in self._circuits.items()},
            "cascade": self._cascade.stats(),
        }
