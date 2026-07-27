import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.rewarder.models import RewardSignal
from core.agent.rewarder.reward_rules import RewardRuleTable
from core.agent.rewarder.time_decay import TimeDecay
from core.agent.rewarder.noise_adaptation import NoiseAdaptation
from core.agent.rewarder.correction_detector import CorrectionDetector
from core.agent.rewarder.abl_reflection import ABLReflectionGenerator
from core.agent.predictor.models import Candidate, PredictionResult

class TestSignal:
    def test_effective(self):
        s = RewardSignal("ek", 0.10, 1.0, 0.5)
        s.compute_effective()
        assert s.effective_reward == 0.05
    def test_explore(self):
        s = RewardSignal("ek", 0.10, 1.0, 0.5, is_exploration=True)
        s.compute_effective()
        assert s.effective_reward == 0.0

class TestRules:
    def test_hit(self):
        c = [Candidate("x", expected_value=0.9)]
        r = PredictionResult(c, {}, "full")
        assert RewardRuleTable().evaluate(r, "x") == 0.10
    def test_correction(self):
        assert RewardRuleTable().evaluate(None, "", True) == -0.20

class TestDecay:
    def test_no(self):
        assert TimeDecay().compute_decay(10) == 1.0
    def test_some(self):
        assert 0 < TimeDecay().compute_decay(300) < 1

class TestNoise:
    def test_init(self):
        assert NoiseAdaptation().noise_level == 0.5

class TestCorrection:
    def test_explicit(self):
        s = CorrectionDetector().detect("不对", [], "")
        assert s.is_correction
    def test_normal(self):
        s = CorrectionDetector().detect("hello", [], "")
        assert not s.is_correction
    def test_rollback(self):
        s = CorrectionDetector().detect("", ["a","b"], "b")
        assert s.is_correction

class TestABL:
    def test_gen(self):
        r = ABLReflectionGenerator().generate("e", "a", "b")
        assert r.error_type == "wrong_entity"