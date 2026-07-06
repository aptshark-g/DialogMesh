from .models import CausalConstraints, SkeletonMatch
from .skeleton_library import SkeletonLibrary

class ConstraintExtractor:
    def extract(self, compiler_out):
        if not compiler_out or getattr(compiler_out, "undefined", False):
            return CausalConstraints()
        slots = getattr(compiler_out, "slots", {})
        action = slots.get("action")
        if action and hasattr(action, "value"):
            mapping = {"run": ("software", False, True, False, "cause->effect", True)}
            mapped = mapping.get(action.value)
            if mapped: return CausalConstraints(*mapped)
        return CausalConstraints()

class SkeletonMatcher:
    def __init__(self, lib=None):
        self.lib = lib or SkeletonLibrary()
    def match(self, constraints):
        if not constraints.domain_hint: return None
        candidates = self.lib.query(constraints)
        if not candidates: return None
        scored = [(sk, sum(getattr(constraints, r, False) for r in sk.requires) / max(len(sk.requires), 1)) for sk in candidates]
        scored.sort(key=lambda x: -x[1])
        best, cov = scored[0]
        multi = len(scored) > 1 and (scored[0][1] - scored[1][1]) < 0.15
        return SkeletonMatch(best.roles, cov, cov, multi)