"""DocumentObservation: Observation extracted from documents, enters cognitive chain.

This module defines the data model for DocumentObservations and the bundle
that carries them into the ObservationPool.
"""
from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent.v4.observation_compiler.models import (
    ObservationBundle,
    DomainObservation,
    Evidence,
)
from .tree import Relation


@dataclass
class DocumentObservation:
    """Observation extracted from a DocumentNode — enters cognitive chain.

    Fields mirror the design document §4.2 DocumentObservation data model.
    """
    observation_id: str
    source_path: str              # Original document path
    node_id: str                  # DocumentNode ID
    event_id: str                 # Ingestion event ID

    # Cognitive content
    observation_type: str         # "definition" | "constraint" | "procedure" | "example" | "relation" | "parameter"
    raw_text: str                # Raw text fragment
    concepts: List[str] = field(default_factory=list)           # Extracted concepts
    relations: List[Relation] = field(default_factory=list)     # Concept relations
    constraints: List[str] = field(default_factory=list)       # Constraint conditions

    # Metadata
    confidence: float = 0.0
    heading_path: List[str] = field(default_factory=list)
    line_start: int = 0
    line_end: int = 0

    # Cognitive chain state
    hypothesis_ids: List[str] = field(default_factory=list)
    knowledge_id: Optional[str] = None

    def to_evidence(self) -> Evidence:
        """Convert to Evidence for the Observation layer."""
        return Evidence(
            evidence_id=self.observation_id,
            source=f"document:{self.source_path}",
            reliability=self.confidence,
            weight=1.0,
            description=self.raw_text,
            timestamp=time.time(),
            domain="document",
            event_id=self.event_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "observation_id": self.observation_id,
            "source_path": self.source_path,
            "node_id": self.node_id,
            "event_id": self.event_id,
            "observation_type": self.observation_type,
            "raw_text": self.raw_text,
            "concepts": self.concepts,
            "relations": [
                {"source": r.source, "target": r.target, "relation_type": r.relation_type}
                for r in self.relations
            ],
            "constraints": self.constraints,
            "confidence": self.confidence,
            "heading_path": self.heading_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "hypothesis_ids": self.hypothesis_ids,
            "knowledge_id": self.knowledge_id,
        }


@dataclass
class DocumentObservationBundle:
    """Bundle of DocumentObservations ready for ObservationPool.put().

    Wraps into a standard ObservationBundle so the existing cognitive chain
    does not need to know about documents.
    """
    bundle_id: str
    event_id: str
    source_path: str
    observations: List[DocumentObservation] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_observation_bundle(self) -> ObservationBundle:
        """Convert to the standard ObservationBundle accepted by ObservationPool.

        Strategy: each DocumentObservation becomes a DomainObservation
        under the "document" domain.  The bundle carries all observations
        as a single event.
        """
        domain_obs: Dict[str, DomainObservation] = {}
        interpretations: List[Dict[str, Any]] = []
        evidence_sources: List[str] = []

        for obs in self.observations:
            evidence = obs.to_evidence()
            evidence_sources.append(evidence.evidence_id)
            interpretations.append({
                "interpretation_id": obs.observation_id,
                "summary": obs.raw_text[:200],
                "hypothesis": f"document_{obs.observation_type}",
                "evidence_refs": [evidence.evidence_id],
                "concepts": obs.concepts,
                "heading_path": obs.heading_path,   # for SemanticPath building
                "relations": [
                    {"source": r.source, "target": r.target, "type": r.relation_type}
                    for r in obs.relations
                ],
            })

        domain_obs["document"] = DomainObservation(
            domain="document",
            observation_id=self.bundle_id,
            event_id=self.event_id,
            summary=f"Document ingestion from {self.source_path}",
            actions=[],
            objects=[obs.observation_type for obs in self.observations],
            relations=[
                {"source": r.source, "target": r.target, "type": r.relation_type}
                for obs in self.observations for r in obs.relations
            ],
            interpretations=interpretations,
            evidence_sources=evidence_sources,
            status="complete",
            meta={
                "source_path": self.source_path,
                "observation_count": len(self.observations),
                "observation_types": list({obs.observation_type for obs in self.observations}),
            },
        )

        return ObservationBundle(
            bundle_id=self.bundle_id,
            event_id=self.event_id,
            created_at=self.created_at,
            domain_observations=domain_obs,
            status="complete",
        )

    @classmethod
    def from_observations(
        cls,
        source_path: str,
        observations: List[DocumentObservation],
        event_id: str = "",
    ) -> "DocumentObservationBundle":
        """Factory: create bundle from a list of DocumentObservations."""
        return cls(
            bundle_id=f"doc_bundle_{uuid.uuid4().hex[:12]}",
            event_id=event_id or f"ingest_{uuid.uuid4().hex[:8]}",
            source_path=source_path,
            observations=observations,
        )
