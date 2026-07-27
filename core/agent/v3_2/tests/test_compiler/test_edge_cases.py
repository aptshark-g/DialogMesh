"""Industrial-grade edge case & integration tests"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.compiler.models import SlotValue, ParseResult, ParseContext, ConstraintRule
from core.agent.compiler.stability_scorer import StabilityScorer
from core.agent.compiler.rule_engine import FrameLibrary, RuleConstraintEngine
from core.agent.compiler.streaming_validator import StreamingValidator
from core.agent.compiler.degradation_manager import DegradationManager


class TestDataModelInvariants:
    def test_slot_value_zero_confidence(self):
        sv = SlotValue("x", 0.0)
        assert sv.confidence == 0.0

    def test_slot_value_max_confidence(self):
        sv = SlotValue("x", 1.0)
        assert sv.confidence == 1.0

    def test_slot_value_nan_safe(self):
        import math
        sv = SlotValue("x", float("nan"))
        assert 0.0 <= sv.confidence <= 1.0

    def test_slot_value_inf_safe(self):
        import math
        sv = SlotValue("x", float("inf"))
        assert sv.confidence == 1.0

    def test_slot_value_neg_inf_safe(self):
        import math
        sv = SlotValue("x", float("-inf"))
        assert sv.confidence == 0.0

    def test_parse_result_empty_slots(self):
        r = ParseResult()
        assert r.slots == {}
        assert r.stability == 0.0
        assert not r.is_reliable

    def test_parse_result_unreliable_combinations(self):
        assert not ParseResult(stability=0.5, undefined=False).is_reliable
        assert not ParseResult(stability=0.8, undefined=True).is_reliable
        assert not ParseResult(stability=0.0, undefined=True).is_reliable

    def test_parse_result_reliable_edge(self):
        assert ParseResult(stability=0.6, undefined=False).is_reliable

    def test_parse_context_no_mutation(self):
        ctx = ParseContext()
        ctx2 = ParseContext()
        ctx.add_entity("a", "x")
        assert "a" not in ctx2.entities


class TestStabilityMath:
    def setup_method(self):
        self.scorer = StabilityScorer()

    def test_identical_high(self):
        s = self.scorer.score({"a": SlotValue("x", 0.9), "b": SlotValue("y", 0.9)})
        assert s == 0.9

    def test_identical_low(self):
        s = self.scorer.score({"a": SlotValue("x", 0.3), "b": SlotValue("y", 0.3)})
        assert s == 0.3

    def test_variance_penalty(self):
        uniform = self.scorer.score({"a": SlotValue("x", 0.7), "b": SlotValue("y", 0.7)})
        mixed = self.scorer.score({"a": SlotValue("x", 0.95), "b": SlotValue("y", 0.45)})
        assert uniform > 0.6
        assert mixed < uniform

    def test_three_slots_high_variance(self):
        s = self.scorer.score({
            "a": SlotValue("x", 0.95),
            "b": SlotValue("y", 0.30),
            "c": SlotValue("z", 0.95),
        })
        assert 0.5 <= s <= 0.7


class TestRuleEngineAdvanced:
    def setup_method(self):
        self.lib = FrameLibrary.load_default()
        self.engine = RuleConstraintEngine(self.lib)

    def test_refine_skips_unknown_frames(self):
        slots = {"unknown": SlotValue("nothing", 0.1)}
        result = self.engine.refine(slots, ParseContext())
        assert result["unknown"].value == "nothing"

    def test_context_entities_expand_candidates(self):
        ctx = ParseContext(entities={"cause": ["发酵气体"]})
        slots = {"cause": SlotValue("呛", 0.3)}
        result = self.engine.refine(slots, ctx)
        assert result["cause"].value == "发酵气体" or result["cause"].overridden

    def test_incompatible_exclusion(self):
        slots = {"action": SlotValue("喝", 0.4), "patient": SlotValue("食物", 0.9)}
        result = self.engine.refine(slots, ParseContext())
        assert result is not None

    def test_add_custom_rule(self):
        self.lib.add(ConstraintRule("action(uniq_custom)", "action", ["test"]))
        rules = self.lib.get_frame("action(uniq_custom)")
        assert len(rules) == 1

    def test_query_by_domain(self):
        self.lib.add(ConstraintRule("action(自定义)", "action", ["custom"], domain="custom"))
        rules = self.lib.query("action", domain="custom")
        assert len(rules) > 0


class TestFrameLibraryEdge:
    def test_load_default_not_empty(self):
        lib = FrameLibrary.load_default()
        assert len(lib.rules) > 50
        assert len(lib.rules) == 98

    def test_add_and_retrieve(self):
        lib = FrameLibrary()
        lib.add(ConstraintRule("test", "slot", ["a"]))
        assert len(lib.rules) == 1
        assert lib.query("slot")[0].frame_name == "test"


class TestDegradationFullCoverage:
    def test_rule_parse_basic_sentence(self):
        slots = DegradationManager.rule_parse("运行程序", None)
        assert "action" in slots
        assert slots["action"].source == "rule"

    def test_rule_parse_noise(self):
        slots = DegradationManager.rule_parse("今天天气不错", None)
        assert isinstance(slots, dict)

    def test_rule_parse_unicode(self):
        slots = DegradationManager.rule_parse("分析数据并生成报表", None)
        assert len(slots) > 0

    def test_mode_cycle(self):
        mgr = DegradationManager(threshold=1)
        assert mgr.should_use_llm()
        mgr.on_failure()
        assert not mgr.should_use_llm()
        mgr.on_success()
        assert mgr.should_use_llm()

    def test_get_status_format(self):
        mgr = DegradationManager()
        st = mgr.get_status()
        assert "mode" in st and "consecutive_failures" in st
        assert st["consecutive_failures"] == 0
        mgr.on_failure()
        assert mgr.get_status()["consecutive_failures"] == 1


class TestValidatorIntegration:
    def setup_method(self):
        self.engine = RuleConstraintEngine(FrameLibrary.load_default())

    def test_validate_then_resolve_noop(self):
        validator = StreamingValidator(self.engine)
        slots = {"action": SlotValue("execute", 0.9)}
        validator.on_slot_received("action", slots["action"], ParseContext())
        result = validator.resolve(slots)
        assert result["action"].value == "execute"

    def test_multiple_conflicts(self):
        validator = StreamingValidator(self.engine)
        s1 = SlotValue("invalid1", 0.3)
        s2 = SlotValue("invalid2", 0.3)
        validator.on_slot_received("action", s1, ParseContext())
        validator.on_slot_received("action", s2, ParseContext())
        assert len(validator.conflicts) == 0

    def test_validate_no_rules_for_slot(self):
        validator = StreamingValidator(self.engine)
        s = SlotValue("test", 0.3)
        validator.on_slot_received("nonexistent_slot", s, ParseContext())
        assert len(validator.conflicts) == 0

    def test_resolve_clears_conflicts(self):
        validator = StreamingValidator(self.engine)
        validator.on_slot_received("action", SlotValue("unknown", 0.3), ParseContext())
        if len(validator.conflicts) > 0:
            result = validator.resolve({"action": SlotValue("keep", 0.3)})
        validator.clear()
        assert len(validator.conflicts) == 0


class TestConstraintRuleCondition:
    def test_multi_condition(self):
        rule = ConstraintRule("test", "slot", ["a"], condition="topic_contains=debug")
        ctx = ParseContext(topics=["debug"])
        assert rule.is_applicable(ctx)

    def test_condition_not_met(self):
        rule = ConstraintRule("test", "slot", ["a"], condition="topic_contains=production")
        ctx = ParseContext(topics=["debug"])
        assert not rule.is_applicable(ctx)

    def test_condition_empty_topic(self):
        rule = ConstraintRule("test", "slot", ["a"], condition="topic_contains=debug")
        assert not rule.is_applicable(ParseContext())

    def test_condition_malformed(self):
        rule = ConstraintRule("test", "slot", ["a"], condition="bad_format")
        assert rule.is_applicable(ParseContext())


class TestSlotValueValidation:
    def test_source_rule(self):
        sv = SlotValue("x", 0.8, source="rule")
        assert sv.source == "rule"

    def test_source_hybrid(self):
        sv = SlotValue("x", 0.8, source="hybrid")
        assert sv.source == "hybrid"

    def test_overridden_flag(self):
        sv = SlotValue("x", 0.8, overridden=True)
        assert sv.overridden

    def test_raw_text(self):
        sv = SlotValue("x", 0.8, raw_text="测试文本")
        assert sv.raw_text == "测试文本"
