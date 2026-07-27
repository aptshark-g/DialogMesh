import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.association.models import TrackType, TrackResult, StageOutput, FusionResult

class TestTrackType:
    def test_values(self):
        assert TrackType.TRACK_0.value == "algo"
        assert TrackType.TRACK_1.value == "llm"
        assert TrackType.CAUSAL.value == "causal"

class TestTrackResult:
    def test_defaults(self):
        tr = TrackResult(TrackType.TRACK_0, {}, 0.8)
        assert tr.confidence == 0.8
        assert not tr.is_timeout

    def test_is_confident_high(self):
        tr = TrackResult(TrackType.TRACK_0, {}, 0.8)
        assert tr.is_confident()

    def test_is_confident_low(self):
        tr = TrackResult(TrackType.TRACK_0, {}, 0.3)
        assert not tr.is_confident()

    def test_is_confident_timeout(self):
        tr = TrackResult(TrackType.TRACK_0, {}, 0.8, is_timeout=True)
        assert not tr.is_confident()

class TestFusionResult:
    def test_defaults(self):
        fr = FusionResult({}, 0, TrackType.TRACK_0, [], [])
        assert not fr.ask_clarification
        assert not fr.profile_lite
        assert fr.confidence == 0
