"""Tests for Document Ingestion Layer (DIL) — Phase 2 core.

Covers:
- DocumentNode / DocumentTree data model
- MarkdownParser (heading hierarchy, code blocks, empty input)
- ObservationExtractor (rule-based extraction, confidence scoring)
- ChunkStrategyRegistry (selection, constraints)
- DocumentIngestionPipeline (end-to-end, directory, inline text)
- DocumentDomainAdapter (bundle adaptation)
- DocumentSource (context retrieval)
- CLI cmd_ingest (dry-run, file, directory)
- API /v4/ingest (request/response shape)

Normal + exception paths for each component.
"""
from __future__ import annotations
import os
import tempfile
import pytest

from core.agent.document.tree import (
    DocumentNode, DocumentTree, DocumentObservation,
    DocumentObservationBundle, make_node_id, Relation,
)
from core.agent.document.parsers import MarkdownParser, ParserRegistry
from core.agent.document.extractor import ObservationExtractor
from core.agent.chunking.strategies import (
    ChunkStrategyRegistry, FixedSizeChunkStrategy,
    HeaderChunkStrategy, SemanticChunkStrategy, RuntimeConstraints,
)
from core.agent.document.pipeline import DocumentIngestionPipeline
from core.agent.observation.document_domain_adapter import DocumentDomainAdapter
from core.agent.context.source import DocumentSource
from core.agent.observation.pool import ObservationPool


# ═══════════════════════════════════════════════════════════════
# DocumentTree / DocumentNode
# ═══════════════════════════════════════════════════════════════

class TestDocumentTree:
    def test_make_node_id_deterministic(self):
        nid1 = make_node_id("/docs/a.md", ["# H1", "## H2"])
        nid2 = make_node_id("/docs/a.md", ["# H1", "## H2"])
        assert nid1 == nid2
        assert len(nid1) == 16

    def test_node_summary(self):
        node = DocumentNode(
            node_id="n1",
            source_path="a.md",
            heading_path=["# H1"],
            level=1,
            raw_text="This is a long paragraph that should be truncated " * 10,
            node_type="paragraph",
        )
        assert len(node.text_summary(50)) <= 53
        assert "..." in node.text_summary(50)

    def test_tree_flatten(self):
        root = DocumentNode(node_id="r", source_path="a.md", heading_path=["# R"], level=1, raw_text="r", node_type="heading")
        child = DocumentNode(node_id="c", source_path="a.md", heading_path=["# R", "## C"], level=2, raw_text="c", node_type="heading", parent=root)
        root.children.append(child)
        tree = DocumentTree(source_path="a.md", root_nodes=[root])
        assert len(tree.all_nodes()) == 2
        assert tree.node_by_id("c") == child


# ═══════════════════════════════════════════════════════════════
# MarkdownParser
# ═══════════════════════════════════════════════════════════════

class TestMarkdownParser:
    def test_parse_headings(self):
        md = "# Title\n\nBody text.\n\n## Section A\n\nContent A.\n\n### Sub A1\n\nDeep content.\n"
        parser = MarkdownParser()
        tree = parser.parse(md, "test.md")
        assert tree.file_type == "markdown"
        nodes = tree.all_nodes()
        assert len(nodes) == 3
        assert nodes[0].level == 1
        assert nodes[1].level == 2
        assert nodes[2].level == 3
        assert nodes[2].heading_path == ["# Title", "## Section A", "### Sub A1"]

    def test_parse_code_block(self):
        md = "# Code\n\n```python\nprint(1)\n```\n"
        tree = MarkdownParser().parse(md, "code.md")
        nodes = tree.all_nodes()
        assert nodes[0].node_type == "code"

    def test_parse_empty(self):
        tree = MarkdownParser().parse("", "empty.md")
        assert tree.root_nodes == []

    def test_parse_no_headings(self):
        tree = MarkdownParser().parse("Just some text without headings.", "plain.md")
        assert len(tree.root_nodes) == 1
        assert tree.root_nodes[0].node_type == "paragraph"

    def test_registry(self):
        reg = ParserRegistry()
        assert reg.get_parser("foo.md") is not None
        assert reg.get_parser("foo.pdf") is None


# ═══════════════════════════════════════════════════════════════
# ObservationExtractor
# ═══════════════════════════════════════════════════════════════

class TestObservationExtractor:
    def test_extract_definition(self):
        node = DocumentNode(
            node_id="n1", source_path="a.md", heading_path=["# H"], level=1,
            raw_text="Context Compiler 是将多域知识编译为 IR 的组件。",
            node_type="paragraph",
        )
        ext = ObservationExtractor()
        obs = ext.extract(node, event_id="e1")
        assert any(o.observation_type == "definition" for o in obs)

    def test_extract_constraint(self):
        node = DocumentNode(
            node_id="n2", source_path="a.md", heading_path=["# H"], level=1,
            raw_text="BudgetAllocator 必须保证总 token ≤ 预算。",
            node_type="paragraph",
        )
        obs = ObservationExtractor().extract(node)
        assert any(o.observation_type == "constraint" for o in obs)

    def test_extract_procedure(self):
        node = DocumentNode(
            node_id="n3", source_path="a.md", heading_path=["# H"], level=1,
            raw_text="步骤：首先观察，然后假设，最后投票。",
            node_type="paragraph",
        )
        obs = ObservationExtractor().extract(node)
        assert any(o.observation_type == "procedure" for o in obs)

    def test_extract_relation(self):
        node = DocumentNode(
            node_id="n4", source_path="a.md", heading_path=["# H"], level=1,
            raw_text="Knowledge 依赖于 Hypothesis 的投票收敛。",
            node_type="paragraph",
        )
        obs = ObservationExtractor().extract(node)
        rel_obs = [o for o in obs if o.observation_type == "relation"]
        assert len(rel_obs) >= 1
        assert any(r.relation_type == "depends_on" for r in rel_obs[0].relations)

    def test_extract_parameter(self):
        node = DocumentNode(
            node_id="n5", source_path="a.md", heading_path=["# H"], level=1,
            raw_text="community_resolution: 1.0 (默认)",
            node_type="paragraph",
        )
        obs = ObservationExtractor().extract(node)
        assert any(o.observation_type == "parameter" for o in obs)

    def test_fallback_observation(self):
        node = DocumentNode(
            node_id="n6", source_path="a.md", heading_path=["# H"], level=1,
            raw_text="Some random text that does not match any rule. " * 5,
            node_type="paragraph",
        )
        obs = ObservationExtractor().extract(node)
        assert len(obs) == 1
        assert obs[0].observation_type == ""
        assert obs[0].confidence == 0.3

    def test_empty_text(self):
        node = DocumentNode(
            node_id="n7", source_path="a.md", heading_path=["# H"], level=1,
            raw_text="", node_type="paragraph",
        )
        obs = ObservationExtractor().extract(node)
        assert obs == []


# ═══════════════════════════════════════════════════════════════
# ChunkStrategy
# ═══════════════════════════════════════════════════════════════

class TestChunkStrategy:
    def test_fixed_size_chunk(self):
        node = DocumentNode(
            node_id="n1", source_path="a.md", heading_path=["# H"], level=1,
            raw_text="x" * 1000, node_type="paragraph",
        )
        strat = FixedSizeChunkStrategy(chunk_size=300, overlap=50)
        chunks = strat.chunk(node)
        assert len(chunks) > 1
        assert all(c.node_type == "paragraph" for c in chunks)

    def test_header_chunk(self):
        parent = DocumentNode(
            node_id="p", source_path="a.md", heading_path=["# H"], level=1,
            raw_text="parent", node_type="heading",
        )
        child = DocumentNode(
            node_id="c", source_path="a.md", heading_path=["# H", "## C"], level=2,
            raw_text="child", node_type="paragraph", parent=parent,
        )
        parent.children.append(child)
        strat = HeaderChunkStrategy()
        chunks = strat.chunk(parent)
        assert chunks == [child]

    def test_semantic_chunk(self):
        text = "Para one.\n\nPara two with more content.\n\nPara three."
        node = DocumentNode(
            node_id="n1", source_path="a.md", heading_path=["# H"], level=1,
            raw_text=text, node_type="paragraph",
        )
        strat = SemanticChunkStrategy(max_len=50, min_len=10)
        chunks = strat.chunk(node)
        assert len(chunks) >= 1

    def test_registry_select(self):
        reg = ChunkStrategyRegistry()
        node = DocumentNode(
            node_id="n1", source_path="a.md", heading_path=["# H"], level=1,
            raw_text="short", node_type="paragraph",
        )
        strat = reg.select(node, RuntimeConstraints(max_latency_ms=10))
        assert strat is not None
        assert strat.name in ("fixed_size", "header", "semantic")

    def test_registry_list(self):
        reg = ChunkStrategyRegistry()
        names = reg.list_strategies()
        assert "fixed_size" in names
        assert "header" in names
        assert "semantic" in names
        assert "llm" in names


# ═══════════════════════════════════════════════════════════════
# DocumentIngestionPipeline
# ═══════════════════════════════════════════════════════════════

class TestDocumentIngestionPipeline:
    def test_ingest_text(self):
        pipeline = DocumentIngestionPipeline()
        md = "# Title\n\nContext Compiler 是将多域知识编译为 IR 的组件。\n\n## Section\n\n必须保证总 token ≤ 预算。\n"
        bundle = pipeline.ingest_text(md, source_path="inline.md")
        assert bundle is not None
        assert len(bundle.observations) >= 2
        types = {o.observation_type for o in bundle.observations}
        assert "definition" in types
        assert "constraint" in types

    def test_ingest_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# File\n\n参数 threshold: 0.5 (默认)\n", encoding="utf-8")
        pipeline = DocumentIngestionPipeline()
        bundle = pipeline.ingest_file(str(f))
        assert bundle is not None
        assert any(o.observation_type == "parameter" for o in bundle.observations)

    def test_ingest_directory(self, tmp_path):
        (tmp_path / "a.md").write_text("# A\n\nA 定义为测试。\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("# B\n\nB 是另一个测试。\n", encoding="utf-8")
        pipeline = DocumentIngestionPipeline()
        bundles = pipeline.ingest_directory(str(tmp_path), pattern="*.md")
        assert len(bundles) == 2

    def test_ingest_missing_file(self):
        pipeline = DocumentIngestionPipeline()
        bundle = pipeline.ingest_file("/nonexistent/path.md")
        assert bundle is None

    def test_ingest_missing_directory(self):
        pipeline = DocumentIngestionPipeline()
        bundles = pipeline.ingest_directory("/nonexistent/dir")
        assert bundles == []

    def test_pipeline_stats(self):
        pipeline = DocumentIngestionPipeline()
        s = pipeline.stats()
        assert s["pool_attached"] is False
        assert "fixed_size" in s["strategies"]


# ═══════════════════════════════════════════════════════════════
# DocumentDomainAdapter
# ═══════════════════════════════════════════════════════════════

class TestDocumentDomainAdapter:
    def test_adapt_bundle(self):
        obs = DocumentObservation(
            observation_id="o1", source_path="a.md", node_id="n1", event_id="e1",
            observation_type="definition", raw_text="X 是 Y", concepts=["X"],
            relations=[Relation("is_a", "X", "Y", 0.7)],
        )
        bundle = DocumentObservationBundle(
            bundle_id="b1", event_id="e1", source_path="a.md", observations=[obs],
        )
        adapter = DocumentDomainAdapter()
        obs_bundle = adapter.adapt(bundle)
        assert obs_bundle.bundle_id == "b1"
        assert "document" in obs_bundle.domain_observations
        do = obs_bundle.domain_observations["document"]
        assert "X" in do.objects
        assert any(r["type"] == "is_a" for r in do.relations)

    def test_adapt_empty(self):
        bundle = DocumentObservationBundle(
            bundle_id="b2", event_id="e2", source_path="a.md", observations=[],
        )
        adapter = DocumentDomainAdapter()
        obs_bundle = adapter.adapt(bundle)
        assert obs_bundle.status == "partial"


# ═══════════════════════════════════════════════════════════════
# DocumentSource (ContextAssembler integration)
# ═══════════════════════════════════════════════════════════════

class TestDocumentSource:
    def test_retrieve_from_pool(self):
        pool = ObservationPool()
        adapter = DocumentDomainAdapter()
        obs = DocumentObservation(
            observation_id="o1", source_path="a.md", node_id="n1", event_id="e1",
            observation_type="definition", raw_text="X 是 Y", concepts=["X"],
            relations=[], constraints=[],
        )
        bundle = DocumentObservationBundle(
            bundle_id="b1", event_id="e1", source_path="a.md", observations=[obs],
        )
        pool.put(adapter.adapt(bundle))

        source = DocumentSource(observation_pool=pool)
        items = source.retrieve("X", top_k=5)
        assert len(items) == 1
        assert items[0].source == "document"
        assert items[0].relevance > 0

    def test_retrieve_no_pool(self):
        source = DocumentSource(observation_pool=None)
        assert source.retrieve("test") == []

    def test_retrieve_no_match(self):
        pool = ObservationPool()
        source = DocumentSource(observation_pool=pool)
        assert source.retrieve("nonexistent") == []


# ═══════════════════════════════════════════════════════════════
# CLI cmd_ingest (integration)
# ═══════════════════════════════════════════════════════════════

class TestCliIngest:
    def test_cmd_ingest_file(self, tmp_path, monkeypatch):
        from core.agent.cli.main import cmd_ingest
        f = tmp_path / "doc.md"
        f.write_text("# Title\n\n定义为测试。\n", encoding="utf-8")

        class FakeArgs:
            path = str(f)
            pattern = "*.md"
            trigger = False
        args = FakeArgs()
        assert cmd_ingest(args) == 0

    def test_cmd_ingest_directory(self, tmp_path, monkeypatch):
        from core.agent.cli.main import cmd_ingest
        (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("# B\n", encoding="utf-8")

        class FakeArgs:
            path = str(tmp_path)
            pattern = "*.md"
            trigger = False
        args = FakeArgs()
        assert cmd_ingest(args) == 0

    def test_cmd_ingest_missing(self):
        from core.agent.cli.main import cmd_ingest

        class FakeArgs:
            path = "/nonexistent"
            pattern = "*.md"
            trigger = False
        args = FakeArgs()
        assert cmd_ingest(args) == 1


# ═══════════════════════════════════════════════════════════════
# API /v4/ingest (shape test, no server)
# ═══════════════════════════════════════════════════════════════

class TestApiIngest:
    def test_ingest_request_model(self):
        from core.agent.v4.api import IngestRequest
        req = IngestRequest(source_path="docs/test.md", content="# Hello\n", file_type="markdown")
        assert req.source_path == "docs/test.md"
        assert req.file_type == "markdown"

    def test_ingest_response_shape(self):
        # Simulate what the endpoint would return
        obs = DocumentObservation(
            observation_id="o1", source_path="a.md", node_id="n1", event_id="e1",
            observation_type="definition", raw_text="X 是 Y", concepts=["X"],
        )
        bundle = DocumentObservationBundle(
            bundle_id="b1", event_id="e1", source_path="a.md", observations=[obs],
        )
        response = {
            "status": "ingested",
            "source_path": bundle.source_path,
            "observation_count": len(bundle.observations),
            "type_distribution": bundle.stats(),
        }
        assert response["observation_count"] == 1
        assert response["type_distribution"] == {"definition": 1}
