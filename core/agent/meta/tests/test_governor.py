# -*- coding: utf-8 -*-
"""ExecutionGovernor 测试（2026-08-16, 元认知子模块）。"""

from __future__ import annotations

import time
import unittest

from core.agent.meta.governor import (
    BreakerState,
    ExecutionGovernor,
    ScopeBreaker,
    classify_error,
)


class FakeBus:
    def __init__(self):
        self.logs = []

    def log(self, kind="", dimension="", before=None, after=None,
            reason="", actor="", attribution=""):
        self.logs.append({
            "kind": kind, "dimension": dimension, "reason": reason,
            "after": after or {},
        })


class TestScopeBreaker(unittest.TestCase):
    def test_open_after_consecutive_failures(self):
        br = ScopeBreaker("x", failure_threshold=3, cooldown_s=60)
        for _ in range(3):
            self.assertTrue(br.allow())
            br.record(False)
        self.assertEqual(br.state, BreakerState.OPEN)
        self.assertFalse(br.allow())

    def test_window_failure_rate_opens(self):
        br = ScopeBreaker("x", failure_threshold=10, min_calls=4,
                          window_failure_rate=0.6, cooldown_s=60)
        for _ in range(4):
            br.record(False)
        self.assertEqual(br.state, BreakerState.OPEN)

    def test_half_open_recovers(self):
        br = ScopeBreaker("x", failure_threshold=2, cooldown_s=0.05)
        br.record(False)
        br.record(False)
        self.assertEqual(br.state, BreakerState.OPEN)
        time.sleep(0.1)
        # 冷却后 allow → HALF_OPEN 放行试探
        self.assertTrue(br.allow())
        self.assertEqual(br.state, BreakerState.HALF_OPEN)
        br.record(True)  # 试探成功 → CLOSED
        self.assertEqual(br.state, BreakerState.CLOSED)
        self.assertTrue(br.allow())

    def test_half_open_failure_reopens(self):
        br = ScopeBreaker("x", failure_threshold=2, cooldown_s=0.05)
        br.record(False)
        br.record(False)
        time.sleep(0.1)
        self.assertTrue(br.allow())
        br.record(False)
        self.assertEqual(br.state, BreakerState.OPEN)
        self.assertFalse(br.allow())


class TestErrorClassification(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify_error("timed out after 90s"), "timeout")
        self.assertEqual(classify_error("WinError 10061 refused"), "connection")
        self.assertEqual(classify_error("Failed to parse LLM graph: json"),
                         "parse")
        self.assertEqual(classify_error("empty_response"), "empty")
        self.assertEqual(classify_error("weird error"), "unknown")


class TestExecutionGovernor(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.gov = ExecutionGovernor(bus=self.bus)

    def test_observe_opens_and_rejects(self):
        self.assertTrue(self.gov.allow("tool_loop"))
        for _ in range(3):
            self.gov.observe("tool_loop", False, error="connection refused")
        self.assertFalse(self.gov.allow("tool_loop"))
        # 治理动作进事件总线
        kinds = [l["kind"] for l in self.bus.logs]
        self.assertIn("governor_action", kinds)
        self.assertTrue(any(
            (l.get("after") or {}).get("action") == "breaker_transition"
            for l in self.bus.logs))

    def test_retry_policy(self):
        self.assertEqual(self.gov.retry_policy_for("timed out"), ("retry", 1))
        self.assertEqual(self.gov.retry_policy_for("empty_response"),
                         ("retry", 2))
        self.assertEqual(self.gov.retry_policy_for("parse error"),
                         ("none", 0))

    def test_idempotent_shortcut(self):
        self.assertTrue(self.gov.begin("req1", "planning"))
        self.assertFalse(self.gov.begin("req1", "planning"))
        self.gov.end("req1", "planning")
        self.assertTrue(self.gov.begin("req1", "planning"))

    def test_stats_shape(self):
        self.gov.observe("tool_loop", True)
        self.gov.observe("tool_loop", False, error="x")
        s = self.gov.stats()
        self.assertEqual(len(s["breakers"]), 1)
        self.assertGreaterEqual(len(s["recent_actions"]), 0)
        self.assertIn("in_flight", s)


if __name__ == "__main__":
    unittest.main()
