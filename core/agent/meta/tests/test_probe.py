# -*- coding: utf-8 -*-
"""ProactiveHealthProbe 测试（2026-08-16 P1-①: 无触发也定期自检）。"""

from __future__ import annotations

import os
import tempfile
import time
import unittest

from core.agent.meta.diagnosis import AsyncDiagnoser
from core.agent.meta.governor import ExecutionGovernor
from core.agent.meta.probe import ProactiveHealthProbe


class FakeRecorder:
    """注入用: 模拟 llm-calls 近窗（recent(n) 接口）。"""

    def __init__(self, calls=None):
        self.calls = calls or []

    def recent(self, n=500):
        return self.calls[-n:]


class TestProactiveProbe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dm_probe_")
        self.gov = ExecutionGovernor()
        self.diag = AsyncDiagnoser(min_interval=0.0, llm_enabled=False,
                                   auto_attach=False)
        self.path = os.path.join(self.tmp, "probe_history.jsonl")

    def _probe(self, **kw):
        kw.setdefault("interval_s", 60.0)
        kw.setdefault("startup_delay_s", 0.0)
        kw.setdefault("path", self.path)
        kw.setdefault("governor", self.gov)
        kw.setdefault("diagnoser", self.diag)
        return ProactiveHealthProbe(**kw)

    def test_healthy_no_findings(self):
        p = self._probe(recorder=FakeRecorder([]))
        run = p.run_once()
        self.assertEqual(run["findings"], [])
        self.assertEqual(run["triggered"], [])
        self.assertEqual(run["skipped"], [])
        self.assertEqual(len(run["signals"]), 3)
        self.assertTrue(os.path.exists(self.path))  # A17 记录落盘

    def test_breaker_weak_spot_triggers_diagnosis(self):
        self.gov.observe("tool_loop", False, "connection refused")
        self.gov.observe("tool_loop", False, "connection refused")
        p = self._probe(recorder=FakeRecorder([]))
        run = p.run_once()
        scopes = [f["scope"] for f in run["findings"]]
        self.assertIn("tool_loop", scopes)
        self.assertIn("tool_loop", run["triggered"])
        self.assertEqual(
            run["findings"][0]["signal"], "breaker")
        # 诊断器已收到主动体检触发（后台线程可能已消费）
        s = self.diag.stats()
        self.assertTrue(s["pending"] >= 0)
        self.assertIn("tool_loop", s["last_trigger"])

    def test_llm_stage_weak_spot_no_false_positive(self):
        rec = FakeRecorder([
            {"stage": "tool_loop", "latency_ms": 100, "ok": False,
             "empty": True, "retries": 2, "error": ""},
            {"stage": "planning", "latency_ms": 50, "ok": True,
             "empty": False, "retries": 0, "error": ""},
        ])
        p = self._probe(recorder=rec)
        run = p.run_once()
        scopes = [f["scope"] for f in run["findings"]]
        self.assertIn("llm:tool_loop", scopes)
        f = next(f for f in run["findings"]
                 if f["scope"] == "llm:tool_loop")
        self.assertIn("empty=1", f["detail"])
        self.assertIn("retries=2", f["detail"])
        # 健康阶段不误报
        self.assertNotIn("llm:planning", scopes)

    def test_diagnoser_frequency_gating_respected(self):
        diag = AsyncDiagnoser(min_interval=60.0, llm_enabled=False,
                              auto_attach=False)
        self.gov.observe("planning", False, "timeout")
        self.gov.observe("planning", False, "timeout")
        p = self._probe(diagnoser=diag, recorder=FakeRecorder([]))
        run1 = p.run_once()
        self.assertIn("planning", run1["triggered"])
        run2 = p.run_once()  # 同 scope 已被诊断器频率门控 → skipped
        self.assertIn("planning", run2["skipped"])
        self.assertNotIn("planning", run2["triggered"])

    def test_history_persist_and_reload(self):
        p = self._probe(recorder=FakeRecorder([]))
        p.run_once()
        # 新实例（模拟重启）从 JSONL 恢复历史
        p2 = self._probe(recorder=FakeRecorder([]))
        self.assertGreaterEqual(p2.stats()["runs"], 1)
        self.assertIsNotNone(p2.stats()["last_run"])

    def test_worker_lifecycle(self):
        p = self._probe(recorder=FakeRecorder([]))
        self.assertFalse(p.stats()["running"])
        p.start()
        self.assertTrue(p.stats()["running"])
        p.start()  # 幂等
        p.stop()
        for _ in range(30):  # stop 1s 内生效（sleep 分片检查）
            if not p.stats()["running"]:
                break
            time.sleep(0.1)
        self.assertFalse(p.stats()["running"])


if __name__ == "__main__":
    unittest.main()
