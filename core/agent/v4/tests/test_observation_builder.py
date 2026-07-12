"""Tests for ObservationBuilder."""
import pytest
from core.agent.v4.observation_compiler.builder import ObservationBuilder


class TestObservationBuilder:
    def test_build_bundle_partial(self):
        builder = ObservationBuilder()
        normalized = {"event_id": "e1", "kind": "dialog.message"}
        domain_results = {
            "dialogue": {
                "summary": "User asked a question",
                "actions": ["query"],
                "objects": ["monitoring"],
                "evidence_ids": ["ev1"],
                "interpretations": [{"summary": "info_request", "hypothesis": "Seeking docs"}],
            }
        }
        bundle = builder.build_bundle(normalized, domain_results)
        assert bundle.event_id == "e1"
        assert bundle.status == "partial"
        assert "dialogue" in bundle.domain_observations

    def test_build_bundle_creates_interpretations(self):
        builder = ObservationBuilder()
        normalized = {"event_id": "e2"}
        domain_results = {
            "engineering": {
                "interpretations": [
                    {"summary": "layout_change", "hypothesis": "Reordering pipeline"}
                ],
                "evidence_ids": ["ev2"],
            }
        }
        bundle = builder.build_bundle(normalized, domain_results)
        do = bundle.domain_observations["engineering"]
        assert len(do.interpretations) == 1
        assert do.interpretations[0].hypothesis == "Reordering pipeline"

    def test_event_fires_on_build(self):
        builder = ObservationBuilder()
        events = []
        builder.subscribe(events.append)
        normalized = {"event_id": "e3"}
        builder.build_bundle(normalized, {"memory": {"evidence_ids": []}})
        assert len(events) == 1
        assert events[0].kind == "domain_observation_created"
