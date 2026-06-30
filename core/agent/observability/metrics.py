# -*- coding: utf-8 -*-
"""
core/agent/observability/metrics.py
─────────────────────────────────
Metrics aggregation for session quality and performance.

设计要点：
  - SessionMetrics: 单会话计数器 + 滑动窗口
  - MetricsAggregator: 全局指标聚合（多会话）
  - 内存占用 < 10MB（滑动窗口限制）
"""

from __future__ import annotations

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
