from .models import NegativeLevel, NegativeResult
from .rule_store import RuleStore
from .fuse_controller import FuseController

class NegativeKB:
    def __init__(self, store=None, fuse=None):
        self.store = store or RuleStore()
        self.fuse = fuse or FuseController()
    def check(self, ctx=""):
        level = self.store.get_highest(ctx)
        if level is None: return NegativeResult()
        for rule in self.store.applicable(ctx):
            if rule.level == level:
                if level == NegativeLevel.HARD_BLOCK and not rule.is_verified:
                    continue
                return self.fuse.evaluate(rule, ctx)
        return NegativeResult()
    def register(self, rule):
        if rule.level == NegativeLevel.HARD_BLOCK and not rule.is_verified:
            raise ValueError("HARD_BLOCK rules must be verified")
        self.store.register(rule)