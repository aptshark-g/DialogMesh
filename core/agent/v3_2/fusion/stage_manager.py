import time, asyncio
from .models import StageOutput, TrackResult, TrackType

class StageManager:
    STAGE1_TIMEOUT = 0.010
    STAGE2_TIMEOUT = 0.080
    STAGE3_TIMEOUT = 0.150
    STAGE4_STRATEGIC_TIMEOUT = 0.200

    def __init__(self):
        self.stages = []

    async def run_stage1(self, track0, causal):
        start = time.monotonic()
        tracks = [t for t in [track0, causal] if t and not t.is_timeout]
        merged = {}
        for t in sorted(tracks, key=lambda x: -x.priority_level):
            if t.is_confident():
                merged.update(t.output)
        out = StageOutput(1, tracks, merged)
        out.latency_ms = (time.monotonic() - start) * 1000
        self.stages.append(out)
        return out

    async def run_stage2(self, stage1, track_p):
        if not stage1 or not track_p or track_p.is_timeout:
            if stage1: stage1.is_final = True
            return stage1
        merged = dict(stage1.merged)
        merged["predicted_actions"] = track_p.output.get("predicted_actions", [])
        out = StageOutput(2, stage1.tracks + [track_p], merged)
        self.stages.append(out)
        return out

    async def run_stage3(self, stage2, track1):
        if not stage2 or not track1 or track1.is_timeout:
            if stage2: stage2.is_final = True
            return stage2
        merged = dict(stage2.merged)
        merged["intent"] = track1.output.get("intent", {})
        merged["semantics"] = track1.output.get("semantics", {})
        out = StageOutput(3, stage2.tracks + [track1], merged, is_final=True)
        self.stages.append(out)
        return out
    async def run_stage_strategic(self, stage3, strategic):
        """Stage4: integrate STRATEGIC planning from background orchestration."""
        if not stage3 or not strategic or strategic.is_timeout:
            if stage3:
                stage3.is_final = True
            return stage3
        if not strategic.is_confident():
            stage3.is_final = True
            return stage3
        merged = dict(stage3.merged)
        merged["strategic"] = strategic.output
        out = StageOutput(4, stage3.tracks + [strategic], merged, is_final=True)
        self.stages.append(out)
        return out
