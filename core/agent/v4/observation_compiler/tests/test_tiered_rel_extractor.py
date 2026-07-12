"""Tests for TieredRelationExtractor."""
import pytest
from core.agent.v4.observation_compiler.tiered_relation_extractor import TieredRelationExtractor


class TestTieredRelationExtractor:
    def test_pattern_tier_en_before(self):
        ext = TieredRelationExtractor()
        rels = ext.extract("put RateLimiter before Auth")
        before_rels = [r for r in rels if r["type"] == "before"]
        assert len(before_rels) >= 1

    def test_pattern_tier_en_after(self):
        ext = TieredRelationExtractor()
        rels = ext.extract("add monitoring after the gateway")
        after_rels = [r for r in rels if r["type"] == "after"]
        assert len(after_rels) >= 1

    def test_pattern_tier_zh_before(self):
        ext = TieredRelationExtractor()
        rels = ext.extract("把 RateLimiter 放在 Auth 前面")
        before_rels = [r for r in rels if r["type"] == "before"]
        assert len(before_rels) >= 1

    def test_embedding_tier_prior_to(self):
        ext = TieredRelationExtractor()
        rels = ext.extract("place the module prior to the gateway")
        # "prior to" should be caught by embedding quick lookup
        assert len(rels) >= 1

    def test_embedding_tier_left_of(self):
        ext = TieredRelationExtractor()
        rels = ext.extract("left of the main panel")
        before_like = [r for r in rels if r["type"] in ("left_of", "before")]
        assert len(before_like) >= 1

    def test_fallback_to_embedding_semantic(self):
        ext = TieredRelationExtractor()
        rels = ext.extract("RateLimiter precedes Authentication")
        # "precedes" should be caught via quick lookup
        assert len(rels) >= 1

    def test_stats(self):
        ext = TieredRelationExtractor()
        ext.extract("test text before after")
        s = ext.stats()
        assert s["total_calls"] >= 1
        assert len(s["tiers"]) == 3
