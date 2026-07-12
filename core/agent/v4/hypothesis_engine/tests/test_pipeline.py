"""Tests for HypothesisPipeline + SessionManager."""
import pytest
from core.agent.v4.hypothesis_engine.models import HypothesisNode
from core.agent.v4.hypothesis_engine.match_vote import MatchVoteEngine
from core.agent.v4.hypothesis_engine.decay_resolve import DecayResolveEngine
from core.agent.v4.hypothesis_engine.session_manager import SessionManager
from core.agent.v4.hypothesis_engine.pipeline import HypothesisPipeline


class TestSessionManager:
    def test_open_close(self):
        mgr = SessionManager()
        s = mgr.open("evt1", "engineering")
        assert s.status == "open"
        assert mgr.close(s.session_id, winner="H1")
        assert s.status == "closed"
        assert s.winner == "H1"

    def test_archive(self):
        mgr = SessionManager()
        s = mgr.open("evt2")
        mgr.close(s.session_id)
        assert mgr.archive(s.session_id)
        assert s.status == "archived"

    def test_stats(self):
        mgr = SessionManager()
        mgr.open("e1"); mgr.open("e2")
        s = mgr.stats()
        assert s["total"] == 2
        assert s["open"] == 2


class TestHypothesisPipeline:
    def test_submit_creates_session(self):
        pipe = HypothesisPipeline()
        h = HypothesisNode(hypothesis_id="H1", interpretation_ref="I1",
                           domain="eng", statement="test")
        pipe.register_hypothesis(h)
        session = pipe.submit({"description": "deploy", "domain": "eng"}, "evt1")
        assert session.status == "open"
        assert len(session.votes) >= 1

    def test_stats(self):
        pipe = HypothesisPipeline()
        h = HypothesisNode(hypothesis_id="H1", interpretation_ref="I1",
                           domain="eng", statement="test")
        pipe.register_hypothesis(h)
        pipe.submit({"description": "modify", "domain": "eng"}, "evt2")
        s = pipe.stats()
        assert s["events_processed"] >= 1
        assert s["hypothesis_count"] >= 1
