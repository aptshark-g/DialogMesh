# -*- coding: utf-8 -*-
"""
core/agent/v3_0/observability/dashboard.py
──────────────────────────────────────────
DialogMesh v3.0 文本仪表盘生成器。

用途：
  - 将会话/全局指标渲染为结构化文本输出（用于 CLI 或日志）
  - 支持实时健康度可视化、告警列表、意图分布
  - 与 AsyncMetricsAggregator 和 AsyncAlertEngine 集成

版本：3.0.0
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.agent.v3_0.observability.models import (
    Alert,
    AlertSeverity,
    GlobalMetricsSnapshot,
    SessionMetricsSnapshot,
)

logger = logging.getLogger(__name__)


class TextDashboard:
    """
    文本仪表盘生成器。

    将指标和告警渲染为易读的文本块，适合 CLI 输出或日志嵌入。
    """

    WIDTH = 62
    HEALTH_BAR_LENGTH = 20

    @classmethod
    def render_session_dashboard(
        cls, snapshot: SessionMetricsSnapshot, alerts: Optional[List[Alert]] = None
    ) -> str:
        """
        渲染单会话仪表盘。

        返回纯文本字符串，可直接 print。
        """
        lines = [
            "=" * cls.WIDTH,
            "  📊 会话指标仪表盘 (v3.0)",
            "=" * cls.WIDTH,
            f"  会话 ID: {snapshot.session_id[:8] + '...' if snapshot.session_id else 'N/A'}",
            f"  总轮数: {snapshot.total_turns}",
            "",
            f"  健康度: {cls._health_bar(snapshot.health_score)}",
            f"  澄清率: {snapshot.clarification_count / max(snapshot.total_turns, 1) * 100:.1f}%",
            f"  规则命中率: {snapshot.rule_hit_count / max(snapshot.total_turns, 1) * 100:.1f}%",
            f"  LLM 回退率: {snapshot.llm_fallback_count / max(snapshot.total_turns, 1) * 100:.1f}%",
            "",
            f"  平均置信度: {snapshot.avg_confidence:.2f}",
            f"  平均延迟: {snapshot.avg_latency_ms:.0f}ms",
            f"  P95 延迟: {snapshot.latency_p95_ms:.0f}ms",
            f"  P99 延迟: {snapshot.latency_p99_ms:.0f}ms",
            "",
            "  意图分布:",
        ]

        if snapshot.intent_distribution:
            for intent, count in list(snapshot.intent_distribution.items())[:5]:
                lines.append(f"    • {intent}: {count} 次")
        else:
            lines.append("    (暂无数据)")

        lines.append("=" * cls.WIDTH)

        # 告警区域
        if alerts:
            lines.append("  ⚠️  活跃告警:")
            for alert in alerts:
                icon = "🔴" if alert.severity == AlertSeverity.CRITICAL else "⚠️"
                lines.append(f"    {icon} {alert.message}")
        else:
            lines.append("  ✅ 无告警")

        lines.append("=" * cls.WIDTH)
        return "\n".join(lines)

    @classmethod
    def render_global_dashboard(
        cls, snapshot: GlobalMetricsSnapshot, alerts: Optional[List[Alert]] = None
    ) -> str:
        """渲染全局仪表盘。"""
        lines = [
            "=" * cls.WIDTH,
            "  🌍 全局指标仪表盘 (v3.0)",
            "=" * cls.WIDTH,
            f"  最近会话数: {snapshot.session_count}",
            f"  总轮数: {snapshot.total_turns}",
            "",
            f"  平均健康度: {cls._health_bar(snapshot.avg_health_score)}",
            f"  平均澄清率: {snapshot.avg_clarification_rate * 100:.1f}%",
            f"  平均 LLM 回退率: {snapshot.avg_llm_fallback_rate * 100:.1f}%",
            f"  平均错误率: {snapshot.avg_error_rate * 100:.1f}%",
            f"  平均延迟: {snapshot.avg_latency_ms:.0f}ms",
            "",
            "  全局意图分布:",
        ]

        if snapshot.intent_distribution:
            for intent, count in list(snapshot.intent_distribution.items())[:5]:
                lines.append(f"    • {intent}: {count} 次")
        else:
            lines.append("    (暂无数据)")

        lines.append("=" * cls.WIDTH)

        if alerts:
            lines.append("  ⚠️  活跃告警:")
            for alert in alerts:
                icon = "🔴" if alert.severity == AlertSeverity.CRITICAL else "⚠️"
                lines.append(f"    {icon} {alert.message}")
        else:
            lines.append("  ✅ 无告警")

        lines.append("=" * cls.WIDTH)
        return "\n".join(lines)

    @classmethod
    def render_alert_summary(cls, summary: Dict[str, Any]) -> str:
        """渲染告警统计摘要。"""
        lines = [
            "─" * cls.WIDTH,
            "  📋 告警统计",
            "─" * cls.WIDTH,
            f"  总告警数: {summary.get('total_alerts', 0)}",
            f"  活跃告警: {summary.get('active_alerts', 0)}",
            "  按级别分布:",
        ]
        by_severity = summary.get("by_severity", {})
        for level in ["info", "warning", "critical"]:
            count = by_severity.get(level, 0)
            icon = "🔴" if level == "critical" else "⚠️" if level == "warning" else "ℹ️"
            lines.append(f"    {icon} {level.upper()}: {count}")
        lines.append("─" * cls.WIDTH)
        return "\n".join(lines)

    @classmethod
    def _health_bar(cls, score: float) -> str:
        """生成健康度进度条。"""
        filled = int(score / 100 * cls.HEALTH_BAR_LENGTH)
        filled = max(0, min(cls.HEALTH_BAR_LENGTH, filled))
        bar = "█" * filled + "░" * (cls.HEALTH_BAR_LENGTH - filled)

        if score >= 80:
            icon = "🟢"
        elif score >= 50:
            icon = "🟡"
        else:
            icon = "🔴"

        return f"{icon} {score:.0f}/100 [{bar}]"
