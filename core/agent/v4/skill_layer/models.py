"""Skill Layer models: CapabilityBlueprint, Skill, SkillBelief, SkillCandidate."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ActionNode:
    action_id: str
    action: str
    input_refs: List[str] = field(default_factory=list)
    output_refs: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)


@dataclass
class CapabilityBlueprint:
    blueprint_id: str
    goal: str
    constraints: List[str] = field(default_factory=list)
    strategy_refs: List[str] = field(default_factory=list)
    action_graph: List[ActionNode] = field(default_factory=list)
    verification: List[str] = field(default_factory=list)
    reflection_hooks: List[str] = field(default_factory=list)
    domain: str = "engineering"
    version: int = 1
    created_at: float = field(default_factory=time.time)


@dataclass
class SkillBelief:
    support: int = 0
    generality: float = 0.5
    benefit: float = 0.5
    conflict: int = 0
    stability: float = 1.0
    coverage: float = 0.0
    recency: float = 1.0


@dataclass
class SkillCandidate:
    candidate_id: str
    blueprint: CapabilityBlueprint
    belief: SkillBelief = field(default_factory=SkillBelief)
    source: str = "internal"
    references: List[str] = field(default_factory=list)
    domain: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class Skill:
    skill_id: str
    blueprint: CapabilityBlueprint
    belief: SkillBelief = field(default_factory=SkillBelief)
    status: str = "candidate"
    source: str = "internal"
    references: List[str] = field(default_factory=list)
    merged_from: List[str] = field(default_factory=list)
    domain: str = ""
    executor: str = "default"
    created_at: float = field(default_factory=time.time)
    verified_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "goal": self.blueprint.goal,
            "domain": self.domain,
            "status": self.status,
            "source": self.source,
            "belief": {k: v for k, v in self.belief.__dict__.items()},
            "executor": self.executor,
        }
