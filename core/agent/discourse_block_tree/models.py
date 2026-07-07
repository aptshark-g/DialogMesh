"""Discourse Block Tree ? ????"""
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EDU:
    """Elementary Discourse Unit ? ??????"""
    index: int
    raw_text: str
    subject: str = ""
    predicate: str = ""
    obj: str = ""
    negation: bool = False
    imperative: bool = False
    uncertainty: bool = False
    question: bool = False
    attrs: dict = field(default_factory=dict)
    entities: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"index": self.index, "text": self.raw_text,
                "subject": self.subject, "predicate": self.predicate,
                "object": self.obj, "negation": self.negation,
                "imperative": self.imperative, "question": self.question,
                "entities": self.entities}


@dataclass
class CohesionScore:
    """???? EDU ????????"""
    left_index: int
    right_index: int
    macro_score: float = 0.5
    micro_score: float = 0.5
    total_score: float = 0.5
    decision: str = "gray_zone"

    def __post_init__(self):
        self.total_score = 0.6 * self.macro_score + 0.4 * self.micro_score
        if self.total_score > 0.75:
            self.decision = "continue"
        elif self.total_score < 0.25:
            self.decision = "fork"
        else:
            self.decision = "gray_zone"


@dataclass
class DiscourseEntity:
    """?????????"""
    text: str
    etype: str = ""
    confidence: float = 0.5
    source: str = "rule"
    block_id: Optional[str] = None


@dataclass
class ProgressiveSummary:
    """???????"""
    v1_raw: str = ""
    v2_entity: str = ""
    v3_evolution: str = ""
    v4_compressed: str = ""
    version: int = 1
    last_updated_turn: int = 0

    def get_best(self) -> str:
        if self.version >= 4 and self.v4_compressed:
            return self.v4_compressed
        if self.version >= 3 and self.v3_evolution:
            return self.v3_evolution
        if self.version >= 2 and self.v2_entity:
            return self.v2_entity
        return self.v1_raw[:120]

    def upgrade_v2(self, entities, primary_intent):
        ents = ", ".join(e.text for e in entities[:5])
        self.v2_entity = f"[{primary_intent}] {ents}"
        self.version = 2

    def upgrade_v3(self, milestones):
        self.v3_evolution = "????: " + " -> ".join(milestones[:3])
        self.version = 3

    def upgrade_v4(self, compressed):
        self.v4_compressed = compressed[:100]
        self.version = 4

    def to_dict(self) -> dict:
        return {"version": self.version, "v1": self.v1_raw[:80],
                "v2": self.v2_entity, "v3": self.v3_evolution,
                "v4": self.v4_compressed}


@dataclass
class DiscourseBlock:
    """DiscourseBlock ? ????????????????"""
    block_id: str
    name: str
    atomic_units: list = field(default_factory=list)
    parent_id: Optional[str] = None
    child_ids: list = field(default_factory=list)
    macro_embedding: list = field(default_factory=list)
    primary_intent: str = "unknown"
    secondary_intents: list = field(default_factory=list)
    entities: list = field(default_factory=list)
    cohesion_internal: float = 0.0
    cohesion_boundary: float = 0.0
    summary: ProgressiveSummary = field(default_factory=ProgressiveSummary)
    status: str = "active"
    capacity: int = 8
    depth: int = 0
    created_at_turn: int = 0
    last_active_turn: int = 0
    response_count: int = 0
    topic_switch: bool = False
    topic_switch_confidence: float = 0.0
    cross_refs: list = field(default_factory=list)  # list[CrossReference]

    def add_edu(self, edu: EDU):
        self.atomic_units.append(edu)
        self.last_active_turn = edu.index

    def to_dict(self) -> dict:
        return {"block_id": self.block_id, "name": self.name,
                "parent_id": self.parent_id, "depth": self.depth,
                "status": self.status, "primary_intent": self.primary_intent,
                "summary_version": self.summary.version,
                "edu_count": len(self.atomic_units),
                "created_at_turn": self.created_at_turn,
                "cross_refs": [{"target": r.target_block_id, "type": r.ref_type,
                                "strength": r.strength, "source": r.source}
                               for r in getattr(self, "cross_refs", [])]}
@dataclass
class CrossReference:
    """Cross-topic reference between two DiscourseBlocks"""
    target_block_id: str
    ref_type: str = "see_also"   # "analogy", "continuation", "correction", "see_also", "behavior_similar"
    strength: float = 0.5
    created_at_turn: int = 0
    source: str = "manual"       # "manual", "auto_entity", "auto_graph"
