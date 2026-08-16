# -*- coding: utf-8 -*-
"""WarmupManager 测试（2026-08-16 P1-②: 启动期有界预热）。"""

from __future__ import annotations

import os
import tempfile
import time
import unittest

from core.agent.meta.warmup import WarmupManager


class FakeParser:
    def __init__(self):
        self.calls = 0

    def process(self, text):
        self.calls += 1
        return {"ok": True}


class FakeDiscourse:
    def __init__(self):
        self.feeds = []

    def feed(self, text, sid, history=None, **kw):
        self.feeds.append((text, sid))
        return {"ok": True}


class FakeTopic:
    def __init__(self):
        self.routes = 0

    def route(self, **kw):
        self.routes += 1
        return {"action": "continue"}


class FakePCR:
    def __init__(self):
        self.routes = 0

    def route(self, text, **kw):
        self.routes += 1
        return {"zone": "MIXED"}


class FakeEngine:
    def __init__(self):
        self._pcr_router = FakePCR()
        self._intent_parser = FakeParser()
        self._discourse_tree = FakeDiscourse()
        self._topic_tree = FakeTopic()
        self._planner = None
        self._llm_provider = object()


class TestWarmupManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dm_warmup_")
        self.path = os.path.join(self.tmp, "warmup_history.jsonl")
        self.eng = FakeEngine()

    def _wm(self, **kw):
        kw.setdefault("budget_s", 45.0)
        kw.setdefault("path", self.path)
        kw.setdefault("prewarmer", lambda: None)
        return WarmupManager(engine=self.eng, **kw)

    def test_run_warms_all_paths(self):
        wm = self._wm()
        rec = wm.run()
        self.assertEqual(rec["status"], "ok")
        self.assertEqual(len(rec["steps"]), 6)
        self.assertEqual(rec["steps"][0]["step"], "prewarm")
        self.assertEqual(self.eng._pcr_router.routes, 1)
        self.assertEqual(self.eng._intent_parser.calls, 1)
        self.assertEqual(len(self.eng._discourse_tree.feeds), 1)
        self.assertEqual(self.eng._discourse_tree.feeds[0][1], "__warmup__")
        self.assertEqual(self.eng._topic_tree.routes, 1)
        self.assertIsNotNone(self.eng._planner)  # 懒初始化已触发
        self.assertTrue(os.path.exists(self.path))  # A17 落盘

    def test_budget_exhausted_skips_tail(self):
        class SlowishParser:
            def process(self, text):
                time.sleep(1.0)
        self.eng._intent_parser = SlowishParser()
        wm = WarmupManager(engine=self.eng, budget_s=0.5,
                           path=self.path, prewarmer=lambda: None)
        rec = wm.run()
        # 预算极短 → 后续步骤 skipped（不阻塞不假跑）
        self.assertTrue(any(r.get("status") == "skipped"
                            or r.get("reason") == "budget_exhausted"
                            for r in rec["steps"]))
        self.assertEqual(rec["status"], "partial")

    def test_step_error_marks_degraded(self):
        class BadParser:
            def process(self, text):
                raise RuntimeError("boom")
        self.eng._intent_parser = BadParser()
        wm = self._wm()
        rec = wm.run()
        self.assertEqual(rec["steps"][2]["status"], "error")
        self.assertEqual(rec["status"], "degraded")

    def test_no_engine_skips(self):
        wm = WarmupManager(engine=None, path=self.path)
        rec = wm.run()
        self.assertEqual(rec["status"], "skipped")

    def test_history_persist_and_reload(self):
        wm = self._wm()
        wm.run()
        wm2 = self._wm()
        self.assertGreaterEqual(wm2.stats()["runs"], 1)
        self.assertIsNotNone(wm2.stats()["last"])


if __name__ == "__main__":
    unittest.main()
