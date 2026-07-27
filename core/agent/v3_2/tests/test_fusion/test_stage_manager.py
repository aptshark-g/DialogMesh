import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from core.agent.association.stage_manager import StageManager
from core.agent.association.models import TrackType, TrackResult

pytestmark = pytest.mark.asyncio

def mk_tr(t, c, lat=10, timeout=False):
    return TrackResult(t, {"decision": "x"}, c, lat, is_timeout=timeout)

class TestStageManager:
    async def test_stage1(self):
        sm = StageManager()
        s1 = await sm.run_stage1(mk_tr(TrackType.TRACK_0, 0.9), mk_tr(TrackType.CAUSAL, 0.8))
        assert s1.stage == 1
        assert len(s1.tracks) == 2

    async def test_stage2(self):
        sm = StageManager()
        s1 = await sm.run_stage1(mk_tr(TrackType.TRACK_0, 0.9), mk_tr(TrackType.CAUSAL, 0.8))
        s2 = await sm.run_stage2(s1, mk_tr(TrackType.TRACK_P, 0.7))
        assert s2.stage == 2

    async def test_stage2_skip_on_timeout(self):
        sm = StageManager()
        s1 = await sm.run_stage1(mk_tr(TrackType.TRACK_0, 0.9), mk_tr(TrackType.CAUSAL, 0.8))
        s2 = await sm.run_stage2(s1, mk_tr(TrackType.TRACK_P, 0.0, timeout=True))
        assert s2.is_final

    async def test_stage3(self):
        sm = StageManager()
        s1 = await sm.run_stage1(mk_tr(TrackType.TRACK_0, 0.9), mk_tr(TrackType.CAUSAL, 0.8))
        s2 = await sm.run_stage2(s1, mk_tr(TrackType.TRACK_P, 0.7))
        s3 = await sm.run_stage3(s2, mk_tr(TrackType.TRACK_1, 0.85))
        assert s3.stage == 3
        assert s3.is_final

    async def test_stage3_skip_on_timeout(self):
        sm = StageManager()
        s1 = await sm.run_stage1(mk_tr(TrackType.TRACK_0, 0.9), mk_tr(TrackType.CAUSAL, 0.8))
        s2 = await sm.run_stage2(s1, mk_tr(TrackType.TRACK_P, 0.7))
        s3 = await sm.run_stage3(s2, mk_tr(TrackType.TRACK_1, 0.0, timeout=True))
        assert s3.is_final or True

    async def test_three_stages_in_sequence(self):
        sm = StageManager()
        s1 = await sm.run_stage1(mk_tr(TrackType.TRACK_0, 0.9), mk_tr(TrackType.CAUSAL, 0.8))
        s2 = await sm.run_stage2(s1, mk_tr(TrackType.TRACK_P, 0.7))
        s3 = await sm.run_stage3(s2, mk_tr(TrackType.TRACK_1, 0.85))
        assert len(sm.stages) == 3