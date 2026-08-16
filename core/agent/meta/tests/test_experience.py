# -*- coding: utf-8 -*-
"""自愈经验库测试（2026-08-16, 贝叶斯 prior 累积 + 伪二阶抽象）。"""

from __future__ import annotations

import os
import tempfile
import unittest

from core.agent.meta.experience import (
    ExperienceStore,
    _llm_lesson,
    _template_lesson,
    condense_lesson,
)
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


class TestLessonCondense(unittest.TestCase):
    """P1-③: design_lesson 凝练（LLM 开关 / 模板兜底）。"""

    def setUp(self):
        self._old = os.environ.get("DM_DIAG_LLM_LESSON", "")
        os.environ.pop("DM_DIAG_LLM_LESSON", None)

    def tearDown(self):
        if self._old:
            os.environ["DM_DIAG_LLM_LESSON"] = self._old
        else:
            os.environ.pop("DM_DIAG_LLM_LESSON", None)

    def test_switch_off_uses_template(self):
        lesson = condense_lesson("tool_loop", "网关连接拒绝",
                                 "熔断前检查")
        self.assertIn("tool_loop", lesson)
        self.assertIn("复用时先核对", lesson)

    def test_switch_on_uses_llm(self):
        os.environ["DM_DIAG_LLM_LESSON"] = "1"
        orig = _llm_lesson

        def fake_llm(scope, root_cause, fix_summary, design,
                     gateway_url=""):
            return "tool_loop 调用必须过 governor 熔断前检查, 复用时先核对预算传播"
        try:
            from core.agent.meta import experience as exp_mod
            exp_mod._llm_lesson = fake_llm
            lesson = condense_lesson("tool_loop", "连接拒绝", "熔断")
            self.assertIn("governor", lesson)
            self.assertNotIn("scope %s 曾失败" % "tool_loop", lesson)
        finally:
            exp_mod._llm_lesson = orig

    def test_switch_on_llm_fail_falls_back(self):
        os.environ["DM_DIAG_LLM_LESSON"] = "1"
        orig = _llm_lesson

        def failing_llm(*a, **k):
            return ""
        try:
            from core.agent.meta import experience as exp_mod
            exp_mod._llm_lesson = failing_llm
            lesson = condense_lesson("planning", "LLM 解析失败", "骨架兜底")
            self.assertIn("复用时先核对", lesson)  # 模板兜底
        finally:
            exp_mod._llm_lesson = orig

    def test_template_lesson(self):
        t = _template_lesson("planning", "r", "f")
        self.assertIn("planning", t)
        self.assertIn("r", t)


if __name__ == "__main__":
    unittest.main()
