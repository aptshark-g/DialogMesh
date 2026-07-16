"""Observation Compiler models: Schema definitions for v4 cognitive pipeline.

Design principle: Observation layer collects EVIDENCE, not CONFIDENCE.
Confidence competition happens at Hypothesis Engine level via BeliefState.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════
# Core Observation Schemas
# ═══════════════════════════════════════════════════════════════

@dataclass
class ObservationBundle:
    """1:1 with Event. Contains per-domain DomainObservations."""
    bundle_id: str
    event_id: str
    created_at: float = field(default_factory=time.time)
    domain_observations: dict[str, "DomainObservation"] = field(default_factory=dict)
    status: str = "partial"  # partial | complete | stale


    @classmethod
    def from_dict(cls, d: dict) -> "ObservationBundle":
        """Deserialize from dict."""
        return cls(
            bundle_id=d.get("bundle_id", d.get("id", "")),
            domain=d.get("domain", ""),
            summary=d.get("summary", ""),
            interpretations=d.get("interpretations", []),
            evidence=d.get("evidence", []),
            timestamp=d.get("timestamp", 0.0),
        )


@dataclass
class DomainObservation:
    """Per-domain observation. Does NOT contain confidence."""
    domain: str = ""
    observation_id: str = ""
    event_id: str = ""
    summary: str = ""
    actions: list[str] = field(default_factory=list)
    objects: list[str] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    interpretations: list["Interpretation"] = field(default_factory=list)
    evidence_sources: list[str] = field(default_factory=list)  # Evidence.evidence_id
    status: str = "partial"
    meta: dict = field(default_factory=dict)


@dataclass
class Interpretation:
    """Per-domain candidate interpretation. Carries evidence references, not confidence."""
    interpretation_id: str
    domain_observation_id: str
    summary: str = ""
    hypothesis: str = ""
    evidence_refs: list[str] = field(default_factory=list)  # Evidence.evidence_id
    competing_with: list[str] = field(default_factory=list)  # interpretation_id
    status: str = "active"  # active | confirmed | dismissed | stale
    version: int = 1


# ═══════════════════════════════════════════════════════════════
# Evidence & Belief
# ═══════════════════════════════════════════════════════════════

@dataclass
class Evidence:
    """First-class citizen in Observation layer. Source reliability is static."""
    evidence_id: str
    source: str  # dialog.message | ui.click | rule_match | llm_extract | ...
    reliability: float  # From ParameterRegistry, immutable in this layer
    weight: float = 1.0
    description: str = ""
    timestamp: float = field(default_factory=time.time)
    domain: str = ""
    event_id: str = ""


@dataclass
class BeliefState:
    """Multi-dimensional belief state. Managed by Hypothesis Engine, not Observation layer."""
    interpretation_id: str
    support: int = 0
    conflict: int = 0
    novelty: float = 1.0
    stability: float = 1.0
    coverage: float = 0.0
    recency: float = 0.0
    entropy: float = 0.0
    last_update: float = 0.0
    version: int = 0


# ═══════════════════════════════════════════════════════════════
# Event
# ═══════════════════════════════════════════════════════════════

@dataclass
class ObservationEvent:
    """Fired when an observation state changes. Downstream modules subscribe to this."""
    kind: str  # domain_observation_created | interpretation_added | bundle_complete
    bundle_id: str
    domain: str | None = None
    observation_id: str | None = None
    interpretation_id: str | None = None
    timestamp: float = field(default_factory=time.time)
