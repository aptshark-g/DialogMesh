"""Tests for ExternalSkillAdapter."""
import pytest
from core.agent.v4.skill_layer.external_adapter import ExternalSkillAdapter
from core.agent.v4.skill_layer.models import SkillCandidate

class TestExternalAdapter:
    def test_harness_basic(self):
        adapter = ExternalSkillAdapter()
        data = {"name": "Gateway Init", "steps": ["create_module", "register", "test"],
                "constraints": ["metrics_required"], "domain": "engineering"}
        c = adapter.import_skill("harness", data)
        assert c is not None
        assert c.source == "external"
        assert c.blueprint.goal == "Gateway Init"
        assert len(c.blueprint.action_graph) == 3

    def test_json_basic(self):
        adapter = ExternalSkillAdapter()
        data = {"goal": "Deploy", "steps": ["build", "push", "deploy"]}
        c = adapter.import_skill("json", data)
        assert c is not None
        assert c.source == "external"
        assert len(c.blueprint.action_graph) == 3

    def test_openapi(self):
        adapter = ExternalSkillAdapter()
        data = {"info": {"title": "MyAPI"}, "paths": {"/health": {"get": {}}}}
        c = adapter.import_skill("openapi", data)
        assert c is not None
        assert c.source == "external"

    def test_batch(self):
        adapter = ExternalSkillAdapter()
        items = [
            {"goal": "S1", "steps": ["a", "b"]},
            {"goal": "S2", "steps": ["c"]},
        ]
        candidates = adapter.import_batch("json", items)
        assert len(candidates) == 2

    def test_unknown_source_fallback(self):
        adapter = ExternalSkillAdapter()
        c = adapter.import_skill("unknown", {"goal": "test", "steps": []})
        assert c is not None
