"""Tests for compiler data models"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from core.agent.compiler.models import SlotValue, ParseResult, ParseContext, ConstraintRule


class TestSlotValue:
    def test_clamp_high(self):
        sv = SlotValue("test", confidence=1.5)
        assert sv.confidence == 1.0

    def test_clamp_low(self):
        sv = SlotValue("test", confidence=-0.5)
        assert sv.confidence == 0.0

    def test_source_validation(self):
        import pytest
        with pytest.raises(AssertionError):
            SlotValue("test", source="invalid")

    def test_defaults(self):
        sv = SlotValue("test")
        assert sv.confidence == 0.5
        assert sv.source == "llm"
        assert not sv.overridden


class TestParseContext:
    def test_add_entity(self):
        ctx = ParseContext()
        ctx.add_entity("action", "run")
        assert ctx.entities["action"] == ["run"]
        ctx.add_entity("action", "run")
        assert len(ctx.entities["action"]) == 1

    def test_defaults(self):
        ctx = ParseContext()
        assert ctx.turn_count == 0


class TestParseResult:
    def test_is_reliable(self):
        assert ParseResult(stability=0.8).is_reliable
        assert not ParseResult(stability=0.5, undefined=True).is_reliable

    def test_to_dict(self):
        sv = SlotValue("human", confidence=0.9)
        r = ParseResult(slots={"agent": sv})
        d = r.to_dict()
        assert d["slots"]["agent"]["value"] == "human"


class TestConstraintRule:
    def test_applicable_no_condition(self):
        rule = ConstraintRule("test", "action", ["a", "b"])
        assert rule.is_applicable(ParseContext())

    def test_applicable_with_condition(self):
        rule = ConstraintRule("test", "action", ["a"], condition="topic_contains=debug")
        assert rule.is_applicable(ParseContext(topics=["debug"]))
        assert not rule.is_applicable(ParseContext(topics=["general"]))
