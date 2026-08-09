import re


def _shared_direction(predicted: str, actual: str) -> bool:
    """Direction-level overlap: shared ASCII word, or a non-trivial middle
    substring overlap for CJK. Strict prefix/suffix containment is excluded so
    that a generic prediction is not rewarded when the user did something more
    specific (e.g. predicted '写代码', user did '写代码注释')."""
    if not predicted or not actual:
        return False
    # Normalize separators so "add_doc" yields tokens {"add", "doc"}.
    _norm = lambda s: s.lower().replace("_", " ").replace("-", " ")
    aw = set(re.findall(r"[A-Za-z0-9]+", _norm(predicted)))
    bw = set(re.findall(r"[A-Za-z0-9]+", _norm(actual)))
    if aw & bw:
        return True
    if len(predicted) < 2 or len(actual) < 2:
        return False
    if predicted in actual or actual in predicted:
        # Reject strict prefix/suffix containment (generic vs specific).
        if actual.startswith(predicted) or actual.endswith(predicted):
            return False
        if predicted.startswith(actual) or predicted.endswith(actual):
            return False
        return True
    return False


def evaluate_accuracy(candidates, actual, is_correction=False, has_alternative=False):
    """BC05 §6.1 accuracy reward kernel (7 tiers, shared by predictor and
    rewarder so there is exactly one reward implementation)."""
    from core.agent.compiler.parameter_registry import get_registry
    reg = get_registry()
    if is_correction:
        return float(reg.get("behavior.reward_correction", -0.2))
    if not candidates:
        return 0.0
    top3 = sorted(candidates, key=lambda c: -c.expected_value)[:3]
    top1 = top3[0].action_summary if top3 else None
    acts = [c.action_summary for c in top3]
    if top1 and top1 == actual:
        return float(reg.get("behavior.reward_top1_hit", 1.0))
    if actual in acts:
        return float(reg.get("behavior.reward_top3_hit", 0.5))
    if any(_shared_direction(a, actual) for a in acts):
        return float(reg.get("behavior.reward_partial", 0.2))
    if has_alternative:
        return float(reg.get("behavior.reward_alternative", -0.3))
    return float(reg.get("behavior.reward_miss", -0.5))


class RewardRuleTable:
    RULES = [
        ("top1_hit", 1.0), ("top3_hit", 0.5), ("partial", 0.2),
        ("miss", -0.5), ("correction", -0.2), ("none", 0.0),
        ("alternative", -0.3),
    ]

    def evaluate(self, prediction, actual, is_correction=False, has_alternative=False):
        if not prediction:
            if is_correction:
                return -0.2
            return 0.0
        candidates = getattr(prediction, "candidates", None) or []
        return evaluate_accuracy(candidates, actual, is_correction, has_alternative)
