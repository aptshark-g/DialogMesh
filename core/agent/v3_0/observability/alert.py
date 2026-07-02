# -*- coding: utf-8 -*-
"""
core/agent/v3_0/observability/alert.py
─────────────────────────────────────
DialogMesh v3.0 异步告警引擎。

用途：
  - 基于阈值检查会话/全局指标，触发分级告警
  - 支持去重（冷却窗口）、热加载阈值、异步回调
  - 与 AsyncMetricsAggregator 集成

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from core.agent.v3_0.observability.models import Alert, AlertSeverity, SessionMetricsSnapshot

logger = logging.getLogger(__name__)


class AsyncAlertEngine:
    """
    异步告警引擎。

    设计要点：
      - 阈值支持运行时热加载（JSON 文件）
      - 三级告警：INFO / WARNING / CRITICAL
      - 去重窗口（默认 5 分钟）
      - 支持异步回调（如发送通知、写入 store）
    """

    DEFAULT_THRESHOLDS = {
        "clarification_rate": 0.30,
        "llm_fallback_rate": 0.20,
        "error_rate": 0.10,
        "avg_latency_ms": 200.0,
        "health_score": 50.0,
    }

    DEDUP_WINDOW_SECONDS = 300.0

    def __init__(
        self,
        thresholds: Optional[Dict[str, float]] = None,
        on_alert: Optional[Callable[[Alert], None]] = None,
        dedup_window_seconds: float = DEDUP_WINDOW_SECONDS,
    ):
        self.thresholds = dict(self.DEFAULT_THRESHOLDS)
        if thresholds:
            self.thresholds.update(thresholds)

        self._on_alert = on_alert
        self._dedup_window = dedup_window_seconds
        self._alerts: List[Alert] = []
        self._last_alert_times: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    # ── 阈值管理 ───────────────────────────────────────────

    def update_threshold(self, metric_name: str, value: float) -> None:
        """更新单个阈值。"""
        self.thresholds[metric_name] = value
        logger.info(f"[AsyncAlertEngine] threshold updated: {metric_name}={value}")

    def load_thresholds_from_file(self, path: str) -> bool:
        """从 JSON 文件加载阈值（热加载）。"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.thresholds.update(data)
                logger.info(f"[AsyncAlertEngine] thresholds loaded from {path}")
                return True
        except (json.JSONDecodeError, FileNotFoundError, PermissionError) as e:
            logger.warning(f"[AsyncAlertEngine] load thresholds failed: {e}")
        return False

    def save_thresholds_to_file(self, path: str) -> bool:
        """保存阈值到 JSON 文件。"""
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.thresholds, f, indent=2, ensure_ascii=False)
            return True
        except (PermissionError, FileNotFoundError) as e:
            logger.warning(f"[AsyncAlertEngine] save thresholds failed: {e}")
            return False

    # ── 告警检查 ───────────────────────────────────────────

    async def check_session_metrics(
        self, metrics_summary: Dict[str, Any]
    ) -> List[Alert]:
        """
        检查会话指标是否触发告警。
        返回本次检查产生的告警列表。
        """
        alerts = []
        session_id = metrics_summary.get("session_id", "")

        for metric_name, threshold in self.thresholds.items():
            if metric_name not in metrics_summary:
                continue

            actual = metrics_summary[metric_name]
            alert = await self._check_single_metric(
                metric_name, threshold, actual, session_id
            )
            if alert:
                alerts.append(alert)

        async with self._lock:
            self._alerts.extend(alerts)

        return alerts

    async def check_snapshot(self, snapshot: SessionMetricsSnapshot) -> List[Alert]:
        """检查 SessionMetricsSnapshot 是否触发告警。"""
        return await self.check_session_metrics(snapshot.to_dict())

    async def _check_single_metric(
        self,
        metric_name: str,
        threshold: float,
        actual: float,
        session_id: str,
    ) -> Optional[Alert]:
        """检查单个指标是否触发告警。"""
        is_lower_better = metric_name == "health_score"

        triggered = False
        if is_lower_better:
            triggered = actual < threshold
        else:
            triggered = actual > threshold

        if not triggered:
            return None

        # 去重检查
        now = time.time()
        key = f"{session_id}:{metric_name}"
        last_time = self._last_alert_times.get(key, 0)
        if now - last_time < self._dedup_window:
            return None

        self._last_alert_times[key] = now

        # 确定告警级别
        severity = await self._determine_severity(metric_name, actual, threshold)
        message = self._format_message(metric_name, threshold, actual, severity)

        alert = Alert(
            severity=severity,
            message=message,
            metric_name=metric_name,
            threshold=threshold,
            actual_value=actual,
            timestamp=now,
            session_id=session_id,
            dedup_key=key,
        )

        # 触发回调
        if self._on_alert:
            try:
                self._on_alert(alert)
            except Exception as e:
                logger.warning(f"[AsyncAlertEngine] on_alert callback error: {e}")

        return alert

    async def _determine_severity(
        self, metric_name: str, actual: float, threshold: float
    ) -> AlertSeverity:
        """根据实际值与阈值的偏离程度确定告警级别。"""
        is_lower_better = metric_name == "health_score"

        if is_lower_better:
            if actual < threshold * 0.8:
                return AlertSeverity.CRITICAL
            elif actual < threshold * 0.9:
                return AlertSeverity.WARNING
            else:
                return AlertSeverity.INFO
        else:
            if actual > threshold * 1.5:
                return AlertSeverity.CRITICAL
            elif actual > threshold * 1.2:
                return AlertSeverity.WARNING
            else:
                return AlertSeverity.INFO

    def _format_message(
        self,
        metric_name: str,
        threshold: float,
        actual: float,
        severity: AlertSeverity,
    ) -> str:
        """格式化告警消息。"""
        direction = "低于" if metric_name == "health_score" else "超过"
        return (
            f"[{severity.value.upper()}] {metric_name} {direction}阈值: "
            f"实际={actual:.2f}, 阈值={threshold:.2f}"
        )

    # ── 查询 ───────────────────────────────────────────

    async def get_active_alerts(self, max_age_seconds: float = 3600) -> List[Alert]:
        """获取最近活跃的告警。"""
        cutoff = time.time() - max_age_seconds
        async with self._lock:
            return [a for a in self._alerts if a.timestamp > cutoff]

    async def get_alert_summary(self) -> Dict[str, Any]:
        """获取告警统计。"""
        async with self._lock:
            total = len(self._alerts)
            by_severity = {"info": 0, "warning": 0, "critical": 0}
            for a in self._alerts:
                by_severity[a.severity.value] += 1

            return {
                "total_alerts": total,
                "by_severity": by_severity,
                "active_alerts": len(
                    [a for a in self._alerts if a.timestamp > time.time() - 3600]
                ),
                "thresholds": dict(self.thresholds),
            }

    async def clear_alerts(self) -> None:
        """清空所有告警。"""
        async with self._lock:
            self._alerts.clear()
            self._last_alert_times.clear()

    # ── 上下文管理器 ───────────────────────────────────────────

    async def __aenter__(self) -> AsyncAlertEngine:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        pass
