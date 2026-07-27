import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.association.models import TrackType, TrackResult, StageOutput, FusionResult
from core.agent.association.conflict_resolver import ConflictResolver
from core.agent.association.global_workspace import GlobalWorkspace


class TestEdgeCases:
    def test_fusion_result_empty(self):
        fr = FusionResult({}, 0, TrackType.TRACK_0, [], [])
        assert fr.dominant_track == TrackType.TRACK_0

    def test_conflict_resolve_empty_stage(self):
        r = ConflictResolver()
        stage = StageOutput(1, [], {})
        dom, cs = r.resolve(stage)
        assert dom is None
        assert cs == []

    def test_workspace_select_empty(self):
        gw = GlobalWorkspace()
        dom = gw.select_dominant([])
        assert dom is None

    def test_workspace_status(self):
        gw = GlobalWorkspace()
        st = gw.get_status()
        assert isinstance(st, dict)
        assert len(st) == len(TrackType)

    def test_priorities_order(self):
        r = ConflictResolver()
        assert r.PRIORITY_ORDER[0] == TrackType.CAUSAL
        assert r.PRIORITY_ORDER[-1] == TrackType.TRACK_P

    def test_track_result_string_types(self):
        tr = TrackResult(TrackType.TRACK_0, {}, 0.5)
        assert str(tr.track.value) == "algo"
