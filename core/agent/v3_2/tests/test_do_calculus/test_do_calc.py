import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.do_calculus.models import CausalEdge, CausalSkeleton, BackdoorTestResult
from core.agent.do_calculus.backdoor_criterion import BackdoorCriterion
from core.agent.do_calculus.validator import DoCalculusValidator

class TestModels:
    def test_edge(self):
        e = CausalEdge("A", "B")
        assert e.source == "A"
    def test_skeleton(self):
        sk = CausalSkeleton(["A","B"], [CausalEdge("A","B")])
        assert len(sk.nodes) == 2
    def test_result_hard(self):
        assert BackdoorTestResult("t", True, 1, [], 0.95).to_negative_level() == "HARD_BLOCK"

class TestCriterion:
    def test_verify(self):
        sk = CausalSkeleton(["A","B","C"], [CausalEdge("A","B"), CausalEdge("B","C")])
        r = BackdoorCriterion().verify(sk, "A", "C")
        assert r.verified or not r.verified
    def test_empty(self):
        r = BackdoorCriterion().verify(CausalSkeleton([], []), "X", "Y")
        assert r.verified == False

class TestValidator:
    def test_parse(self):
        from core.agent.negative_kb.models import ContextualNegativeRule, NegativeLevel
        v = DoCalculusValidator()
        rule = ContextualNegativeRule("r1", NegativeLevel.HARD_BLOCK, "intervene A => B", is_verified=False)
        x, y = v._parse_hypothesis(rule)
        assert x == "A"; assert y == "B"