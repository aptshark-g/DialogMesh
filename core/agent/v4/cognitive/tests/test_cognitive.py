"""Unit tests for Cognitive Profile V2 (capacitor memory model)."""
import time, math
from core.agent.v4.cognitive.models import (
    CognitiveProfileV2, CognitiveDynamics, UserTag, MemoryPoint, MemoryChunk,
)
from core.agent.v4.cognitive.convergence import ConvergenceEngine, ProfileStore
from core.agent.v4.cognitive.dynamics import DynamicsComputer


class TestModels:
    def test_user_tag_confidence_update(self):
        tag = UserTag("test", "value")
        tag.update_confidence(0.5, "L1")
        assert tag.confidence > 0.8
        tag.update_confidence(0.5, "L2")
        assert tag.source == "L2"
        assert tag.verification_count == 1

    def test_memory_point_capacitor(self):
        mp = MemoryPoint("p1", time.time(), "test", importance=0.5)
        assert mp.weight > 0
        mp.access()  # activation 1→2
        w2 = mp.weight
        mp.access()  # activation 2→3
        w3 = mp.weight
        assert w3 > w2  # capacitor charges with access

    def test_memory_chunk_capacitor(self):
        mc = MemoryChunk("c1", time.time(), importance=0.5)
        assert mc.activation_count == 0
        assert mc.stage == "cold"
        mc.access()  # 0→1 → warm
        assert mc.stage == "warm"
        mc.access(); mc.access()  # 1→3 → hot
        assert mc.stage == "hot"
        assert mc.weight > 0

    def test_memory_chunk_importance_protection(self):
        """High-importance chunks need 2x activation to degrade."""
        mc_high = MemoryChunk("h", time.time(), importance=0.9, activation_count=1)
        mc_low = MemoryChunk("l", time.time(), importance=0.3, activation_count=1)
        # High importance gets effective count ×2
        assert mc_high.weight > mc_low.weight

    def test_profile_v2_roundtrip(self):
        p = CognitiveProfileV2(user_id="test", session_id="s1")
        p.track_a.cognitive_inertia = 0.7
        p.track_b["lang"] = UserTag("lang", "zh", 0.9, "L1")
        p.memory_points.append(MemoryPoint("m1", time.time(), "event", activation_count=5))
        d = p.to_dict()
        p2 = CognitiveProfileV2.from_dict(d)
        assert p2.user_id == "test"
        assert p2.track_a.cognitive_inertia == 0.7
        assert p2.track_b["lang"].confidence == 0.9
        assert len(p2.memory_points) == 1
        assert p2.memory_points[0].activation_count == 5


class TestConvergence:
    def test_alpha_decay(self):
        dyn = CognitiveDynamics()
        ce = ConvergenceEngine(dyn)
        a1 = ce.alpha(turns=1)
        a10 = ce.alpha(turns=10)
        a50 = ce.alpha(turns=50)
        assert a1 > a10 > a50
        assert a50 >= 0.05

    def test_ema_update(self):
        dyn = CognitiveDynamics()
        ce = ConvergenceEngine(dyn)
        v, diag = ce.update("cognitive_inertia", 0.8)
        assert 0.5 < v < 0.8
        assert not diag["anomaly"]

    def test_anomaly_detection(self):
        dyn = CognitiveDynamics()
        ce = ConvergenceEngine(dyn)
        for _ in range(10):
            ce.update("cognitive_inertia", 0.6)
        v, diag = ce.update("cognitive_inertia", 0.95)
        assert diag["anomaly"]

    def test_freeze(self):
        dyn = CognitiveDynamics()
        dyn.observation_count = 55
        ce = ConvergenceEngine(dyn)
        for _ in range(25):
            ce.update("cognitive_inertia", 0.6 + (0.001 * _))
        assert "cognitive_inertia" in dyn.frozen_dimensions


class TestDynamics:
    def test_cognitive_inertia(self):
        dc = DynamicsComputer()
        val = dc.cognitive_inertia([0.5, 0.6, 0.55, 0.58, 0.52])
        assert 0 < val < 1.0

    def test_trust_score(self):
        dc = DynamicsComputer()
        assert dc.trust_score(8, 10) == 0.8
        assert dc.trust_score(0, 0) == 0.5

    def test_compute_all(self):
        dc = DynamicsComputer()
        obs = {
            "style_scores": [0.5, 0.6, 0.55],
            "accept": 5, "clarify": 3, "dispute": 2,
            "commitments_fulfilled": 8, "total_commitments": 10,
            "recent_polarities": [-0.5, 0.3, 0.1],
            "topic_weights": {"a": 10, "b": 3},
            "satisfaction_deltas": [0.1, -0.2, 0.05],
            "self_affirmation_count": 2, "total_turns": 10,
            "response_speed_sec": 15, "response_length_chars": 300,
            "query_complexity": 0.5,
        }
        result = dc.compute_all(obs)
        assert len(result) == 8
        for k, v in result.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} out of range"
