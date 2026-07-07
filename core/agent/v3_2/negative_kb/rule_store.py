from .models import ContextualNegativeRule, NegativeLevel, NegativeResult

class RuleStore:
    def __init__(self):
        self.rules = []
    def register(self, rule):
        self.rules.append(rule)
    def applicable(self, ctx):
        return [r for r in self.rules if r.is_applicable(ctx)]
    def get_highest(self, ctx):
        applicable = self.applicable(ctx)
        if not applicable: return None
        levels = [r.level for r in applicable]
        if NegativeLevel.HARD_BLOCK in levels: return NegativeLevel.HARD_BLOCK
        if NegativeLevel.WARN in levels: return NegativeLevel.WARN

        return NegativeLevel.SOFT_DISCOURAGE

    def add_with_verification(self, rule, verified=False):
        from .models import NegativeLevel as NL
        if rule.level == NL.HARD_BLOCK and not verified:
            rule.level = NL.WARN
            rule.message = '[downgraded] ' + rule.message
        self.register(rule)
        return rule.level