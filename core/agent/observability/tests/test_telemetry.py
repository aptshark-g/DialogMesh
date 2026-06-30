# -*- coding: utf-8 -*-
"""
core/agent/observability/tests/test_telemetry.py
─────────────────────────────────────────────────
Telemetry, tracer, store integration tests.
"""

import os
import tempfile
import unittest
import time
import threading

from core.agent.observability.tracer import Tracer, TurnTrace, Span
from core.agent.observability.store import ObservabilityStore
from core.agent.observability.telemetry import Telemetry
from core.agent.observability.alert import AlertSeverity


class TestTracer(unittest.TestCase):

    def test_start_end_turn(self):
        t = Tracer()
        trace = t.start_turn("sess-1", 1, "hello")
        self.assertIsNotNone(trace)
        self.assertEqual(trace.session_id, "sess-1")
        self.assertEqual(trace.turn_index, 1)

        span = t.start_span("COMPILE", input_summary="query")
        self.assertEqual(span.name, "COMPILE")
        self.assertIsNotNone(span.span_id)

        t.end_span("ok", output_summary="fast")
        finished = t.end_turn()
        self.assertIsNotNone(finished)
        self.assertEqual(len(finished.spans), 1)
        # 可能因系统时钟分辨率导致 0ms，所以用 >= 0
        self.assertGreaterEqual(finished.total_duration_ms, 0.0)
        self.assertFalse(finished.has_error)

    def test_nested_spans(self):
        t = Tracer()
        t.start_turn("s1", 1, "q")
        t.start_span("A")
        t.start_span("B")
        t.end_span("ok")
        t.end_span("ok")
        trace = t.end_turn()
        self.assertEqual(len(trace.spans), 2)
        # B 是 A 的子 span
        self.assertEqual(trace.spans[1].parent_id, trace.spans[0].span_id)

    def test_error_trace(self):
        t = Tracer()
        t.start_turn("s1", 1, "q")
        t.start_span("ROUTE")
        t.end_span("error")
        trace = t.end_turn()
        self.assertTrue(trace.has_error)

    def test_get_slow_spans(self):
        t = Tracer()
        t.start_turn("s1", 1, "q")
        span = t.start_span("SLOW")
        time.sleep(0.15)
        t.end_span("ok")
        t.end_turn()

        slow = t.get_slow_spans(threshold_ms=50.0)
        self.assertEqual(len(slow), 1)
        self.assertEqual(slow[0].name, "SLOW")

    def test_max_traces_lru(self):
        t = Tracer(max_traces=3)
        for i in range(5):
            t.start_turn("s", i, "q")
            t.end_turn()
        self.assertEqual(len(t._traces), 3)
        # 最近的是 turn 4,3,2
        self.assertEqual(t._traces[-1].turn_index, 4)
        self.assertEqual(t._traces[0].turn_index, 2)

    def test_annotate_span(self):
        t = Tracer()
        t.start_turn("s", 1, "q")
        t.start_span("X")
        t.annotate_span("key", "value")
        t.end_span("ok")
        t.end_turn()
        self.assertEqual(t._traces[-1].spans[0].metadata["key"], "value")

    def test_trace_dict(self):
        t = Tracer()
        t.start_turn("s", 1, "q")
        t.start_span("COMPILE")
        t.end_span("ok")
        trace = t.end_turn()
        d = trace.to_dict()
        self.assertIn("trace_id", d)
        self.assertIn("spans", d)
        self.assertEqual(d["span_count"], 1)
        self.assertIn("duration_ms", d["spans"][0])


class TestObservabilityStore(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.store = ObservabilityStore(self.db_path)
        self.store._ensure_connection()

    def tearDown(self):
        self.store.close()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_save_and_load_trace(self):
        from core.agent.observability.tracer import TurnTrace
        trace = TurnTrace(session_id="s1", turn_index=1, query="hello")
        trace.add_span(name="COMPILE")
        trace.finish()

        self.assertTrue(self.store.save_trace(trace))
        loaded = self.store.load_recent_traces(limit=10)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["turn_index"], 1)

    def test_save_metrics(self):
        summary = {
            "total_turns": 5,
            "clarification_rate": 0.1,
            "llm_fallback_rate": 0.0,
            "avg_confidence": 0.85,
            "avg_latency_ms": 50.0,
            "health_score": 92.0,
            "intent_distribution": {"scan": 3, "read": 2},
        }
        self.assertTrue(self.store.save_metrics("s1", 3, summary))
        hist = self.store.load_metrics_history("s1", limit=10)
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["health_score"], 92.0)

    def test_save_alerts(self):
        from core.agent.observability.alert import Alert, AlertSeverity
        alert = Alert(
            severity=AlertSeverity.WARNING,
            message="test alert",
            metric_name="error_rate",
            threshold=0.1,
            actual_value=0.15,
            timestamp=time.time(),
            session_id="s1",
        )
        self.assertTrue(self.store.save_alerts([alert]))
        loaded = self.store.load_recent_alerts(limit=10)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["metric_name"], "error_rate")

    def test_cleanup_old(self):
        trace = TurnTrace(session_id="s1", turn_index=1, query="q")
        trace.finish()
        self.store.save_trace(trace)

        # 修改 timestamp 到过去
        self.store._conn.execute(
            "UPDATE obs_traces SET timestamp = ? WHERE trace_id = ?",
            (time.time() - 10000, trace.trace_id)
        )
        self.store._conn.commit()

        counts = self.store.cleanup_old(ttl_seconds=3600)
        self.assertGreater(counts[0], 0)
        traces = self.store.load_recent_traces(limit=10)
        self.assertEqual(len(traces), 0)

    def test_stats(self):
        self.assertEqual(self.store.get_stats()["traces"], 0)
        self.assertEqual(self.store.get_stats()["metrics"], 0)
        self.assertEqual(self.store.get_stats()["alerts"], 0)

    def test_batch_traces(self):
        traces = []
        for i in range(5):
            t = TurnTrace(session_id="s", turn_index=i, query="q")
            t.finish()
            traces.append(t)
        self.assertTrue(self.store.save_traces_batch(traces))
        loaded = self.store.load_recent_traces(limit=10)
        self.assertEqual(len(loaded), 5)


class TestTelemetry(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.telemetry = Telemetry(
            store=ObservabilityStore(self.db_path),
            store_enabled=True,
        )
        self.telemetry.store._ensure_connection()

    def tearDown(self):
        self.telemetry.shutdown()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_record_turn(self):
        trace, alerts = self.telemetry.record_turn(
            session_id="s1",
            turn_index=1,
            query="hello",
            latency_ms=50.0,
            intent="scan_memory",
            confidence=0.9,
            execution_status="success",
        )
        # record_turn 简单模式不返回 trace
        self.assertIsNone(trace)
        self.assertEqual(len(alerts), 0)

        # 检查 metrics
        health = self.telemetry.get_session_health("s1")
        self.assertEqual(health["total_turns"], 1)

    def test_start_end_trace(self):
        self.telemetry.start_trace("s1", 1, "hello")
        self.telemetry.start_span("COMPILE", input_summary="q")
        self.telemetry.end_span("ok", output_summary="fast")
        trace, alerts = self.telemetry.end_trace(
            intent="scan",
            confidence=0.9,
            execution_status="success",
        )
        self.assertIsNotNone(trace)
        self.assertEqual(len(trace.spans), 1)
        self.assertEqual(trace.spans[0].name, "COMPILE")

    def test_disabled(self):
        t = Telemetry(enabled=False)
        trace, alerts = t.record_turn("s", 1, "q", 10.0)
        self.assertIsNone(trace)
        self.assertEqual(len(alerts), 0)

    def test_alert_persistence(self):
        # 制造高澄清率触发告警
        for i in range(10):
            self.telemetry.record_turn(
                session_id="s2",
                turn_index=i,
                query="q",
                latency_ms=10.0,
                required_clarification=True,
            )
        health = self.telemetry.get_session_health("s2")
        self.assertLess(health["health_score"], 100)

        # 检查告警已写入 store
        alerts = self.telemetry.store.load_recent_alerts(limit=10)
        self.assertGreater(len(alerts), 0)

    def test_get_global_health(self):
        self.telemetry.record_turn("s1", 1, "q", 10.0)
        self.telemetry.record_turn("s2", 1, "q", 20.0)
        summary = self.telemetry.get_global_health()
        self.assertEqual(summary["sessions"], 2)
        self.assertEqual(summary["total_turns"], 2)

    def test_cleanup(self):
        self.telemetry.record_turn("s", 1, "q", 10.0)
        result = self.telemetry.cleanup(ttl_seconds=1)
        # 1秒内不会被删除
        self.assertEqual(result["logs_deleted"], 0)
        # store 内数据刚写入，也不会被删除
        self.assertEqual(result["traces_deleted"], 0)

    def test_shutdown(self):
        # 确保不抛出异常
        self.telemetry.shutdown()


if __name__ == "__main__":
    unittest.main()
