"""Planner models — re-exports from v4 skill_layer (merged to v6)."""
try:
    from core.agent.v4.skill_layer.models import (
        ActionNode, CapabilityBlueprint, SkillBelief, SkillCandidate, Skill
    )
except ImportError:
    from dataclasses import dataclass
    @dataclass
    class ActionNode: action_id: str = ""; action: str = ""
    @dataclass
    class CapabilityBlueprint: blueprint_id: str = ""; goal: str = ""
    @dataclass
    class SkillBelief: generality: float = 0.5
    @dataclass
    class SkillCandidate: candidate_id: str = ""; source: str = "internal"
    @dataclass
    class Skill: skill_id: str = ""; status: str = "candidate"

AllocationError = ValueError  # backward compat alias
