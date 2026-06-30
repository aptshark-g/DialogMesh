# -*- coding: utf-8 -*-
"""
core/agent/window/tests/test_window.py
──────────────────────────────────────
Context window manager unit tests.
"""

import unittest

from core.agent.pcr.datacontract import HistoryEntry
from core.agent.window.token_counter import TokenCounter
from core.agent.window.compressor import (
    PassThroughCompressor,
    TruncationCompressor,
    HierarchicalCompressor,
    CompressionResult,
)
from core.agent.window.context_window_manager import ContextWindowManager, WindowBudget


class TestTokenCounter(unittest.TestCase):

    def test_empty(self):
        c = TokenCounter()
        self.assertEqual(c.estimate_text(""), 0)

    def test_ascii_text(self):
        c = TokenCounter()
        # "hello world" = 11 chars / 4 = 2.75 -> int = 2 tokens
        self.assertEqual(c.estimate_text("hello world"), 2)

    def test_cjk_text(self):
        c = TokenCounter()
        text = "你好世界"  # 4 CJK chars
        self.assertEqual(c.estimate_text(text), 4)

    def test_mixed_text(self):
        c = TokenCounter()
        text = "hello 世界"  # 5 ascii + 1 space + 2 CJK = 7 non-cjk / 4 + 2*1 = 1 + 2 = 3
        self.assertEqual(c.estimate_text(text), 3)

    def test_history_entry(self):
        c = TokenCounter()
        entry = HistoryEntry(role="user", content="hello", expectation="test")
        tokens = c.estimate_entry(entry)
        self.assertGreater(tokens, 0)

    def test_entries_total(self):
        c = TokenCounter()
        entries = [
            HistoryEntry(role="user", content="hi"),
            HistoryEntry(role="assistant", content="hello"),
        ]
        total = c.estimate_entries(entries)
        self.assertEqual(total, sum(c.estimate_entry(e) for e in entries))


class TestPassThroughCompressor(unittest.TestCase):

    def test_no_change(self):
        comp = PassThroughCompressor()
        entries = [HistoryEntry(role="user", content=f"msg{i}") for i in range(3)]
        result = comp.compress(entries)
        self.assertEqual(len(result.entries), 3)
        self.assertEqual(result.dropped, 0)


class TestTruncationCompressor(unittest.TestCase):

    def test_within_limit(self):
        comp = TruncationCompressor(max_turns=10)
        entries = [HistoryEntry(role="user", content=f"msg{i}") for i in range(5)]
        result = comp.compress(entries)
        self.assertEqual(len(result.entries), 5)
        self.assertEqual(result.dropped, 0)

    def test_truncates_head(self):
        comp = TruncationCompressor(max_turns=3)
        entries = [HistoryEntry(role="user", content=f"msg{i}") for i in range(5)]
        result = comp.compress(entries)
        self.assertEqual(len(result.entries), 3)
        self.assertEqual(result.dropped, 2)
        # 保留尾部
        self.assertEqual(result.entries[-1].content, "msg4")
        self.assertEqual(result.entries[0].content, "msg2")

    def test_token_limit(self):
        comp = TruncationCompressor(max_turns=100, max_tokens=20)
        # 每条约 5-6 tokens（role + content + 开销），4条会超 20
        entries = [HistoryEntry(role="user", content="hello world") for _ in range(10)]
        result = comp.compress(entries)
        # 应该被截断到大约 3-4 条
        self.assertLess(len(result.entries), 10)


class TestHierarchicalCompressor(unittest.TestCase):

    def test_small_history_no_compress(self):
        comp = HierarchicalCompressor(hot_max_turns=5)
        entries = [HistoryEntry(role="user", content=f"msg{i}") for i in range(3)]
        result = comp.compress(entries)
        self.assertEqual(len(result.entries), 3)
        self.assertEqual(result.dropped, 0)

    def test_hot_zone_preserved(self):
        comp = HierarchicalCompressor(hot_max_turns=3, warm_max_turns=5)
        entries = [HistoryEntry(role="user", content=f"msg{i}") for i in range(10)]
        result = comp.compress(entries)
        # Hot 3 + Warm 5 = 8 kept, Cold 2 dropped
        self.assertEqual(len(result.entries), 8)
        self.assertEqual(result.dropped, 2)
        # 尾部是 Hot
        self.assertEqual(result.entries[-1].content, "msg9")
        self.assertEqual(result.entries[-2].content, "msg8")
        self.assertEqual(result.entries[-3].content, "msg7")

    def test_hot_token_limit(self):
        comp = HierarchicalCompressor(
            hot_max_turns=5,
            hot_max_tokens=10,  # 很小，只能保留 1-2 条
        )
        entries = [HistoryEntry(role="user", content="hello world long message") for _ in range(5)]
        result = comp.compress(entries)
        # Hot 内部被截断到 1 或 2 条
        self.assertGreaterEqual(len(result.entries), 1)
        self.assertLessEqual(len(result.entries), 2)

    def test_cold_summary(self):
        comp = HierarchicalCompressor(
            hot_max_turns=2,
            warm_max_turns=2,
            enable_cold_summary=True,
        )
        entries = [
            HistoryEntry(role="user", content="q1", expectation="scan"),
            HistoryEntry(role="assistant", content="a1"),
            HistoryEntry(role="user", content="q2"),
            HistoryEntry(role="assistant", content="a2"),
            HistoryEntry(role="user", content="q3"),
            HistoryEntry(role="assistant", content="a3"),
        ]
        result = comp.compress(entries)
        # Hot=2 (q3,a3), Warm=2 (q2,a2), Cold=2 (q1,a1) -> summary
        self.assertEqual(result.dropped, 0)
        self.assertEqual(result.merged, 2)  # 2 cold entries merged
        # 检查摘要存在
        summary_found = any(e.expectation == "cold_summary" for e in result.entries)
        self.assertTrue(summary_found)


class TestWindowBudget(unittest.TestCase):

    def test_default_budget(self):
        b = WindowBudget()
        self.assertEqual(b.context_window, 16000)
        self.assertEqual(b.history_tokens, 1600)
        self.assertEqual(b.system_tokens, 800)
        self.assertEqual(b.hot_turns, 5)

    def test_custom_budget(self):
        b = WindowBudget(context_window=8000, history_ratio=0.2)
        self.assertEqual(b.context_window, 8000)
        self.assertEqual(b.history_tokens, 1600)

    def test_dict_roundtrip(self):
        b = WindowBudget()
        d = b.to_dict()
        self.assertIn("context_window", d)
        self.assertIn("hot_tokens", d)


class TestContextWindowManager(unittest.TestCase):

    def test_pass_through_small(self):
        mgr = ContextWindowManager()
        entries = [HistoryEntry(role="user", content="hi") for _ in range(3)]
        compressed, meta = mgr.compress(entries)
        self.assertEqual(len(compressed), 3)
        self.assertEqual(meta["status"], "pass_through")
        self.assertEqual(meta["compression_ratio"], 1.0)

    def test_compress_large(self):
        # 构造大量历史，超出预算
        mgr = ContextWindowManager(
            budget=WindowBudget(context_window=1000, history_ratio=0.1)
        )
        # history_tokens = 100, 构造 50 条每条约 5 tokens = 250 > 100
        entries = [HistoryEntry(role="user", content="hello world message") for _ in range(50)]
        compressed, meta = mgr.compress(entries)
        self.assertEqual(meta["status"], "compressed")
        self.assertLess(meta["tokens_after"], meta["tokens_before"])
        self.assertLessEqual(meta["tokens_after"], 100)

    def test_empty_history(self):
        mgr = ContextWindowManager()
        compressed, meta = mgr.compress([])
        self.assertEqual(len(compressed), 0)
        self.assertEqual(meta["status"], "empty")

    def test_stats(self):
        mgr = ContextWindowManager()
        entries = [HistoryEntry(role="user", content="hi") for _ in range(5)]
        stats = mgr.get_stats(entries)
        self.assertEqual(stats["turns"], 5)
        self.assertTrue(stats["within_budget"])

    def test_budget_summary(self):
        mgr = ContextWindowManager()
        summary = mgr.get_budget_summary()
        self.assertEqual(summary["context_window"], 16000)

    def test_from_config(self):
        # 使用假配置对象
        class FakeConfig:
            llm_profiles = {"default": {"context_window": 32000}}
            prompt_budget = {
                "system_prompt_max_ratio": 0.05,
                "history_max_ratio": 0.10,
                "glossary_max_ratio": 0.05,
                "output_max_ratio": 0.30,
                "reserve_ratio": 0.10,
            }
            thresholds = {"context_window": {"hot_max": 3, "warm_max": 10, "cold_max": 50}}

        b = WindowBudget.from_config(FakeConfig())
        self.assertEqual(b.context_window, 32000)
        self.assertEqual(b.hot_turns, 3)
        self.assertEqual(b.warm_turns, 10)


if __name__ == "__main__":
    unittest.main()
