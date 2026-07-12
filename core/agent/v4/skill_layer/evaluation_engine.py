"""EvaluationEngine: multi-dimensional Skill belief evaluation."""
from typing import Tuple
from .models import SkillBelief


class EvaluationEngine:
    def __init__(self, registry=None):
        self._registry = registry

    def evaluate(self, belief: SkillBelief) -> Tuple[str, float]:
        w = {
            "generality": self._p("skill.weight_generality", 0.30),
            "benefit": self._p("skill.weight_benefit", 0.25),
            "stability": self._p("skill.weight_stability", 0.20),
            "coverage": self._p("skill.weight_coverage", 0.15),
            "recency": self._p("skill.weight_recency", 0.10),
        }
        score = (belief.generality * w["generality"] + belief.benefit * w["benefit"]
                 + belief.stability * w["stability"] + belief.coverage * w["coverage"]
                 + belief.recency * w["recency"])
        threshold = self._p("skill.verified_threshold", 0.80)
        return ("verified", score) if score >= threshold else ("candidate", score)

    def promote_ready(self, belief: SkillBelief) -> bool:
        return (belief.support >= self._p("skill.min_support", 15)
                and belief.generality >= self._p("skill.min_generality", 0.80)
                and belief.stability >= self._p("skill.min_stability", 0.90))

    def _p(self, key: str, default: float) -> float:
        if self._registry:
            try: return self._registry.value(key)
            except Exception: pass
        return default
