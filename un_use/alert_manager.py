# -*- coding: utf-8 -*-
"""
core/agent/alert_manager.py
─────────────────────────────
Alert manager (P2-3). Monitors metrics against thresholds and triggers alerts.

Rules:
    - error_rate > threshold           → ALERT_ERROR_RATE_HIGH
    - consecutive_llm_failures > N     → ALERT_LLM_DEGRADED
    - security_block_rate > threshold  → ALERT_SECURITY_SPIKE
    - avg_llm_latency_ms > threshold   → ALERT_LATENCY_HIGH
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable


@dataclass
class AlertRule:
    name: str
    metric: str          # key in MetricsCollector
    comparator: str      # ">" | "<" | ">=" | "<="
    threshold: float
    window: int = 100    # look at last N samples
    cooldown_s: float = 300.0
    severity: str = "warning"  # "warning" | "critical"


@dataclass
class Alert:
    rule: str
    severity: str
    message: str
    timestamp: float
    value: float
    threshold: float
    context: Dict = field(default_factory=dict)


class AlertManager:
    """Lightweight alert manager with threshold-based rules."""

    DEFAULT_RULES = [
        AlertRule("error_rate_high", "error_rate", ">", 0.10, severity="critical"),
        AlertRule("llm_degraded", "consecutive_llm_failures", ">=", 3, severity="warning"),
        AlertRule("security_spike", "security_block_rate", ">", 0.30, severity="warning"),
        AlertRule("latency_high", "avg_llm_latency_ms", ">", 10000, severity="warning"),
    ]

    def __init__(
        self,
        rules: Optional[List[AlertRule]] = None,
        on_alert: Optional[Callable[[Alert], None]] = None,
    ):
        self.rules = rules or list(self.DEFAULT_RULES)
        self.on_alert = on_alert
        self._last_alert_time: Dict[str, float] = {}
        self._alerts: List[Alert] = []
        self._max_alerts = 100

    def check(self, metrics: Dict[str, any]) -> List[Alert]:
        """Evaluate all rules against current metrics. Return new alerts."""
        now = time.time()
        new_alerts = []

        for rule in self.rules:
            # cooldown check
            last = self._last_alert_time.get(rule.name, 0)
            if now - last < rule.cooldown_s:
                continue

            value = metrics.get(rule.metric, 0)
            triggered = self._compare(value, rule.comparator, rule.threshold)

            if triggered:
                alert = Alert(
                    rule=rule.name,
                    severity=rule.severity,
                    message=f"{rule.name}: {rule.metric}={value:.4f} {rule.comparator} {rule.threshold}",
                    timestamp=now,
                    value=value,
                    threshold=rule.threshold,
                    context={"metric": rule.metric, "window": rule.window},
                )
                self._alerts.append(alert)
                self._last_alert_time[rule.name] = now
                new_alerts.append(alert)
                if self.on_alert:
                    self.on_alert(alert)

                if len(self._alerts) > self._max_alerts:
                    self._alerts.pop(0)

        return new_alerts

    @staticmethod
    def _compare(value: float, comparator: str, threshold: float) -> bool:
        if comparator == ">":
            return value > threshold
        if comparator == "<":
            return value < threshold
        if comparator == ">=":
            return value >= threshold
        if comparator == "<=":
            return value <= threshold
        return False

    def summary(self) -> Dict[str, any]:
        return {
            "rules": len(self.rules),
            "total_alerts": len(self._alerts),
            "recent_alerts": [
                {"rule": a.rule, "severity": a.severity, "message": a.message, "time": a.timestamp}
                for a in self._alerts[-10:]
            ],
        }
