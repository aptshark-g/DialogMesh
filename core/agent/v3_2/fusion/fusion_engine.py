import time
from .models import FusionResult, TrackType, TrackResult
from .stage_manager import StageManager
from .conflict_resolver import ConflictResolver
from .global_workspace import GlobalWorkspace

class FusionEngine:
    def __init__(self, stage_mgr=None, resolver=None, workspace=None):
        self.stage_mgr = stage_mgr or StageManager()
        self.resolver = resolver or ConflictResolver()
        self.workspace = workspace or GlobalWorkspace()

    async def fuse(self, track0=None, track1=None, track_p=None, causal=None, profile_lite=False):
        start = time.monotonic()
        all_conflicts = []

        if profile_lite:
            stage1 = await self.stage_mgr.run_stage1(track0, causal)
            dom, cs = self.resolver.resolve(stage1)
            all_conflicts.extend(cs)
            if not dom or not dom.is_confident():
                return FusionResult({}, 0, TrackType.TRACK_0, all_conflicts, [stage1], ask_clarification=True, latency_ms=(time.monotonic()-start)*1000, profile_lite=True)
            out = self.resolver.apply(dom, all_conflicts)
            return FusionResult(out, dom.confidence, dom.track, all_conflicts, [stage1], latency_ms=(time.monotonic()-start)*1000, profile_lite=True)

        stage1 = await self.stage_mgr.run_stage1(track0, causal)
        dom1, c1 = self.resolver.resolve(stage1)
        all_conflicts.extend(c1)

        stage2 = await self.stage_mgr.run_stage2(stage1, track_p)
        if stage2 and stage2.is_final:
            return self._finalize(stage2, all_conflicts, start)
        dom2, c2 = self.resolver.resolve(stage2)
        all_conflicts.extend(c2)

        stage3 = await self.stage_mgr.run_stage3(stage2, track1)
        if stage3 and stage3.is_final:
            dom3, c3 = self.resolver.resolve(stage3)
            all_conflicts.extend(c3)
            all_tracks = stage3.tracks
            gs_dom = self.workspace.select_dominant(all_tracks) or dom3
            out = self.resolver.apply(gs_dom, all_conflicts)
            low = all(t.confidence < 0.5 for t in stage3.tracks)
            return FusionResult(out, gs_dom.confidence if gs_dom else 0, gs_dom.track if gs_dom else TrackType.TRACK_0, all_conflicts, self.stage_mgr.stages, ask_clarification=low, latency_ms=(time.monotonic()-start)*1000)

        return FusionResult({}, 0, TrackType.TRACK_0, all_conflicts, [], ask_clarification=True, latency_ms=(time.monotonic()-start)*1000)

    def _finalize(self, stage, conflicts, start):
        dom, _ = self.resolver.resolve(stage)
        if not dom: return FusionResult({}, 0, TrackType.TRACK_0, conflicts, [], ask_clarification=True, latency_ms=(time.monotonic()-start)*1000)
        out = self.resolver.apply(dom, conflicts)
        return FusionResult(out, dom.confidence, dom.track, conflicts, [], latency_ms=(time.monotonic()-start)*1000)