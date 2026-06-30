# -*- coding: utf-8 -*-
"""
core/agent/observability/alert.py
─────────────────────────────────
Alert engine with hot-reload thresholds.

设计要点：
  - 阈值可热加载（无需重启）
  - 三级告警：INFO / WARNING / CRITICAL
  - 告警去重（相同告警 5 分钟内不重复）
  - 无外部依赖（不依赖邮件/短信服务）
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable


class AlertSeverity(Enum):
    """告警级别。"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """告警记录。"""
    severity: AlertSeverity
    message: str
    metric_name: str
    threshold: float
    actual_value: float
    timestamp: float
    session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity.value,
            "message": self.message,
            "metric_name": self.metric_name,
            "threshold": self.threshold,
            "actual_value": self.actual_value,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
        }


class AlertEngine:
    """
    告警引擎。
    检查指标是否超过阈值，触发告警。
    """

    # 默认阈值
    DEFAULT_THRESHOLDS = {
        "clarification_rate": 0.30,    # 澄清率 > 30% 告警
        "llm_fallback_rate": 0.20,     # LLM 回退率 > 20% 告警
        "error_rate": 0.10,            # 错误率 > 10% 告警
        "avg_latency_ms": 200.0,       # 平均延迟 > 200ms 告警
        "health_score": 50.0,          # 健康度 < 50 告警
    }

    # 去重窗口（秒）
    DEDUP_WINDOW_SECONDS = 300

    def __init__(
        self,
        thresholds: Optional[Dict[str, float]] = None,
        on_alert: Optional[Callable[[Alert], None]] = None,
    ):
        self.thresholds = dict(self.DEFAULT_THRESHOLDS)
        if thresholds:
            self.thresholds.update(thresholds)

        self._on_alert = on_alert
        self._alerts: List[Alert] = []
        self._last_alert_times: Dict[str, float] = {}  # metric_name -> last_alert_time
        self._lock = threading.Lock()

    # ── 阈值管理 ───────────────────────────────────────────

    def update_threshold(self, metric_name: str, value: float) -> None:
        """更新单个阈值。"""
        self.thresholds[metric_name] = value

    def load_thresholds_from_file(self, path: str) -> bool:
        """从 JSON 文件加载阈值（热加载）。"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.thresholds.update(data)
                return True
        except (json.JSONDecodeError, FileNotFoundError, PermissionError):
            pass
        return False

    def save_thresholds_to_file(self, path: str) -> bool:
        """保存阈值到 JSON 文件。"""
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.thresholds, f, indent=2, ensure_ascii=False)
            return True
        except (PermissionError, FileNotFoundError):
            return False

    # ── 告警检查 ───────────────────────────────────────────

    def check_session_metrics(self, metrics_summary: Dict[str, Any]) -> List[Alert]:
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
            alert = self._check_single_metric(
                metric_name, threshold, actual, session_id
            )
            if alert:
                alerts.append(alert)

        with self._lock:
            self._alerts.extend(alerts)

        return alerts

    def _check_single_metric(
        self, metric_name: str, threshold: float, actual: float, session_id: str
    ) -> Optional[Alert]:
        """检查单个指标是否触发告警。"""
        # 判断方向：health_score 是越低越差，其他是越高越差
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
        if now - last_time < self.DEDUP_WINDOW_SECONDS:
            return None

        self._last_alert_times[key] = now

        # 确定告警级别
        severity = AlertSeverity.WARNING
        if is_lower_better:
            # 健康度：低于阈值 20% 为 CRITICAL
            if actual < threshold * 0.8:
                severity = AlertSeverity.CRITICAL
            elif actual < threshold * 0.9:
                severity = AlertSeverity.WARNING
            else:
                severity = AlertSeverity.INFO
        else:
            # 其他指标：超过阈值 50% 为 CRITICAL
            if actual > threshold * 1.5:
                severity = AlertSeverity.CRITICAL
            elif actual > threshold * 1.2:
                severity = AlertSeverity.WARNING
            else:
                severity = AlertSeverity.INFO

        message = self._format_message(metric_name, threshold, actual, severity)
        alert = Alert(
            severity=severity,
            message=message,
            metric_name=metric_name,
            threshold=threshold,
            actual_value=actual,
            timestamp=now,
            session_id=session_id,
        )

        # 触发回调
        if self._on_alert:
            try:
                self._on_alert(alert)
            except Exception:
                pass

        return alert

    def _format_message(
        self, metric_name: str, threshold: float, actual: float, severity: AlertSeverity
    ) -> str:
        """格式化告警消息。"""
        direction = "超过" if metric_name != "health_score" else "低于"
        return (
            f"[{severity.value.upper()}] {metric_name} {direction}阈值: "
            f"实际={actual:.2f}, 阈值={threshold:.2f}"
        )

    # ── 查询 ───────────────────────────────────────────

    def get_active_alerts(self, max_age_seconds: float = 3600) -> List[Alert]:
        """获取最近活跃的告警。"""
        cutoff = time.time() - max_age_seconds
        with self._lock:
            return [a for a in self._alerts if a.timestamp > cutoff]

    def get_alert_summary(self) -> Dict[str, Any]:
        """获取告警统计。"""
        with self._lock:
            total = len(self._alerts)
            by_severity = {"info": 0, "warning": 0, "critical": 0}
            for a in self._alerts:
                by_severity[a.severity.value] += 1

            return {
                "total_alerts": total,
                "by_severity": by_severity,
                "active_alerts": len(self.get_active_alerts()),
                "thresholds": dict(self.thresholds),
            }

    def clear_alerts(self) -> None:
        """清空所有告警。"""
        with self._lock:
            self._alerts.clear()
            self._last_alert_times.clear()
