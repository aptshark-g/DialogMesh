"""Tests for Skill Layer models."""
import pytest
from core.agent.v4.skill_layer.models import ActionNode, CapabilityBlueprint, SkillBelief, SkillCandidate, Skill

class TestActionNode:
    def test_creation(self):
        a = ActionNode(action_id="a1", action="create_module")
        assert a.action == "create_module"

class TestCapabilityBlueprint:
    def test_creation(self):
        cb = CapabilityBlueprint(blueprint_id="bp1", goal="Gateway Init")
        assert cb.goal == "Gateway Init"

class TestSkillBelief:
    def test_defaults(self):
        sb = SkillBelief()
        assert sb.generality == 0.5

class TestSkillCandidate:
    def test_creation(self):
        bp = CapabilityBlueprint(blueprint_id="bp1", goal="test")
        c = SkillCandidate(candidate_id="c1", blueprint=bp)
        assert c.source == "internal"

class TestSkill:
    def test_creation(self):
        bp = CapabilityBlueprint(blueprint_id="bp2", goal="Gateway")
        s = Skill(skill_id="s1", blueprint=bp)
        assert s.status == "candidate"
        assert s.to_dict()["goal"] == "Gateway"
