# -*- coding: utf-8 -*-
"""
core/agent/v3_0/observability/metrics.py
────────────────────────────────────────
DialogMesh v3.0 异步指标聚合器。

用途：
  - 实时计算单会话和全局指标
  - 支持滑动窗口、分位点计算、健康度评分
  - 异步事件驱动，支持外部事件总线订阅

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque, Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

from core.agent.v3_0.observability.models import (
    SessionMetricsSnapshot,
    GlobalMetricsSnapshot,
    MetricPoint,
    MetricType,
)

logger = logging.getLogger(__name__)


@dataclass
class _SessionMetricsInternal:
    """内部会话指标状态（可变）。"""
    session_id: str
    total_turns: int = 0
    clarification_count: int = 0
    llm_fallback_count: int = 0
    rule_hit_count: int = 0
    direct_reply_count: int = 0
    error_count: int = 0

    _confidence_sum: float = 0.0
    _latency_sum: float = 0.0
    _confidence_window: deque = field(default_factory=lambda: deque(maxlen=100))
    _latency_window: deque = field(default_factory=lambda: deque(maxlen=100))
    _intent_counter: Counter = field(default_factory=Counter)

    def record_turn(
        self,
        confidence: float,
        latency_ms: float,
        intent: str = "unknown",
        required_clarification: bool = False,
        used_llm_fallback: bool = False,
        used_rule_hit: bool = False,
        direct_reply: bool = False,
        execution_status: Optional[str] = None,
    ) -> None:
        """记录一轮指标。"""
        self.total_turns += 1
        self._confidence_sum += confidence
        self._latency_sum += latency_ms
        self._confidence_window.append(confidence)
        self._latency_window.append(latency_ms)
        self._intent_counter[intent] += 1

        if required_clarification:
            self.clarification_count += 1
        if used_llm_fallback:
            self.llm_fallback_count += 1
        if used_rule_hit:
            self.rule_hit_count += 1
        if direct_reply:
            self.direct_reply_count += 1
        if execution_status == "error":
            self.error_count += 1

    @property
    def avg_confidence(self) -> float:
        if self.total_turns == 0:
            return 0.0
        return self._confidence_sum / self.total_turns

    @property
    def avg_latency_ms(self) -> float:
        if self.total_turns == 0:
            return 0.0
        return self._latency_sum / self.total_turns

    def _percentile(self, values: deque, p: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = int(len(sorted_vals) * p)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]

    @property
    def latency_p95_ms(self) -> float:
        return self._percentile(self._latency_window, 0.95)

    @property
    def latency_p99_ms(self) -> float:
        return self._percentile(self._latency_window, 0.99)

    @property
    def health_score(self) -> float:
        """会话健康度评分 (0-100)。"""
        if self.total_turns == 0:
            return 100.0

        clar_penalty = self.clarification_count / self.total_turns * 100
        llm_penalty = self.llm_fallback_count / self.total_turns * 50
        error_penalty = self.error_count / self.total_turns * 150

        score = 100.0 - clar_penalty - llm_penalty - error_penalty
        confidence_bonus = min(10, self.avg_confidence * 10)
        score = min(100, max(0, score + confidence_bonus))
        return round(score, 1)

    def get_snapshot(self) -> SessionMetricsSnapshot:
        return SessionMetricsSnapshot(
            session_id=self.session_id,
            timestamp=time.time(),
            total_turns=self.total_turns,
            clarification_count=self.clarification_count,
            llm_fallback_count=self.llm_fallback_count,
            rule_hit_count=self.rule_hit_count,
            direct_reply_count=self.direct_reply_count,
            error_count=self.error_count,
            avg_confidence=self.avg_confidence,
            avg_latency_ms=self.avg_latency_ms,
            latency_p95_ms=self.latency_p95_ms,
            latency_p99_ms=self.latency_p99_ms,
            health_score=self.health_score,
            intent_distribution=dict(self._intent_counter.most_common()),
        )


class AsyncMetricsAggregator:
    """
    异步全局指标聚合器。

    设计要点：
      - 使用 asyncio.Lock 保证线程/协程安全
      - 支持事件回调（on_session_update / on_global_update）
      - 支持最大会话数限制（LRU 淘汰）
    """

    def __init__(
        self,
        max_sessions: int = 100,
        on_session_update: Optional[Callable[[SessionMetricsSnapshot], None]] = None,
        on_global_update: Optional[Callable[[GlobalMetricsSnapshot], None]] = None,
    ):
        self._metrics: Dict[str, _SessionMetricsInternal] = {}
        self._max_sessions = max_sessions
        self._on_session_update = on_session_update
        self._on_global_update = on_global_update
        self._lock = asyncio.Lock()
        self._global_window: deque = deque(maxlen=max_sessions)

    # ── 会话管理 ───────────────────────────────────────────

    async def get_or_create(self, session_id: str) -> _SessionMetricsInternal:
        """获取或创建会话指标。"""
        async with self._lock:
            if session_id not in self._metrics:
                if len(self._metrics) >= self._max_sessions:
                    oldest = min(
                        self._metrics,
                        key=lambda k: self._metrics[k].total_turns,
                    )
                    del self._metrics[oldest]
                self._metrics[session_id] = _SessionMetricsInternal(
                    session_id=session_id
                )
            return self._metrics[session_id]

    async def record_turn(
        self,
        session_id: str,
        confidence: float,
        latency_ms: float,
        intent: str = "unknown",
        required_clarification: bool = False,
        used_llm_fallback: bool = False,
        used_rule_hit: bool = False,
        direct_reply: bool = False,
        execution_status: Optional[str] = None,
    ) -> SessionMetricsSnapshot:
        """记录一轮指标并返回会话快照。"""
        metrics = await self.get_or_create(session_id)
        metrics.record_turn(
            confidence=confidence,
            latency_ms=latency_ms,
            intent=intent,
            required_clarification=required_clarification,
            used_llm_fallback=used_llm_fallback,
            used_rule_hit=used_rule_hit,
            direct_reply=direct_reply,
            execution_status=execution_status,
        )
        snapshot = metrics.get_snapshot()

        if self._on_session_update:
            try:
                self._on_session_update(snapshot)
            except Exception as e:
                logger.warning(f"[AsyncMetricsAggregator] session callback error: {e}")

        return snapshot

    async def end_session(self, session_id: str) -> Optional[SessionMetricsSnapshot]:
        """结束会话，移入全局窗口。"""
        async with self._lock:
            metrics = self._metrics.pop(session_id, None)
            if metrics is None:
                return None

            snapshot = metrics.get_snapshot()
            self._global_window.append(snapshot)
            return snapshot

    async def remove_session(self, session_id: str) -> None:
        """删除会话指标。"""
        async with self._lock:
            self._metrics.pop(session_id, None)

    # ── 查询 ───────────────────────────────────────────

    async def get_session_snapshot(self, session_id: str) -> Optional[SessionMetricsSnapshot]:
        """获取单会话指标快照。"""
        async with self._lock:
            metrics = self._metrics.get(session_id)
            return metrics.get_snapshot() if metrics else None

    async def get_global_snapshot(self) -> GlobalMetricsSnapshot:
        """获取全局指标快照。"""
        async with self._lock:
            window = list(self._global_window)
            current = [m.get_snapshot() for m in self._metrics.values()]
            all_sessions = window + current

        if not all_sessions:
            return GlobalMetricsSnapshot()

        total_turns = sum(m.total_turns for m in all_sessions)
        return GlobalMetricsSnapshot(
            timestamp=time.time(),
            session_count=len(all_sessions),
            total_turns=total_turns,
            avg_clarification_rate=(
                sum(m.clarification_count for m in all_sessions) / total_turns
                if total_turns else 0.0
            ),
            avg_llm_fallback_rate=(
                sum(m.llm_fallback_count for m in all_sessions) / total_turns
                if total_turns else 0.0
            ),
            avg_error_rate=(
                sum(m.error_count for m in all_sessions) / total_turns
                if total_turns else 0.0
            ),
            avg_health_score=(
                sum(m.health_score for m in all_sessions) / len(all_sessions)
            ),
            avg_latency_ms=(
                sum(m.avg_latency_ms for m in all_sessions) / len(all_sessions)
            ),
            intent_distribution=self._merge_intent_distributions(all_sessions),
        )

    async def get_all_session_snapshots(self, limit: int = 20) -> List[SessionMetricsSnapshot]:
        """获取所有活跃会话的指标快照。"""
        async with self._lock:
            snapshots = [
                m.get_snapshot()
                for m in list(self._metrics.values())[:limit]
            ]
        return snapshots

    # ── 指标点 API（适配 Prometheus 风格）──────────────────

    async def emit_metric(
        self,
        name: str,
        metric_type: MetricType,
        value: Union[int, float],
        labels: Optional[Dict[str, str]] = None,
    ) -> MetricPoint:
        """发射一个指标点。"""
        point = MetricPoint(
            name=name,
            metric_type=metric_type,
            value=value,
            labels=labels or {},
        )
        logger.debug(f"[AsyncMetricsAggregator] emit metric: {point.to_dict()}")
        return point

    # ── 内部工具 ───────────────────────────────────────────

    @staticmethod
    def _merge_intent_distributions(
        snapshots: List[SessionMetricsSnapshot]
    ) -> Dict[str, int]:
        merged: Counter = Counter()
        for snap in snapshots:
            merged.update(snap.intent_distribution)
        return dict(merged.most_common(10))

    # ── 上下文管理器 ───────────────────────────────────────────

    async def __aenter__(self) -> AsyncMetricsAggregator:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        pass
