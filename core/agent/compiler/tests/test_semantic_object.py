"""Tests for SemanticObject, LOD, CompositionEdge data models."""
import pytest
from core.agent.compiler.semantic_object import SemanticObject, LOD, CompositionEdge


class TestLOD:
    def test_defaults(self):
        lod = LOD()
        assert lod.level == 2.0
        assert lod.token_budget == 1800
        assert lod.strategy == "structural_summary"

    def test_custom_levels(self):
        lod = LOD(level=3.0, token_budget=500, strategy="definition_only")
        assert lod.level == 3.0
        assert lod.token_budget == 500
        assert lod.strategy == "definition_only"


class TestSemanticObject:
    def test_basic_creation(self):
        obj = SemanticObject(identity="dom_sel_1", name="DomainSelector")
        assert obj.name == "DomainSelector"
        assert obj.identity == "dom_sel_1"

    def test_identity_required(self):
        obj = SemanticObject(identity="ctx_comp_1", name="ContextCompiler")
        assert obj.identity is not None

    def test_with_relations(self):
        obj = SemanticObject(
            identity="ba_1",
            name="BudgetAllocator",
            semantic_path=["8. 调度与消费周期"],
        )
        assert len(obj.semantic_path) >= 1

    def test_composition_edges(self):
        obj = SemanticObject(identity="a_1", name="A")
        edge = CompositionEdge(target="B", type="contains", weight=0.8)
        obj.composition_edges.append(edge)
        assert len(obj.composition_edges) == 1
        assert obj.composition_edges[0].target == "B"
        assert obj.composition_edges[0].weight == 0.8
        assert obj.composition_edges[0].type == "contains"
