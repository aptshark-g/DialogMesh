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