from .models import MetaRole, SkeletonMatch, CausalConstraints
from .meta_roles import MetaRoles
from .skeleton_library import SkeletonLibrary
from .skeleton_matcher import ConstraintExtractor, SkeletonMatcher
from .delta_adjuster import DeltaAdjuster


class CausalSubstrate:
    MIN_CHAIN = 10

    def __init__(self, graph, lib=None, adj=None):
        self.graph = graph
        self.lib = lib or SkeletonLibrary()
        self.matcher = SkeletonMatcher(self.lib)
        self.adj = adj or DeltaAdjuster()

    def should_trigger(self, chain_len):
        return chain_len > self.MIN_CHAIN

    def process_single(self, compiler_out):
        ex = ConstraintExtractor()
        c = ex.extract(compiler_out)
        m = self.matcher.match(c)
        return m.to_prior() if m else 0.0

    def process_chain(self, behavior_chain):
        """Iterate over chain's steps, find matching edges in graph, compute structural_prior for each transition."""
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
                prior = self.process_single(step_b)
                results.append({"edge_key": edge_key, "structural_prior": prior})
        return results

    def update_edge_prior(self, edge_key, prior):
        """Write structural_prior back to graph edge."""
        if hasattr(self.graph, "edges"):
            edge = self.graph.edges.get(edge_key)
            if edge:
                edge.structural_prior = max(0.0, min(1.0, prior))
                return True
        return False
