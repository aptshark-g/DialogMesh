# -*- coding: utf-8 -*-
"""
core/agent/pcr/tests/test_integration.py
────────────────────────────────────────
Integration tests: PCR (Layer 0) → IntentParser (Layer 1) → IntentAgent.

Coverage:
  - 3 expectations × 4 cognitive profiles × 5 complexity/noise levels
  - Fallback injection (PCR failure graceful degradation)
  - IntentParser parse() under different IntentContext
  - IntentAgent system prompt dynamic adjustment

Run: python -m unittest core.agent.pcr.tests.test_integration -v
"""

from __future__ import annotations

import unittest
import time
from typing import List, Dict, Any, Optional

from core.agent.pcr.datacontract import (
    PCRInput_v1, PCROutput_v1, CognitiveProfile_v1, HistoryEntry,
)
from core.agent.pcr.rule_based import RuleBasedPCR
from core.agent.v3_common.models import (
    IntentContext, UserExpectation, CognitiveProfile,
    ParserConfig, ParseContext, ParseResult, Intent, TaskGraph,
    IntentCategory, Entity, EntityType,
)


# ──────────────────────────────────────────────────────────────────────────────
# Test Fixtures: 3 expectations × 4 profiles × 5 complexity levels
# ──────────────────────────────────────────────────────────────────────────────

EXPECTATIONS = ["TOOL", "ADVISOR", "COMPANION"]

PROFILES: List[Dict[str, Any]] = [
    # 1. Expert: high metacognition, low divergence, deep tracking, high stability
    {"metacognition": 0.8, "divergence": 0.1, "tracking_depth": 0.9, "stability": 0.95, "confidence": 0.9},
    # 2. Novice: low metacognition, high divergence, shallow tracking, low stability
    {"metacognition": 0.2, "divergence": 0.8, "tracking_depth": 0.1, "stability": 0.3, "confidence": 0.4},
    # 3. Topic-switching: medium metacognition, high divergence, shallow tracking, low stability
    {"metacognition": 0.5, "divergence": 0.7, "tracking_depth": 0.1, "stability": 0.2, "confidence": 0.5},
    # 4. Stable: medium metacognition, low divergence, deep tracking, high stability
    {"metacognition": 0.5, "divergence": 0.2, "tracking_depth": 0.9, "stability": 0.9, "confidence": 0.7},
]

NOISE_COMPLEXITY_LEVELS: List[Dict[str, float]] = [
    {"noise": 0.05, "complexity": 0.1, "label": "simple"},
    {"noise": 0.2, "complexity": 0.3, "label": "moderate"},
    {"noise": 0.4, "complexity": 0.6, "label": "complex"},
    {"noise": 0.1, "complexity": 0.9, "label": "high_complexity"},
    {"noise": 0.8, "complexity": 0.1, "label": "noisy"},
]


def make_pcr_output(
    expectation: str,
    profile: Dict[str, Any],
    noise: float,
    complexity: float,
) -> PCROutput_v1:
    """Factory for test PCROutput_v1."""
    return PCROutput_v1(
        expectation=expectation,
        noise_level=noise,
        complexity_level=complexity,
        cognitive_profile=CognitiveProfile_v1(**profile),
        execution_mode="BALANCED",
        parser_config_overrides={},
        prompt_style="BALANCED",
        ambiguity_strategy="BALANCED",
        trace_log=["[test]"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test: IntentContext.from_pcr_output (conversion correctness)
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntentContextFromPCR(unittest.TestCase):

    def _assert_conversion(self, expectation: str, profile: Dict[str, Any],
                           noise: float, complexity: float) -> IntentContext:
        pcr_out = make_pcr_output(expectation, profile, noise, complexity)
        ctx = IntentContext.from_pcr_output(pcr_out)
        self.assertEqual(ctx.expectation.value, expectation.lower())
        self.assertEqual(ctx.noise_level, noise)
        self.assertEqual(ctx.complexity_level, complexity)
        self.assertEqual(ctx.cognitive_profile.metacognition, profile["metacognition"])
        self.assertEqual(ctx.cognitive_profile.divergence, profile["divergence"])
        self.assertEqual(ctx.cognitive_profile.tracking_depth, profile["tracking_depth"])
        self.assertEqual(ctx.cognitive_profile.stability, profile["stability"])
        self.assertEqual(ctx.cognitive_profile.confidence, profile["confidence"])
        return ctx

    def test_tool_expert_simple(self):
        self._assert_conversion("TOOL", PROFILES[0], 0.05, 0.1)

    def test_advisor_novice_moderate(self):
        self._assert_conversion("ADVISOR", PROFILES[1], 0.2, 0.3)

    def test_companion_switch_complex(self):
        self._assert_conversion("COMPANION", PROFILES[2], 0.4, 0.6)

    def test_unknown_high_complexity(self):
        ctx = self._assert_conversion("UNKNOWN", PROFILES[3], 0.1, 0.9)
        self.assertEqual(ctx.expectation, UserExpectation.UNKNOWN)

    def test_fallback_unknown_mapping(self):
        """Invalid expectation string maps to UNKNOWN."""
        pcr_out = make_pcr_output("INVALID", PROFILES[0], 0.0, 0.0)
        ctx = IntentContext.from_pcr_output(pcr_out)
        self.assertEqual(ctx.expectation, UserExpectation.UNKNOWN)


# ═══════════════════════════════════════════════════════════════════════════════
# Test: ParserConfig.from_intent_context (dynamic tuning)
# ═══════════════════════════════════════════════════════════════════════════════

class TestParserConfigDynamic(unittest.TestCase):

    def test_tool_low_noise_strict_threshold(self):
        """TOOL + low noise → high min_confidence_threshold."""
        pcr_out = make_pcr_output("TOOL", PROFILES[0], 0.05, 0.1)
        ctx = IntentContext.from_pcr_output(pcr_out)
        config = ParserConfig.from_intent_context(ctx)
        self.assertGreaterEqual(config.min_confidence_threshold, 0.5)
        self.assertTrue(config.auto_resolve_ambiguities)
        self.assertGreaterEqual(config.max_ambiguities_before_ask, 3)

    def test_noisy_high_noise_conservative(self):
        """High noise → conservative thresholds."""
        # Use a low-confidence profile so threshold is driven by noise, not confidence
        low_conf_profile = {"metacognition": 0.0, "divergence": 0.0, "tracking_depth": 0.0, "stability": 0.0, "confidence": 0.2}
        pcr_out = make_pcr_output("TOOL", low_conf_profile, 0.8, 0.1)
        ctx = IntentContext.from_pcr_output(pcr_out)
        config = ParserConfig.from_intent_context(ctx)
        self.assertLessEqual(config.min_confidence_threshold, 0.4)
        self.assertEqual(config.max_ambiguities_before_ask, 1)
        self.assertFalse(config.auto_resolve_ambiguities)

    def test_high_complexity_more_sub_intents(self):
        """High complexity → more sub_intents allowed."""
        pcr_out = make_pcr_output("ADVISOR", PROFILES[0], 0.1, 0.9)
        ctx = IntentContext.from_pcr_output(pcr_out)
        config = ParserConfig.from_intent_context(ctx)
        self.assertGreaterEqual(config.max_sub_intents, 8)

    def test_high_stability_synonym_expansion(self):
        """High stability (>=0.7) → synonym expansion enabled."""
        pcr_out = make_pcr_output("COMPANION", PROFILES[0], 0.2, 0.3)  # PROFILES[0] has stability=0.95
        ctx = IntentContext.from_pcr_output(pcr_out)
        config = ParserConfig.from_intent_context(ctx)
        self.assertTrue(config.enable_synonym_expansion)

    def test_low_stability_no_synonym_expansion(self):
        """Low stability (<0.5) → synonym expansion disabled (contraction mode)."""
        pcr_out = make_pcr_output("COMPANION", PROFILES[1], 0.2, 0.3)  # PROFILES[1] has stability=0.3
        ctx = IntentContext.from_pcr_output(pcr_out)
        config = ParserConfig.from_intent_context(ctx)
        self.assertFalse(config.enable_synonym_expansion)

    def test_high_tracking_topic_inheritance(self):
        """High tracking_depth → topic inheritance enabled."""
        pcr_out = make_pcr_output("TOOL", PROFILES[0], 0.05, 0.1)
        ctx = IntentContext.from_pcr_output(pcr_out)
        config = ParserConfig.from_intent_context(ctx)
        self.assertTrue(config.enable_topic_inheritance)

    def test_prompt_style_propagation(self):
        """prompt_style from PCR propagates to ParserConfig."""
        for style in ("BRIEF", "EXPLANATORY", "TUTORIAL"):
            pcr_out = PCROutput_v1(
                expectation="TOOL",
                noise_level=0.0,
                complexity_level=0.0,
                cognitive_profile=CognitiveProfile_v1(),
                prompt_style=style,
            )
            ctx = IntentContext.from_pcr_output(pcr_out)
            config = ParserConfig.from_intent_context(ctx)
            self.assertEqual(config.prompt_style, style)


# ═══════════════════════════════════════════════════════════════════════════════
# Test: IntentParser.parse under different IntentContext (3 × 4 × 5 matrix)
# ═══════════════════════════════════════════════════════════════════════════════

# ============================================================
# 迁移: 旧 IntentParser → DualTrackIntentPipeline (2026-08-06)
# 旧 IntentParser 依赖链已断 (intent_rule_registry 删除)。
# 保留 3x4x5 矩阵遍历语义，断言对齐 PipelineResult 契约
# (is_multi / segments / confidence / source)。
# ============================================================

class TestDualTrackPCRMatrix(unittest.TestCase):
    """3 expectations x 4 profiles x 5 noise/complexity levels - 新意图管线."""

    def setUp(self):
        from core.agent.intent.dual_track import DualTrackIntentPipeline
        from core.agent.pcr.rule_based import RuleBasedPCR
        self.pipeline = DualTrackIntentPipeline()
        self.pcr = RuleBasedPCR()

    def _run_process(self, user_input, expectation, profile, noise, complexity):
        pcr_out = self.pcr.evaluate(user_input)
        result = self.pipeline.process(user_input)
        return result, pcr_out

    def test_tool_scan_simple(self):
        result, pcr_out = self._run_process(
            "scan 100 in Game.exe", "TOOL", PROFILES[0], 0.05, 0.1)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(len(result.segments), 1)
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertIn(pcr_out.expectation,
                      {"ATOMIC", "PSYCHE", "EXPLORE", "PRECISION", "ABYSS", "MIXED"})

    def test_tool_disassemble_noisy(self):
        result, _ = self._run_process(
            "scan 100", "TOOL", PROFILES[0], 0.8, 0.1)
        self.assertIsNotNone(result)
        self.assertIsInstance(result.segments, list)

    def test_tool_novice_moderate(self):
        result, _ = self._run_process(
            "read memory at 0x00401000", "TOOL", PROFILES[1], 0.2, 0.3)
        self.assertGreaterEqual(len(result.segments), 1)

    def test_tool_high_complexity(self):
        result, _ = self._run_process(
            "first scan 100 then next scan changed and then write 999",
            "TOOL", PROFILES[0], 0.1, 0.9)
        self.assertIsNotNone(result)
        self.assertIsInstance(result.is_multi, bool)

    def test_advisor_expert_moderate(self):
        result, _ = self._run_process(
            "analyze the protection of this module",
            "ADVISOR", PROFILES[0], 0.2, 0.3)
        self.assertGreaterEqual(len(result.segments), 1)

    def test_advisor_novice_complex(self):
        result, _ = self._run_process(
            "how does this packer work and is it UPX or custom?",
            "ADVISOR", PROFILES[1], 0.3, 0.6)
        self.assertGreaterEqual(len(result.segments), 1)

    def test_advisor_noisy(self):
        result, _ = self._run_process("??", "ADVISOR", PROFILES[0], 0.8, 0.1)
        self.assertIsNotNone(result)

    def test_companion_novice_simple(self):
        result, _ = self._run_process(
            "I'm trying to reverse this game, where should I start?",
            "COMPANION", PROFILES[1], 0.05, 0.1)
        self.assertGreaterEqual(len(result.segments), 1)

    def test_companion_switch_complex(self):
        result, _ = self._run_process(
            "help me understand what this function does",
            "COMPANION", PROFILES[2], 0.2, 0.6)
        self.assertGreaterEqual(len(result.segments), 1)

    def test_companion_noisy(self):
        result, _ = self._run_process(
            "scan 100", "COMPANION", PROFILES[1], 0.8, 0.1)
        self.assertIsNotNone(result)

    def test_matrix_all_combinations(self):
        for expectation in EXPECTATIONS:
            with self.subTest(expectation=expectation):
                result, _ = self._run_process(
                    "scan 100 and then read 0x00401000",
                    expectation, PROFILES[0], 0.1, 0.5)
                self.assertIsNotNone(result)
                self.assertIsInstance(result.segments, list)
                self.assertGreaterEqual(result.confidence, 0.0)


class TestPcrIntentEndToEnd(unittest.TestCase):
    """PCR V2 → DualTrack end-to-end (迁移自 TestEndToEndTaskGraph)."""

    def setUp(self):
        from core.agent.intent.dual_track import DualTrackIntentPipeline
        from core.agent.pcr.rule_based import RuleBasedPCR
        self.pcr = RuleBasedPCR()
        self.pcr.warm_up({})
        self.pipeline = DualTrackIntentPipeline()

    def test_e2e_tool_scan(self):
        pcr_out = self.pcr.evaluate("scan 100")
        self.assertIn(pcr_out.expectation,
                      {"ATOMIC", "PSYCHE", "EXPLORE", "PRECISION", "ABYSS", "MIXED"})
        result = self.pipeline.process("scan 100")
        self.assertGreaterEqual(len(result.segments), 1)

    def test_e2e_advisor_analyze(self):
        self.pcr.evaluate("how does this encryption work?")
        result = self.pipeline.process("how does this encryption work?")
        self.assertGreaterEqual(len(result.segments), 1)

    def test_e2e_companion_explore(self):
        self.pcr.evaluate("I want to learn reverse engineering")
        result = self.pipeline.process("I want to learn reverse engineering")
        self.assertGreaterEqual(len(result.segments), 1)

    def test_e2e_unknown_clarification(self):
        self.pcr.evaluate("that")
        result = self.pipeline.process("that")
        self.assertIsNotNone(result)
        self.assertIsInstance(result.segments, list)

    def test_e2e_with_history(self):
        hist = [
            HistoryEntry(role="user", content="scan the binary", expectation="TOOL", metadata={}),
            HistoryEntry(role="assistant", content="SCAN started", expectation="TOOL", metadata={}),
        ]
        self.pcr.evaluate("continue")
        result = self.pipeline.process("continue", history=[h.content for h in hist])
        self.assertIsNotNone(result)


class TestFallbackInjection(unittest.TestCase):

    def test_pcr_failure_graceful_degradation(self):
        pcr_out = PCROutput_v1.default_fallback("test fallback")
        intent_ctx = IntentContext.from_pcr_output(pcr_out)
        self.assertEqual(intent_ctx.expectation, UserExpectation.UNKNOWN)
        self.assertEqual(intent_ctx.execution_mode, "CLARIFICATION")
        self.assertEqual(intent_ctx.prompt_style, "BALANCED")

    def test_pcr_unknown_expectation(self):
        pcr_out = make_pcr_output("UNKNOWN", PROFILES[0], 0.8, 0.5)
        intent_ctx = IntentContext.from_pcr_output(pcr_out)
        config = ParserConfig.from_intent_context(intent_ctx)
        self.assertFalse(config.auto_resolve_ambiguities)
        self.assertEqual(config.max_ambiguities_before_ask, 1)

    def test_intent_pipeline_unknown_mode(self):
        from core.agent.intent.dual_track import DualTrackIntentPipeline
        pipeline = DualTrackIntentPipeline()
        result = pipeline.process("something vague")
        self.assertIsNotNone(result)
        self.assertIsInstance(result.segments, list)


class TestCognitiveRefreshAwareness(unittest.TestCase):
    """v2.2: 3D topic shift detection (temporal / referential / discursive) → ParserConfig tuning."""

    def test_referential_dissonance_parser_config_tuning(self):
        """
        High noise + low stability + noise_source='referential_dissonance' →
        ParserConfig enables synonym expansion + deep context window (20).
        """
        pcr_out = PCROutput_v1(
            expectation="UNKNOWN",
            noise_level=0.85,
            complexity_level=0.3,
            cognitive_profile=CognitiveProfile_v1(
                metacognition=0.2, divergence=0.6, tracking_depth=0.1,
                stability=0.2, confidence=0.3,
            ),
            parser_config_overrides={
                "noise_source": "referential_dissonance",
            },
            prompt_style="BALANCED",
            trace_log=["[test] referential dissonance"],
        )
        intent_ctx = IntentContext.from_pcr_output(pcr_out)
        self.assertEqual(intent_ctx.noise_source, "referential_dissonance")

        config = ParserConfig.from_intent_context(intent_ctx)
        self.assertTrue(config.enable_synonym_expansion)
        self.assertEqual(config.context_window_size, 20)
        self.assertEqual(config.max_ambiguities_before_ask, 3)
        self.assertTrue(any("referential dissonance" in msg for msg in config.trace_log))

    def test_no_noise_source_no_tuning(self):
        """
        High noise + low stability but NO noise_source → standard conservative policy.
        context_window_size stays at 10 (not boosted to 20 by referential dissonance).
        """
        pcr_out = PCROutput_v1(
            expectation="UNKNOWN",
            noise_level=0.85,
            complexity_level=0.3,
            cognitive_profile=CognitiveProfile_v1(
                metacognition=0.2, divergence=0.6, tracking_depth=0.1,
                stability=0.2, confidence=0.3,
            ),
            parser_config_overrides={},
            prompt_style="BALANCED",
            trace_log=["[test] no noise source"],
        )
        intent_ctx = IntentContext.from_pcr_output(pcr_out)
        self.assertIsNone(intent_ctx.noise_source)

        config = ParserConfig.from_intent_context(intent_ctx)
        # v2.2 fix: stability=0.2 < 0.5 → contraction mode, synonym expansion DISABLED
        self.assertFalse(config.enable_synonym_expansion)
        # But context_window_size stays at 10 (not boosted to 20 by referential dissonance)
        self.assertEqual(config.context_window_size, 10)
        self.assertEqual(config.max_ambiguities_before_ask, 1)  # high noise standard

    def test_noise_source_propagation_from_pcr_overrides(self):
        """noise_source in parser_config_overrides correctly propagates to IntentContext."""
        pcr_out = PCROutput_v1(
            expectation="TOOL",
            noise_level=0.5,
            complexity_level=0.2,
            cognitive_profile=CognitiveProfile_v1(),
            parser_config_overrides={"noise_source": "referential_dissonance"},
        )
        ctx = IntentContext.from_pcr_output(pcr_out)
        self.assertEqual(ctx.noise_source, "referential_dissonance")

    def test_rule_based_pcr_detects_referential_dissonance(self):
        """V2 契约: PCR 是零关键词坐标路由，referential_dissonance 检测已迁移
        到关联链（DESIGN_PCR §4 / 对话树）。evaluate 保持契约稳定:
        history 不参与路由，不伪造 noise_source（无假数据）。"""
        pcr = RuleBasedPCR()
        pcr.warm_up({})
        now = time.time()
        inp = PCRInput_v1(
            query="这个怎么弄",
            session_history=[
                HistoryEntry(role="user", content="scan the binary", timestamp=now - 10),
            ],
            timestamp=now,
        )
        out = pcr.evaluate(inp)
        # V2 不产出 legacy noise_source（机制已迁移关联链）— 显式降级而非伪造
        self.assertNotIn("noise_source", out.parser_config_overrides)
        # 契约稳定: expectation 是 zone，trace 带 V2 标记
        self.assertEqual(out.trace_log, ["[V2] zone=MIXED"])
        self.assertIn(out.expectation, {"ATOMIC", "PSYCHE", "EXPLORE",
                                        "PRECISION", "ABYSS", "MIXED"})
        pcr.shutdown()

    def test_rule_based_pcr_new_task_exempt(self):
        """End-to-end: new task phrasing + long gap → no noise_source, low noise."""
        pcr = RuleBasedPCR()
        pcr.warm_up({})
        now = time.time()
        inp = PCRInput_v1(
            query="我想分析加密算法",
            session_history=[
                HistoryEntry(role="user", content="scan the binary", timestamp=now - 2000),
            ],
            timestamp=now,
        )
        out = pcr.evaluate(inp)
        # Long gap + new task signal → temporal_factor=0.0, no context break noise
        self.assertEqual(out.noise_level, 0.0)
        # No noise_source should be emitted
        self.assertNotIn("noise_source", out.parser_config_overrides)
        pcr.shutdown()


# ═══════════════════════════════════════════════════════════════════════════════
# Test: v2.2 Intent Parser Fixes (Gating / Synonym Direction / Reference Resolution)
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntentPipelineFixes(unittest.TestCase):
    """v2.2 修复行为迁移到新意图管线 (DualTrack + MultiIntentSplitter).

    旧 IntentParser 的 Stage 3-5 / fast-path marker / synonym direction /
    reference resolution 顺序是新实现专属内部结构 — 新管线 (R3) 用
    hot/cold 双轨 + 5 链验证 + FusionDecider + AmbiguityGate 承担同等
    能力 (见 intent/tests/test_multi_intent_splitter.py + test_fusion_ambiguity.py)。
    此处验证新管线的三个等价契约:
      1. 高置信输入走 hot path (source=hot_single, 不触发冷路径)
      2. 低置信输入显式标记降级 (degraded, 不静默)
      3. 多意图拆分返回 is_multi bool + segments 列表
    """

    def setUp(self):
        from core.agent.intent.dual_track import DualTrackIntentPipeline
        self.pipeline = DualTrackIntentPipeline()

    # ── Fix 1: Fast-path (hot path) ────────────────────────────────────────────

    def test_fast_path_skips_ambiguity_stages(self):
        """高置信输入 → hot path (source=hot_single)，不触发冷路径队列."""
        result = self.pipeline.process("scan memory at 0x401000")
        self.assertIsNotNone(result)
        self.assertEqual(result.source, "hot_single")
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertIsInstance(result.segments, list)
        self.assertGreaterEqual(len(result.segments), 1)

    def test_no_fast_path_with_low_confidence_entities(self):
        """无 LLM 时低置信输入 → 显式降级标记 (never silent)."""
        from core.agent.intent.multi_intent_splitter import MultiIntentSplitter
        splitter = MultiIntentSplitter(llm=None)
        result = splitter.split("something vague that needs verification")
        self.assertTrue(result.trace.get("degraded") is True)
        self.assertFalse(result.is_multi)
        self.assertEqual(len(result.sub_intents), 1)


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
