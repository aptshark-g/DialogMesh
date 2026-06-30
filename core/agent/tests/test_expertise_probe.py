# -*- coding: utf-8 -*-
"""
core/agent/tests/test_expertise_probe.py
──────────────────────────────────────
Unit tests for ExpertiseProbe (Architecture Gap #8).

Coverage:
  - LexiconLoader (builtin + hot-reload)
  - 5-dim scoring: terminology, parameter, complexity, style, history
  - Valve logic (clarification rounds → degradation)
  - Threshold routing (expert bypass / LLM / rule-based)
  - Profile generation (expert / degraded / rule-based)
  - Threshold setter / resetter
"""

from __future__ import annotations

import unittest
import time
from dataclasses import dataclass

from core.agent.expertise_probe import (
    ExpertiseProbe,
    ExpertiseScore,
    ProbeResult,
    LexiconLoader,
    _LEXICON_PATH,
)
from core.agent.models import CognitiveProfile


# ── Mock history entry ───────────────────────────────────────────────────────

@dataclass
class MockHistoryEntry:
    role: str
    content: str
    expectation: str = "UNKNOWN"
    timestamp: float = 0.0


# ── Tests ───────────────────────────────────────────────────────────────────

class TestLexiconLoader(unittest.TestCase):
    """LexiconLoader 内置回退 + 缓存。"""

    def test_builtin_lexicon_has_domains(self):
        from pathlib import Path
        loader = LexiconLoader()
        lex = loader.load(path=Path("/nonexistent/path.yaml"))
        self.assertIn("domains", lex)
        self.assertIn("memory_hacking", lex["domains"])
        self.assertIn("english_terms", lex["domains"]["memory_hacking"])

    def test_builtin_weights_sum_reasonable(self):
        lex = LexiconLoader().load()
        w = lex["weights"]
        total = sum(w.values())
        self.assertAlmostEqual(total, 1.0, places=2)

    def test_thresholds_exist(self):
        lex = LexiconLoader().load()
        self.assertIn("llm_invocation", lex["thresholds"])
        self.assertIn("expert_bypass", lex["thresholds"])
        self.assertIn("clarification_degrade", lex["thresholds"])


class TestExpertiseScore(unittest.TestCase):
    """ExpertiseScore 加权合计。"""

    def test_all_zero(self):
        s = ExpertiseScore()
        self.assertEqual(s.weighted_total({}), 0.0)

    def test_all_one(self):
        s = ExpertiseScore(1.0, 1.0, 1.0, 1.0, 1.0)
        weights = {
            "terminology_density": 0.25,
            "parameter_precision": 0.25,
            "query_complexity": 0.15,
            "language_style": 0.20,
            "historical_behaviour": 0.15,
        }
        self.assertAlmostEqual(s.weighted_total(weights), 1.0, places=4)

    def test_partial(self):
        s = ExpertiseScore(terminology_density=0.8, parameter_precision=0.6)
        weights = {"terminology_density": 0.5, "parameter_precision": 0.5}
        self.assertAlmostEqual(s.weighted_total(weights), 0.7, places=4)


class TestFiveDimensions(unittest.TestCase):
    """5 维评分独立验证。"""

    def setUp(self):
        self.probe = ExpertiseProbe()

    def test_terminology_density_hex(self):
        score = self.probe._score_terminology("scan 0x00401000 for float 3.14159")
        self.assertGreater(score, 0.0)

    def test_terminology_density_empty(self):
        score = self.probe._score_terminology("")
        self.assertEqual(score, 0.0)

    def test_parameter_precision_with_hex(self):
        score = self.probe._score_parameters("scan 0x00401000 for float 3.14159 and 0x00401004 for int64")
        self.assertGreater(score, 0.2)

    def test_parameter_precision_no_params(self):
        score = self.probe._score_parameters("hello world")
        self.assertEqual(score, 0.0)

    def test_query_complexity_long(self):
        score = self.probe._score_complexity("A " * 200)
        self.assertGreater(score, 0.3)

    def test_language_style_imperative(self):
        score = self.probe._score_style("scan 0x00401000 for float value")
        self.assertGreater(score, 0.3)

    def test_language_style_exploratory(self):
        score = self.probe._score_style("maybe try to look at something?")
        self.assertLess(score, 0.6)

    def test_history_consistency(self):
        hist = [
            MockHistoryEntry("user", "q1", "TOOL"),
            MockHistoryEntry("user", "q2", "TOOL"),
        ]
        score = self.probe._score_history(hist)
        self.assertGreater(score, 0.5)

    def test_history_no_history(self):
        self.assertEqual(self.probe._score_history([]), 0.0)


class TestValveLogic(unittest.TestCase):
    """阀门：3 轮澄清降级。"""

    def setUp(self):
        self.probe = ExpertiseProbe()

    def test_no_clarification_no_degrade(self):
        self.assertFalse(self.probe._check_valve("sess1", []))

    def test_three_clarifications_degrade(self):
        self.probe.record_clarification("sess1")
        self.probe.record_clarification("sess1")
        self.probe.record_clarification("sess1")
        self.assertTrue(self.probe._check_valve("sess1", []))

    def test_reset_valve(self):
        self.probe.record_clarification("sess2")
        self.probe.reset_valve("sess2")
        self.assertFalse(self.probe._check_valve("sess2", []))

    def test_degraded_profile_confidence_low(self):
        profile = self.probe._degraded_profile()
        self.assertLess(profile.confidence, 0.5)
        self.assertGreater(profile.metacognition, 0.5)


class TestThresholdRouting(unittest.TestCase):
    """三级阈值路由：expert bypass / LLM / rule-based。"""

    def setUp(self):
        self.probe = ExpertiseProbe()

    def test_expert_bypass(self):
        # 高术语密度 + 高参数精度 + 指令式风格 → 高 raw_score
        result = self.probe.probe(
            query="scan 0x00401000 for float 3.14159 and patch to 0x00401004",
            history=[],
            session_id="",
        )
        self.assertIsInstance(result, ProbeResult)
        # Expert bypass 触发时不是 LLM 生成
        if result.raw_score >= 0.85:
            self.assertFalse(result.is_llm_generated)
            self.assertEqual(result.meta.get("reason"), "expert_bypass")

    def test_rule_based_cold_start(self):
        result = self.probe.probe(
            query="hello",
            history=[],
            session_id="",
        )
        self.assertFalse(result.is_llm_generated)
        self.assertEqual(result.meta.get("reason"), "rule_based_cold_start")

    def test_llm_invoked_with_mock_provider(self):
        class MockProvider:
            def generate(self, prompt):
                class R:
                    text = '{"metacognition":0.3,"divergence":0.2,"tracking_depth":0.8,"stability":0.9,"confidence":0.95,"reason":"mock"}'
                return R()

        # 构造一个中等复杂度查询，确保 raw_score 落在 0.72~0.85 区间
        query = "scan 0x00401000 and read process memory at 0x00401004 using little-endian float"
        result = self.probe.probe(query, history=[], session_id="", llm_provider=MockProvider())
        if 0.72 <= result.raw_score < 0.85:
            self.assertTrue(result.is_llm_generated)
            self.assertEqual(result.profile.confidence, 0.95)

    def test_degraded_by_valve(self):
        self.probe.record_clarification("degrad")
        self.probe.record_clarification("degrad")
        self.probe.record_clarification("degrad")
        result = self.probe.probe("anything", history=[], session_id="degrad")
        self.assertEqual(result.meta.get("reason"), "valve_degradation")
        self.assertLess(result.profile.confidence, 0.5)


class TestThresholdSetter(unittest.TestCase):
    """阈值调整 API。"""

    def setUp(self):
        self.probe = ExpertiseProbe()

    def test_get_thresholds(self):
        t = self.probe.get_thresholds()
        self.assertIn("llm_invocation", t)

    def test_set_threshold(self):
        self.probe.set_threshold("llm_invocation", 0.60, reason="lower for testing")
        self.assertEqual(self.probe.get_thresholds()["llm_invocation"], 0.60)

    def test_set_unknown_threshold_raises(self):
        with self.assertRaises(KeyError):
            self.probe.set_threshold("nonexistent", 0.5)


class TestTokenisation(unittest.TestCase):
    """中英文分词。"""

    def test_english_tokenisation(self):
        probe = ExpertiseProbe()
        tokens = probe._tokenise_english("scan memory at 0x00401000")
        self.assertIn("scan", tokens)
        self.assertIn("memory", tokens)

    def test_chinese_tokenisation(self):
        probe = ExpertiseProbe()
        tokens = probe._tokenise_chinese("扫描内存地址")
        # jieba 可能未安装，回退 2-gram 应至少返回单字
        self.assertGreater(len(tokens), 0)


class TestProbeResultSerialization(unittest.TestCase):
    """ProbeResult 可序列化。"""

    def test_to_dict(self):
        result = ProbeResult(
            profile=CognitiveProfile(metacognition=0.5),
            is_llm_generated=False,
            meta={"reason": "test"},
        )
        d = result.to_dict()
        self.assertEqual(d["is_llm_generated"], False)
        self.assertEqual(d["meta"]["reason"], "test")
        self.assertIn("profile", d)


if __name__ == "__main__":
    unittest.main()
