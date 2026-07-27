import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.association.models import MetaRole, SkeletonMatch
from core.agent.association.meta_roles import MetaRoles
from core.agent.association.skeleton_library import SkeletonLibrary
from core.agent.association.skeleton_matcher import ConstraintExtractor, SkeletonMatcher
from core.agent.association.delta_adjuster import DeltaAdjuster
from core.agent.association.causal_substrate import CausalSubstrate

class TestMetaRole:
    def test_domain_roles(self):
        roles = MetaRoles.domain_roles("physical")
        assert len(roles) > 0
class TestSkeleton:
    def test_default(self):
        lib = SkeletonLibrary()
        assert len(lib.skeletons) > 0
from core.agent.association.models import CausalConstraints
class TestMatcher:
    def test_match_none(self):
        m = SkeletonMatcher()
        assert m.match(CausalConstraints()) is not None
class TestAdjuster:
    def test_initial(self):
        d = DeltaAdjuster()
        assert d.current == 0.05
class TestSubstrate:
    def test_trigger(self):
        cs = CausalSubstrate(None)
        assert cs.should_trigger(15)
        assert not cs.should_trigger(5)