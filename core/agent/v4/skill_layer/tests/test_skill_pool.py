"""Tests for SkillPool."""
import pytest
from core.agent.v4.skill_layer.models import CapabilityBlueprint, SkillCandidate, SkillBelief
from core.agent.v4.skill_layer.skill_pool import SkillPool

class TestSkillPool:
    def test_add_and_get(self):
        pool = SkillPool()
        bp = CapabilityBlueprint(blueprint_id="bp1", goal="Gateway")
        pool.add_candidate(SkillCandidate(candidate_id="c1", blueprint=bp, belief=SkillBelief()))
        assert pool.get("c1").status == "candidate"

    def test_promote(self):
        pool = SkillPool()
        pool.add_candidate(SkillCandidate(candidate_id="c2", blueprint=CapabilityBlueprint(blueprint_id="b", goal="G")))
        assert pool.promote("c2") == "verified"
        assert pool.promote("c2") == "core"

    def test_get_ready(self):
        pool = SkillPool()
        pool.add_candidate(SkillCandidate(candidate_id="c3", blueprint=CapabilityBlueprint(blueprint_id="b3", goal="R", domain="eng")))
        pool.promote("c3")
        assert len(pool.get_ready("eng")) == 1

    def test_deprecate(self):
        pool = SkillPool()
        pool.add_candidate(SkillCandidate(candidate_id="c4", blueprint=CapabilityBlueprint(blueprint_id="b4", goal="Old")))
        pool.deprecate("c4")
        assert pool.get("c4").status == "deprecated"

    def test_stats(self):
        pool = SkillPool()
        pool.add_candidate(SkillCandidate(candidate_id="s1", blueprint=CapabilityBlueprint(blueprint_id="b1", goal="G1")))
        s = pool.stats()
        assert s["total"] == 1
