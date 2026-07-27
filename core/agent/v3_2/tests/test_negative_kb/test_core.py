import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.negative_kb.models import NegativeLevel, ContextualNegativeRule, NegativeResult
from core.agent.negative_kb.rule_store import RuleStore
from core.agent.negative_kb.fuse_controller import FuseController
from core.agent.negative_kb.negative_kb import NegativeKB

class TestLevels:
    def test_values(self):
        assert NegativeLevel.HARD_BLOCK.value == "hard_block"
        assert NegativeLevel.WARN.value == "warn"
class TestRule:
    def test_applicable(self):
        r = ContextualNegativeRule("r1", NegativeLevel.WARN, "msg")
        assert r.is_applicable()
    def test_keyword(self):
        r = ContextualNegativeRule("r1", NegativeLevel.WARN, "msg", keywords=["danger"])
        assert r.is_applicable("danger")
        assert not r.is_applicable("safe")
class TestStore:
    def test_register_query(self):
        s = RuleStore()
        s.register(ContextualNegativeRule("r1", NegativeLevel.WARN, "m"))
        assert len(s.applicable("")) == 1
class TestFuse:
    def test_hard_block(self):
        r = ContextualNegativeRule("r1", NegativeLevel.HARD_BLOCK, "no")
        r = ContextualNegativeRule("r1", NegativeLevel.HARD_BLOCK, "no", is_verified=True)
        res = FuseController().evaluate(r)
        assert res.blocked
    def test_warn_three_strikes(self):
        fc = FuseController()
        r = ContextualNegativeRule("r1", NegativeLevel.WARN, "warn")
        assert fc.evaluate(r).blocked
        assert not fc.evaluate(r).blocked
        assert fc.evaluate(r).learned
class TestKB:
    def test_no_rules(self):
        kb = NegativeKB()
        res = kb.check("")
        assert not res.blocked
    def test_hard_block(self):
        kb = NegativeKB()
        r = ContextualNegativeRule("r1", NegativeLevel.HARD_BLOCK, "no", is_verified=True)
        kb.register(r)
        res = kb.check("")
        assert res.blocked