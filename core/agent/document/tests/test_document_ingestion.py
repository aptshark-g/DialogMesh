"""Tests for Document Ingestion Layer (DIL).

Covers:
    - DocumentNode / DocumentTree
    - MarkdownParser
    - ObservationExtractor
    - ChunkStrategyRegistry + strategies
    - DocumentIngestionPipeline
    - DocumentObservationBundle → ObservationBundle
    - DocumentSource retrieval
    - DocumentDomainAdapter
"""
import pytest
import os
import tempfile

from core.agent.document.tree import DocumentNode, DocumentTree, Relation, make_node_id
from core.agent.document.parsers import MarkdownParser
from core.agent.document.extractor import ObservationExtractor
from core.agent.document.observation import DocumentObservation, DocumentObservationBundle
from core.agent.document.pipeline import DocumentIngestionPipeline
from core.agent.chunking.strategies import (
    FixedSizeChunkStrategy,
    HeaderChunkStrategy,
    SemanticChunkStrategy,
    LLMChunkStrategy,
    ChunkStrategyRegistry,
    TaskContext,
    RuntimeConstraints,
    default_registry,
)
from core.agent.observation.pool import ObservationPool
from core.agent.context.source import DocumentSource
from core.agent.observation.document_domain_adapter import DocumentDomainAdapter


# ============================================================================
# DocumentNode / DocumentTree
# ============================================================================

class TestDocumentNode:
    def test_basic_fields(self):
        n = DocumentNode(
            node_id="n1",
            source_path="/docs/test.md",
            heading_path=["# A", "## B"],
            level=2,
            raw_text="content",
            node_type="paragraph",
        )
        assert n.node_id == "n1"
        assert n.level == 2
        assert n.full_path() == "# A > ## B"

    def test_add_child(self):
        root = DocumentNode(node_id="r", source_path="/t.md", level=0)
        child = DocumentNode(node_id="c", source_path="/t.md", level=1)
        root.add_child(child)
        assert child.parent == root
        assert len(root.children) == 1

    def test_walk(self):
        root = DocumentNode(node_id="r", source_path="/t.md", level=0)
        c1 = DocumentNode(node_id="c1", source_path="/t.md", level=1)
        c2 = DocumentNode(node_id="c2", source_path="/t.md", level=1)
        root.add_child(c1)
        root.add_child(c2)
        assert len(root.walk()) == 3

    def test_to_dict(self):
        n = DocumentNode(node_id="n1", source_path="/t.md", raw_text="x")
        d = n.to_dict()
        assert d["node_id"] == "n1"
        assert "children" in d


class TestDocumentTree:
    def test_all_nodes(self):
        root = DocumentNode(node_id="r", source_path="/t.md", level=0)
        root.add_child(DocumentNode(node_id="c", source_path="/t.md", level=1))
        tree = DocumentTree(root)
        assert len(tree.all_nodes()) == 2

    def test_nodes_by_type(self):
        root = DocumentNode(node_id="r", source_path="/t.md", level=0, node_type="heading")
        root.add_child(DocumentNode(node_id="c", source_path="/t.md", level=1, node_type="code"))
        tree = DocumentTree(root)
        assert len(tree.nodes_by_type("code")) == 1

    def test_stats(self):
        root = DocumentNode(node_id="r", source_path="/t.md", level=0)
        tree = DocumentTree(root)
        s = tree.stats()
        assert s["total_nodes"] == 1
        assert s["source_path"] == "/t.md"


class TestMakeNodeId:
    def test_stable(self):
        a = make_node_id("/a.md", ["# H"])
        b = make_node_id("/a.md", ["# H"])
        assert a == b
        assert len(a) == 16


# ============================================================================
# MarkdownParser
# ============================================================================

class TestMarkdownParser:
    def test_parse_headings(self):
        md = "# Title\n\ncontent\n\n## Section\n\nmore\n"
        parser = MarkdownParser()
        root = parser.parse(md, "/test.md")
        assert root.level == 0
        assert len(root.children) >= 1

    def test_no_headings(self):
        md = "Just a paragraph.\n\nAnother paragraph.\n"
        parser = MarkdownParser()
        root = parser.parse(md, "/test.md")
        assert root.node_type == "paragraph"
        assert len(root.children) == 0

    def test_code_block_detection(self):
        md = "```python\nprint(1)\n```\n"
        parser = MarkdownParser()
        root = parser.parse(md, "/test.md")
        # Code block inside heading-less doc is root node_type
        assert root.node_type == "code"

    def test_supports(self):
        parser = MarkdownParser()
        assert parser.supports("file.md")
        assert parser.supports("file.markdown")
        assert not parser.supports("file.txt")

    def test_parse_exception_fallback(self):
        parser = MarkdownParser()
        # Force exception by passing non-string (should be handled gracefully)
        # Actually parse expects str, so we test fallback via monkey-patch
        original = parser._HEADING_RE
        parser._HEADING_RE = None  # type: ignore
        try:
            root = parser.parse("# Test\n", "/test.md")
            assert root.node_type == "paragraph"
        finally:
            parser._HEADING_RE = original


# ============================================================================
# ObservationExtractor
# ============================================================================

class TestObservationExtractor:
    def test_extract_definition(self):
        node = DocumentNode(
            node_id="n1",
            source_path="/t.md",
            raw_text="Context Compiler 是将多域知识编译为 IR 的组件。",
            node_type="paragraph",
        )
        ext = ObservationExtractor()
        obs = ext.extract(node, event_id="e1")
        assert any(o.observation_type == "definition" for o in obs)

    def test_extract_constraint(self):
        node = DocumentNode(
            node_id="n2",
            source_path="/t.md",
            raw_text="BudgetAllocator 必须保证总 token ≤ 预算。",
            node_type="paragraph",
        )
        ext = ObservationExtractor()
        obs = ext.extract(node, event_id="e1")
        assert any(o.observation_type == "constraint" for o in obs)

    def test_extract_procedure(self):
        node = DocumentNode(
            node_id="n3",
            source_path="/t.md",
            raw_text="步骤 1: 观察输入。步骤 2: 生成假设。",
            node_type="paragraph",
        )
        ext = ObservationExtractor()
        obs = ext.extract(node, event_id="e1")
        assert any(o.observation_type == "procedure" for o in obs)

    def test_extract_parameter(self):
        node = DocumentNode(
            node_id="n4",
            source_path="/t.md",
            raw_text="community_resolution: 1.0 (默认)",
            node_type="paragraph",
        )
        ext = ObservationExtractor()
        obs = ext.extract(node, event_id="e1")
        assert any(o.observation_type == "parameter" for o in obs)

    def test_min_confidence_filter(self):
        node = DocumentNode(
            node_id="n5",
            source_path="/t.md",
            raw_text="x",
            node_type="paragraph",
        )
        ext = ObservationExtractor(min_confidence=0.9)
        obs = ext.extract(node, event_id="e1")
        # Very short text should not pass 0.9 confidence
        assert all(o.confidence < 0.9 for o in obs) or len(obs) == 0

    def test_deduplication(self):
        node = DocumentNode(
            node_id="n6",
            source_path="/t.md",
            raw_text="A 是 B。A 是 B。",
            node_type="paragraph",
        )
        ext = ObservationExtractor()
        obs = ext.extract(node, event_id="e1")
        texts = [o.raw_text for o in obs]
        assert len(texts) == len(set(texts))


# ============================================================================
# ChunkStrategy
# ============================================================================

class TestFixedSizeChunkStrategy:
    def test_apply(self):
        node = DocumentNode(
            node_id="n1",
            source_path="/t.md",
            raw_text="a" * 2500,
            node_type="paragraph",
        )
        strat = FixedSizeChunkStrategy(chunk_size=1024)
        result = strat.apply(node)
        assert len(result.nodes) == 3
        assert result.strategy_name == "fixed_size"

    def test_can_handle(self):
        strat = FixedSizeChunkStrategy()
        ctx = TaskContext(file_type="markdown")
        cons = RuntimeConstraints(max_latency_ms=10)
        assert strat.can_handle(ctx, cons)


class TestHeaderChunkStrategy:
    def test_apply(self):
        node = DocumentNode(
            node_id="n1",
            source_path="/t.md",
            raw_text="# H\ncontent",
            node_type="heading",
        )
        strat = HeaderChunkStrategy()
        result = strat.apply(node)
        assert len(result.nodes) == 1
        assert result.nodes[0].node_id == "n1"


class TestSemanticChunkStrategy:
    def test_apply(self):
        text = "Para 1.\n\nPara 2.\n\nPara 3."
        node = DocumentNode(
            node_id="n1",
            source_path="/t.md",
            raw_text=text,
            node_type="paragraph",
        )
        strat = SemanticChunkStrategy()
        result = strat.apply(node, max_chunk_size=20)
        assert len(result.nodes) >= 2

    def test_unsupported_type(self):
        strat = SemanticChunkStrategy()
        ctx = TaskContext(file_type="pdf")
        cons = RuntimeConstraints()
        assert not strat.can_handle(ctx, cons)


class TestLLMChunkStrategy:
    def test_can_handle_no_llm(self):
        strat = LLMChunkStrategy()
        ctx = TaskContext(file_type="markdown")
        cons = RuntimeConstraints(llm_available=False)
        assert not strat.can_handle(ctx, cons)

    def test_can_handle_with_llm(self):
        strat = LLMChunkStrategy()
        ctx = TaskContext(file_type="markdown")
        cons = RuntimeConstraints(llm_available=True, max_latency_ms=5000)
        assert strat.can_handle(ctx, cons)


class TestChunkStrategyRegistry:
    def test_register_and_select(self):
        reg = ChunkStrategyRegistry()
        reg.register(FixedSizeChunkStrategy())
        reg.register(HeaderChunkStrategy())
        ctx = TaskContext(file_type="markdown", doc_size_chars=100)
        cons = RuntimeConstraints(max_latency_ms=100)
        selected = reg.select(ctx, cons)
        assert selected.name in ("fixed_size", "header")

    def test_default_registry(self):
        reg = default_registry()
        assert "fixed_size" in reg.list_strategies()
        assert "llm" in reg.list_strategies()

    def test_fallback_when_no_candidates(self):
        reg = ChunkStrategyRegistry()
        ctx = TaskContext(file_type="markdown")
        cons = RuntimeConstraints(max_latency_ms=1)
        selected = reg.select(ctx, cons)
        assert selected.name == "fixed_size"


# ============================================================================
# DocumentObservation / DocumentObservationBundle
# ============================================================================

class TestDocumentObservation:
    def test_to_evidence(self):
        obs = DocumentObservation(
            observation_id="o1",
            source_path="/t.md",
            node_id="n1",
            event_id="e1",
            observation_type="definition",
            raw_text="test",
            confidence=0.8,
        )
        ev = obs.to_evidence()
        assert ev.source == "document:/t.md"
        assert ev.reliability == 0.8


class TestDocumentObservationBundle:
    def test_to_observation_bundle(self):
        obs = DocumentObservation(
            observation_id="o1",
            source_path="/t.md",
            node_id="n1",
            event_id="e1",
            observation_type="definition",
            raw_text="test",
            concepts=["A"],
            relations=[Relation(source="A", target="B", relation_type="is_a")],
        )
        bundle = DocumentObservationBundle.from_observations("/t.md", [obs])
        obs_bundle = bundle.to_observation_bundle()
        assert obs_bundle.bundle_id == bundle.bundle_id
        assert "document" in obs_bundle.domain_observations
        assert obs_bundle.status == "complete"

    def test_empty_observations(self):
        bundle = DocumentObservationBundle.from_observations("/t.md", [])
        obs_bundle = bundle.to_observation_bundle()
        assert obs_bundle.domain_observations["document"].meta["observation_count"] == 0


# ============================================================================
# DocumentIngestionPipeline
# ============================================================================

class TestDocumentIngestionPipeline:
    def test_ingest_text(self):
        pool = ObservationPool()
        pipeline = DocumentIngestionPipeline(pool=pool)
        md = "# Title\n\nContext Compiler 是将多域知识编译为 IR 的组件。\n"
        bundle = pipeline.ingest_text(md, "/test.md")
        assert bundle.bundle_id.startswith("doc_bundle_")
        assert len(bundle.observations) > 0
        # Verify pool received it
        assert pool.stats()["total_bundles"] == 1

    def test_ingest_file(self):
        pool = ObservationPool()
        pipeline = DocumentIngestionPipeline(pool=pool)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# Test\n\nA 是 B。\n")
            path = f.name
        try:
            bundle = pipeline.ingest_file(path)
            assert len(bundle.observations) > 0
        finally:
            os.unlink(path)

    def test_ingest_file_not_found(self):
        pool = ObservationPool()
        pipeline = DocumentIngestionPipeline(pool=pool)
        bundle = pipeline.ingest_file("/nonexistent/file.md")
        assert len(bundle.observations) == 0

    def test_ingest_directory(self):
        pool = ObservationPool()
        pipeline = DocumentIngestionPipeline(pool=pool)
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                with open(os.path.join(tmpdir, f"doc{i}.md"), "w", encoding="utf-8") as f:
                    f.write(f"# Doc {i}\n\nContent.\n")
            bundles = pipeline.ingest_directory(tmpdir, pattern="*.md")
            assert len(bundles) == 3

    def test_no_pool(self):
        pipeline = DocumentIngestionPipeline(pool=None)
        md = "# Title\n\nContent.\n"
        bundle = pipeline.ingest_text(md, "/test.md")
        assert bundle.bundle_id.startswith("doc_bundle_")


# ============================================================================
# DocumentSource (ContextAssembler integration)
# ============================================================================

class TestDocumentSource:
    def test_retrieve_from_pool(self):
        pool = ObservationPool()
        pipeline = DocumentIngestionPipeline(pool=pool)
        pipeline.ingest_text("# Design\n\nContext Compiler 是将多域知识编译为 IR 的组件。\n", "/design.md")

        source = DocumentSource(observation_pool=pool)
        items = source.retrieve("Context Compiler", top_k=5)
        assert len(items) > 0
        assert all(i.source == "document" for i in items)

    def test_retrieve_no_pool(self):
        source = DocumentSource(observation_pool=None)
        items = source.retrieve("test")
        assert items == []

    def test_retrieve_no_match(self):
        pool = ObservationPool()
        pipeline = DocumentIngestionPipeline(pool=pool)
        pipeline.ingest_text("# Other\n\nUnrelated content.\n", "/other.md")

        source = DocumentSource(observation_pool=pool)
        items = source.retrieve("xyz_nonexistent")
        assert items == []


# ============================================================================
# DocumentDomainAdapter
# ============================================================================

class TestDocumentDomainAdapter:
    def test_ingest_without_compiler(self):
        adapter = DocumentDomainAdapter(compiler=None)
        obs = DocumentObservation(
            observation_id="o1",
            source_path="/t.md",
            node_id="n1",
            event_id="e1",
            observation_type="definition",
            raw_text="test",
        )
        bundle = DocumentObservationBundle.from_observations("/t.md", [obs])
        result = adapter.ingest(bundle)
        assert result is not None
        assert "document" in result.domain_observations

    def test_to_domain_observation(self):
        adapter = DocumentDomainAdapter(compiler=None)
        obs = DocumentObservation(
            observation_id="o1",
            source_path="/t.md",
            node_id="n1",
            event_id="e1",
            observation_type="definition",
            raw_text="test",
        )
        bundle = DocumentObservationBundle.from_observations("/t.md", [obs])
        dom = adapter.to_domain_observation(bundle)
        assert dom is not None
        assert dom.domain == "document"

    def test_ingest_with_bad_bundle(self):
        adapter = DocumentDomainAdapter(compiler=None)
        # Force failure by passing something without the expected interface
        class FakeBundle:
            pass
        result = adapter.ingest(FakeBundle())  # type: ignore
        assert result is None


# ============================================================================
# End-to-end
# ============================================================================

class TestEndToEnd:
    def test_full_pipeline(self):
        """Simulate: ingest docs/ → ask question → retrieve from DocumentSource."""
        pool = ObservationPool()
        pipeline = DocumentIngestionPipeline(pool=pool)

        md = """
# DialogMesh v4

## Context Compiler

Context Compiler 是将多域知识编译为 IR 的组件。

### Parameters

community_resolution: 1.0 (默认)
min_support: 8

## Hypothesis Engine

Hypothesis 冻结流程：观察→假设→投票→知识。
BudgetAllocator 必须保证总 token ≤ 预算。
"""
        pipeline.ingest_text(md, "/docs/v4.md")

        # Simulate user query
        source = DocumentSource(observation_pool=pool)
        items = source.retrieve("Context Compiler 是什么", top_k=3)
        assert len(items) > 0

        # Also test parameter retrieval
        param_items = source.retrieve("min_support", top_k=3)
        assert len(param_items) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
