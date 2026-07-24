"""Tests for Engineering Chain modules."""
import pytest
from core.agent.engineering import (
    ArtifactType, EdgeType, is_a, Artifact,
    ArtifactRegistry, KnowledgeGraph, KnowledgeType, ConstraintEngine,
)

class TestArtifactTypeTree:
    def test_is_a_self(self):
        assert is_a(ArtifactType.PROVIDER, ArtifactType.PROVIDER)
    def test_is_a_parent(self):
        assert is_a(ArtifactType.PROVIDER, ArtifactType.MODULE)
    def test_is_a_ancestor(self):
        assert is_a(ArtifactType.PROVIDER, ArtifactType.ARTIFACT)
    def test_is_a_false(self):
        assert not is_a(ArtifactType.CONFIG, ArtifactType.MODULE)

class TestArtifactRegistry:
    def test_register(self):
        reg = ArtifactRegistry()
        art = reg.register("OpenAIProvider", atype=ArtifactType.PROVIDER)
        assert art.atype == ArtifactType.PROVIDER
    def test_find_by_type(self):
        reg = ArtifactRegistry()
        reg.register("DB", atype=ArtifactType.DATABASE)
        found = reg.find_by_type(ArtifactType.DATABASE)
        assert len(found) == 1

class TestKnowledgeGraph:
    def test_presets(self):
        kg = KnowledgeGraph()
        assert len(kg.get_by_type(KnowledgeType.CONSTRAINT)) >= 3
        assert len(kg.get_by_type(KnowledgeType.PATTERN)) >= 2
    def test_constraints_for_provider(self):
        kg = KnowledgeGraph()
        c = kg.get_constraints_for(ArtifactType.PROVIDER)
        assert any("Metrics" in x.name for x in c)

class TestConstraintEngine:
    def test_compile(self):
        reg = ArtifactRegistry()
        art = reg.register("TestProvider", atype=ArtifactType.PROVIDER)
        kg = KnowledgeGraph()
        engine = ConstraintEngine(reg, kg)
        ctx = engine.compile_context(art)
        assert len(ctx.applicable_constraints) >= 1
