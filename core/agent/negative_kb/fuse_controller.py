from .models import NegativeLevel, NegativeResult

class FuseController:
    FUSE_LIMIT = 3
    def __init__(self):
        self.hits = {}; self.learned = {}
    def evaluate(self, rule, ctx=""):
        if rule.level == NegativeLevel.HARD_BLOCK:
            return NegativeResult(rule.level, rule.rule_id, rule.message, True)
        if rule.level == NegativeLevel.SOFT_DISCOURAGE:
            return NegativeResult(rule.level, rule.rule_id, rule.message)
        rid = rule.rule_id
        self.hits[rid] = self.hits.get(rid, 0) + 1
        c = self.hits[rid]
        if c == 1: return NegativeResult(NegativeLevel.WARN, rid, rule.message, True)
        if c == 2: return NegativeResult(NegativeLevel.WARN, rid, "注意: " + rule.message)
        self.learned[rid] = f"{rid}: user overrode this rule"
        return NegativeResult(None, rid, "", learned=True)