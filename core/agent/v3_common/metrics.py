# -*- coding: utf-8 -*-
"""
core/agent/metrics.py
─────────────────────
Runtime metrics collection (P2-1). Lightweight — no external deps.

Tracks: request counts, errors, latencies, security blocks, LLM calls.
Can export to Prometheus text format if prometheus_client is available.

DiscourseBlockTree Metrics (added in v0.2.0):
- discourse_pipeline_requests_total
- discourse_pipeline_latency_seconds
- discourse_blocks_active
- discourse_blocks_total
- discourse_edu_processed_total
- discourse_summary_v3_triggered_total
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class LatencyBucket:
    """Histogram-style bucket."""
    upper_bound_ms: float
    count: int = 0


class MetricsCollector:
    """Simple in-memory metrics collector with Prometheus-style export."""

    # Standard histogram buckets (ms)
    DEFAULT_BUCKETS = [10, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 30000, 60000]

    def __init__(self, prefix: str = "memorygraph"):
        self.prefix = prefix
        self._counters: Dict[str, int] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[LatencyBucket]] = {}
        self._errors: List[Dict] = []
        self._max_errors = 100

    # ── Counter ──────────────────────────────────────────────────────────────

    def inc(self, name: str, value: int = 1):
        self._counters[name] = self._counters.get(name, 0) + value

    # ── Gauge ────────────────────────────────────────────────────────────────

    def set(self, name: str, value: float):
        self._gauges[name] = value

    # ── Histogram ────────────────────────────────────────────────────────────

    def observe(self, name: str, latency_ms: float):
        if name not in self._histograms:
            self._histograms[name] = [LatencyBucket(b) for b in self.DEFAULT_BUCKETS]
        for bucket in self._histograms[name]:
            if latency_ms <= bucket.upper_bound_ms:
                bucket.count += 1

    # ── Error tracking ─────────────────────────────────────────────────────────

    def record_error(self, error_type: str, detail: str):
        self._errors.append({
            "timestamp": time.time(),
            "type": error_type,
            "detail": detail,
        })
        if len(self._errors) > self._max_errors:
            self._errors.pop(0)

    # ── Query ────────────────────────────────────────────────────────────────

    def get(self, name: str) -> int:
        return self._counters.get(name, 0)

    def error_rate(self, window: int = 100) -> float:
        """Error rate over last N requests."""
        total = self.get("requests_total")
        errors = self.get("errors_total")
        if total == 0:
            return 0.0
        return errors / total

    def security_block_rate(self) -> float:
        """Security block rate."""
        total = self.get("requests_total")
        blocks = self.get("security_blocks_total")
        if total == 0:
            return 0.0
        return blocks / total

    def consecutive_llm_failures(self) -> int:
        """Count consecutive LLM failures from recent errors."""
        # Count trailing errors that are llm_error
        count = 0
        for e in reversed(self._errors):
            if e.get("type") == "llm_error":
                count += 1
            else:
                break
        return count

    def avg_llm_latency_ms(self) -> float:
        """Average LLM latency from histogram buckets."""
        buckets = self._histograms.get("llm_latency_ms", [])
        if not buckets:
            return 0.0
        # Approximate using bucket midpoints weighted by count
        total = 0
        count = 0
        prev = 0.0
        for b in buckets:
            midpoint = (prev + b.upper_bound_ms) / 2 if prev > 0 else b.upper_bound_ms / 2
            bucket_count = b.count - sum(b2.count for b2 in buckets if b2.upper_bound_ms < b.upper_bound_ms)
            if bucket_count > 0:
                total += midpoint * bucket_count
                count += bucket_count
            prev = b.upper_bound_ms
        return total / count if count > 0 else 0.0

    # ── DiscourseBlockTree metrics (v0.2.0) ─────────────────────────────────

    def inc_discourse_requests(self, value: int = 1):
        """Increment total DiscoursePipeline request count."""
        self._counters["discourse_pipeline_requests_total"] = (
            self._counters.get("discourse_pipeline_requests_total", 0) + value
        )

    def observe_discourse_latency(self, latency_s: float):
        """Record DiscoursePipeline processing latency (seconds)."""
        # Store histogram keyed by ms; convert seconds to ms for bucket alignment
        self.observe("discourse_pipeline_latency_seconds", latency_s * 1000.0)

    def set_active_blocks(self, count: int):
        """Set the number of currently active (hot) discourse blocks."""
        self._gauges["discourse_blocks_active"] = float(count)

    def inc_total_blocks(self, value: int = 1):
        """Increment total DiscourseBlock created count."""
        self._counters["discourse_blocks_total"] = (
            self._counters.get("discourse_blocks_total", 0) + value
        )

    def inc_edu_processed(self, value: int = 1):
        """Increment total EDU processed count."""
        self._counters["discourse_edu_processed_total"] = (
            self._counters.get("discourse_edu_processed_total", 0) + value
        )

    def inc_v3_triggered(self, value: int = 1):
        """Increment v3 summary triggered count."""
        self._counters["discourse_summary_v3_triggered_total"] = (
            self._counters.get("discourse_summary_v3_triggered_total", 0) + value
        )

    def discourse_summary(self) -> Dict[str, any]:
        """Return a snapshot of DiscourseBlockTree metrics."""
        return {
            "requests_total": self._counters.get("discourse_pipeline_requests_total", 0),
            "latency_ms": {
                b.upper_bound_ms: b.count
                for b in self._histograms.get("discourse_pipeline_latency_seconds", [])
            },
            "blocks_active": self._gauges.get("discourse_blocks_active", 0.0),
            "blocks_total": self._counters.get("discourse_blocks_total", 0),
            "edu_processed_total": self._counters.get("discourse_edu_processed_total", 0),
            "v3_triggered_total": self._counters.get("discourse_summary_v3_triggered_total", 0),
        }

    # ── Legacy summary / Prometheus export ───────────────────────────────────

    def summary(self) -> Dict[str, any]:
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                k: [{"le": b.upper_bound_ms, "count": b.count} for b in buckets]
                for k, buckets in self._histograms.items()
            },
            "recent_errors": self._errors[-10:],
            "error_rate": self.error_rate(),
            "security_block_rate": self.security_block_rate(),
            "consecutive_llm_failures": self.consecutive_llm_failures(),
            "avg_llm_latency_ms": self.avg_llm_latency_ms(),
        }

    # ── Prometheus text format export ────────────────────────────────────────

    def to_prometheus(self) -> str:
        """Export metrics in Prometheus exposition format."""
        lines = []

        # Counters
        for name, value in self._counters.items():
            lines.append(f"# TYPE {self.prefix}_{name} counter")
            lines.append(f"{self.prefix}_{name} {value}")

        # Gauges
        for name, value in self._gauges.items():
            lines.append(f"# TYPE {self.prefix}_{name} gauge")
            lines.append(f"{self.prefix}_{name} {value}")

        # Histograms
        for name, buckets in self._histograms.items():
            lines.append(f"# TYPE {self.prefix}_{name}_bucket histogram")
            for b in buckets:
                lines.append(
                    f'{self.prefix}_{name}_bucket{{le="{b.upper_bound_ms}"}} {b.count}'
                )
            # +Inf bucket
            total = sum(b.count for b in buckets)
            lines.append(f'{self.prefix}_{name}_bucket{{le="+Inf"}} {total}')
            lines.append(f"{self.prefix}_{name}_count {total}")

        return "\n".join(lines) + "\n"
