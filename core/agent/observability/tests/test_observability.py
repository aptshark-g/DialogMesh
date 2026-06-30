# -*- coding: utf-8 -*-
"""
core/agent/observability/tests/test_observability.py
──────────────────────────────────────────────────
Observability layer tests.
"""

import os
import tempfile
import unittest
import time

from core.agent.observability.logger import StructuredLogger
from core.agent.observability.metrics import SessionMetrics, MetricsAggregator
from core.agent.observability.alert import AlertEngine, AlertSeverity


class TestStructuredLogger(unittest.TestCase):

    def setUp(self):
        self.log_dir = tempfile.mkdtemp()
        self.logger = StructuredLogger(log_dir=self.log_dir, buffer_size=3, flush_interval_seconds=1.0)

    def tearDown(self):
        self.logger.shutdown()

    def test_log_turn_and_flush(self):
        for i in range(5):
            self.logger.log_turn(
                session_id=f"sess-{i}",
                turn_index=i,
                query=f"query {i}",
                latency_ms=10.0 * i,
                confidence=0.5 + i * 0.1,
            )
        # 强制 flush（通过 shutdown 前的 flush）
        self.logger._flush()
        records = self.logger.read_recent(n_lines=10)
        self.assertEqual(len(records), 5)
        self.assertEqual(records[0]["turn_index"], 0)

    def test_log_file_rotation(self):
        # 同一天写入
        self.logger.log_turn(session_id="s1", turn_index=1, query="test", latency_ms=1.0)
        self.logger._flush()
        files = list(os.listdir(self.log_dir))
        self.assertTrue(any(f.endswith(".jsonl") for f in files))


class TestSessionMetrics(unittest.TestCase):

    def test_record_turn_and_rates(self):
        m = SessionMetrics(session_id="test")
        for i in range(10):
            m.record_turn(
                confidence=0.5 + i * 0.05,
                latency_ms=20.0 + i * 5,
                intent="scan_memory" if i % 2 == 0 else "read_memory",
                required_clarification=i == 5,
                used_llm_fallback=i == 7,
            )

        self.assertEqual(m.total_turns, 10)
        self.assertEqual(m.clarification_count, 1)
        self.assertEqual(m.llm_fallback_count, 1)
        self.assertAlmostEqual(m.clarification_rate, 0.1)
        self.assertAlmostEqual(m.llm_fallback_rate, 0.1)
        self.assertGreater(m.avg_confidence, 0.0)
        self.assertGreater(m.avg_latency_ms, 0.0)
        self.assertGreaterEqual(m.health_score, 0.0)
        self.assertLessEqual(m.health_score, 100.0)

    def test_health_score_penalty(self):
        m = SessionMetrics(session_id="test")
        for i in range(10):
            m.record_turn(
                confidence=0.3,
                latency_ms=300.0,
                intent="unknown",
                required_clarification=True,
                used_llm_fallback=True,
                execution_status="error",
            )
        self.assertLess(m.health_score, 50.0)

    def test_intent_distribution(self):
        m = SessionMetrics(session_id="test")
        for i in range(6):
            m.record_turn(
                confidence=0.8,
                latency_ms=10.0,
                intent="scan_memory" if i < 4 else "read_memory",
            )
        self.assertEqual(m._intent_distribution.get("scan_memory"), 4)
        self.assertEqual(m._intent_distribution.get("read_memory"), 2)


class TestMetricsAggregator(unittest.TestCase):

    def test_global_summary(self):
        agg = MetricsAggregator()
        for i in range(3):
            m = agg.get_or_create(f"sess-{i}")
            for j in range(5):
                m.record_turn(
                    confidence=0.7,
                    latency_ms=15.0,
                    intent="scan_memory",
                )
        summary = agg.get_global_summary()
        self.assertEqual(summary["sessions"], 3)
        self.assertEqual(summary["total_turns"], 15)


class TestAlertEngine(unittest.TestCase):

    def test_check_session_metrics(self):
        engine = AlertEngine()
        metrics = {
            "session_id": "s1",
            "clarification_rate": 0.35,  # > 0.30，应触发
            "llm_fallback_rate": 0.25,  # > 0.20，应触发
            "health_score": 45.0,       # < 50.0，应触发
            "avg_latency_ms": 150.0,    # < 200.0，不触发
        }
        alerts = engine.check_session_metrics(metrics)
        self.assertGreaterEqual(len(alerts), 2)
        # 检查去重：同一指标再次检查不应触发
        alerts2 = engine.check_session_metrics(metrics)
        self.assertEqual(len(alerts2), 0)  # 5 分钟内去重

    def test_alert_severity_levels(self):
        engine = AlertEngine()
        # 健康度极低 → CRITICAL
        alerts = engine.check_session_metrics({
            "session_id": "s1",
            "health_score": 20.0,
        })
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, AlertSeverity.CRITICAL)

    def test_threshold_hot_reload(self):
        engine = AlertEngine()
        engine.update_threshold("clarification_rate", 0.50)
        alerts = engine.check_session_metrics({
            "session_id": "s1",
            "clarification_rate": 0.35,  # < 0.50，不触发
        })
        self.assertEqual(len(alerts), 0)

    def test_alert_callback(self):
        received = []
        def callback(alert):
            received.append(alert)
        engine = AlertEngine(on_alert=callback)
        engine.check_session_metrics({
            "session_id": "s1",
            "clarification_rate": 0.35,
        })
        self.assertEqual(len(received), 1)


if __name__ == "__main__":
    unittest.main()
