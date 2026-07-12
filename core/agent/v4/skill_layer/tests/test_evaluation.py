"""Tests for EvaluationEngine."""
import pytest
from core.agent.v4.skill_layer.models import SkillBelief
from core.agent.v4.skill_layer.evaluation_engine import EvaluationEngine

class TestEvaluationEngine:
    def test_candidate(self):
        engine = EvaluationEngine()
        belief = SkillBelief(support=2, generality=0.4, stability=0.7)
        status, score = engine.evaluate(belief)
        assert status == "candidate"

    def test_verified(self):
        engine = EvaluationEngine()
        belief = SkillBelief(support=20, generality=0.9, benefit=0.9, stability=0.95, coverage=0.85, recency=0.9)
        status, score = engine.evaluate(belief)
        assert status == "verified"

    def test_promote_ready(self):
        engine = EvaluationEngine()
        belief = SkillBelief(support=20, generality=0.85, stability=0.95)
        assert engine.promote_ready(belief)
