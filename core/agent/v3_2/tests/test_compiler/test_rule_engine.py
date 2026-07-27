"""Tests for rule engine"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.compiler.rule_engine import FrameLibrary, RuleConstraintEngine
from core.agent.compiler.models import SlotValue, ParseContext


class TestFrameLibrary:
    def test_load_default(self):
        lib = FrameLibrary.load_default()
        assert len(lib.rules) > 0

    def test_query_by_slot(self):
        lib = FrameLibrary.load_default()
        rules = lib.query("action")
        assert len(rules) > 0

    def test_get_frame(self):
        lib = FrameLibrary.load_default()
        rules = lib.get_frame("cause(呛)")
        assert len(rules) > 0


class TestRuleConstraintEngine:
    def setup_method(self):
        self.engine = RuleConstraintEngine(FrameLibrary.load_default())

    def test_skip_high_confidence(self):
        slots = {"action": SlotValue("execute", confidence=0.9)}
        result = self.engine.refine(slots, ParseContext())
        assert result["action"].source == "llm"

    def test_refine_low_confidence(self):
        slots = {"action": SlotValue("run", confidence=0.4)}
        result = self.engine.refine(slots, ParseContext())
        assert result is not None

    def test_threshold(self):
        assert RuleConstraintEngine.CONFIDENCE_THRESHOLD == 0.75

    def test_resolve_all(self):
        slots = {"action": SlotValue("run", confidence=0.4)}
        result = self.engine.resolve_all(slots, ParseContext())
        assert result is not None

    def test_empty_slots(self):
        result = self.engine.refine({}, ParseContext())
        assert result == {}
