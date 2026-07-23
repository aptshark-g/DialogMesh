from .models import BackdoorTestResult
from .backdoor_criterion import BackdoorCriterion
from .do_calculus import DoCalculusEngine


class DoCalculusValidator:
    def __init__(self, criterion=None):
        self.criterion = criterion or BackdoorCriterion()
        self.engine = DoCalculusEngine(self.criterion)

    def validate_hard_block(self, skeleton, rule):
        x, y = self._parse_hypothesis(rule)
        if not x or not y:
            return BackdoorTestResult(rule.rule_id, False, 0, ["parse_error"], 0.0)
        # Try full do-calculus identification
        success, modified_skeleton, explanation = self.engine.identify(skeleton, x, y)
        if success:
            return BackdoorTestResult(
                hypothesis=f"do({x}=0) => {y}=0",
                verified=True,
                paths_checked=getattr(self.criterion, "MAX_PATH_DEPTH", 5),
                confounders_found=[],
                p_y_given_do_x=1.0,
            )
        # If identify fails, auto-downgrade HARD_BLOCK to WARN
        return BackdoorTestResult(
            hypothesis=f"do({x}=0) => {y}=0",
            verified=False,
            paths_checked=getattr(self.criterion, "MAX_PATH_DEPTH", 5),
            confounders_found=[explanation],
            p_y_given_do_x=0.0,
        )

    def _parse_hypothesis(self, rule):
        import re
        pat = "intervene\\s*(\\w+)\\s*=>?\\s*(\\w+)"
        m = re.search(pat, rule.message)
        if m:
            return (m.group(1), m.group(2))
        return (None, None)
