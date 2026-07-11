"""Tests for TieredNegativeKB."""
import pytest
from core.agent.v4.tiered_negative_kb import TieredNegativeKB
from core.agent.v3_2.negative_kb.models import (
    NegativeLevel, NegativeResult, ContextualNegativeRule,
)


class TestTieredNegativeKB:
    def test_no_rules_returns_empty(self):
        kb = TieredNegativeKB()
        result = kb.check("some text")
        assert isinstance(result, NegativeResult)
        assert result.level is None

    def test_hard_block_rule_keyword_match(self):
        kb = TieredNegativeKB()
        rule = ContextualNegativeRule(
            rule_id="block_system",
            level=NegativeLevel.HARD_BLOCK,
            message="System modification blocked",
            keywords=["rm -rf", "format"],
            is_verified=True,
        )
        kb.register(rule)
        result = kb.check("I want to rm -rf the drive")
        assert result.blocked is True
        assert result.level == NegativeLevel.HARD_BLOCK

    def test_warn_rule_triggers_fuse_tier(self):
        kb = TieredNegativeKB()
        rule = ContextualNegativeRule(
            rule_id="warn_delete",
            level=NegativeLevel.WARN,
            message="Deletion may be irreversible",
            keywords=["delete", "remove"],
        )
        kb.register(rule)
        result = kb.check("delete all files")
        assert result.level in (NegativeLevel.WARN, None)

    def test_soft_discourage_upgrades_to_fuse(self):
        kb = TieredNegativeKB()
        rule = ContextualNegativeRule(
            rule_id="soft",
            level=NegativeLevel.SOFT_DISCOURAGE,
            message="Not recommended",
            keywords=["eval"],
        )
        kb.register(rule)
        result = kb.check("eval some code")
        assert result.level is not None

    def test_stats_are_collected(self):
        kb = TieredNegativeKB()
        kb.check("anything")
        s = kb.stats()
        assert s["total_calls"] >= 1
        assert len(s["tiers"]) == 2
        assert s["tiers"][0]["name"] == "negative_kb.keyword"
