import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.association.fusion_engine import FusionEngine
from core.agent.association.models import TrackType, TrackResult

pytestmark = pytest.mark.asyncio

def mk_tr(t, c, lat=10, timeout=False):
    return TrackResult(t, {"decision": "x"}, c, lat, is_timeout=timeout)

class TestFusionEngine:
    async def test_full_three_stages(self):
        fe = FusionEngine()
        r = await fe.fuse(
            mk_tr(TrackType.TRACK_0, 0.9),
            mk_tr(TrackType.TRACK_1, 0.85),
            mk_tr(TrackType.TRACK_P, 0.7),
            mk_tr(TrackType.CAUSAL, 0.6),
        )
        assert r.final_output is not None
        assert r.confidence > 0

    async def test_lite_mode(self):
        fe = FusionEngine()
        r = await fe.fuse(
            mk_tr(TrackType.TRACK_0, 0.9),
            profile_lite=True,
        )
        assert r.profile_lite

    async def test_all_low_confidence(self):
        fe = FusionEngine()
        r = await fe.fuse(
            mk_tr(TrackType.TRACK_0, 0.3),
            mk_tr(TrackType.TRACK_1, 0.2),
        )
        assert r.ask_clarification

    async def test_track1_timeout(self):
        fe = FusionEngine()
        r = await fe.fuse(
            mk_tr(TrackType.TRACK_0, 0.9),
            mk_tr(TrackType.TRACK_1, 0.0, timeout=True),
            mk_tr(TrackType.TRACK_P, 0.7),
        )
        assert r.final_output is not None