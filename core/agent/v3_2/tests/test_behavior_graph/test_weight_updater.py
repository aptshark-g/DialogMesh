import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.behavior.weight_updater import WeightUpdater
from core.agent.behavior.models import BehaviorEdge
import pytest

class TestWeightUpdater:
    def setup_method(self):
        self.updater = WeightUpdater()
        self.edge = BehaviorEdge("e1", "s1", "s2")

    def test_initial_params(self):
        assert self.updater.alpha == 0.25

    def test_update_baseline(self):
        w = self.updater.update(self.edge)
        assert w == pytest.approx(0.175, 0.01)

    def test_update_with_llm(self):
        w = self.updater.update(self.edge, llm_prob=0.9)
        assert w == 0.4

    def test_freq_ratio_no_corrections(self):
        self.edge.record_observation(True)
        r = self.updater.update_freq_ratio(self.edge)
        assert r == 1.0

    def test_freq_ratio_with_correction(self):
        self.edge.record_observation(True)
        self.edge.record_observation(True, correction=True)
        r = self.updater.update_freq_ratio(self.edge)
        assert r == 2/3

    def test_profile_boost_capped(self):
        r = self.updater.update_profile_boost(self.edge, 0.5)
        assert r == 0.3

    def test_structural_prior_capped(self):
        r = self.updater.update_structural_prior(self.edge, 0.8)
        assert r == 0.7

    def test_correction_mode_drop(self):
        self.edge.correction_mode = True
        self.edge.weight = 0.8
        w = self.updater.update(self.edge)
        assert w == 0.24

    def test_reconfigure_floating(self):
        self.updater.reconfigure(0.1, 0.2, 0.3, 0.4)
        assert abs(self.updater.ema_remainder) < 1e-10

    def test_reconfigure_weights(self):
        self.updater.reconfigure(0.1, 0.2, 0.3, 0.4)
        assert self.updater.alpha == 0.1
        assert self.updater.beta == 0.2
        assert self.updater.gamma == 0.3
        assert self.updater.delta == 0.4
