# -*- coding: utf-8 -*-
"""Observability package — re-exports the legacy module surface.

Keeps `from core.agent.observability import StructuredLogger, SessionMetrics,
MetricsAggregator, AlertEngine` working for the v3_common integration bridge
(previously provided by the single-file module core/agent/observability.py).
"""
from __future__ import annotations

from core.agent.observability.alert import AlertEngine
from core.agent.observability.logger import StructuredLogger
from core.agent.observability.metrics import MetricsAggregator, SessionMetrics

__all__ = ["StructuredLogger", "SessionMetrics", "MetricsAggregator", "AlertEngine"]
