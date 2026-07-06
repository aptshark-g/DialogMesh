class RewardRuleTable:
    RULES = [
        ("top1_hit", 0.10), ("top3_hit", 0.05), ("partial", 0.03),
        ("miss", -0.15), ("correction", -0.20), ("none", 0.00),
    ]

    def evaluate(self, prediction, actual, is_correction=False):
        if is_correction: return -0.20
        if not prediction or not prediction.candidates: return 0.0
        top3 = sorted(prediction.candidates, key=lambda c: -c.expected_value)[:3]
        top1 = top3[0].action_summary if top3 else None
        acts = [c.action_summary for c in top3]
        if top1 and top1 == actual: return 0.10
        if actual in acts: return 0.05
        if any(a in actual for a in acts): return 0.03
        return -0.15