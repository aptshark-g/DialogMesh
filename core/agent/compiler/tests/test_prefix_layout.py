# -*- coding: utf-8 -*-
"""B-3 固化前缀 golden 测试: 同逻辑上下文 → 0 漂移。"""

import sys
import unittest

sys.path.insert(0, ".")
from core.agent.compiler.prefix_layout import (  # noqa: E402
    normalize_stable_prefix,
    stable_fingerprint,
    strip_volatile,
    tool_defs_sorted,
)


def logical_context(now: str, request_id: str) -> list:
    return [
        {"role": "system", "content": (
            "你是 DialogMesh 助手。\n"
            f"当前时间: {now}\n"           # 易变 → 应被归一化
            f"request_id: {request_id}\n"
            "稳定规则: 回答保持简洁。")},
        {"role": "user", "content": "第一轮提问"},
        {"role": "assistant", "content": "第一轮回答"},
        {"role": "user", "content": "第二轮提问"},
    ]


class TestPrefixLayout(unittest.TestCase):
    def test_same_logical_context_zero_drift(self):
        a = logical_context("2026-08-22T10:00:00Z", "req-abc123")
        b = logical_context("2026-08-23T18:30:45+08:00", "req-xyz789")
        self.assertEqual(
            stable_fingerprint(a), stable_fingerprint(b),
            "同逻辑上下文(不同时间戳/request_id) 必须 0 漂移",
        )

    def test_volatile_only_in_p4(self):
        a = logical_context("2026-08-22T10:00:00Z", "req-abc123")
        b = logical_context("2026-08-22T10:00:01Z", "req-abc124")
        b[-1]["content"] = "第二轮提问(不同本轮输入)"
        # P4（最后一条 user）不同 → include_p4 指纹不同
        self.assertNotEqual(stable_fingerprint(a, include_p4=True),
                            stable_fingerprint(b, include_p4=True))
        # 但 P0-P3 稳定
        self.assertEqual(stable_fingerprint(a), stable_fingerprint(b))

    def test_system_prompt_first_and_stable(self):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "system", "content": "system prompt"},
        ]
        norm = normalize_stable_prefix(msgs)
        self.assertEqual(norm[0]["role"], "system", "system 必须置前")
        self.assertEqual(norm[0]["content"], "system prompt")
        self.assertEqual(norm[-1]["content"], "hi", "P4 保留原文")

    def test_strip_volatile(self):
        dirty = "ts=2026-08-22T10:00:00Z id=550e8400-e29b-41d4-a716-446655440000 req=req-a1b2c3"
        clean = strip_volatile(dirty)
        self.assertNotIn("2026-08-22", clean)
        self.assertNotIn("550e8400", clean)
        self.assertNotIn("req-a1b2c3", clean)

    def test_tools_sorted(self):
        tools = [{"name": "z_tool"}, {"name": "a_tool"}, {"name": "m_tool"}]
        self.assertEqual([t["name"] for t in tool_defs_sorted(tools)],
                         ["a_tool", "m_tool", "z_tool"])


if __name__ == "__main__":
    unittest.main()
