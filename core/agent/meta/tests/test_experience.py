# -*- coding: utf-8 -*-
"""自愈经验库测试（2026-08-16, 贝叶斯 prior 累积 + 伪二阶抽象）。"""

from __future__ import annotations

import os
import tempfile
import unittest

import numpy as np

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


class CharBigramVectorizer:
    """基于语义字的稀疏向量（模拟 BGE 尺度: 相关 1.0 / 无关 0.0）。

    与真实模型解耦——测试验证"语义命中 + 噪声过滤"的行为, 不依赖具体
    相似度尺度（BGE-M3 真实阈值 0.45 由 production 常量决定）。
    """

    def __init__(self):
        self.calls = 0

    def encode(self, texts):
        self.calls += 1
        texts = [texts] if isinstance(texts, str) else texts
        out = []
        for t in [str(x) for x in texts]:
            if "网关" in t or "连" in t:
                out.append([1.0, 0.0, 0.0])      # 网关/连接类
            elif "空" in t or "deepseek" in t:
                out.append([0.0, 1.0, 0.0])      # 空返回类
            elif "解析" in t or "LLM" in t:
                out.append([0.0, 0.0, 1.0])      # 解析类
            else:
                out.append([0.0, 0.0, 0.0])      # 无关 → 全零 → sim=0
        return np.array(out)


class TestExperienceRAG(unittest.TestCase):
    """P2-①: 经验检索 RAG（语义 + 关键词混合 / 持久化 / 降级）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dm_exp_rag_")
        self.path = os.path.join(self.tmp, "self_repairs.jsonl")

    def _store(self, **kw):
        kw.setdefault("path", self.path)
        return ExperienceStore(**kw)

    def test_rag_semantic_search_hits_without_keyword_overlap(self):
        vec = CharBigramVectorizer()
        store = self._store(vectorizer=vec)
        store.add({"scope": "tool_loop", "root_cause": "网关连接拒绝导致工具调用失败",
                   "fix_summary": "熔断前检查 + 预算感知重试",
                   "design_lesson": "先核对网关健康与预算余量", "axioms": [],
                   "verify_passed": True})
        store.add({"scope": "llm_reply", "root_cause": "deepseek 返回空",
                   "fix_summary": "空返回重试两次", "design_lesson": "空回复重试",
                   "axioms": [], "verify_passed": True})
        # 无关键词重合（query 不是任一条目子串）→ 关键词检索会空; RAG 命中
        hits = store.search("网关连不上工具失败了")
        self.assertGreaterEqual(len(hits), 1)
        self.assertIn("网关", hits[0]["root_cause"])
        s = store.stats()
        self.assertEqual(s["rag"]["backend"], "semantic")
        self.assertEqual(s["rag"]["vectorized"], 2)

    def test_rag_persistence_reload_no_recompute(self):
        vec1 = CharBigramVectorizer()
        store1 = self._store(vectorizer=vec1)
        store1.add({"scope": "a", "root_cause": "网关连接拒绝 connection refused",
                    "fix_summary": "f1", "design_lesson": "d1",
                    "axioms": [], "verify_passed": True})
        store1.add({"scope": "b", "root_cause": "LLM 空返回",
                    "fix_summary": "f2", "design_lesson": "d2",
                    "axioms": [], "verify_passed": True})
        calls_after_add = vec1.calls
        self.assertGreater(calls_after_add, 0)
        # 重启: 新实例从 JSONL + vectors sidecar 恢复, 不重算条目向量
        vec2 = CharBigramVectorizer()
        store2 = self._store(vectorizer=vec2)
        s = store2.stats()
        self.assertEqual(s["rag"]["vectorized"], 2)
        self.assertEqual(vec2.calls, 0)  # 加载零编码
        hits = store2.search("网关连接断了")
        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(vec2.calls, 1)  # 只编码 query

    def test_rag_disabled_uses_keyword(self):
        store = self._store(rag_enabled=False)
        store.add({"scope": "planning", "root_cause": "LLM 解析失败",
                   "fix_summary": "骨架兜底", "design_lesson": "依赖骨架",
                   "axioms": [], "verify_passed": True})
        # 子串命中（关键词）
        self.assertEqual(len(store.search("LLM 解析失败")), 1)
        # 无子串重合 → 空（关键词检索边界）
        self.assertEqual(store.search("网络问题"), [])
        self.assertEqual(store.stats()["rag"]["backend"], "keyword")

    def test_vectorize_failure_falls_back_to_keyword(self):
        class BrokenVectorizer:
            def encode(self, texts):
                raise RuntimeError("model unavailable")
        store = self._store(vectorizer=BrokenVectorizer())
        store.add({"scope": "tool_loop", "root_cause": "网关连接拒绝",
                   "fix_summary": "f", "design_lesson": "d",
                   "axioms": [], "verify_passed": True})
        # 编码失败 → 关键词兜底, 不抛
        self.assertEqual(len(store.search("网关连接拒绝")), 1)
        s = store.stats()
        self.assertEqual(s["rag"]["vectorized"], 0)

    def test_trim_keeps_entries_vectors_aligned(self):
        vec = CharBigramVectorizer()
        store = self._store(vectorizer=vec, max_entries=3)
        for i in range(5):
            store.add({"scope": f"s{i}",
                       "root_cause": f"根因 {i} 网关连接",
                       "fix_summary": "f", "design_lesson": "d",
                       "axioms": [], "verify_passed": True})
        s = store.stats()
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["rag"]["vectorized"], 3)
        # 检索不崩（entries/vectors 对齐）
        hits = store.search("网关")
        self.assertGreaterEqual(len(hits), 1)


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
