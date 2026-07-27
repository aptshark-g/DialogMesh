"""Tests for ChunkStrategyRegistry and the four chunk strategies.

Covers normal paths, exception paths, and edge cases.
"""
from __future__ import annotations

import pytest

from core.agent.chunking import (
    ChunkStrategyRegistry,
    FixedSizeChunkStrategy,
    HeaderChunkStrategy,
    LLMChunkStrategy,
    RuntimeConstraints,
    SemanticChunkStrategy,
    TaskContext,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_md() -> str:
    return """# DialogMesh v4

## Context Compiler

Context Compiler 是将多域知识编译为 IR 的组件。

### Parameters

- min_support: 8 (default)
- max_conflict: 0.2

## Hypothesis Engine

Hypothesis 冻结流程：观察 → 假设 → 投票 → 知识。

### Constraints

BudgetAllocator 必须保证总 token ≤ 预算。
"""


@pytest.fixture
def sample_text() -> str:
    return "This is sentence one. This is sentence two! Is this sentence three? Yes, it is."


@pytest.fixture
def registry() -> ChunkStrategyRegistry:
    r = ChunkStrategyRegistry()
    r.register(FixedSizeChunkStrategy())
    r.register(HeaderChunkStrategy())
    r.register(SemanticChunkStrategy())
    r.register(LLMChunkStrategy())
    return r


# =============================================================================
# FixedSizeChunkStrategy
# =============================================================================

class TestFixedSizeChunkStrategy:
    def test_basic_chunking(self, sample_text: str) -> None:
        strategy = FixedSizeChunkStrategy(chunk_size=30, overlap=5)
        ctx = TaskContext(file_type="txt", content_length=len(sample_text))
        chunks = strategy.chunk(sample_text, ctx)
        assert len(chunks) > 0
        assert all(len(c) <= 30 for c in chunks)

    def test_empty_text(self) -> None:
        strategy = FixedSizeChunkStrategy()
        ctx = TaskContext(file_type="txt")
        assert strategy.chunk("", ctx) == []

    def test_supports(self) -> None:
        strategy = FixedSizeChunkStrategy()
        assert strategy.supports("md")
        assert strategy.supports("txt")
        assert strategy.supports("pdf")

    def test_estimate_latency(self) -> None:
        strategy = FixedSizeChunkStrategy()
        assert strategy.estimate_latency(10000) > 0


# =============================================================================
# HeaderChunkStrategy
# =============================================================================

class TestHeaderChunkStrategy:
    def test_header_splitting(self, sample_md: str) -> None:
        strategy = HeaderChunkStrategy()
        ctx = TaskContext(file_type="md", content_length=len(sample_md))
        chunks = strategy.chunk(sample_md, ctx)
        assert len(chunks) >= 3  # at least top-level headers
        assert all("#" in c for c in chunks)

    def test_fallback_no_headers(self, sample_text: str) -> None:
        strategy = HeaderChunkStrategy()
        ctx = TaskContext(file_type="txt", content_length=len(sample_text))
        chunks = strategy.chunk(sample_text, ctx)
        assert len(chunks) == 1
        assert chunks[0] == sample_text

    def test_empty_text(self) -> None:
        strategy = HeaderChunkStrategy()
        ctx = TaskContext(file_type="md")
        assert strategy.chunk("", ctx) == []

    def test_supports(self) -> None:
        strategy = HeaderChunkStrategy()
        assert strategy.supports("md")
        assert not strategy.supports("py")


# =============================================================================
# SemanticChunkStrategy
# =============================================================================

class TestSemanticChunkStrategy:
    def test_paragraph_boundaries(self, sample_text: str) -> None:
        strategy = SemanticChunkStrategy(max_len=40, min_len=10)
        ctx = TaskContext(file_type="txt", content_length=len(sample_text))
        chunks = strategy.chunk(sample_text, ctx)
        assert len(chunks) > 0
        assert all(len(c) <= 40 for c in chunks)

    def test_empty_text(self) -> None:
        strategy = SemanticChunkStrategy()
        ctx = TaskContext(file_type="txt")
        assert strategy.chunk("", ctx) == []

    def test_supports(self) -> None:
        strategy = SemanticChunkStrategy()
        assert strategy.supports("md")
        assert strategy.supports("py")
        assert strategy.supports("docx")

    def test_short_text(self) -> None:
        text = "Short text."
        strategy = SemanticChunkStrategy(max_len=100, min_len=50)
        ctx = TaskContext(file_type="txt", content_length=len(text))
        chunks = strategy.chunk(text, ctx)
        assert chunks == [text]


# =============================================================================
# LLMChunkStrategy
# =============================================================================

class TestLLMChunkStrategy:
    def test_fallback_without_llm(self, sample_text: str) -> None:
        strategy = LLMChunkStrategy()
        ctx = TaskContext(file_type="md", content_length=len(sample_text))
        chunks = strategy.chunk(sample_text, ctx)
        assert len(chunks) > 0  # falls back to SemanticChunkStrategy

    def test_empty_text(self) -> None:
        strategy = LLMChunkStrategy()
        ctx = TaskContext(file_type="md")
        assert strategy.chunk("", ctx) == []

    def test_supports(self) -> None:
        strategy = LLMChunkStrategy()
        assert strategy.supports("md")
        assert strategy.supports("pdf")
        assert strategy.supports("docx")


# =============================================================================
# ChunkStrategyRegistry
# =============================================================================

class TestChunkStrategyRegistry:
    def test_register_and_get(self) -> None:
        registry = ChunkStrategyRegistry()
        strategy = FixedSizeChunkStrategy()
        registry.register(strategy)
        assert registry.get("fixed_size") is strategy
        assert "fixed_size" in registry

    def test_unregister(self) -> None:
        registry = ChunkStrategyRegistry()
        registry.register(FixedSizeChunkStrategy())
        registry.unregister("fixed_size")
        assert registry.get("fixed_size") is None
        assert "fixed_size" not in registry

    def test_unregister_missing_warns(self, caplog) -> None:
        registry = ChunkStrategyRegistry()
        with caplog.at_level("WARNING", logger="core.agent.v4.chunking.registry"):
            registry.unregister("missing")
        assert "not found" in caplog.text

    def test_overwrite_warns(self, caplog) -> None:
        registry = ChunkStrategyRegistry()
        registry.register(FixedSizeChunkStrategy())
        with caplog.at_level("WARNING", logger="core.agent.v4.chunking.registry"):
            registry.register(FixedSizeChunkStrategy())
        assert "Overwriting" in caplog.text

    def test_select_by_latency_budget(self, registry: ChunkStrategyRegistry) -> None:
        ctx = TaskContext(file_type="md", content_length=5000)
        # Very tight budget → only FixedSize qualifies
        tight = RuntimeConstraints(latency_budget_ms=2.0)
        selected = registry.select(ctx, tight)
        assert isinstance(selected, FixedSizeChunkStrategy)

    def test_select_no_match_raises(self, registry: ChunkStrategyRegistry) -> None:
        ctx = TaskContext(file_type="docx", content_length=5000)
        # No strategy supports "docx" in our default setup (Header doesn't)
        # But FixedSize and Semantic support all types, so this won't raise.
        # Let's use a custom unsupported type by creating a registry with only Header.
        r = ChunkStrategyRegistry()
        r.register(HeaderChunkStrategy())
        ctx = TaskContext(file_type="docx", content_length=5000)
        with pytest.raises(ValueError, match="No chunk strategy matches"):
            r.select(ctx)

    def test_select_default_constraints(self, registry: ChunkStrategyRegistry) -> None:
        ctx = TaskContext(file_type="md", content_length=5000)
        selected = registry.select(ctx)
        assert selected is not None
        assert selected.supports("md")

    def test_list_strategies(self, registry: ChunkStrategyRegistry) -> None:
        names = registry.list_strategies()
        assert set(names) == {
            "fixed_size",
            "header",
            "semantic",
            "llm",
        }

    def test_len(self, registry: ChunkStrategyRegistry) -> None:
        assert len(registry) == 4

    def test_optimizer_fallback_on_exception(self, registry: ChunkStrategyRegistry, caplog) -> None:
        """Optimizer failure should log warning and fall back to default scoring."""

        class BadOptimizer:
            def predict_quality(self, candidates, task):
                raise RuntimeError("boom")

        registry._optimizer = BadOptimizer()
        ctx = TaskContext(file_type="md", content_length=5000)
        with caplog.at_level("WARNING", logger="core.agent.v4.chunking.registry"):
            selected = registry.select(ctx)
        assert selected is not None
        assert "falling back" in caplog.text

    def test_optimizer_selects_best(self) -> None:
        """Optimizer with valid scores should select highest-scoring strategy."""

        class GoodOptimizer:
            def predict_quality(self, candidates, task):
                return {name: 0.5 if name != "semantic" else 0.99 for name in candidates}

        registry = ChunkStrategyRegistry(optimizer=GoodOptimizer())
        registry.register(FixedSizeChunkStrategy())
        registry.register(SemanticChunkStrategy())
        ctx = TaskContext(file_type="md", content_length=5000)
        selected = registry.select(ctx)
        assert isinstance(selected, SemanticChunkStrategy)
