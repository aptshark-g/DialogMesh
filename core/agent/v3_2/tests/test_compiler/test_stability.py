"""Tests for stability scorer"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.compiler.stability_scorer import StabilityScorer
from core.agent.compiler.models import SlotValue


class TestStabilityScorer:
    def setup_method(self):
        self.scorer = StabilityScorer()

    def test_empty_slots(self):
        assert self.scorer.score({}) == 0.0
        assert self.scorer.is_undefined(0.0)

    def test_high_stability(self):
        slots = {"a": SlotValue("x", 0.95), "b": SlotValue("y", 0.98), "c": SlotValue("z", 0.90)}
        s = self.scorer.score(slots)
        assert s > 0.8

    def test_low_stability(self):
        slots = {"a": SlotValue("x", 0.50), "b": SlotValue("y", 0.50)}
        s = self.scorer.score(slots)
        assert s < 0.6

    def test_single_slot(self):
        slots = {"a": SlotValue("x", 0.8)}
        s = self.scorer.score(slots)
        assert s == 0.8
