"""Tests for TieredRuleEngine."""
import pytest
from core.agent.v4.tiered_rule_engine import TieredRuleEngine


class TestTieredRuleEngine:
    def test_rule_match_action_check(self):
        engine = TieredRuleEngine()
        matched, conf, rule = engine.evaluate("check the status")
        assert isinstance(matched, bool)
        assert 0.0 <= conf <= 1.0
        if matched:
            assert rule is not None

    def test_rule_match_action_deploy(self):
        engine = TieredRuleEngine()
        matched, conf, rule = engine.evaluate("deploy the package")
        assert conf >= 0.0

    def test_unknown_text_returns_low_confidence(self):
        engine = TieredRuleEngine()
        matched, conf, rule = engine.evaluate("xyzzy flurb the worble")
        assert not matched or conf < 0.7

    def test_stats_are_collected(self):
        engine = TieredRuleEngine()
        engine.evaluate("restart service")
        s = engine.stats()
        assert "tiers" in s
        assert len(s["tiers"]) == 2
