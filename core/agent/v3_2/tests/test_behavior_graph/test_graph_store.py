import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.behavior.graph_store import BehaviorGraph
from core.agent.behavior.models import BehaviorStep

def make_step(sid, summary="run", atype="TOOL_EXEC"):
    return BehaviorStep(sid, summary, atype)

class TestBehaviorGraph:
    def setup_method(self):
        self.bg = BehaviorGraph()

    def test_add_step(self):
        sid = self.bg.add_step(make_step("s1"))
        assert sid == "s1"
        assert len(self.bg.nodes) == 1

    def test_add_duplicate_step(self):
        self.bg.add_step(make_step("s1"))
        self.bg.add_step(make_step("s1"))
        assert len(self.bg.nodes) == 1

    def test_get_step(self):
        self.bg.add_step(make_step("s1"))
        s = self.bg.get_step("s1")
        assert s.action_summary == "run"

    def test_get_step_missing(self):
        s = self.bg.get_step("nonexistent")
        assert s is None

    def test_record_edge(self):
        s1 = make_step("s1", "run")
        s2 = make_step("s2", "check")
        ek = self.bg.record_edge(s1, s2)
        assert ek is not None
        assert len(self.bg.edges) == 1

    def test_record_edge_with_correction(self):
        s1 = make_step("s1", "run")
        s2 = make_step("s2", "check")
        ek = self.bg.record_edge(s1, s2, correction=True)
        e = self.bg.edges[ek]
        assert e.correction_count == 1

    def test_get_edge_weight_exact(self):
        s1 = make_step("s1", "run")
        s2 = make_step("s2", "check")
        self.bg.record_edge(s1, s2)
        w = self.bg.get_edge_weight("run", "check")
        assert w is not None
        assert 0 <= w <= 1

    def test_get_edge_weight_missing(self):
        w = self.bg.get_edge_weight("none", "none")
        assert w is None

    def test_get_statistics(self):
        s1 = make_step("s1", "run")
        s2 = make_step("s2", "check")
        self.bg.record_edge(s1, s2)
        stats = self.bg.get_statistics()
        assert stats.node_count == 2
        assert stats.edge_count == 1
        assert stats.total_samples == 1
