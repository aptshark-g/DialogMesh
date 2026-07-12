"""Tests for MatchVoteEngine."""
import pytest
from core.agent.v4.hypothesis_engine.models import HypothesisNode, ReasonSession
from core.agent.v4.hypothesis_engine.match_vote import MatchVoteEngine


class TestMatchVoteEngine:
    def test_match_by_object(self):
        engine = MatchVoteEngine()
        h = HypothesisNode(hypothesis_id="H1", interpretation_ref="I1", domain="engineering",
                           statement="Dev Gateway", objects=["Gateway"])
        engine.register(h)
        evidence = {"description": "modify Gateway config", "objects": ["Gateway"], "domain": "engineering"}
        votes = engine.process(evidence)
        assert len(votes) >= 1
        assert votes[0].vote == "support"

    def test_match_by_domain(self):
        engine = MatchVoteEngine()
        h = HypothesisNode(hypothesis_id="H1", interpretation_ref="I1", domain="engineering",
                           statement="test")
        engine.register(h)
        evidence = {"description": "update config", "objects": [], "domain": "engineering"}
        votes = engine.process(evidence)
        assert len(votes) >= 1

    def test_conflict_vote(self):
        engine = MatchVoteEngine()
        h = HypothesisNode(hypothesis_id="H1", interpretation_ref="I1", domain="engineering",
                           statement="test")
        engine.register(h)
        evidence = {"description": "revert Gateway changes", "objects": ["Gateway"], "domain": "engineering"}
        votes = engine.process(evidence)
        assert any(v.vote == "conflict" for v in votes)

    def test_frozen_hypothesis_not_matched(self):
        engine = MatchVoteEngine()
        h = HypothesisNode(hypothesis_id="H1", interpretation_ref="I1", domain="eng", statement="test")
        h.status = "frozen"
        engine.register(h)
        evidence = {"description": "modify", "objects": [], "domain": "eng"}
        votes = engine.process(evidence)
        assert len(votes) == 0

    def test_session_records_votes(self):
        engine = MatchVoteEngine()
        h = HypothesisNode(hypothesis_id="H1", interpretation_ref="I1", domain="eng", statement="test")
        engine.register(h)
        session = ReasonSession(session_id="S1", triggering_event="evt1")
        evidence = {"description": "deploy", "objects": [], "domain": "eng"}
        engine.process(evidence, session=session)
        assert len(session.votes) == 1
