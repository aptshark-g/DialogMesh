# -*- coding: utf-8 -*-
"""
core/agent/pcr/telemetry.py
──────────────────────────
PCR telemetry collector.

Collects per-call metrics (latency, error, cache hit) and computes
distribution statistics (avg, p50, p99, max). Thread-safe via internal lock.

Usage:
    telemetry = TelemetryCollector()
    telemetry.record(latency_ms=12.5, error=False, cache_hit=True)
    stats = telemetry.get_stats()
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class CallRecord:
    """Single call telemetry record."""
    latency_ms: float
    error: bool
    cache_hit: bool
    timestamp: float


class TelemetryCollector:
    """
    Thread-safe telemetry collector for PCR implementations.
    
    Maintains a sliding window of recent call records (default 10000).
    Computes latency distribution and error/cache-hit rates on demand.
    """

    def __init__(self, max_records: int = 10000):
        self._max_records = max_records
        self._records: List[CallRecord] = []
        self._lock = threading.Lock()
        self._last_error: Optional[str] = None
        self._health_transitions: List[str] = []

    def record(
        self,
        latency_ms: float,
        error: bool = False,
        cache_hit: bool = False,
        error_message: Optional[str] = None,
    ) -> None:
        """Record a single call. Thread-safe."""
        with self._lock:
            self._records.append(CallRecord(
                latency_ms=latency_ms,
                error=error,
                cache_hit=cache_hit,
                timestamp=time.time(),
            ))
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records:]
            if error and error_message:
                self._last_error = error_message

    def record_health_transition(self, from_status: str, to_status: str) -> None:
        """Record a health status transition."""
        with self._lock:
            self._health_transitions.append(
                f"{time.time():.0f}: {from_status} -> {to_status}"
            )
            if len(self._health_transitions) > 100:
                self._health_transitions = self._health_transitions[-100:]

    def get_stats(self) -> Dict[str, Any]:
        """Compute and return telemetry statistics. Thread-safe."""
        with self._lock:
            if not self._records:
                return {
                    "call_count": 0,
                    "error_count": 0,
                    "error_rate": 0.0,
                    "cache_hit_count": 0,
                    "cache_hit_rate": 0.0,
                    "avg_latency_ms": 0.0,
                    "p50_latency_ms": 0.0,
                    "p99_latency_ms": 0.0,
                    "max_latency_ms": 0.0,
                    "last_error": None,
                    "health_transitions": [],
                }

            count = len(self._records)
            errors = sum(1 for r in self._records if r.error)
            cache_hits = sum(1 for r in self._records if r.cache_hit)
            latencies = sorted(r.latency_ms for r in self._records)

            return {
                "call_count": count,
                "error_count": errors,
                "error_rate": errors / count,
                "cache_hit_count": cache_hits,
                "cache_hit_rate": cache_hits / count,
                "avg_latency_ms": sum(latencies) / count,
                "p50_latency_ms": latencies[int(count * 0.50)],
                "p99_latency_ms": latencies[int(count * 0.99)] if count >= 100 else latencies[-1],
                "max_latency_ms": latencies[-1],
                "last_error": self._last_error,
                "health_transitions": list(self._health_transitions),
            }

    def reset(self) -> None:
        """Clear all records. Thread-safe."""
        with self._lock:
            self._records.clear()
            self._last_error = None
            self._health_transitions.clear()
