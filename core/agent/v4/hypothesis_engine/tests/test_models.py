"""Tests for Hypothesis Engine models."""
import pytest
from core.agent.v4.hypothesis_engine.models import (
    HypothesisNode, HypothesisEdge, KnowledgeNode, VoteRecord, ReasonSession,
)


class TestHypothesisNode:
    def test_creation(self):
        h = HypothesisNode(hypothesis_id="H1", interpretation_ref="I1", domain="engineering",
                           statement="User is developing Gateway")
        assert h.hypothesis_id == "H1"
        assert h.status == "active"
        assert h.belief_state["support"] == 0

    def test_belief_score_default(self):
        h = HypothesisNode(hypothesis_id="H2", interpretation_ref="I2", domain="engineering",
                           statement="test", objects=["X"])
        h.belief_state["support"] = 10
        h.belief_state["stability"] = 0.80
        h.belief_state["coverage"] = 0.50
        h.belief_state["recency"] = 0.90
        h.belief_state["entropy"] = 0.70
        score = h.belief_score()
        assert 0.3 < score < 0.9

    def test_should_freeze_insufficient(self):
        h = HypothesisNode(hypothesis_id="H3", interpretation_ref="I3", domain="eng", statement="test")
        assert not h.should_freeze()

    def test_should_freeze_sufficient(self):
        h = HypothesisNode(hypothesis_id="H4", interpretation_ref="I4", domain="eng", statement="test")
        h.belief_state["support"] = 10
        h.belief_state["conflict"] = 1
        h.belief_state["stability"] = 0.85
        h.belief_state["coverage"] = 0.60
        h.domain_signals["engineering"] = "support"
        h.domain_signals["behavior"] = "support"
        assert h.should_freeze()


class TestHypothesisEdge:
    def test_creation(self):
        e = HypothesisEdge(type="references", source_id="H1", target_id="C23", target_type="constraint")
        assert e.type == "references"
        assert e.target_type == "constraint"
        assert e.weight == 1.0


class TestKnowledgeNode:
    def test_creation(self):
        kn = KnowledgeNode(knowledge_id="KN1", hypothesis_ref="H1", statement="test",
                           domain="eng", belief_score=0.82)
        assert kn.knowledge_id == "KN1"
        assert kn.hypothesis_ref == "H1"
        assert kn.belief_score == 0.82


class TestVoteRecord:
    def test_creation(self):
        v = VoteRecord(evidence_id="E1", hypothesis_id="H1", vote="support", domain="engineering")
        assert v.vote == "support"
        assert v.domain == "engineering"


class TestReasonSession:
    def test_creation(self):
        rs = ReasonSession(session_id="S1", triggering_event="evt_001")
        assert rs.session_id == "S1"
        assert rs.status == "open"
        assert rs.candidates == []

    def test_add_vote(self):
        rs = ReasonSession(session_id="S2", triggering_event="evt_002")
        rs.votes.append(VoteRecord(evidence_id="E1", hypothesis_id="H1", vote="support"))
        assert len(rs.votes) == 1
