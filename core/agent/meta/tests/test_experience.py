# -*- coding: utf-8 -*-
"""自愈经验库测试（2026-08-16, 贝叶斯 prior 累积 + 伪二阶抽象）。"""

from __future__ import annotations

import os
import tempfile
import unittest

from core.agent.meta.experience import ExperienceStore
from core.agent.meta.diagnosis import _design_constraints


class TestExperienceStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dm_exp_")
        self.path = os.path.join(self.tmp, "self_repairs.jsonl")
        self.store = ExperienceStore(path=self.path)

    def test_add_and_search(self):
        self.store.add({
            "scope": "tool_loop", "root_cause": "网关连接拒绝",
            "fix_summary": "熔断前检查 + 预算感知",
            "design_lesson": "tool_loop 调用须过 governor 检查",
            "axioms": ["A11", "A21"], "verify_passed": True,
        })
        self.store.add({
            "scope": "planning", "root_cause": "LLM 解析失败",
            "fix_summary": "规则骨架兜底",
            "design_lesson": "planning 依赖骨架", "axioms": [],
            "verify_passed": True,
        })
        hits = self.store.search("tool_loop 网关")
        self.assertGreaterEqual(len(hits), 1)
        self.assertIn("tool_loop", hits[0]["scope"])
        # 不相关不命中
        self.assertEqual(self.store.search("zzz_not_exist"), [])

    def test_persist_and_reload(self):
        self.store.add({"scope": "x", "root_cause": "r",
                        "fix_summary": "f", "design_lesson": "d",
                        "axioms": [], "verify_passed": True})
        self.assertTrue(os.path.exists(self.path))
        store2 = ExperienceStore(path=self.path)
        self.assertEqual(store2.stats()["total"], 1)

    def test_design_constraints_available(self):
        # a 的设计约束摘要应非空（AGENTS.md 存在）
        dc = _design_constraints()
        self.assertGreater(len(dc), 0)


if __name__ == "__main__":
    unittest.main()
