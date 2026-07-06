from .models import BackdoorTestResult
from .backdoor_criterion import BackdoorCriterion


class DoCalculusValidator:
    def __init__(self, criterion=None):
        self.criterion = criterion or BackdoorCriterion()

    def validate_hard_block(self, skeleton, rule):
        x, y = self._parse_hypothesis(rule)
        if not x or not y:
            return BackdoorTestResult(rule.rule_id, False, 0, ["parse_error"], 0.0)
        return self.criterion.verify(skeleton, x, y)

    def _parse_hypothesis(self, rule):
        import re
        pat = "intervene\\s*(\\w+)\\s*=>?\\s*(\\w+)"
        m = re.search(pat, rule.message)
        if m:
            return (m.group(1), m.group(2))
        return (None, None)
