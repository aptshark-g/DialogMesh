# -*- coding: utf-8 -*-
"""
core/agent/pcr/tests/test_rule_based.py
───────────────────────────────────────
Unit tests for RuleBasedPCR and its sub-components.

Covers:
  - ExpectationIdentifier (rule-based + history inference + fallback)
  - NoiseEstimator (4-dimension noise scoring)
  - ComplexityEstimator (config + heuristic rules)
  - CognitiveProfiler (EMA + Jaccard similarity)
  - RuleBasedPCR full pipeline integration

Run: python -m unittest core.agent.pcr.tests.test_rule_based -v
"""

from __future__ import annotations

import unittest
import tempfile
import os
import time

from core.agent.pcr.rule_based import (
    ExpectationIdentifier, NoiseEstimator, ComplexityEstimator,
    CognitiveProfiler, RuleBasedPCR,
)
from core.agent.pcr.datacontract import PCRInput_v1, PCROutput_v1, HistoryEntry, CognitiveProfile_v1


# ──────────────────────────────────────────────────────────────────────────────
# ExpectationIdentifier Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestExpectationIdentifier(unittest.TestCase):

    def setUp(self):
        self.idf = ExpectationIdentifier()

    def test_scan_keyword(self):
        exp, src = self.idf.identify("scan the binary", [])
        self.assertEqual(exp, "TOOL")
        self.assertGreater(src, 0.8)

    def test_patch_keyword(self):
        exp, src = self.idf.identify("patch this function", [])
        self.assertEqual(exp, "TOOL")

    def test_read_keyword(self):
        exp, src = self.idf.identify("read memory at 0x1000", [])
        self.assertEqual(exp, "TOOL")

    def test_write_keyword(self):
        exp, src = self.idf.identify("write bytes to address", [])
        self.assertEqual(exp, "TOOL")

    def test_breakpoint_keyword(self):
        exp, src = self.idf.identify("set a breakpoint on main", [])
        self.assertEqual(exp, "TOOL")

    def test_dump_keyword(self):
        exp, src = self.idf.identify("dump the registers", [])
        self.assertEqual(exp, "TOOL")

    def test_hook_keyword(self):
        exp, src = self.idf.identify("hook the API call", [])
        self.assertEqual(exp, "TOOL")

    def test_trace_keyword(self):
        exp, src = self.idf.identify("trace execution", [])
        self.assertEqual(exp, "TOOL")

    def test_attach_keyword(self):
        exp, src = self.idf.identify("attach to the process", [])
        self.assertEqual(exp, "TOOL")

    def test_detach_keyword(self):
        exp, src = self.idf.identify("detach from the process", [])
        self.assertEqual(exp, "TOOL")

    def test_disassemble_keyword(self):
        exp, src = self.idf.identify("disassemble the function", [])
        self.assertEqual(exp, "TOOL")

    def test_find_keyword(self):
        exp, src = self.idf.identify("find string references", [])
        self.assertEqual(exp, "TOOL")

    def test_analyze_keyword(self):
        exp, src = self.idf.identify("analyze this binary", [])
        self.assertEqual(exp, "ADVISOR")

    def test_chinese_scan(self):
        exp, src = self.idf.identify("扫描这个函数", [])
        self.assertEqual(exp, "TOOL")

    def test_chinese_patch(self):
        exp, src = self.idf.identify("修改这里", [])
        self.assertEqual(exp, "TOOL")

    def test_chinese_breakpoint(self):
        exp, src = self.idf.identify("下断点", [])
        self.assertEqual(exp, "TOOL")

    def test_mixed_language(self):
        exp, src = self.idf.identify("scan 这个函数", [])
        self.assertEqual(exp, "TOOL")

    def test_unknown_query(self):
        exp, src = self.idf.identify("asdfgh jkl", [])
        self.assertEqual(exp, "UNKNOWN")
        self.assertIsInstance(src, float)

    def test_history_inference(self):
        hist = [
            HistoryEntry(role="user", content="scan the binary", expectation="TOOL", metadata={}),
            HistoryEntry(role="assistant", content="SCAN started", expectation="TOOL", metadata={}),
        ]
        exp, src = self.idf.identify("continue", hist)
        self.assertEqual(exp, "TOOL")
        self.assertGreater(src, 0.7)

    def test_history_no_relevant(self):
        hist = [
            HistoryEntry(role="user", content="what is the weather", metadata={}),
            HistoryEntry(role="assistant", content="Sunny", metadata={}),
        ]
        exp, src = self.idf.identify("scan", hist)
        self.assertEqual(exp, "TOOL")
        self.assertGreater(src, 0.8)

    def test_empty_query(self):
        exp, src = self.idf.identify("", [])
        self.assertEqual(exp, "UNKNOWN")

    def test_whitespace_only(self):
        exp, src = self.idf.identify("   \t\n  ", [])
        self.assertEqual(exp, "UNKNOWN")

    def test_case_insensitive(self):
        exp, src = self.idf.identify("SCAN the binary", [])
        self.assertEqual(exp, "TOOL")
        exp, src = self.idf.identify("ScAn", [])
        self.assertEqual(exp, "TOOL")

    def test_multiple_keywords_priority(self):
        # "scan" + "patch" — scan appears first in text
        exp, src = self.idf.identify("scan and patch the function", [])
        self.assertEqual(exp, "TOOL")

    def test_phrase_priority_over_keyword(self):
        # "patch test" is a specific phrase in rule map, takes priority over "patch"
        exp, src = self.idf.identify("patch test", [])
        self.assertEqual(exp, "TOOL")

    def test_add_custom_rule(self):
        self.idf.add_rule("customtool", ["customtool"], ["custom_keyword"])
        exp, src = self.idf.identify("use custom_keyword", [])
        self.assertEqual(exp, "CUSTOMTOOL")

    def test_remove_rule(self):
        self.idf.add_rule("temp", ["temp"], ["temporary"])
        self.idf.remove_rule("temp")
        exp, src = self.idf.identify("temporary", [])
        self.assertEqual(exp, "UNKNOWN")


# ──────────────────────────────────────────────────────────────────────────────
# NoiseEstimator Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestNoiseEstimator(unittest.TestCase):

    def setUp(self):
        self.ne = NoiseEstimator()

    def test_clean_query(self):
        noise = self.ne.estimate("scan the binary", [])
        self.assertEqual(noise, 0.0)

    def test_gibberish_query(self):
        noise = self.ne.estimate("asdkjfhaksjdhfkasjdfh", [])
        self.assertGreater(noise, 0.3)

    def test_mixed_clean_and_noise(self):
        noise = self.ne.estimate("scan asdkjfh binary", [])
        self.assertGreater(noise, 0.0)
        self.assertLess(noise, 1.0)

    def test_short_query(self):
        noise = self.ne.estimate("x", [])
        self.assertGreater(noise, 0.0)

    def test_very_long_query(self):
        noise = self.ne.estimate("scan " * 1000, [])
        self.assertGreater(noise, 0.0)

    def test_empty_query(self):
        noise = self.ne.estimate("", [])
        self.assertEqual(noise, 0.0)

    def test_control_chars(self):
        noise = self.ne.estimate("scan\x00\x01\x02", [])
        self.assertGreater(noise, 0.0)

    def test_special_chars(self):
        noise = self.ne.estimate("scan @#$%^&*()", [])
        self.assertGreater(noise, 0.0)

    def test_unicode_noise(self):
        noise = self.ne.estimate("scan 🔍 🎉 🚀", [])
        self.assertGreater(noise, 0.0)

    def test_history_continuity_short_gap(self):
        """Short gap (<30s) + no overlap + multi-domain scatter → context break noise."""
        now = time.time()
        hist = [HistoryEntry(role="user", content="scan the binary", timestamp=now - 10)]
        noise = self.ne.estimate("hook and decrypt", hist, current_time=now)
        self.assertGreater(noise, 0.0)

    def test_history_topic_shift_long_gap(self):
        """Long gap (>30min) + no overlap → normal topic shift, no noise (cognitive refresh)."""
        now = time.time()
        hist = [HistoryEntry(role="user", content="scan the binary", timestamp=now - 2000)]
        noise = self.ne.estimate("patch the function", hist, current_time=now)
        self.assertEqual(noise, 0.0)  # temporal_factor=0.0, no noise

    def test_history_referential_dissonance(self):
        """Strong referential + no overlap → true context break (high noise)."""
        now = time.time()
        hist = [HistoryEntry(role="user", content="scan the binary", timestamp=now - 10)]
        noise = self.ne.estimate("这个怎么弄", hist, current_time=now)
        self.assertGreater(noise, 0.0)  # strong referential + no overlap → high dissonance

    def test_history_new_task_exemption(self):
        """New task phrasing + long gap → exempt from noise (cognitive refresh)."""
        now = time.time()
        hist = [HistoryEntry(role="user", content="scan the binary", timestamp=now - 2000)]
        noise = self.ne.estimate("我想分析加密算法", hist, current_time=now)
        self.assertEqual(noise, 0.0)  # new task signal + no referential → exempt

    def test_history_continuity_consistent(self):
        """Same topic + short gap → low noise."""
        now = time.time()
        hist = [HistoryEntry(role="user", content="scan the binary", timestamp=now - 10)]
        noise = self.ne.estimate("scan again", hist, current_time=now)
        self.assertLess(noise, 0.5)

    def test_cap_at_one(self):
        noise = self.ne.estimate("\x00" * 1000 + "asdf" * 5000, [])
        self.assertLessEqual(noise, 1.0)


# ──────────────────────────────────────────────────────────────────────────────
# ComplexityEstimator Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestComplexityEstimator(unittest.TestCase):

    def setUp(self):
        self.ce = ComplexityEstimator()

    def test_simple_query(self):
        comp = self.ce.estimate("scan", "SCAN")
        self.assertLess(comp, 0.3)

    def test_moderate_query(self):
        comp = self.ce.estimate("scan the binary for strings", "SCAN")
        self.assertGreater(comp, 0.0)
        self.assertLess(comp, 0.7)

    def test_complex_query(self):
        comp = self.ce.estimate(
            "if the function is hooked then scan the import table otherwise trace the export table",
            "HOOK"
        )
        self.assertGreater(comp, 0.5)

    def test_conditional_keywords(self):
        comp = self.ce.estimate("if this then that", "UNKNOWN")
        self.assertGreater(comp, 0.0)

    def test_temporal_keywords(self):
        comp = self.ce.estimate("first scan then patch", "PATCH")
        self.assertGreater(comp, 0.0)

    def test_comparative_keywords(self):
        comp = self.ce.estimate("compare the before and after", "ANALYZE")
        self.assertGreater(comp, 0.0)

    def test_multi_step_keywords(self):
        comp = self.ce.estimate("first do this then do that finally do the other thing", "UNKNOWN")
        self.assertGreater(comp, 0.0)

    def test_unclear_keywords(self):
        comp = self.ce.estimate("do something about this", "UNKNOWN")
        self.assertGreater(comp, 0.0)

    def test_metacognitive_keywords(self):
        comp = self.ce.estimate("what is the best way to analyze this", "ANALYZE")
        self.assertGreater(comp, 0.0)

    def test_unknown_expectation(self):
        comp = self.ce.estimate("hello world", "UNKNOWN")
        self.assertGreater(comp, 0.0)

    def test_config_override(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not available")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("complexity_map:\n  SCAN: 0.5\n")
            path = f.name
        try:
            ce = ComplexityEstimator(config_path=path)
            comp = ce.estimate("scan", "SCAN")
            self.assertEqual(comp, 0.5)
        finally:
            os.unlink(path)

    def test_cap_at_one(self):
        comp = self.ce.estimate("if" * 500, "UNKNOWN")
        self.assertLessEqual(comp, 1.0)


# ──────────────────────────────────────────────────────────────────────────────
# CognitiveProfiler Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestCognitiveProfiler(unittest.TestCase):

    def setUp(self):
        self.cp = CognitiveProfiler()

    def test_initial_state(self):
        prof = self.cp.get_profile()
        self.assertEqual(prof.metacognitive_level, 0.5)
        self.assertEqual(prof.divergence_ratio, 0.5)
        self.assertEqual(prof.tracking_depth, 0)
        self.assertEqual(prof.description_stability, 0.5)

    def test_update_scan(self):
        prof = self.cp.update("scan the binary", "SCAN")
        self.assertEqual(prof.tracking_depth, 1)

    def test_update_analyze(self):
        prof = self.cp.update("analyze this", "ANALYZE")
        self.assertGreater(prof.metacognitive_level, 0.0)

    def test_multiple_updates(self):
        for _ in range(10):
            self.cp.update("scan the binary", "SCAN")
        prof = self.cp.get_profile()
        self.assertGreater(prof.tracking_depth, 0)

    def test_divergence_ratio(self):
        self.cp.update("scan the binary", "SCAN")
        self.cp.update("patch the function", "PATCH")
        self.cp.update("what is this", "ANALYZE")
        prof = self.cp.get_profile()
        self.assertGreater(prof.divergence_ratio, 0.0)
        self.assertLess(prof.divergence_ratio, 1.0)

    def test_description_stability_same_topic(self):
        for _ in range(5):
            self.cp.update("scan the binary", "SCAN")
        prof = self.cp.get_profile()
        self.assertGreater(prof.description_stability, 0.5)

    def test_description_stability_topic_switch(self):
        self.cp.update("scan the binary", "SCAN")
        self.cp.update("patch the function", "PATCH")
        self.cp.update("hook the API", "HOOK")
        prof = self.cp.get_profile()
        self.assertLess(prof.description_stability, 1.0)

    def test_reset(self):
        self.cp.update("scan", "SCAN")
        self.cp.reset()
        prof = self.cp.get_profile()
        self.assertEqual(prof.tracking_depth, 0)

    def test_jaccard_similarity(self):
        sim = self.cp._jaccard_similarity("scan the binary", "scan the function")
        self.assertGreater(sim, 0.0)
        self.assertLessEqual(sim, 1.0)

    def test_jaccard_identical(self):
        sim = self.cp._jaccard_similarity("scan", "scan")
        self.assertEqual(sim, 1.0)

    def test_jaccard_completely_different(self):
        sim = self.cp._jaccard_similarity("scan", "patch")
        self.assertEqual(sim, 0.0)

    def test_ema_decay(self):
        self.cp.update("scan the binary", "SCAN")
        self.cp.update("scan the binary", "SCAN")
        prof1 = self.cp.get_profile()
        self.cp.reset()
        self.cp.update("scan the binary", "SCAN")
        self.cp.update("patch the function", "PATCH")
        prof2 = self.cp.get_profile()
        self.assertNotEqual(prof1.tracking_depth, prof2.tracking_depth)

    # ── v2.3.1 first-turn stability fix ──────────────────────────────────────

    def test_first_turn_vague_low_stability(self):
        """Vague first turn (high noise) should start with low stability."""
        prof = self.cp.update("那个东西帮我搞一下", "UNKNOWN")
        self.assertLess(prof.description_stability, 0.5,
                        "Vague first turn should NOT start at 1.0")

    def test_first_turn_clean_high_stability(self):
        """Clean first turn (low noise) should start near 1.0."""
        prof = self.cp.update("scan memory at 0x1000", "TOOL")
        self.assertGreater(prof.description_stability, 0.7,
                           "Clean first turn should keep high stability")

    def test_first_turn_noise_estimate(self):
        """Direct test of _estimate_first_turn_noise heuristic."""
        noise_vague = self.cp._estimate_first_turn_noise("那个东西帮我搞一下")
        self.assertGreater(noise_vague, 0.3)

        noise_clean = self.cp._estimate_first_turn_noise("scan memory at 0x1000")
        self.assertLess(noise_clean, 0.2)

        noise_short = self.cp._estimate_first_turn_noise("搞")
        self.assertGreater(noise_short, 0.2)

    def test_first_turn_convergence_within_two_turns(self):
        """EMA should converge to true stability within 2 turns."""
        # Turn 1: vague but contains a keyword (low stability, not zero)
        prof1 = self.cp.update("那个东西帮我 scan 一下", "UNKNOWN")
        s1 = prof1.description_stability
        # Turn 2: clean, same keyword (some Jaccard overlap)
        prof2 = self.cp.update("scan the binary", "TOOL")
        s2 = prof2.description_stability
        # After 2 turns, stability should be influenced by real Jaccard,
        # not the initial 1.0 bias. s1 is low (~0.2-0.4), s2 should
        # reflect actual Jaccard between the two texts (small but >0).
        self.assertLess(s2, 0.9, "Should not be locked to 1.0 after 2 turns")
        self.assertGreater(s2, 0.0, "Should not be zero either")


# ──────────────────────────────────────────────────────────────────────────────
# RuleBasedPCR Integration Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestRuleBasedPCR(unittest.TestCase):

    def setUp(self):
        self.pcr = RuleBasedPCR()
        self.pcr.warm_up({})

    def tearDown(self):
        self.pcr.shutdown()

    def test_evaluate_scan(self):
        inp = PCRInput_v1(query="scan the binary", session_history=[])
        out = self.pcr.evaluate(inp)
        self.assertEqual(out.expectation, "TOOL")
        self.assertEqual(out.noise_level, 0.0)
        self.assertGreaterEqual(out.complexity_level, 0.0)
        self.assertLessEqual(out.complexity_level, 1.0)

    def test_evaluate_patch(self):
        inp = PCRInput_v1(query="patch the function", session_history=[])
        out = self.pcr.evaluate(inp)
        self.assertEqual(out.expectation, "TOOL")

    def test_evaluate_chinese(self):
        inp = PCRInput_v1(query="扫描这个函数", session_history=[])
        out = self.pcr.evaluate(inp)
        self.assertEqual(out.expectation, "TOOL")

    def test_evaluate_with_history(self):
        hist = [
            HistoryEntry(role="user", content="scan the binary", expectation="TOOL", metadata={}),
            HistoryEntry(role="assistant", content="SCAN started", expectation="TOOL", metadata={}),
        ]
        inp = PCRInput_v1(query="continue", session_history=hist)
        out = self.pcr.evaluate(inp)
        self.assertEqual(out.expectation, "TOOL")

    def test_evaluate_returns_cognitive_profile(self):
        inp = PCRInput_v1(query="scan", session_history=[])
        out = self.pcr.evaluate(inp)
        self.assertIsNotNone(out.cognitive_profile)
        self.assertIsInstance(out.cognitive_profile, CognitiveProfile_v1)

    def test_evaluate_returns_execution_mode(self):
        inp = PCRInput_v1(query="scan", session_history=[])
        out = self.pcr.evaluate(inp)
        self.assertIn(out.execution_mode, ["CONSERVATIVE", "BALANCED", "AGGRESSIVE", "UNKNOWN"])

    def test_evaluate_returns_prompt_style(self):
        inp = PCRInput_v1(query="scan", session_history=[])
        out = self.pcr.evaluate(inp)
        self.assertIn(out.prompt_style, ["CONSERVATIVE", "BALANCED", "AGGRESSIVE"])

    def test_evaluate_ambiguity_strategy(self):
        inp = PCRInput_v1(query="scan", session_history=[])
        out = self.pcr.evaluate(inp)
        self.assertIn(out.ambiguity_strategy, ["CONSERVATIVE", "BALANCED", "EXPLICIT"])

    def test_evaluate_parser_overrides(self):
        inp = PCRInput_v1(query="scan", session_history=[])
        out = self.pcr.evaluate(inp)
        self.assertIsInstance(out.parser_config_overrides, dict)

    def test_health(self):
        health = self.pcr.get_health()
        self.assertTrue(health.is_healthy)

    def test_telemetry(self):
        self.pcr.evaluate(PCRInput_v1(query="scan"))
        telem = self.pcr.get_telemetry()
        self.assertIn("call_count", telem)
        self.assertIn("avg_latency_ms", telem)

    def test_capabilities(self):
        caps = self.pcr.get_capabilities()
        self.assertIn("supports_rules", caps)
        self.assertTrue(caps["supports_rules"])

    def test_schema(self):
        schema = self.pcr.get_schema()
        self.assertEqual(schema["version"], "v1")
        self.assertEqual(schema["type"], "rule_based")

    def test_reload_config(self):
        result = self.pcr.reload_config({"some_key": "value"})
        self.assertTrue(result)

    def test_complex_query(self):
        inp = PCRInput_v1(query="first scan the binary then patch the function and finally hook the API", session_history=[])
        out = self.pcr.evaluate(inp)
        self.assertGreater(out.complexity_level, 0.3)

    def test_noisy_query(self):
        inp = PCRInput_v1(query="asdkjfhaksjdhf scan binary", session_history=[])
        out = self.pcr.evaluate(inp)
        self.assertGreater(out.noise_level, 0.0)

    def test_unknown_query(self):
        inp = PCRInput_v1(query="what is the weather today", session_history=[])
        out = self.pcr.evaluate(inp)
        self.assertEqual(out.expectation, "UNKNOWN")

    def test_evaluate_twice_updates_profile(self):
        self.pcr.evaluate(PCRInput_v1(query="scan the binary"))
        out2 = self.pcr.evaluate(PCRInput_v1(query="patch the function"))
        self.assertEqual(out2.cognitive_profile.tracking_depth, 1)

    def test_name(self):
        self.assertEqual(self.pcr.name, "rule_based")

    def test_evaluate_with_complex_history(self):
        hist = []
        for i in range(20):
            hist.append(HistoryEntry(role="user", content="scan module %d" % i, metadata={}))
            hist.append(HistoryEntry(role="assistant", content="SCAN result %d" % i, metadata={}))
        inp = PCRInput_v1(query="scan module 20", session_history=hist)
        out = self.pcr.evaluate(inp)
        self.assertEqual(out.expectation, "TOOL")

    def test_latency_under_threshold(self):
        import time
        inp = PCRInput_v1(query="scan the binary")
        t0 = time.perf_counter()
        self.pcr.evaluate(inp)
        elapsed = (time.perf_counter() - t0) * 1000
        self.assertLess(elapsed, 100)  # Should complete in <100ms


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    unittest.main()
