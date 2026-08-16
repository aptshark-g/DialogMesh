# -*- coding: utf-8 -*-
"""LLM 调用观测测试（2026-08-16）。"""

from __future__ import annotations

import os
import tempfile
import unittest

from core.agent.llm.call_recorder import (
    LLMCallRecorder,
    llm_call_recent,
    llm_call_stats,
    record_llm_call,
)


class TestLLMCallRecorder(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="dm_llm_calls_")
        self._path = os.path.join(self._tmp, "llm_calls.jsonl")
        self._rec = LLMCallRecorder(
            path=self._path, persist_every=10)

    def test_record_and_stats(self):
        for i in range(5):
            self._rec.record(
                stage="tool_loop", latency_ms=100 + i, ok=True)
        self._rec.record(
            stage="tool_loop", latency_ms=300, ok=False,
            empty=True, error="empty_response")
        s = self._rec.stats()
        self.assertEqual(s["total"], 6)
        self.assertEqual(s["empty"], 1)
        self.assertEqual(s["errors"], 1)
        tl = s["by_stage"]["tool_loop"]
        self.assertEqual(tl["count"], 6)
        self.assertGreaterEqual(tl["p95_ms"], 300)

    def test_recent_and_trim(self):
        rec = LLMCallRecorder(path=self._path, max_entries=3)
        for i in range(5):
            rec.record(stage="planning", latency_ms=i, ok=True)
        self.assertEqual(rec.stats()["total"], 3)
        recent = rec.recent(10)
        self.assertEqual(len(recent), 3)

    def test_persist_and_tail_restore(self):
        rec1 = LLMCallRecorder(path=self._path, persist_every=3)
        for i in range(4):
            rec1.record(stage="llm_reply", latency_ms=i * 10, ok=True)
        rec1._persist()
        self.assertTrue(os.path.exists(self._path))
        # 新实例（模拟重启）从 JSONL 尾部恢复
        rec2 = LLMCallRecorder(path=self._path, persist_every=3)
        s = rec2.stats()
        self.assertGreaterEqual(s["total"], 1)
        self.assertIn("llm_reply", s["by_stage"])

    def test_module_level_api(self):
        record_llm_call(stage="intent_classify", latency_ms=12.0, ok=True)
        s = llm_call_stats()
        self.assertGreaterEqual(s["total"], 1)
        self.assertGreaterEqual(len(llm_call_recent(5)), 1)


if __name__ == "__main__":
    unittest.main()
