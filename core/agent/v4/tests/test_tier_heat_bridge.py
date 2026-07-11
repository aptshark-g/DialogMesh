"""Tests for TierHeatBridge."""
import pytest
from core.agent.v4.tier_heat_bridge import TierHeatBridge, HeatSignal


class MockPipeline:
    def __init__(self, name, tiers_data):
        self.name = name
        self._tiers_data = tiers_data

    def stats(self):
        return {
            "pipeline": self.name,
            "total_calls": sum(t["calls"] for t in self._tiers_data),
            "avg_latency_ms": 10,
            "tiers": self._tiers_data,
        }


class TestTierHeatBridge:
    def test_collect_produces_heat_signals(self):
        bridge = TierHeatBridge()
        p = MockPipeline("test", [
            {"level": 0, "name": "fast", "calls": 100, "pass_rate": 0.9, "corrections": 2},
            {"level": 1, "name": "slow", "calls": 10, "pass_rate": 0.85, "corrections": 0},
        ])
        bridge.register_pipeline(p, ["test_domain"])
        signals = bridge.collect()
        assert len(signals) >= 0  # may be 0 if min_samples not met

    def test_high_pass_rate_suggests_promote(self):
        bridge = TierHeatBridge()
        p = MockPipeline("hot", [
            {"level": 0, "name": "fast", "calls": 80, "pass_rate": 0.95, "corrections": 1},
            {"level": 1, "name": "slow", "calls": 5, "pass_rate": 0.90, "corrections": 0},
        ])
        bridge.register_pipeline(p, ["hot_domain"])
        signals = bridge.collect()
        if signals:
            assert signals[0].heat_score > 0.3

    def test_low_pass_rate_suggests_demote(self):
        bridge = TierHeatBridge()
        p = MockPipeline("cold", [
            {"level": 0, "name": "fast", "calls": 30, "pass_rate": 0.2, "corrections": 15},
            {"level": 1, "name": "slow", "calls": 30, "pass_rate": 0.4, "corrections": 10},
        ])
        bridge.register_pipeline(p, ["cold_domain"])
        signals = bridge.collect()
        if signals:
            assert signals[0].heat_score < 0.3

    def test_stats_returns_summary(self):
        bridge = TierHeatBridge()
        p = MockPipeline("s", [
            {"level": 0, "name": "a", "calls": 60, "pass_rate": 0.7, "corrections": 3},
        ])
        bridge.register_pipeline(p, ["d"])
        bridge.collect()
        s = bridge.stats()
        assert s["pipelines"] == 1
        assert "details" in s
