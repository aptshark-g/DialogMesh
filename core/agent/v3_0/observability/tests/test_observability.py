# -*- coding: utf-8 -*-
"""
core/agent/v3_0/observability/tests/test_observability.py
─────────────────────────────────────────────────────────
DialogMesh v3.0 可观测性模块测试。

运行方式：
  cd C:/Users/APTShark/PycharmProjects/DialogMesh
  python -m pytest core/agent/v3_0/observability/tests/test_observability.py -v

或直接使用 asyncio.run 运行测试：
  python core/agent/v3_0/observability/tests/test_observability.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

# 确保项目根目录在路径中
project_root = Path(__file__).resolve().parents[5]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.agent.observability.models import (
    Alert,
    AlertSeverity,
    DecisionLogEntry,
    LogLevel,
    MetricType,
    SessionMetricsSnapshot,
    SpanStatus,
    TurnTrace,
)
from core.agent.observability.logger import AsyncStructuredLogger
from core.agent.observability.metrics import AsyncMetricsAggregator
from core.agent.observability.alert import AsyncAlertEngine
from core.agent.observability.tracer import AsyncTracer
from core.agent.observability.store import AsyncObservabilityStore
from core.agent.observability.telemetry import Telemetry
from core.agent.observability.dashboard import TextDashboard


class TestModels(unittest.TestCase):
    """测试数据模型。"""

    def test_log_entry_creation(self):
        entry = DecisionLogEntry(
            timestamp=time.time(),
            session_id="sess-123",
            turn_index=1,
            query="scan 100",
            total_latency_ms=45.5,
        )
        self.assertEqual(entry.session_id, "sess-123")
        self.assertEqual(entry.turn_index, 1)
        d = entry.to_dict()
        self.assertIn("session_id", d)

    def test_alert_creation(self):
        alert = Alert(
            severity=AlertSeverity.WARNING,
            message="test alert",
            metric_name="error_rate",
            threshold=0.1,
            actual_value=0.15,
            timestamp=time.time(),
        )
        self.assertEqual(alert.dedup_key, "global:error_rate")
        self.assertEqual(alert.to_dict()["severity"], "warning")

    def test_turn_trace(self):
        trace = TurnTrace(session_id="sess-123", turn_index=1, query="scan 100")
        span = trace.add_span(name="COMPILE")
        span.end_ns = time.time_ns()
        time.sleep(0.001)
        trace.finish()
        self.assertTrue(len(trace.spans) > 0)
        self.assertGreater(trace.total_duration_ms, 0)

    def test_span_status_enum(self):
        self.assertEqual(SpanStatus.OK.value, "ok")
        self.assertEqual(SpanStatus.ERROR.value, "error")


class TestAsyncComponents(unittest.IsolatedAsyncioTestCase):
    """测试异步组件。"""

    async def test_async_logger(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AsyncStructuredLogger(
                log_dir=tmpdir,
                buffer_size=5,
                flush_interval_seconds=0.1,
            )
            await logger.start()
            await logger.info("test", "hello v3.0")
            await logger.error("test", "something wrong")
            await asyncio.sleep(0.3)
            await logger.shutdown()

            records = logger.read_recent(10)
            self.assertTrue(len(records) >= 2)
            levels = [r["level"] for r in records]
            self.assertIn("info", levels)
            self.assertIn("error", levels)

    async def test_async_metrics(self):
        async with AsyncMetricsAggregator(max_sessions=10) as agg:
            snap = await agg.record_turn(
                session_id="sess-abc",
                confidence=0.85,
                latency_ms=50.0,
                intent="scan_memory",
                required_clarification=False,
                used_llm_fallback=False,
            )
            self.assertEqual(snap.total_turns, 1)
            self.assertGreater(snap.health_score, 0)

            global_snap = await agg.get_global_snapshot()
            self.assertEqual(global_snap.session_count, 1)

    async def test_async_alert_engine(self):
        async with AsyncAlertEngine() as engine:
            metrics_summary = {
                "session_id": "sess-123",
                "clarification_rate": 0.35,
                "llm_fallback_rate": 0.25,
                "error_rate": 0.20,
                "health_score": 30.0,
                "avg_latency_ms": 250.0,
            }
            alerts = await engine.check_session_metrics(metrics_summary)
            self.assertTrue(len(alerts) > 0)
            severities = [a.severity for a in alerts]
            self.assertIn(AlertSeverity.CRITICAL, severities)

    async def test_async_tracer(self):
        async with AsyncTracer(max_traces=10) as tracer:
            trace = await tracer.start_turn("sess-123", 1, "scan 100")
            self.assertIsNotNone(tracer.get_active_trace())

            span = await tracer.start_span("COMPILE", "input")
            await asyncio.sleep(0.01)
            ended = await tracer.end_span("ok", "compiled")
            self.assertIsNotNone(ended)
            self.assertEqual(ended.status, SpanStatus.OK)

            ended_trace = await tracer.end_turn()
            self.assertIsNotNone(ended_trace)
            self.assertEqual(ended_trace.trace_id, trace.trace_id)

    async def test_async_tracer_context_manager(self):
        async with AsyncTracer(max_traces=10) as tracer:
            await tracer.start_turn("sess-456", 1, "scan 100")
            async with tracer.span("ROUTE", "route input") as span:
                self.assertEqual(span.name, "ROUTE")
            await tracer.end_turn()

    async def test_async_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_obs.db")
            async with AsyncObservabilityStore(db_path) as store:
                trace = TurnTrace(session_id="sess-123", turn_index=1, query="scan")
                trace.finish()
                ok = await store.save_trace(trace)
                self.assertTrue(ok)

                stats = await store.get_stats()
                self.assertEqual(stats["obs_traces_count"], 1)

                recent = await store.get_recent_traces(10)
                self.assertEqual(len(recent), 1)

    async def test_telemetry_record_turn(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            db_path = os.path.join(tmpdir, "obs.db")
            async with Telemetry(
                logger=AsyncStructuredLogger(log_dir=log_dir, buffer_size=5, flush_interval_seconds=0.1),
                metrics=AsyncMetricsAggregator(max_sessions=10),
                alert=AsyncAlertEngine(),
                tracer=AsyncTracer(max_traces=10),
                store=AsyncObservabilityStore(db_path),
                enabled=True,
                store_enabled=True,
            ) as telemetry:
                _, alerts = await telemetry.record_turn(
                    session_id="sess-123",
                    turn_index=1,
                    query="scan 100",
                    latency_ms=30.0,
                    intent="scan_memory",
                    confidence=0.9,
                    execution_status="success",
                )
                self.assertIsInstance(alerts, list)

                health = await telemetry.get_session_health("sess-123")
                self.assertIn("total_turns", health)

    async def test_dashboard_render(self):
        snapshot = SessionMetricsSnapshot(
            session_id="sess-123",
            total_turns=10,
            clarification_count=1,
            llm_fallback_count=1,
            rule_hit_count=5,
            avg_confidence=0.85,
            avg_latency_ms=45.0,
            latency_p95_ms=80.0,
            latency_p99_ms=120.0,
            health_score=85.0,
            intent_distribution={"scan_memory": 5, "read_memory": 3},
        )
        text = TextDashboard.render_session_dashboard(snapshot)
        self.assertIn("会话指标仪表盘", text)
        self.assertIn("scan_memory", text)
        self.assertIn("85", text)

    async def test_telemetry_trace_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "logs")
            async with Telemetry(
                logger=AsyncStructuredLogger(log_dir=log_dir, buffer_size=5, flush_interval_seconds=0.1),
                metrics=AsyncMetricsAggregator(max_sessions=10),
                alert=AsyncAlertEngine(),
                tracer=AsyncTracer(max_traces=10),
                enabled=True,
                store_enabled=False,
            ) as telemetry:
                trace = await telemetry.start_trace("sess-abc", 1, "scan 100")
                self.assertIsNotNone(trace)

                await telemetry.start_span("COMPILE")
                await asyncio.sleep(0.01)
                await telemetry.end_span("ok")

                trace, alerts = await telemetry.end_trace(
                    intent="scan_memory",
                    confidence=0.92,
                    execution_status="success",
                )
                self.assertIsNotNone(trace)
                self.assertEqual(trace.turn_index, 1)


async def main():
    """主测试入口。"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestModels))
    suite.addTests(loader.loadTestsFromTestCase(TestAsyncComponents))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
