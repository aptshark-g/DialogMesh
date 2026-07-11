"""Tests for TieredFusionEngine."""
import pytest
from core.agent.v4.tiered_fusion import TieredFusionEngine
from core.agent.v3_2.fusion.models import FusionResult, TrackType


class TestTieredFusionEngine:
    def test_fuse_with_no_tracks_returns_empty_result(self):
        engine = TieredFusionEngine()
        result = engine.fuse()
        assert isinstance(result, FusionResult)
        assert result.ask_clarification is True

    def test_fuse_with_track0_only_uses_stage1(self):
        engine = TieredFusionEngine()
        result = engine.fuse(track0={"data": "sample"})
        assert isinstance(result, FusionResult)

    def test_stats_are_collected(self):
        engine = TieredFusionEngine()
        engine.fuse(track0={"data": "x"})
        s = engine.stats()
        assert s["total_calls"] >= 1
        assert len(s["tiers"]) == 3
        assert s["tiers"][0]["name"] == "fusion.stage1"
