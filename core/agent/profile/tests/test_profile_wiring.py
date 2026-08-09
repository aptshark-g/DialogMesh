# -*- coding: utf-8 -*-
"""画像批次 P2-P12 接线测试 — 2026-08-04.

覆盖:
  P2  _feed_profile_runtime（Track A + Track B 复活）
  P4  _l3_profile_traits（OCEAN → L3 profile 视角）
  P5  cognitive_state / discourse manager cognitive_hints
  P6  _update_profile_from_pcr + _profile_prior_text（双向先验）
  P7  _feed_inertia_evidence（inertia_graph 喂数据）
  P8  ProfileContextSource（P 域统一画像源注册）
  P10 g 因子领域化
  P11 OCEANProfileAnalyst 门面方法（CLI 死命令修复）
  H2  FactStore WRITE_GUIDANCE
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest


@pytest.fixture
def engine():
    from core.agent.runtime.engine import CognitiveRuntimeEngine
    return CognitiveRuntimeEngine()


# ── P2: _feed_profile_runtime 复活 Track A + Track B ────────────────────

class TestP2FeedProfileRuntime:
    def test_feed_updates_track_a_and_track_b(self, engine):
        engine._turn_counter = 5
        engine._feed_profile_runtime("帮我详细分析这个架构", "已给出 5 点分析")
        assert engine._cognitive_profile is not None
        a = engine._cognitive_profile.track_a
        assert a.observation_count > 0
        assert engine._convergence_engine is not None

    def test_feed_is_never_fatal(self, engine):
        engine._cognitive_profile = None
        engine._convergence_engine = None
        engine._feed_profile_runtime("x", "y")  # 不应抛异常


# ── P4: L3 profile 视角 ────────────────────────────────────────────────

class TestP4L3ProfileTraits:
    def test_maps_ocean_dims_to_traits(self, engine):
        from core.agent.v4.cognitive.ocean_profile import OCEANProfile
        analyst = SimpleNamespace(profile=OCEANProfile())
        analyst.profile.dims["C"] = 0.8
        analyst.profile.dims["O"] = 0.7
        engine._ocean_analyst = analyst
        traits = engine._l3_profile_traits()
        assert traits["conscientiousness"] == 0.8
        assert traits["openness"] == 0.7

    def test_abstains_honestly_without_analyst(self, engine):
        assert engine._l3_profile_traits() == {}


# ── P5: cognitive_state + discourse hints ──────────────────────────────

class TestP5CognitiveState:
    def test_accessor_returns_track_a_snapshot(self, engine):
        engine._feed_profile_runtime("text", "response")
        state = engine.cognitive_state()
        assert state["available"] is True
        assert "cognitive_resource" in state
        assert "attention_anchor" in state

    def test_manager_accepts_cognitive_hints(self):
        from core.agent.discourse_block_tree.manager import DiscourseBlockTreeManager
        m = DiscourseBlockTreeManager()
        hints = {"cognitive_resource": 0.3, "attention_anchor": 0.2}
        m.feed("第一句", "s1", cognitive_hints=hints)
        stats = m.get_stats("s1")
        assert stats["cognitive_hints"]["cognitive_resource"] == 0.3
        m.ingest_turn(2, "第二句", cognitive_hints=hints)
        assert m._last_cognitive_hints == hints


# ── P6: PCR ↔ Track A 双向先验 ─────────────────────────────────────────

class TestP6Bidirectional:
    def test_pcr_feeds_track_a(self, engine):
        engine._feed_profile_runtime("text", "response")
        before = engine._convergence_engine._dyn.cognitive_resource
        pcr = SimpleNamespace(zone="PRECISION", cognitive_level="expert",
                              x_axis=0.2, y_axis=0.8, z_axis=0.1)
        engine._update_profile_from_pcr(pcr)
        after = engine._convergence_engine._dyn.cognitive_resource
        assert 0.0 <= after <= 1.0
        # PRECISION → 认知资源消耗更高（观察值 0.35），EMA 后应低于原值
        assert after < before + 1e-9

    def test_profile_prior_text_from_ocean(self, engine):
        from core.agent.v4.cognitive.ocean_profile import OCEANProfile
        analyst = SimpleNamespace(profile=OCEANProfile())
        analyst.profile.dims["C"] = 0.9
        analyst.profile.dims["DK"] = 0.8
        engine._ocean_analyst = analyst
        prior = engine._profile_prior_text()
        assert prior is not None
        assert "structured" in prior

    def test_no_prior_without_profile(self, engine):
        assert engine._profile_prior_text() is None


# ── P7: inertia_graph 喂数据 ───────────────────────────────────────────

class TestP7InertiaFeed:
    def test_feeds_multi_perspective_evidence(self, engine):
        from core.agent.v4.cognitive.inertia_graph import InertiaWeightGraph
        ig = InertiaWeightGraph(persist_path="")
        engine._inertia_graph = ig
        phase_results = {
            "behavior": {"recorded": True, "edge_count": 4},
            "meta": {"reviewed": True},
            "profile": {"dims_updated": True},
            "association": {"pronouns_resolved": True},
        }
        engine._feed_inertia_evidence(phase_results)
        p = ig._patterns.get("quality_centric")
        assert p is not None
        assert p.state in ("candidate", "confirmed")
        assert "behavior" in p.evidence and "meta" in p.evidence

    def test_empty_results_noop(self, engine):
        from core.agent.v4.cognitive.inertia_graph import InertiaWeightGraph
        engine._inertia_graph = InertiaWeightGraph(persist_path="")
        engine._feed_inertia_evidence({})
        assert not engine._inertia_graph._patterns


# ── P8: ProfileContextSource P 域注册 ──────────────────────────────────

class TestP8ProfileSource:
    def test_profile_source_bound_in_init(self, engine):
        engine._init_profile_runtime()
        assert engine._profile_source is not None
        items = engine._profile_source.retrieve("query")
        assert isinstance(items, list)

    def test_profile_source_render_v2(self):
        from core.agent.v4.cognitive.models import CognitiveProfileV2
        from core.agent.compiler.profile_source import ProfileContextSource
        ps = ProfileContextSource(profile=CognitiveProfileV2())
        items = ps.retrieve("query")
        assert len(items) == 1
        assert items[0].source == "profile"


# ── P10: g 因子领域化 ──────────────────────────────────────────────────

class TestP10GFactorDomain:
    def test_domain_specific_key(self):
        from core.agent.v4.cognitive.tag_layer import TagAcquisitionEngine
        gf = TagAcquisitionEngine()
        result = gf.assess_from_history(["对话"])
        tag = gf.build_tag(result, domain="coding")
        assert tag.name == "g_factor:coding"
        tag_general = gf.build_tag(result, domain="general")
        assert tag_general.name == "g_factor"


# ── P11: OCEAN analyst 门面（CLI 死命令修复）──────────────────────────

class TestP11AnalystFacade:
    def _analyst(self):
        from core.agent.v4.cognitive.ocean_profile import OCEANProfileAnalyst
        return OCEANProfileAnalyst(llm_provider=None)

    def test_update_dimension(self):
        a = self._analyst()
        r = a.update_dimension("C", 0.9)
        assert r["status"] == "updated"
        assert a.profile.dims["C"] == 0.9
        bad = a.update_dimension("ZZ", 0.5)
        assert "error" in bad

    def test_snapshot(self):
        a = self._analyst()
        a.update_dimension("O", 0.8)
        snap = a.snapshot()
        assert snap["dims"]["O"] == 0.8
        assert snap["mbti"]

    def test_history_and_reset(self):
        a = self._analyst()
        a.profile.update({"O": 0.7, "C": 0.6})
        assert len(a.history()) == 1
        a.reset()
        assert a.profile.dims["O"] == 0.5

    def test_save_and_load_roundtrip(self, tmp_path):
        from core.agent.v4.cognitive.ocean_profile import OCEANProfile
        path = os.path.join(str(tmp_path), "ocean.json")
        p = OCEANProfile()
        p.update({"O": 0.8, "C": 0.6})
        p.save(path)
        loaded = OCEANProfile.load(path)
        # EMA α=0.3: 0.3*0.8 + 0.7*0.5 = 0.59
        assert loaded.dims["O"] == pytest.approx(0.59)
        assert loaded.dims["C"] == pytest.approx(0.53)


# ── H2: FactStore 写入规范 ─────────────────────────────────────────────

class TestH2WriteGuidance:
    def test_guidance_constant_present(self):
        from core.agent.profile.fact_store import WRITE_GUIDANCE
        assert "declarative" in WRITE_GUIDANCE.lower()
        assert "steering" in WRITE_GUIDANCE.lower()
        assert "SKILLS" in WRITE_GUIDANCE
