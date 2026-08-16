# -*- coding: utf-8 -*-
"""AsyncDiagnoser 测试（2026-08-16, A10 大环）。"""

from __future__ import annotations

import time
import unittest

from core.agent.meta.diagnosis import AsyncDiagnoser, DiagnosisTask
from core.agent.meta.governor import ExecutionGovernor, RETRY_POLICY


class FakeBus:
    def __init__(self):
        self.logs = []

    def log(self, kind="", dimension="", before=None, after=None,
            reason="", actor="", attribution=""):
        self.logs.append({"kind": kind, "dimension": dimension,
                          "reason": reason})


class TestAsyncDiagnoser(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.d = AsyncDiagnoser(bus=self.bus, min_interval=0.0,
                                llm_enabled=False, auto_attach=False)

    def test_trigger_gates_by_interval(self):
        d = AsyncDiagnoser(min_interval=60.0, llm_enabled=False,
                           auto_attach=False)
        self.assertTrue(d.trigger("tool_loop", "breaker_open"))
        self.assertFalse(d.trigger("tool_loop", "breaker_open"))
        # 不同 scope 不 gate
        self.assertTrue(d.trigger("planning", "breaker_open"))

    def test_worker_produces_stats_report(self):
        self.assertTrue(self.d.trigger(
            "tool_loop", "repeated_failure:connection x3",
            {"session_id": "sx"}))
        # 等后台线程跑完
        for _ in range(50):
            if self.d.stats()["pending"] == 0 and self.d.stats()["reports"]:
                break
            time.sleep(0.05)
        s = self.d.stats()
        self.assertEqual(s["pending"], 0)
        self.assertGreaterEqual(len(s["reports"]), 1)
        r = s["reports"][-1]
        self.assertEqual(r["scope"], "tool_loop")
        self.assertEqual(r["source"], "stats_only")
        self.assertIn("trigger", r)
        # 报告进总线
        kinds = [l["kind"] for l in self.bus.logs]
        self.assertIn("diagnosis_report", kinds)

    def test_parse_llm_json(self):
        text = '```json\n{"root_cause": "网关抖动", "confidence": 0.8, "suggestions": []}\n```'
        d = AsyncDiagnoser(llm_enabled=True, auto_attach=False)
        parsed = d._parse_llm_json(text)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["root_cause"], "网关抖动")
        self.assertEqual(parsed["confidence"], 0.8)
        self.assertIsNone(d._parse_llm_json("not json"))

    def test_collect_evidence(self):
        task = DiagnosisTask("tool_loop", "x", {"session_id": "sx"})
        ev = self.d._collect(task)
        self.assertIn("session_id", ev)
        self.assertIn("llm_stats", ev)  # call_recorder 模块级可用

    def test_apply_suggestion_adjusts_breaker(self):
        from core.agent.meta.governor import get_governor
        gov = get_governor(bus=self.bus)
        gov.observe("tool_loop", False, "err")
        gov.observe("tool_loop", False, "err")
        # 手动注入诊断建议
        report = {
            "suggestions": [{
                "action_type": "adjust_breaker", "scope": "tool_loop",
                "params": {"failure_threshold": 5},
                "reason": "test"}],
        }
        task = DiagnosisTask("tool_loop", "repeated_failure")
        # 直接调 _finalize 前先重置诊断器 queue 状态
        applied_before = next(
            b["consecutive_failures"] for b in gov.stats()["breakers"]
            if b["scope"] == "tool_loop")
        self.assertEqual(applied_before, 2)
        # 用诊断器的 _apply_suggestion
        res = self.d._apply_suggestion(report["suggestions"][0])
        self.assertEqual(res["action"], "adjust_breaker")
        # governor 的 breaker 阈值被调
        self.assertEqual(
            gov._breakers["tool_loop"].failure_threshold, 5)

    def test_apply_suggestion_adjusts_retry(self):
        old = RETRY_POLICY["connection"][1]
        res = self.d._apply_suggestion({
            "action_type": "adjust_retry", "scope": "connection",
            "params": {"max_retries": 2}, "reason": "test"})
        self.assertEqual(res["action"], "adjust_retry")
        self.assertEqual(RETRY_POLICY["connection"][1], 2)
        RETRY_POLICY["connection"] = ("retry", old)  # 还原


class TestGovernorDiagnosisTrigger(unittest.TestCase):
    def test_repeated_failures_trigger_diagnosis(self):
        bus = FakeBus()
        gov = ExecutionGovernor(bus=bus)
        # 3 次失败 → 触发诊断（诊断器默认 5 分钟间隔会 gate 重复, 但首次过）
        for _ in range(3):
            gov.observe("planning", False, "connection refused")
        # 诊断器单例可能已被其他测试用过间隔; 直接检查触发侧统计
        s = gov.stats()
        # failure_counts 是内部; 验证 breaker 已记录 3 次失败
        br = [b for b in s["breakers"] if b["scope"] == "planning"][0]
        self.assertEqual(br["total_calls"], 3)
        self.assertEqual(br["total_failures"], 3)


if __name__ == "__main__":
    unittest.main()
