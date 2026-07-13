"""Hypothesis Engine models: HypothesisNode, KnowledgeNode, VoteRecord, ReasonSession."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class HypothesisNode:
    hypothesis_id: str
    interpretation_ref: str
    domain: str
    statement: str
    objects: list[str] = field(default_factory=list)
    topic: str = ""
    belief_state: dict = field(default_factory=lambda: {
        "support": 0, "conflict": 0, "novelty": 1.0, "stability": 1.0,
        "coverage": 0.0, "recency": 1.0, "entropy": 0.0,
    })
    domain_signals: dict[str, str] = field(default_factory=dict)
    edges: list[HypothesisEdge] = field(default_factory=list)
    status: str = "active"
    merged_into: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_vote_at: float = 0.0

    def belief_score(self, params: dict = None) -> float:
        p = params or {}
        bs = self.belief_state
        sup = bs["support"]; con = bs["conflict"]
        sr = sup / max(1, sup + con)
        return (
            sr * p.get("weight_support", 0.35)
            + bs["stability"] * p.get("weight_stability", 0.25)
            + bs["coverage"] * p.get("weight_coverage", 0.20)
            + bs["recency"] * p.get("weight_recency", 0.10)
            + min(1.0, bs["entropy"]) * p.get("weight_entropy", 0.10)
        )

    def to_dict(self) -> dict:
        """Serialize to dict for persistence."""
        return {
            "hypothesis_id": self.hypothesis_id,
            "interpretation_ref": self.interpretation_ref,
            "domain": self.domain,
            "statement": self.statement,
            "objects": self.objects,
            "topic": self.topic,
            "belief_state": dict(self.belief_state),
            "domain_signals": dict(self.domain_signals),
            "status": self.status,
            "merged_into": self.merged_into,
            "created_at": self.created_at,
            "last_vote_at": self.last_vote_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HypothesisNode":
        """Deserialize from dict."""
        return cls(
            hypothesis_id=d.get("hypothesis_id", ""),
            interpretation_ref=d.get("interpretation_ref", ""),
            domain=d.get("domain", ""),
            statement=d.get("statement", ""),
            objects=d.get("objects", []),
            topic=d.get("topic", ""),
            belief_state=d.get("belief_state", {}),
            domain_signals=d.get("domain_signals", {}),
            status=d.get("status", "active"),
            merged_into=d.get("merged_into"),
            created_at=d.get("created_at", 0.0),
            last_vote_at=d.get("last_vote_at", 0.0),
        )

    def should_freeze(self, params: dict = None) -> bool:
        p = params or {}
        bs = self.belief_state
        return (
            bs["support"] >= p.get("min_support", 8)
            and bs["conflict"] <= p.get("max_conflict", 3)
            and bs["stability"] >= p.get("min_stability", 0.70)
            and bs["coverage"] >= p.get("min_coverage", 0.40)
            and len(self.domain_signals) >= p.get("min_consensus_domains", 2)
        )


@dataclass
class HypothesisEdge:
    type: str
    source_id: str
    target_id: str
    target_type: str = ""
    weight: float = 1.0
    created_at: float = field(default_factory=time.time)


@dataclass
class KnowledgeNode:
    knowledge_id: str
    hypothesis_ref: str
    statement: str
    domain: str
    belief_score: float
    belief_snapshot: dict = field(default_factory=dict)
    frozen_at: float = field(default_factory=time.time)


@dataclass
class VoteRecord:
    evidence_id: str
    hypothesis_id: str
    vote: str
    domain: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class ReasonSession:
    session_id: str
    triggering_event: str
    domain: str = ""
    candidates: list[str] = field(default_factory=list)
    votes: list[VoteRecord] = field(default_factory=list)
    merged: list[dict] = field(default_factory=list)
    winner: Optional[str] = None
    knowledge_ref: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    closed_at: Optional[float] = None
    status: str = "open"
