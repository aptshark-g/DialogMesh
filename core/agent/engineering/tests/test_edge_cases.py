"""Edge case tests for Engineering Chain."""
import pytest
from core.agent.engineering import (
    ArtifactType, EdgeType, ArtifactRegistry, KnowledgeGraph,
    KnowledgeType, ConstraintEngine,
)
from core.agent.engineering.models import ArtifactEdge


class TestIsAConstraint:

    def test_module_constraint_applies_to_middleware(self):
        kg = KnowledgeGraph()
        kg.add("Every Module needs logging", KnowledgeType.CONSTRAINT,
               binds_to=ArtifactType.MODULE)
        constraints = kg.get_constraints_for(ArtifactType.MIDDLEWARE)
        assert any("Module" in c.name for c in constraints)

    def test_module_constraint_applies_to_provider(self):
        kg = KnowledgeGraph()
        kg.add("Every Module needs logging", KnowledgeType.CONSTRAINT,
               binds_to=ArtifactType.MODULE)
        constraints = kg.get_constraints_for(ArtifactType.PROVIDER)
        assert any("Module" in c.name for c in constraints)


class TestAntiPattern:

    def test_detect_violation(self):
        reg = ArtifactRegistry()
        art = reg.register("UserController", atype=ArtifactType.CONTROLLER)
        kg = KnowledgeGraph()
        engine = ConstraintEngine(reg, kg)
        edge = ArtifactEdge(id="e1", source_id=art.id, target_id="db",
                            etype=EdgeType.DEPENDS_ON)
        violations = engine.check_anti_patterns(edge)
        assert len(violations) >= 1

    def test_no_violation_for_non_controller(self):
        reg = ArtifactRegistry()
        art = reg.register("Logger", atype=ArtifactType.MIDDLEWARE)
        kg = KnowledgeGraph()
        engine = ConstraintEngine(reg, kg)
        edge = ArtifactEdge(id="e2", source_id=art.id, target_id="db",
                            etype=EdgeType.DEPENDS_ON)
        violations = engine.check_anti_patterns(edge)
        assert len(violations) == 0


class TestStructuralTypeInference:

    def test_name_based_inference(self):
        reg = ArtifactRegistry()
        art = reg.register("SomeProviderThing", atype=ArtifactType.PROVIDER)
        found = reg.find_by_type(ArtifactType.PROVIDER)
        assert len(found) == 1

    def test_fallback_to_module(self):
        reg = ArtifactRegistry()
        art = reg.register("SomeRandomThing")
        assert art.atype == ArtifactType.MODULE
