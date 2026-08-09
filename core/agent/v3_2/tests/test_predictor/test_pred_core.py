import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.predictor.models import Candidate, PredictionResult, TrainingSignal
from core.agent.predictor.cognitive_load import CognitiveLoadEstimator

class TestCandidate:
    def test_compute(self):
        c = Candidate("a", "", 0.5, 0.7, 0.2, 0.3, 0.0)
        v = c.compute_value()
        assert abs(v - 0.60) < 0.01

class TestResult:
    def test_top3(self):
        c = [Candidate("a", expected_value=0.3), Candidate("b", expected_value=0.9)]
        r = PredictionResult(c, {}, "full")
        assert r.top3[0].action_summary == "b"

class TestSignal:
    def test_hit(self):
        s = TrainingSignal([Candidate("x", expected_value=0.9)], "x")
        assert s.compute_reward() == 1.0
    def test_top3_hit(self):
        s = TrainingSignal(
            [Candidate("a", expected_value=0.9), Candidate("x", expected_value=0.5)],
            "x",
        )
        assert s.compute_reward() == 0.5
    def test_miss(self):
        s = TrainingSignal([Candidate("a", expected_value=0.9)], "z")
        assert s.compute_reward() == -0.5
    def test_correction(self):
        s = TrainingSignal([Candidate("a", expected_value=0.9)], "z", is_correction=True)
        assert s.compute_reward() == -0.2

class TestLoad:
    def test_known(self):
        e = CognitiveLoadEstimator()
        assert e.estimate("TOOL_EXEC") == 0.2
        assert e.estimate("UNKNOWN") == 0.3

class TestParse:
    def test_parse(self):
        from core.agent.predictor.candidate_generator import CandidateGenerator
        g = CandidateGenerator(None)
        r = g._parse("[{\"action\": \"t\", \"probability\": 0.8}]")
        assert r and r[0][0] == "t"
    def test_invalid(self):
        from core.agent.predictor.candidate_generator import CandidateGenerator
        g = CandidateGenerator(None)
        assert g._parse("bad") is None
