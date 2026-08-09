from .models import MetaRole  # SkeletonMatch, CausalConstraints moved to lazy import
from .meta_roles import MetaRoles
from .skeleton_library import SkeletonLibrary
from .skeleton_matcher import ConstraintExtractor, SkeletonMatcher
from .delta_adjuster import DeltaAdjuster


class CausalSubstrate:
    MIN_CHAIN = 10

    def __init__(self, graph, lib=None, adj=None, min_chain: int = 10):
        self.graph = graph
        self.lib = lib or SkeletonLibrary()
        self.matcher = SkeletonMatcher(self.lib)
        self.adj = adj or DeltaAdjuster()
        self.MIN_CHAIN = min_chain  # configurable threshold (adapter wiring)
        self._do_validator = None
        self.blocked_edges: list = []   # do-calculus HARD_BLOCK log (A22 white-box)

    def should_trigger(self, chain_len):
        return chain_len > self.MIN_CHAIN

    def process_single(self, compiler_out):
        ex = ConstraintExtractor()
        c = ex.extract(compiler_out)
        m = self.matcher.match(c)
        return m.to_prior() if m else 0.0

    # ------------------------------------------------------------------ #
    # A22 negative verification: do-calculus excludes, never discovers
    # ------------------------------------------------------------------ #

    def _ensure_do_validator(self):
        if self._do_validator is None:
            from ..do_calculus.validator import DoCalculusValidator
            self._do_validator = DoCalculusValidator()
        return self._do_validator

    def verify_negative(self, from_summary: str, to_summary: str) -> str:
        """D-10: run do-calculus backdoor check on a candidate edge.

        Returns ``"HARD_BLOCK"`` (P(do(x)) >= 0.95 → exclude), ``"WARN"``
        (cannot identify / downgraded), or ``"PASS"`` (no directed path).
        This is negative validation only — it never *discovers* causality.
        """
        try:
            from ..do_calculus.models import CausalSkeleton as DoSkeleton, CausalEdge as DoEdge
            val = self._ensure_do_validator()
            sk = DoSkeleton(
                nodes=[from_summary, to_summary],
                edges=[DoEdge(from_summary, to_summary, label="causal")],
            )
            rule = type("R", (), {
                "rule_id": "neg",
                "message": f"intervene {from_summary} => {to_summary}",
            })()
            result = val.validate_hard_block(sk, rule)
            level = result.to_negative_level()
            if level == "HARD_BLOCK":
                self.blocked_edges.append({
                    "from": from_summary,
                    "to": to_summary,
                    "level": level,
                })
            return level
        except Exception as e:
            logger.debug("do-calculus negative check unavailable: %s", e)
            return "WARN"

    def process_chain(self, behavior_chain):
        """Iterate over chain's steps, find matching edges in graph, compute structural_prior for each transition.

        D-10: each candidate edge passes do-calculus negative verification
        first — HARD_BLOCK edges are skipped (structural_prior stays 0) and
        logged to ``blocked_edges``. Discovery stays within A22 bounds.
        """
        results = []
        if not behavior_chain or len(behavior_chain) < 2:
            return results
        for i in range(len(behavior_chain) - 1):
            step_a = behavior_chain[i]
            step_b = behavior_chain[i + 1]
            # Find edge in graph matching this transition
            edge_key = None
            if hasattr(self.graph, "edges") and hasattr(self.graph, "nodes"):
                for ek, edge in self.graph.edges.items():
                    from_step = self.graph.nodes.get(edge.from_step_id)
                    to_step = self.graph.nodes.get(edge.to_step_id)
                    if (from_step and to_step and
                        from_step.action_summary == getattr(step_a, "action_summary", step_a) and
                        to_step.action_summary == getattr(step_b, "action_summary", step_b)):
                        edge_key = ek
                        break
            if edge_key:
                from_summary = getattr(step_a, "action_summary", step_a)
                to_summary = getattr(step_b, "action_summary", step_b)
                level = self.verify_negative(from_summary, to_summary)
                if level == "HARD_BLOCK":
                    results.append({
                        "edge_key": edge_key,
                        "structural_prior": 0.0,
                        "blocked": True,
                        "reason": "do-calculus HARD_BLOCK",
                    })
                    continue
                prior = self.process_single(step_b)
                results.append({
                    "edge_key": edge_key,
                    "structural_prior": prior,
                    "blocked": False,
                })
        return results

    def update_edge_prior(self, edge_key, prior):
        """Write structural_prior back to graph edge."""
        if hasattr(self.graph, "edges"):
            edge = self.graph.edges.get(edge_key)
            if edge:
                edge.structural_prior = max(0.0, min(1.0, prior))
                return True
        return False
