"""TieredFusionEngine: stage1 (fast) → stage2 (mid) → stage3+4 (slow)."""
from __future__ import annotations
import asyncio
import concurrent.futures
import logging
from typing import Any, Dict, Optional

from core.agent.v4.tiered_pipeline import Tier, TierResult, MultiTierPipeline
from core.agent.v3_2.fusion.fusion_engine import FusionEngine
from core.agent.v3_2.fusion.models import FusionResult, TrackType

logger = logging.getLogger(__name__)


class TieredFusionEngine:
    """Multi-tier fusion with progressive refinement.
    Pipeline:
        Tier 0 (stage1):      track0 + causal          – deterministic,  sub-ms.
        Tier 1 (stage2):      track_p                  – person-track,  ~10 ms.
        Tier 2 (stage3_4):    track1 + strategic       – full analysis, ~100+ ms.
    """

    def __init__(self, fusion_engine=None, registry=None):
        self._engine = fusion_engine or FusionEngine()

        stage1_tier = Tier(
            level=0, name="fusion.stage1", process=self._run_stage1,
            confidence_threshold=0.8, confidence_threshold_param="fusion.stage1_threshold",
            registry=registry, time_budget_ms=20,
        )
        stage2_tier = Tier(
            level=1, name="fusion.stage2", process=self._run_stage2,
            confidence_threshold=0.75, confidence_threshold_param="fusion.stage2_threshold",
            registry=registry, time_budget_ms=50,
        )
        stage3_tier = Tier(
            level=2, name="fusion.stage3_4", process=self._run_stage3_4,
            confidence_threshold=0.7, confidence_threshold_param="fusion.stage3_4_threshold",
            registry=registry, time_budget_ms=200,
        )

        self._pipeline = MultiTierPipeline(
            [stage1_tier, stage2_tier, stage3_tier], name="fusion",
        )

    # ── public API ──────────────────────────────────────────────

    def fuse(self, track0=None, track1=None, track_p=None, causal=None,
             strategic=None, metacog_result=None) -> FusionResult:
        ctx = {
            "track0": track0, "track1": track1, "track_p": track_p,
            "causal": causal, "strategic": strategic,
            "metacog_result": metacog_result,
        }
        result = self._pipeline.execute(ctx)
        val = result.value
        return val if isinstance(val, FusionResult) else FusionResult(
            {}, 0, TrackType.TRACK_0, [], [], ask_clarification=True, latency_ms=0
        )

    def stats(self) -> dict:
        return self._pipeline.stats()

    # ── tier processors ─────────────────────────────────────────

    @staticmethod
    def _run_stage1(ctx: dict, _context: dict) -> FusionResult:
        return _sync_run(_stage1_impl(ctx))

    @staticmethod
    def _run_stage2(ctx: dict, _context: dict) -> FusionResult:
        return _sync_run(_stage2_impl(ctx))

    @staticmethod
    def _run_stage3_4(ctx: dict, _context: dict) -> FusionResult:
        return _sync_run(_stage3_4_impl(ctx))


# ── internal async helpers ─────────────────────────────────────

async def _stage1_impl(ctx: dict) -> FusionResult:
    eng = FusionEngine()
    return await eng.fuse(
        track0=ctx["track0"], causal=ctx["causal"],
        profile_lite=True, metacog_result=ctx.get("metacog_result"),
    )

async def _stage2_impl(ctx: dict) -> FusionResult:
    eng = FusionEngine()
    return await eng.fuse(
        track0=ctx["track0"], track_p=ctx["track_p"],
        causal=ctx["causal"], metacog_result=ctx.get("metacog_result"),
    )

async def _stage3_4_impl(ctx: dict) -> FusionResult:
    eng = FusionEngine()
    return await eng.fuse(
        track0=ctx["track0"], track1=ctx["track1"], track_p=ctx["track_p"],
        causal=ctx["causal"], strategic=ctx["strategic"],
        metacog_result=ctx.get("metacog_result"),
    )

def _sync_run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result(timeout=30)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)
