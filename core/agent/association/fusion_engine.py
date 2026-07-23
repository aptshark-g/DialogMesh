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

    async def fuse(self, track0=None, track1=None, track_p=None, causal=None, strategic=None, profile_lite=False, metacog_result=None):
        start = time.monotonic()
        all_conflicts = []

        # Apply metacognition signals early
        ask_clarify = False
        if metacog_result is not None:
            if metacog_result.action_recommended == "clarify":
                ask_clarify = True
            if metacog_result.action_recommended == "fallback":
                profile_lite = True

        if profile_lite:
            stage1 = await self.stage_mgr.run_stage1(track0, causal)
            dom, cs = self.resolver.resolve(stage1)
            all_conflicts.extend(cs)
            if not dom or not dom.is_confident():
                return FusionResult({}, 0, TrackType.TRACK_0, all_conflicts, [stage1], ask_clarification=True, latency_ms=(time.monotonic()-start)*1000, profile_lite=True)
            out = self.resolver.apply(dom, all_conflicts)
            return FusionResult(out, dom.confidence, dom.track, all_conflicts, [stage1], ask_clarification=True, latency_ms=(time.monotonic()-start)*1000, profile_lite=True)

        stage1 = await self.stage_mgr.run_stage1(track0, causal)
        dom1, c1 = self.resolver.resolve(stage1)
        all_conflicts.extend(c1)

        stage2 = await self.stage_mgr.run_stage2(stage1, track_p)
        if stage2 and stage2.is_final:
            return self._finalize(stage2, all_conflicts, start, metacog_result=metacog_result)
        dom2, c2 = self.resolver.resolve(stage2)
        all_conflicts.extend(c2)

        stage3 = await self.stage_mgr.run_stage3(stage2, track1)
        # Stage4: STRATEGIC planning (slow-one-frame, from background orchestration)
        stage4 = await self.stage_mgr.run_stage_strategic(stage3, strategic)
        # Use stage4 result if stage4 ran, otherwise use original stage3
        final_stage = stage4 if (strategic and strategic.is_confident() and stage4) else stage3
        if final_stage and final_stage.is_final:
            dom3, c3 = self.resolver.resolve(final_stage)
            all_conflicts.extend(c3)
            all_tracks = final_stage.tracks
            # Apply confidence adjustment from metacognition
            if metacog_result is not None and metacog_result.confidence_adjustment != 0.0:
                for t in all_tracks:
                    if hasattr(t, "confidence"):
                        t.confidence = max(0.0, min(1.0, t.confidence + metacog_result.confidence_adjustment))
            gs_dom = self.workspace.select_dominant(all_tracks) or dom3
            out = self.resolver.apply(gs_dom, all_conflicts)
            low = all(t.confidence < 0.5 for t in final_stage.tracks)
            # Wire ask_clarification from metacognition if set
            if ask_clarify:
                low = True
            return FusionResult(out, gs_dom.confidence if gs_dom else 0, gs_dom.track if gs_dom else TrackType.TRACK_0, all_conflicts, self.stage_mgr.stages, ask_clarification=low, latency_ms=(time.monotonic()-start)*1000)

        return FusionResult({}, 0, TrackType.TRACK_0, all_conflicts, [], ask_clarification=True, latency_ms=(time.monotonic()-start)*1000)

    def _finalize(self, stage, conflicts, start, metacog_result=None):
        dom, _ = self.resolver.resolve(stage)
        if not dom:
            return FusionResult({}, 0, TrackType.TRACK_0, conflicts, [], ask_clarification=True, latency_ms=(time.monotonic()-start)*1000)
        # Apply confidence adjustment
        if metacog_result is not None and metacog_result.confidence_adjustment != 0.0:
            if hasattr(dom, "confidence"):
                dom.confidence = max(0.0, min(1.0, dom.confidence + metacog_result.confidence_adjustment))
        out = self.resolver.apply(dom, conflicts)
        ask = False
        if metacog_result is not None and metacog_result.action_recommended == "clarify":
            ask = True
        return FusionResult(out, dom.confidence, dom.track, conflicts, [], ask_clarification=ask, latency_ms=(time.monotonic()-start)*1000)
