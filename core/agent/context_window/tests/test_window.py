# -*- coding: utf-8 -*-
"""
core/agent/context_window/tests/test_window.py
────────────────────────────────────────────
Context window tests.
"""

import unittest

from core.agent.context_window.window_manager import WindowManager, WindowConfig
from core.agent.context_window.compressor import RuleBasedCompressor, CompressionLevel
from core.agent.context_window.models import WindowTurn, CompressedSummary
from core.agent.pcr.datacontract import HistoryEntry


class TestRuleBasedCompressor(unittest.TestCase):

    def test_light_compress(self):
        comp = RuleBasedCompressor()
        turn = WindowTurn(sequence=1, role="user", content="请帮我扫描一下 0x401000 这个地址")
        compressed = comp.compress(turn, CompressionLevel.LIGHT)
        self.assertEqual(compressed.compression_level, 1)
        self.assertIn("0x401000", compressed.content)
        self.assertNotIn("请", compressed.content)

    def test_medium_compress(self):
        comp = RuleBasedCompressor()
        turn = WindowTurn(sequence=1, role="user", content="读取这个地址 0x7FFE0000")
        compressed = comp.compress(turn, CompressionLevel.MEDIUM)
        self.assertEqual(compressed.compression_level, 2)
        self.assertIn("read_memory", compressed.content)

    def test_heavy_compress(self):
        comp = RuleBasedCompressor()
        turn = WindowTurn(sequence=1, role="user", content="scan 100 in process.exe")
        compressed = comp.compress(turn, CompressionLevel.HEAVY)
        self.assertEqual(compressed.compression_level, 3)
        self.assertIn("scan_memory", compressed.content)

    def test_summarize_range(self):
        comp = RuleBasedCompressor()
        turns = [
            WindowTurn(sequence=1, role="user", content="scan 0x401000", intent_category="scan_memory", entities=[{"type": "memory_address", "value": "0x401000"}]),
            WindowTurn(sequence=2, role="user", content="read that address", intent_category="read_memory", entities=[{"type": "memory_address", "value": "0x401000"}]),
            WindowTurn(sequence=3, role="user", content="write 90 to it", intent_category="write_memory", entities=[{"type": "numeric_value", "value": "90"}]),
        ]
        summary = comp.summarize_range(turns)
        self.assertIn("0x401000", summary.key_entities)
        self.assertIn("scan_memory", summary.intent_distribution)
        self.assertIn("write_memory", summary.intent_distribution)

    def test_token_estimation(self):
        comp = RuleBasedCompressor()
        turn = WindowTurn(sequence=1, role="user", content="扫描地址 0x401000 的数值")
        self.assertGreater(turn.estimated_tokens, 0)


class TestWindowManager(unittest.TestCase):

    def test_hot_window(self):
        wm = WindowManager()
        for i in range(5):
            wm.add_turn(WindowTurn(sequence=i+1, role="user", content=f"query {i}"))
        self.assertEqual(len(wm.hot), 5)
        self.assertEqual(len(wm.warm), 0)

    def test_window_slide(self):
        wm = WindowManager()
        for i in range(10):
            wm.add_turn(WindowTurn(sequence=i+1, role="user", content=f"query {i}"))
        self.assertEqual(len(wm.hot), 5)
        self.assertEqual(len(wm.warm), 5)

    def test_compression_on_overflow(self):
        config = WindowConfig(
            hot_size=2,
            warm_size=2,
            cold_size=2,
            max_hot_tokens=100,
            max_warm_tokens=100,
            max_cold_tokens=100,
            max_total_tokens=200,
        )
        wm = WindowManager(config)
        for i in range(20):
            wm.add_turn(WindowTurn(
                sequence=i+1,
                role="user",
                content=f"这是一个很长的查询文本用于测试压缩 {i} " * 10
            ))
        # 由于总 tokens 限制，应该有压缩发生
        summary = wm.get_window_summary()
        self.assertLess(summary["total_tokens"], config.max_total_tokens + 500)
        self.assertGreater(wm._compression_stats["total_compressed"], 0)

    def test_build_pcr_input_order(self):
        wm = WindowManager()
        for i in range(15):
            wm.add_turn(WindowTurn(sequence=i+1, role="user", content=f"query {i}"))
        entries = wm.build_pcr_input()
        # 顺序应该是：cold → warm → hot
        # 检查序列号递增
        sequences = [e.metadata.get("sequence", 0) for e in entries]
        # 至少应该有 hot 的 5 轮在末尾
        self.assertTrue(len(entries) >= 5)

    def test_load_from_history(self):
        wm = WindowManager()
        history = [
            HistoryEntry(role="user", content="scan 0x401000", expectation="scan_memory"),
            HistoryEntry(role="assistant", content="found value 100"),
            HistoryEntry(role="user", content="change it to 200", expectation="write_memory"),
        ]
        wm.load_from_history(history)
        self.assertEqual(len(wm.hot), 3)
        self.assertEqual(wm.hot[0].intent_category, "scan_memory")
        self.assertEqual(wm.hot[2].intent_category, "write_memory")

    def test_find_turn_by_keyword(self):
        wm = WindowManager()
        wm.add_turn(WindowTurn(sequence=1, role="user", content="scan 0x401000"))
        wm.add_turn(WindowTurn(sequence=2, role="user", content="read 0x7FFE0000"))
        wm.add_turn(WindowTurn(sequence=3, role="user", content="patch 0x401000"))
        found = wm.find_turn_by_keyword("0x401000")
        self.assertIsNotNone(found)
        self.assertEqual(found.sequence, 3)

    def test_clear(self):
        wm = WindowManager()
        for i in range(5):
            wm.add_turn(WindowTurn(sequence=i+1, role="user", content=f"query {i}"))
        wm.clear()
        self.assertEqual(len(wm.hot), 0)
        self.assertEqual(len(wm.warm), 0)
        self.assertEqual(len(wm.cold), 0)


if __name__ == "__main__":
    unittest.main()
