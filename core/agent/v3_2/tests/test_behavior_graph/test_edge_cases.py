import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.behavior.models import BehaviorStep, BehaviorEdge
from core.agent.behavior.graph_store import BehaviorGraph
from core.agent.behavior.weight_updater import WeightUpdater
from core.agent.behavior.cold_start import ColdStartManager
from core.agent.behavior.fast_correction import FastCorrectionDetector
from core.agent.behavior.pruning import GraphPruner
from core.agent.behavior.causal_discovery import LightweightCausalDiscovery

def mk(sid, summary="run", atype="TOOL_EXEC"):
    return BehaviorStep(sid, summary, atype)

class TestEdgeCases:
    def test_empty_graph_properties(self):
        bg = BehaviorGraph()
        assert len(bg.nodes) == 0
        assert len(bg.edges) == 0
        assert bg.get_statistics().node_count == 0

    def test_duplicate_edge_same(self):
        bg = BehaviorGraph()
        bg.record_edge(mk("s1","run"), mk("s2","check"))
        bg.record_edge(mk("s1","run"), mk("s2","check"))
        assert len(bg.edges) == 1
        assert bg.edges["s1->s2"].sample_count == 2

    def test_many_samples_converge_weight(self):
        bg = BehaviorGraph()
        for i in range(10):
            bg.record_edge(mk("s1","run"), mk("s2","check"), success=True)
        e = bg.edges["s1->s2"]
        assert e.sample_count == 10
        assert e.success_count == 10

    def test_mixed_success_failure(self):
        bg = BehaviorGraph()
        for i in range(5):
            bg.record_edge(mk("s1","run"), mk("s2","check"), success=True)
        for i in range(3):
            bg.record_edge(mk("s1","run"), mk("s2","check"), success=False)
        e = bg.edges["s1->s2"]
        assert e.success_count == 5
        assert e.failure_count == 3

    def test_correction_mode_weight_drop(self):
        updater = WeightUpdater()
        e = BehaviorEdge("e1", "s1", "s2", weight=0.8)
        e.correction_mode = True
        w = updater.update(e)
        assert w == 0.24

    def test_fast_correction_detection(self):
        bg = BehaviorGraph()
        fcd = FastCorrectionDetector(bg)
        bg.record_edge(mk("s1","run"), mk("s2","check"))
        fcd.record_observation("s1->s2", True)
        assert not fcd.is_fast_correction_needed("s1->s2")
        fcd.record_observation("s1->s2", True)
        assert fcd.is_fast_correction_needed("s1->s2")

    def test_fast_correction_applied(self):
        bg = BehaviorGraph()
        fcd = FastCorrectionDetector(bg)
        bg.record_edge(mk("s1","run"), mk("s2","check"))
        fcd.apply_fast_correction("s1->s2")
        assert bg.edges["s1->s2"].correction_mode

    def test_fast_correction_release(self):
        bg = BehaviorGraph()
        fcd = FastCorrectionDetector(bg)
        bg.record_edge(mk("s1","run"), mk("s2","check"))
        fcd.apply_fast_correction("s1->s2")
        fcd.release_correction("s1->s2")
        assert not bg.edges["s1->s2"].correction_mode

    def test_cold_start_has_seeds(self):
        csm = ColdStartManager()
        assert len(csm.get_active_seeds()) > 0

    def test_pruner_should_not_prune_empty(self):
        bg = BehaviorGraph()
        pruner = GraphPruner(bg)
        assert not pruner.should_prune()

    def test_pruner_prune_empty(self):
        bg = BehaviorGraph()
        pruner = GraphPruner(bg)
        count, deleted = pruner.prune()
        assert count == 0
        assert deleted == []

    def test_causal_discovery_no_trigger(self):
        bg = BehaviorGraph()
        cd = LightweightCausalDiscovery(bg)
        triggered = cd.check_trigger()
        assert triggered == []

    def test_stats_after_operations(self):
        bg = BehaviorGraph()
        bg.record_edge(mk("s1","run"), mk("s2","check"))
        bg.record_edge(mk("s2","check"), mk("s3","analyze"))
        stats = bg.get_statistics()
        assert stats.node_count == 3
        assert stats.edge_count == 2
        assert stats.total_samples == 2
