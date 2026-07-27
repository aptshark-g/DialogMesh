import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.association.conflict_resolver import ConflictResolver
from core.agent.association.models import TrackType, TrackResult, StageOutput

class TestConflictResolver:
    def setup_method(self):
        self.r = ConflictResolver()

    def test_resolve_causal_highest(self):
        tracks = [
            TrackResult(TrackType.CAUSAL, {"x": 1}, 0.9),
            TrackResult(TrackType.TRACK_0, {"x": 2}, 0.9),
        ]
        stage = StageOutput(1, tracks, {})
        dom, cs = self.r.resolve(stage)
        assert dom.track == TrackType.CAUSAL

    def test_resolve_algo_second(self):
        tracks = [TrackResult(TrackType.TRACK_0, {"x": 1}, 0.9)]
        stage = StageOutput(1, tracks, {})
        dom, cs = self.r.resolve(stage)
        assert dom.track == TrackType.TRACK_0

    def test_no_confident_tracks(self):
        tracks = [TrackResult(TrackType.TRACK_0, {}, 0.3)]
        stage = StageOutput(1, tracks, {})
        dom, cs = self.r.resolve(stage)
        assert dom is None

    def test_apply_conflict(self):
        dom = TrackResult(TrackType.TRACK_0, {"decision": "a"}, 0.9)
        conflicts = [{"type": "CONFIDENCE_DIVERGENCE"}]
        out = self.r.apply(dom, conflicts)
        assert out.get("conservative_mode")
