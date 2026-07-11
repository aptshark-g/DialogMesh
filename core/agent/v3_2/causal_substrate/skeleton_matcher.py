from .models import CausalConstraints, SkeletonMatch
from .skeleton_library import SkeletonLibrary


class ConstraintExtractor:
    DOMAIN_MAPPINGS = {
        "run": ("software", False, True, False, "cause->effect", True),
        "debug": ("software", False, True, False, "cause->effect", True),
        "configure": ("software", False, True, False, "cause->effect", True),
        "deploy": ("software", False, True, False, "cause->effect", True),
        "scan": ("security", False, False, False, "cause->effect", True),
        "monitor": ("monitoring", True, False, False, "cause->effect", True),
        "test": ("testing", False, False, False, "cause->effect", True),
        "analyze": ("analysis", False, False, False, "cause->effect", True),
        "build": ("build", False, True, False, "cause->effect", True),
        "restart": ("system", False, False, False, "cause->effect", True),
    }

    def extract(self, compiler_out):
        if not compiler_out or getattr(compiler_out, "undefined", False):
            return CausalConstraints()
        slots = getattr(compiler_out, "slots", {})
        action = slots.get("action")
        if action and hasattr(action, "value"):
            mapped = self.DOMAIN_MAPPINGS.get(action.value)
            if mapped:
                return CausalConstraints(*mapped)
        return CausalConstraints()

    def extract_from_behavior_step(self, step):
        """Extract action_type and action_summary to infer domain."""
        action_type = getattr(step, "action_type", "")
        action_summary = getattr(step, "action_summary", "")
        # Infer domain from action_type keywords
        domain_hint = "general"
        type_lower = (action_type or "").lower()
        summary_lower = (action_summary or "").lower()
        if any(k in type_lower or k in summary_lower for k in ("run", "debug", "configure", "deploy", "code")):
            domain_hint = "software"
        elif any(k in type_lower or k in summary_lower for k in ("scan", "security", "vuln")):
            domain_hint = "security"
        elif any(k in type_lower or k in summary_lower for k in ("monitor", "watch", "observe")):
            domain_hint = "monitoring"
        elif any(k in type_lower or k in summary_lower for k in ("test", "verify", "validate")):
            domain_hint = "testing"
        elif any(k in type_lower or k in summary_lower for k in ("analyze", "analysis", "inspect")):
            domain_hint = "analysis"
        elif any(k in type_lower or k in summary_lower for k in ("build", "compile", "make")):
            domain_hint = "build"
        elif any(k in type_lower or k in summary_lower for k in ("restart", "reboot", "system")):
            domain_hint = "system"
        return CausalConstraints(
            domain_hint=domain_hint,
            has_feedback=False,
            involves_dissipation=False,
            involves_storage=False,
            causal_direction="cause->effect",
            involves_transformation=True,
        )


class SkeletonMatcher:
    def __init__(self, lib=None):
        self.lib = lib or SkeletonLibrary()

    def match(self, constraints):
        if not constraints.domain_hint:
            return None
        candidates = self.lib.query(constraints)
        if not candidates:
            return None
        scored = [(sk, sum(getattr(constraints, r, False) for r in sk.requires) / max(len(sk.requires), 1)) for sk in candidates]
        scored.sort(key=lambda x: -x[1])
        best, cov = scored[0]
        multi = len(scored) > 1 and (scored[0][1] - scored[1][1]) < 0.15
        return SkeletonMatch(best.roles, cov, cov, multi)
