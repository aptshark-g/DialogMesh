"""Tests for DistillationEngine."""
import pytest
from core.agent.v4.skill_layer.models import CapabilityBlueprint, SkillCandidate
from core.agent.v4.skill_layer.distillation_engine import DistillationEngine


class MockConstraintStore:
    def get_all(self):
        return [
            {"id": "c1", "objects": ["Metrics", "Health"], "constraint_id": "C1"},
            {"id": "c2", "objects": ["Metrics", "Health", "Config"], "constraint_id": "C2"},
            {"id": "c3", "objects": ["Metrics", "Health"], "constraint_id": "C3"},
            {"id": "c5", "objects": ["Metrics", "Health"], "constraint_id": "C5"},
            {"id": "c4", "objects": ["Logger"], "constraint_id": "C4"},
        ]


class MockKnowledgeStore:
    def get_by_domain(self, domain):
        return [
            {"id": "k1", "knowledge_id": "KN1", "objects": ["Gateway", "Provider"]},
            {"id": "k2", "knowledge_id": "KN2", "objects": ["Gateway", "Provider", "Config"]},
            {"id": "k3", "knowledge_id": "KN3", "objects": ["Gateway", "Provider"]},
            {"id": "k4", "knowledge_id": "KN4", "objects": ["Gateway", "Provider"]},
        ]


class MockBehaviorStore:
    def get_sequences(self):
        return [
            {"actions": ["drag", "click"]},
            {"actions": ["drag", "click"]},
            {"actions": ["drag", "click"]},
            {"actions": ["drag", "click"]},
            {"actions": ["drag", "click"]},
            {"actions": ["drag", "click"]},
        ]


class MockHypothesisEngine:
    class MockHypothesis:
        def __init__(self):
            self.hypothesis_id = "H1"
            self.statement = "User prefers Plugin Pattern"
            self.domain = "engineering"
            self.belief_state = {"support": 8, "conflict": 1, "stability": 0.85}
            self.domain_signals = {"engineering": "support", "behavior": "support"}
            self.status = "active"
    def __init__(self):
        self._hypotheses = {"H1": self.MockHypothesis(), "H2": self.MockHypothesis()}


class TestDistillationEngine:
    def test_cluster_constraints(self):
        engine = DistillationEngine()
        store = MockConstraintStore()
        candidates = engine._cluster_constraints(store)
        assert len(candidates) >= 1

    def test_cluster_knowledge(self):
        engine = DistillationEngine()
        store = MockKnowledgeStore()
        candidates = engine._cluster_knowledge(store)
        assert len(candidates) >= 1

    def test_find_behavior_patterns(self):
        engine = DistillationEngine()
        store = MockBehaviorStore()
        candidates = engine._find_behavior_patterns(store)
        assert len(candidates) >= 1

    def test_consensus_hypotheses(self):
        engine = DistillationEngine()
        engine._p = lambda k, d: {"skill.distill.min_hypothesis_consensus": 0.5}.get(k, d)
        mock = MockHypothesisEngine()
        candidates = engine._consensus_hypotheses(mock)
        assert len(candidates) >= 1

    def test_scan_integration(self):
        engine = DistillationEngine()
        candidates = engine.scan(
            constraint_store=MockConstraintStore(),
            knowledge_store=MockKnowledgeStore(),
            behavior_store=MockBehaviorStore(),
            hypothesis_engine=MockHypothesisEngine(),
        )
        assert len(candidates) >= 3

    def test_empty_inputs(self):
        engine = DistillationEngine()
        candidates = engine.scan()
        assert candidates == []
