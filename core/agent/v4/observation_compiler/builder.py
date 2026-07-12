"""Observation Builder: assembles ObservationBundle from normalized events + domain results."""
from __future__ import annotations
import uuid
import time
from typing import Any, Callable, Dict, List

from .models import (
    ObservationBundle, DomainObservation, Interpretation, ObservationEvent,
)


class ObservationBuilder:
    """Assembles DomainObservations into a versioned ObservationBundle."""

    def __init__(self):
        self._subscribers: List[Callable[[ObservationEvent], None]] = []

    def build_bundle(self, normalized: dict, domain_results: Dict[str, "DomainResult"]) -> ObservationBundle:
        """Create initial bundle (partial)."""
        bundle_id = self._new_id("bun")
        bundle = ObservationBundle(
            bundle_id=bundle_id,
            event_id=normalized["event_id"],
            domain_observations={},
            status="partial",
        )
        for domain, result in domain_results.items():
            do = self._build_domain_obs(domain, normalized, result, bundle_id)
            bundle.domain_observations[domain] = do
            self._fire(ObservationEvent(
                kind="domain_observation_created",
                bundle_id=bundle_id,
                domain=domain,
                observation_id=do.observation_id,
            ))
        return bundle

    def add_domain(self, bundle: ObservationBundle, domain: str,
                   result: "DomainResult") -> ObservationBundle:
        """Append a domain observation to an existing bundle (partial update)."""
        do = self._build_domain_obs(domain, result.get("normalized", {}), result, bundle.bundle_id)
        bundle.domain_observations[domain] = do
        bundle.status = "complete" if len(bundle.domain_observations) >= result.get("total_domains", 1) else "partial"
        self._fire(ObservationEvent(
            kind="domain_observation_created",
            bundle_id=bundle.bundle_id,
            domain=domain,
            observation_id=do.observation_id,
        ))
        if bundle.status == "complete":
            self._fire(ObservationEvent(kind="bundle_complete", bundle_id=bundle.bundle_id))
        return bundle

    def subscribe(self, callback: Callable[[ObservationEvent], None]) -> None:
        self._subscribers.append(callback)

    def _build_domain_obs(self, domain: str, normalized: dict,
                          result: "DomainResult", bundle_id: str) -> DomainObservation:
        obs_id = self._new_id("obs")
        evidence_ids = result.get("evidence_ids", [])
        return DomainObservation(
            domain=domain,
            observation_id=obs_id,
            event_id=normalized.get("event_id", ""),
            summary=result.get("summary", ""),
            actions=result.get("actions", []),
            objects=result.get("objects", []),
            relations=result.get("relations", []),
            interpretations=[
                Interpretation(
                    interpretation_id=self._new_id("int"),
                    domain_observation_id=obs_id,
                    summary=i.get("summary", ""),
                    hypothesis=i.get("hypothesis", ""),
                    evidence_refs=i.get("evidence_refs", evidence_ids),
                )
                for i in result.get("interpretations", [])
            ],
            evidence_sources=evidence_ids,
        )

    def _fire(self, event: ObservationEvent) -> None:
        for cb in self._subscribers:
            try:
                cb(event)
            except Exception:
                pass

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"


# DomainResult is a dict with keys: summary, actions, objects, relations,
# interpretations, evidence_ids
DomainResult = Dict[str, Any]
