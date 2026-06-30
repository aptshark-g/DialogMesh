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
from core.agent.models import (
    IntentContext, UserExpectation, CognitiveProfile,
    ParserConfig, ParseContext, ParseResult, Intent, TaskGraph,
    IntentCategory, Entity, EntityType,
)
from core.agent.intent_parser import IntentParser


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

class TestIntentParserPCRMatrix(unittest.TestCase):
    """3 expectations × 4 profiles × 5 noise/complexity levels."""

    def setUp(self):
        self.parser = IntentParser()
        self.parse_ctx = ParseContext(session_id="test-session")

    def _run_parse(self, user_input: str, expectation: str,
                   profile: Dict[str, Any], noise: float, complexity: float) -> ParseResult:
        pcr_out = make_pcr_output(expectation, profile, noise, complexity)
        intent_ctx = IntentContext.from_pcr_output(pcr_out)
        return self.parser.parse(user_input, intent_ctx, self.parse_ctx)

    # ── TOOL expectation ────────────────────────────────────────────────────────
    def test_tool_scan_simple(self):
        """TOOL + expert + simple → single-node graph, high confidence."""
        result = self._run_parse("scan 100 in Game.exe", "TOOL", PROFILES[0], 0.05, 0.1)
        self.assertTrue(result.is_actionable or result.intent.category == IntentCategory.UNKNOWN)
        self.assertIsNotNone(result.task_graph)
        if result.task_graph:
            self.assertEqual(len(result.task_graph.nodes), 1)
        self.assertIn("[IntentParser] expectation=tool", result.trace_log[0])

    def test_tool_disassemble_noisy(self):
        """TOOL + high noise → may generate ambiguities / ask user."""
        result = self._run_parse("那个，帮我看看", "TOOL", PROFILES[0], 0.8, 0.1)
        self.assertFalse(result.is_actionable)
        self.assertIsNotNone(result.clarification_message)
        self.assertGreater(len(result.suggestions), 0)

    def test_tool_novice_moderate(self):
        """TOOL + novice + moderate → basic graph."""
        result = self._run_parse("read memory at 0x00401000", "TOOL", PROFILES[1], 0.2, 0.3)
        self.assertIsNotNone(result.task_graph)

    def test_tool_high_complexity(self):
        """TOOL + high complexity → may split into sub-intents (multi-intent = not actionable)."""
        result = self._run_parse(
            "first scan 100 then next scan changed and then write 999",
            "TOOL", PROFILES[0], 0.1, 0.9
        )
        # High complexity can trigger multi-intent split; if >1 sub-intents, is_actionable=False
        self.assertIsNotNone(result)
        if result.is_actionable:
            self.assertIsNotNone(result.task_graph)
        else:
            # Multi-intent split detected → either clarification or task_graph=None
            self.assertIsNone(result.task_graph)

    # ── ADVISOR expectation ─────────────────────────────────────────────────────
    def test_advisor_expert_moderate(self):
        """ADVISOR + expert + moderate → full decomposition + explain nodes."""
        result = self._run_parse(
            "analyze the protection of this module",
            "ADVISOR", PROFILES[0], 0.2, 0.3
        )
        self.assertIsNotNone(result.task_graph)
        if result.task_graph:
            # ADVISOR mode adds explanation nodes alongside action nodes
            self.assertGreaterEqual(len(result.task_graph.nodes), 1)

    def test_advisor_novice_complex(self):
        """ADVISOR + novice + complex → more explanatory nodes."""
        result = self._run_parse(
            "how does this packer work and is it UPX or custom?",
            "ADVISOR", PROFILES[1], 0.3, 0.6
        )
        self.assertIsNotNone(result.task_graph)

    def test_advisor_noisy(self):
        """ADVISOR + high noise → ambiguities but may auto-resolve."""
        result = self._run_parse(
            "??",
            "ADVISOR", PROFILES[0], 0.8, 0.1
        )
        self.assertFalse(result.is_actionable)

    # ── COMPANION expectation ───────────────────────────────────────────────────
    def test_companion_novice_simple(self):
        """COMPANION + novice + simple → companion graph with ask_user node."""
        result = self._run_parse(
            "I'm trying to reverse this game, where should I start?",
            "COMPANION", PROFILES[1], 0.05, 0.1
        )
        self.assertIsNotNone(result.task_graph)
        if result.task_graph:
            # COMPANION mode appends ask_user node at the end
            self.assertGreaterEqual(len(result.task_graph.nodes), 1)

    def test_companion_switch_complex(self):
        """COMPANION + topic-switch + complex → exploratory."""
        result = self._run_parse(
            "help me understand what this function does",
            "COMPANION", PROFILES[2], 0.2, 0.6
        )
        self.assertIsNotNone(result.task_graph)

    def test_companion_noisy(self):
        """COMPANION + high noise → ask user for clarification."""
        result = self._run_parse(
            "那个东西",
            "COMPANION", PROFILES[1], 0.8, 0.1
        )
        self.assertFalse(result.is_actionable)

    # ── Full matrix sweep (parameterized via manual expansion) ──────────────────
    def test_matrix_all_combinations(self):
        """Sweep all 3 × 4 × 5 = 60 combinations; ensure no crashes."""
        for expectation in EXPECTATIONS:
            for profile in PROFILES:
                for level in NOISE_COMPLEXITY_LEVELS:
                    with self.subTest(
                        expectation=expectation,
                        profile=profile["metacognition"],
                        noise=level["noise"],
                        complexity=level["complexity"],
                    ):
                        result = self._run_parse(
                            "scan 100 and then read 0x00401000",
                            expectation, profile, level["noise"], level["complexity"],
                        )
                        self.assertIsNotNone(result)
                        self.assertIsNotNone(result.intent)
                        self.assertIsNotNone(result.trace_log)
                        self.assertGreater(len(result.trace_log), 0)


# ═══════════════════════════════════════════════════════════════════════════════
# Test: PCR → IntentParser → TaskGraph (end-to-end)
# ═══════════════════════════════════════════════════════════════════════════════

class TestEndToEndTaskGraph(unittest.TestCase):

    def setUp(self):
        self.pcr = RuleBasedPCR()
        self.pcr.warm_up({})
        self.parser = IntentParser()
        self.parse_ctx = ParseContext(session_id="e2e-test")

    def test_e2e_tool_scan(self):
        """End-to-end: user says 'scan 100' → PCR → IntentParser → TaskGraph."""
        pcr_input = PCRInput_v1(query="scan 100", session_history=[])
        pcr_output = self.pcr.evaluate(pcr_input)
        self.assertEqual(pcr_output.expectation, "TOOL")
        self.assertLess(pcr_output.noise_level, 0.2)

        intent_ctx = IntentContext.from_pcr_output(pcr_output)
        result = self.parser.parse("scan 100", intent_ctx, self.parse_ctx)
        self.assertTrue(result.is_actionable)
        self.assertIsNotNone(result.task_graph)
        self.assertGreaterEqual(len(result.task_graph.nodes), 1)

    def test_e2e_advisor_analyze(self):
        """End-to-end: user asks analytical question."""
        pcr_input = PCRInput_v1(query="how does this encryption work?", session_history=[])
        pcr_output = self.pcr.evaluate(pcr_input)
        intent_ctx = IntentContext.from_pcr_output(pcr_output)
        result = self.parser.parse("how does this encryption work?", intent_ctx, self.parse_ctx)
        self.assertIsNotNone(result.task_graph)

    def test_e2e_companion_explore(self):
        """End-to-end: user is exploratory."""
        pcr_input = PCRInput_v1(query="I want to learn reverse engineering", session_history=[])
        pcr_output = self.pcr.evaluate(pcr_input)
        intent_ctx = IntentContext.from_pcr_output(pcr_output)
        result = self.parser.parse("I want to learn reverse engineering", intent_ctx, self.parse_ctx)
        self.assertIsNotNone(result.task_graph)
        if result.task_graph:
            self.assertGreaterEqual(len(result.task_graph.nodes), 1)

    def test_e2e_unknown_clarification(self):
        """End-to-end: vague input → clarification required."""
        pcr_input = PCRInput_v1(query="那个", session_history=[])
        pcr_output = self.pcr.evaluate(pcr_input)
        intent_ctx = IntentContext.from_pcr_output(pcr_output)
        result = self.parser.parse("那个", intent_ctx, self.parse_ctx)
        self.assertFalse(result.is_actionable)
        self.assertIsNotNone(result.clarification_message)
        self.assertGreater(len(result.suggestions), 0)

    def test_e2e_with_history(self):
        """End-to-end: multi-turn history inference."""
        hist = [
            HistoryEntry(role="user", content="scan the binary", expectation="TOOL", metadata={}),
            HistoryEntry(role="assistant", content="SCAN started", expectation="TOOL", metadata={}),
        ]
        pcr_input = PCRInput_v1(query="continue", session_history=hist)
        pcr_output = self.pcr.evaluate(pcr_input)
        self.assertEqual(pcr_output.expectation, "TOOL")
        intent_ctx = IntentContext.from_pcr_output(pcr_output)
        result = self.parser.parse("continue", intent_ctx, self.parse_ctx)
        self.assertTrue(result.is_actionable)


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Fallback injection (PCR failure does not break IntentAgent)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFallbackInjection(unittest.TestCase):

    def test_pcr_failure_graceful_degradation(self):
        """If PCR fails, IntentContext falls back to UNKNOWN defaults."""
        # Simulate a bad PCR output by forcing an invalid state
        # In real code, this is caught by try-except in IntentAgent
        pcr_out = PCROutput_v1.default_fallback("test fallback")
        intent_ctx = IntentContext.from_pcr_output(pcr_out)
        self.assertEqual(intent_ctx.expectation, UserExpectation.UNKNOWN)
        self.assertEqual(intent_ctx.execution_mode, "CLARIFICATION")
        self.assertEqual(intent_ctx.prompt_style, "BALANCED")

    def test_pcr_unknown_expectation(self):
        """PCR returns UNKNOWN → ParserConfig conservative."""
        pcr_out = make_pcr_output("UNKNOWN", PROFILES[0], 0.8, 0.5)
        intent_ctx = IntentContext.from_pcr_output(pcr_out)
        config = ParserConfig.from_intent_context(intent_ctx)
        self.assertFalse(config.auto_resolve_ambiguities)
        self.assertEqual(config.max_ambiguities_before_ask, 1)

    def test_intent_parser_unknown_mode(self):
        """UNKNOWN expectation → parse still runs, may produce clarification if ambiguities."""
        parser = IntentParser()
        parse_ctx = ParseContext()
        pcr_out = make_pcr_output("UNKNOWN", PROFILES[0], 0.5, 0.5)
        intent_ctx = IntentContext.from_pcr_output(pcr_out)
        result = parser.parse("something vague", intent_ctx, parse_ctx)
        # UNKNOWN expectation does not guarantee non-actionable; 
        # Parser still attempts classification. Ambiguities depend on input.
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.intent)


# ═══════════════════════════════════════════════════════════════════════════════
# Test: v2.2 Cognitive Refresh Awareness — End-to-end 3D topic shift detection
# ═══════════════════════════════════════════════════════════════════════════════

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
        """End-to-end: RuleBasedPCR.evaluate detects referential dissonance and emits noise_source."""
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
        self.assertIn("noise_source", out.parser_config_overrides)
        self.assertEqual(out.parser_config_overrides["noise_source"], "referential_dissonance")
        self.assertGreater(out.noise_level, 0.0)
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

class TestIntentParserV22Fixes(unittest.TestCase):
    """
    Verify the three critical fixes to IntentParser:
    1. Fast-path gating: high-confidence entities → skip Stage 3-5
    2. Synonym direction: high stability=expand, low stability=contract
    3. Reference resolution: moved before entity extraction (Pre-Stage 3.5)
    """

    def setUp(self):
        self.parser = IntentParser()
        self.parse_ctx = ParseContext(session_id="test-v22")

    def _make_context(self, expectation=UserExpectation.TOOL, noise=0.1, complexity=0.2,
                      stability=0.95, tracking_depth=0.9, confidence=0.9) -> IntentContext:
        """Helper: build IntentContext with tunable cognitive profile."""
        pcr_out = PCROutput_v1(
            expectation=expectation.value if hasattr(expectation, 'value') else expectation,
            noise_level=noise,
            complexity_level=complexity,
            cognitive_profile=CognitiveProfile_v1(
                metacognition=0.8, divergence=0.1,
                tracking_depth=tracking_depth, stability=stability, confidence=confidence,
            ),
            execution_mode="BALANCED",
            parser_config_overrides={},
            prompt_style="BALANCED",
            trace_log=["[test]"],
        )
        return IntentContext.from_pcr_output(pcr_out)

    # ── Fix 1: Fast-path Gating ───────────────────────────────────────────────────

    def test_fast_path_skips_ambiguity_stages(self):
        """
        High-confidence entities (all >=0.95) + strong intent match →
        fast path activates, Stage 3-5 (split/ambiguity detect/resolution) skipped.
        """
        # Use input with a hex address (high-confidence entity, confidence=1.0)
        # and a pattern that matches SCAN_MEMORY rules (search match, confidence ~0.5)
        ctx = self._make_context(stability=0.95, confidence=0.2)
        result = self.parser.parse("scan memory at 0x401000", ctx, self.parse_ctx)
        # Trace should contain fast-path marker
        self.assertTrue(
            any("Fast path activated" in t for t in result.trace_log),
            f"Expected fast-path marker in trace: {result.trace_log}"
        )
        # No ambiguity stages should appear in trace
        self.assertFalse(
            any(t.startswith("[Stage 3]") or t.startswith("[Stage 4]") or t.startswith("[Stage 5]") for t in result.trace_log),
            "Fast path should skip Stage 3-5"
        )
        # Result should still be actionable
        self.assertTrue(result.is_actionable)

    def test_no_fast_path_with_low_confidence_entities(self):
        """
        Low-confidence entity (e.g., decimal value confidence=0.9) →
        fast path NOT activated, full pipeline runs.
        """
        ctx = self._make_context(stability=0.95, confidence=0.95)
        result = self.parser.parse("scan for value 100", ctx, self.parse_ctx)
        # Decimal value has confidence=0.9, so fast path should NOT trigger
        self.assertFalse(
            any("Fast path activated" in t for t in result.trace_log),
            f"Should NOT fast-path with low-confidence entity: {result.trace_log}"
        )

    # ── Fix 2: Synonym Direction (Expand vs Contract) ────────────────────────────

    def test_high_stability_no_text_mutation(self):
        """High stability (>=0.7) → _preprocess does NOT mutate text (rules already cover synonyms)."""
        ctx = self._make_context(stability=0.95)
        text = self.parser._preprocess("读取这个地址", ctx)
        # _preprocess no longer does destructive text replacement;
        # synonym expansion is handled safely in _classify as a fallback
        self.assertEqual(text, "读取这个地址")

    def test_low_stability_contracts_vocabulary(self):
        """Low stability (<0.5) → _preprocess removes vague words."""
        ctx = self._make_context(stability=0.3)
        text = self.parser._preprocess("那个东西搞一下", ctx)
        # Vague words should be removed
        self.assertNotIn("东西", text)
        self.assertNotIn("搞一下", text)
        # Core action words should remain if present
        # (this test mainly verifies contraction doesn't crash)

    def test_neutral_stability_no_change(self):
        """Neutral stability (0.5-0.7) → no synonym expansion or contraction."""
        ctx = self._make_context(stability=0.6)
        text = self.parser._preprocess("scan memory at 0x401000", ctx)
        self.assertEqual(text, "scan memory at 0x401000")

    # ── Fix 3: Reference Resolution (Pre-Stage 3.5) ───────────────────────────────

    def test_reference_resolution_before_extraction(self):
        """
        "读取这个地址" with history containing 0x401000 →
        Pre-Stage 3.5 resolves "这个地址" to 0x401000 before entity extraction.
        """
        # Seed history with a previous intent containing a memory address
        prev_intent = Intent(
            category=IntentCategory.SCAN_MEMORY,
            raw_input="scan 0x401000",
            normalized_input="scan 0x401000",
            entities=[
                Entity(type=EntityType.MEMORY_ADDRESS, value="0x401000",
                       raw_text="0x401000", confidence=1.0, start_pos=5, end_pos=13),
            ],
            confidence=0.95,
        )
        self.parse_ctx.add_intent(prev_intent)

        ctx = self._make_context(tracking_depth=0.9, stability=0.9)
        result = self.parser.parse("读取这个地址", ctx, self.parse_ctx)

        # Entity extraction should find the resolved address
        addr_entities = result.intent.get_entities(EntityType.MEMORY_ADDRESS)
        self.assertTrue(len(addr_entities) > 0, "Resolved address should appear in entities")
        self.assertEqual(addr_entities[0].value, "0x401000")

        # Trace should show Pre-Stage 3.5 resolution
        self.assertTrue(
            any("Pre-Stage 3.5" in t for t in result.trace_log),
            f"Expected Pre-Stage 3.5 marker in trace: {result.trace_log}"
        )

    def test_no_reference_resolution_without_history(self):
        """No history → no reference resolution, text passes through unchanged."""
        fresh_ctx = ParseContext(session_id="empty-history")
        ctx = self._make_context(tracking_depth=0.9, stability=0.9)
        result = self.parser.parse("读取这个地址", ctx, fresh_ctx)
        # Without history, "这个地址" cannot be resolved
        # The result may or may not have an address entity depending on extraction rules
        # Main check: trace should show no Pre-Stage 3.5 resolution (or 0 resolved)
        prestage_lines = [t for t in result.trace_log if "Pre-Stage 3.5" in t]
        if prestage_lines:
            self.assertIn("Resolved 0 references", prestage_lines[0])


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
