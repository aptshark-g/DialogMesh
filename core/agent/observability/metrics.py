# -*- coding: utf-8 -*-
from __future__ import annotations
"""
core/agent/observability/metrics.py
─────────────────────────────────
Metrics aggregation for session quality and performance.

设计要点：
  - SessionMetrics: 单会话计数器 + 滑动窗口
  - MetricsAggregator: 全局指标聚合（多会话）
  - 内存占用 < 10MB（滑动窗口限制）
"""


import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SessionMetrics:
    """
    单会话质量指标。
    使用滑动窗口限制内存占用。
    """
    session_id: str
    total_turns: int = 0
    clarification_count: int = 0
    llm_fallback_count: int = 0
    direct_success_count: int = 0
    error_count: int = 0

    # 滑动窗口（最近 100 轮）
    _confidence_window: deque = field(default_factory=lambda: deque(maxlen=100))
    _latency_window: deque = field(default_factory=lambda: deque(maxlen=100))
    _intent_distribution: Dict[str, int] = field(default_factory=dict)

    def record_turn(
        self,
        confidence: float,
        latency_ms: float,
        intent: str,
        required_clarification: bool = False,
        used_llm_fallback: bool = False,
        execution_status: Optional[str] = None,
    ) -> None:
        """记录一轮指标。"""
        self.total_turns += 1
        self._confidence_window.append(confidence)
        self._latency_window.append(latency_ms)
        self._intent_distribution[intent] = self._intent_distribution.get(intent, 0) + 1

        if required_clarification:
            self.clarification_count += 1
        if used_llm_fallback:
            self.llm_fallback_count += 1
        if execution_status == "success":
            self.direct_success_count += 1
        if execution_status == "error":
            self.error_count += 1

    @property
    def clarification_rate(self) -> float:
        """澄清率。"""
        if self.total_turns == 0:
            return 0.0
        return self.clarification_count / self.total_turns

    @property
    def llm_fallback_rate(self) -> float:
        """LLM 回退率。"""
        if self.total_turns == 0:
            return 0.0
        return self.llm_fallback_count / self.total_turns

    @property
    def avg_confidence(self) -> float:
        """平均置信度。"""
        if not self._confidence_window:
            return 0.0
        return sum(self._confidence_window) / len(self._confidence_window)

    @property
    def avg_latency_ms(self) -> float:
        """平均延迟。"""
        if not self._latency_window:
            return 0.0
        return sum(self._latency_window) / len(self._latency_window)

    @property
    def health_score(self) -> float:
        """
        健康度评分 (0-100)。
        基于：澄清率、LLM回退率、平均置信度、错误率。
        """
        if self.total_turns == 0:
            return 100.0

        # 澄清率惩罚：每 10% 扣 10 分
        clar_penalty = self.clarification_rate * 100
        # LLM 回退率惩罚：每 10% 扣 5 分
        llm_penalty = self.llm_fallback_rate * 50
        # 错误率惩罚：每 10% 扣 15 分
        error_rate = self.error_count / self.total_turns
        error_penalty = error_rate * 150

        score = 100.0 - clar_penalty - llm_penalty - error_penalty
        # 置信度奖励：高置信度 +10 分封顶
        confidence_bonus = min(10, self.avg_confidence * 10)
        score = min(100, max(0, score + confidence_bonus))
        return round(score, 1)

    def get_summary(self) -> Dict[str, Any]:
        """获取指标摘要。"""
        return {
            "session_id": self.session_id[:8] + "...",
            "total_turns": self.total_turns,
            "clarification_rate": round(self.clarification_rate, 3),
            "llm_fallback_rate": round(self.llm_fallback_rate, 3),
            "avg_confidence": round(self.avg_confidence, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "health_score": self.health_score,
            "intent_distribution": dict(self._intent_distribution),
        }

    def __repr__(self) -> str:
        return f"SessionMetrics({self.session_id[:8]}..., health={self.health_score}, turns={self.total_turns})"


class MetricsAggregator:
    """
    全局指标聚合器。
    管理多个会话的指标，支持跨会话统计。
    """

    def __init__(self, max_sessions: int = 100):
        self._metrics: Dict[str, SessionMetrics] = {}
        self._max_sessions = max_sessions
        self._lock = __import__("threading").Lock()

    def get_or_create(self, session_id: str) -> SessionMetrics:
        """获取或创建会话指标。"""
        with self._lock:
            if session_id not in self._metrics:
                # LRU：如果超限，删除最旧的
                if len(self._metrics) >= self._max_sessions:
                    oldest = min(self._metrics, key=lambda k: self._metrics[k].total_turns)
                    del self._metrics[oldest]
                self._metrics[session_id] = SessionMetrics(session_id=session_id)
            return self._metrics[session_id]

    def get_global_summary(self) -> Dict[str, Any]:
        """获取全局指标摘要。"""
        with self._lock:
            if not self._metrics:
                return {"sessions": 0}

            total_turns = sum(m.total_turns for m in self._metrics.values())
            total_clar = sum(m.clarification_count for m in self._metrics.values())
            total_llm = sum(m.llm_fallback_count for m in self._metrics.values())
            total_errors = sum(m.error_count for m in self._metrics.values())

            all_confidences = []
            all_latencies = []
            for m in self._metrics.values():
                all_confidences.extend(m._confidence_window)
                all_latencies.extend(m._latency_window)

            return {
                "sessions": len(self._metrics),
                "total_turns": total_turns,
                "clarification_rate": round(total_clar / total_turns, 3) if total_turns else 0.0,
                "llm_fallback_rate": round(total_llm / total_turns, 3) if total_turns else 0.0,
                "error_rate": round(total_errors / total_turns, 3) if total_turns else 0.0,
                "avg_confidence": round(sum(all_confidences) / len(all_confidences), 3) if all_confidences else 0.0,
                "avg_latency_ms": round(sum(all_latencies) / len(all_latencies), 2) if all_latencies else 0.0,
                "health_scores": [m.health_score for m in self._metrics.values()],
            }

    def get_session_summaries(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取所有会话的指标摘要。"""
        with self._lock:
            return [m.get_summary() for m in list(self._metrics.values())[:limit]]

    def remove_session(self, session_id: str) -> None:
        """删除会话指标。"""
        with self._lock:
            self._metrics.pop(session_id, None)

# === DiscourseBlockTree metrics (merged from v3_common/metrics.py) ===
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

    