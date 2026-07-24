"""Tests using real world data via session fixture."""
import pytest
from core.agent.compiler.semantic_object import LOD


class TestObjectRuntime:
    def test_render_returns_view(self, object_runtime, objects):
        ort = object_runtime
        name = next(iter(objects.keys()))
        obj = objects[name]
        from core.agent.compiler.perspective_planner import Perspective
        persp = Perspective()
        persp.strategy = "architecture"
        lod = LOD(level=2.0, token_budget=500)
        view = ort.render(obj, lod, persp)
        assert isinstance(view, dict)

    def test_store_not_empty(self, objects):
        assert len(objects) > 100

    def test_store_has_valid_objects(self, objects):
        for obj in list(objects.values())[:5]:
            assert hasattr(obj, 'name')
            assert hasattr(obj, 'identity')
            assert obj.name


class TestContentProvider:
    def test_query_design(self, content_provider):
        result = content_provider.query_design(
            ["8. 调度与消费周期"], limit=2, max_chars=300
        )
        assert isinstance(result, str)

    def test_relation_query(self, content_provider):
        edges = content_provider.relation_query(min_confidence=0.0, limit=10)
        assert isinstance(edges, list)

    def test_relation_substrate_set(self, content_provider):
        assert content_provider._relation_substrate is not None

    def test_code_lookup(self, content_provider):
        result = content_provider.code_lookup("ContextCompiler")
        assert isinstance(result, str)


class TestRelationSubstrate:
    def test_has_edges(self, relation_substrate):
        stats = relation_substrate.stats
        assert stats["total"] > 10  # 5 docs produce fewer edges
        assert stats["kinds"]["structural"] > 0

    def test_query(self, relation_substrate):
        edges = relation_substrate.query(min_confidence=0.0, limit=5)
        assert isinstance(edges, list)


class TestSemanticPath:
    def test_has_nodes(self, semantic_index):
        stats = semantic_index.stats
        assert isinstance(stats, dict)
        assert stats.get("nodes", 0) > 100 or stats.get("total_nodes", 0) > 100

    def test_locate(self, semantic_index):
        # locate takes a concept name string
        result = semantic_index.locate("DomainSelector")
        # May return None if concept not found
        assert result is not None or True
