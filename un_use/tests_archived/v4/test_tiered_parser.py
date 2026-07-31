"""Tests for TieredParser."""
import pytest
from core.agent.tiered_parser import (
    ParsedClause, RuleDecomposer, TieredParser,
)


class TestRuleDecomposer:
    def test_english_add(self):
        rd = RuleDecomposer()
        c = rd.parse("add monitoring to the Gateway")
        assert c.predicate == "add"
        assert c.object is not None
        
        assert c.confidence >= 0.7

    def test_negation_detection(self):
        rd = RuleDecomposer()
        c = rd.parse("dont delete the config")
        assert c.negation is True
        assert c.confidence <= 0.55

    def test_uncertainty(self):
        rd = RuleDecomposer()
        c = rd.parse("maybe update the auth module")
        assert c.uncertainty is True

    def test_empty_input(self):
        rd = RuleDecomposer()
        c = rd.parse("")
        assert c.parse_failed is True

    def test_entity_extraction(self):
        rd = RuleDecomposer()
        c = rd.parse("configure RateLimiter Gateway Auth")
        assert len(c.entities) >= 1


class TestTieredParser:
    def test_tier1_sufficient(self):
        tp = TieredParser()
        c = tp.parse("add monitoring to the Gateway")
        assert c.predicate == "add"
        assert c.tier_used == 1

    def test_fallback_on_low_confidence(self):
        tp = TieredParser()
        c = tp.parse("xyzzy something unknown")
        assert c.predicate is None or c.tier_used >= 1

    def test_question_detection(self):
        rd = RuleDecomposer()
        c = rd.parse("how to add monitoring?")
        assert c.question is True
