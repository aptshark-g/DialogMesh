"""Tests for Observation Compiler models."""
import pytest
from core.agent.v4.observation_compiler.models import (
    ObservationBundle, DomainObservation, Interpretation,
    Evidence, BeliefState, ObservationEvent,
)


class TestObservationBundle:
    def test_creation(self):
        b = ObservationBundle(bundle_id="b1", event_id="e1")
        assert b.bundle_id == "b1"
        assert b.event_id == "e1"
        assert b.status == "partial"
        assert b.domain_observations == {}

    def test_add_domain_observation(self):
        b = ObservationBundle(bundle_id="b1", event_id="e1")
        do = DomainObservation(domain="engineering", observation_id="o1", event_id="e1")
        b.domain_observations["engineering"] = do
        assert "engineering" in b.domain_observations


class TestDomainObservation:
    def test_creation(self):
        do = DomainObservation(domain="engineering", observation_id="o1", event_id="e1")
        assert do.domain == "engineering"
        assert do.evidence_sources == []
        assert do.interpretations == []

    def test_no_confidence_field(self):
        do = DomainObservation(domain="behavior", observation_id="o2", event_id="e2")
        assert not hasattr(do, "confidence")


class TestInterpretation:
    def test_creation(self):
        i = Interpretation(interpretation_id="i1", domain_observation_id="o1")
        assert i.interpretation_id == "i1"
        assert i.evidence_refs == []
        assert i.status == "active"

    def test_no_confidence_field(self):
        i = Interpretation(interpretation_id="i2", domain_observation_id="o2")
        assert not hasattr(i, "confidence")


class TestEvidence:
    def test_creation(self):
        e = Evidence(evidence_id="ev1", source="dialog.message", reliability=0.98)
        assert e.source == "dialog.message"
        assert e.reliability == 0.98
        assert e.weight == 1.0

    def test_default_values(self):
        e = Evidence(evidence_id="ev2", source="ui.click", reliability=0.95)
        assert e.description == ""
        assert e.domain == ""


class TestBeliefState:
    def test_creation(self):
        bs = BeliefState(interpretation_id="i1")
        assert bs.support == 0
        assert bs.stability == 1.0
        assert bs.coverage == 0.0

    def test_update_support(self):
        bs = BeliefState(interpretation_id="i1", support=5, conflict=2)
        assert bs.support == 5
        assert bs.conflict == 2


class TestObservationEvent:
    def test_creation(self):
        oe = ObservationEvent(kind="bundle_complete", bundle_id="b1")
        assert oe.kind == "bundle_complete"
        assert oe.bundle_id == "b1"
