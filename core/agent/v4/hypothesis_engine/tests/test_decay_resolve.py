"""Tests for DecayResolveEngine."""
import time
import pytest
from core.agent.v4.hypothesis_engine.models import HypothesisNode
from core.agent.v4.hypothesis_engine.decay_resolve import DecayResolveEngine


class TestDecayResolveEngine:
    def test_decay_reduces_support(self):
        engine = DecayResolveEngine()
        h = HypothesisNode(hypothesis_id="H1", interpretation_ref="I1", domain="eng", statement="test")
        h.belief_state["support"] = 10
        h.last_vote_at = time.time() - 8 * 86400  # 8 days ago
        engine.register(h)
        engine.decay_all(now=time.time(), half_life_days=7.0)
        assert h.belief_state["support"] < 10

    def test_freeze_creates_knowledge(self):
        engine = DecayResolveEngine()
        h = HypothesisNode(hypothesis_id="H1", interpretation_ref="I1", domain="eng", statement="test")
        h.belief_state["support"] = 10
        h.belief_state["conflict"] = 1
        h.belief_state["stability"] = 0.85
        h.belief_state["coverage"] = 0.60
        h.domain_signals["engineering"] = "support"
        h.domain_signals["behavior"] = "support"
        engine.register(h)
        result = engine.resolve()
        assert len(result["frozen"]) >= 1
        assert engine.knowledge_count >= 1

    def test_stale_detection(self):
        engine = DecayResolveEngine()
        h = HypothesisNode(hypothesis_id="H1", interpretation_ref="I1", domain="eng", statement="test")
        h.belief_state["support"] = 1
        h.belief_state["recency"] = 0.05
        engine.register(h)
        result = engine.resolve()
        assert len(result["stale"]) >= 1

    def test_merge_candidates(self):
        engine = DecayResolveEngine()
        a = HypothesisNode(hypothesis_id="A", interpretation_ref="IA", domain="eng",
                           statement="Dev Gateway", objects=["Gateway", "RateLimiter"])
        b = HypothesisNode(hypothesis_id="B", interpretation_ref="IB", domain="eng",
                           statement="Learn Gateway", objects=["Gateway", "RateLimiter"])
        engine.register(a); engine.register(b)
        merged = engine.merge_candidates(threshold=0.5)
        assert len(merged) >= 1

    def test_support_score(self):
        engine = DecayResolveEngine()
        a = HypothesisNode(hypothesis_id="A", interpretation_ref="IA", domain="eng",
                           statement="Dev Gateway", objects=["Gateway", "Logger"])
        b = HypothesisNode(hypothesis_id="B", interpretation_ref="IB", domain="eng",
                           statement="Learn Gateway", objects=["Gateway", "RateLimiter"])
        score = engine.compute_support_score(a, b)
        assert 0.0 <= score <= 1.0
