"""ChunkStrategy: pluggable document chunking with strategy selection.

Design principle:
    - NOT just for chunking — general strategy selection framework.
    - Can be reused for retrieval strategy, LLM provider selection, etc.
    - Selection is driven by TaskContext + RuntimeConstraints.
"""
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent.v4.document.tree import DocumentNode

logger = logging.getLogger(__name__)


@dataclass
class TaskContext:
    """Context for strategy selection."""
    file_type: str = "markdown"
    doc_size_chars: int = 0
    doc_depth: int = 0
    urgency: str = "normal"  # "critical" | "normal" | "background"
    quality_target: str = "balanced"  # "speed" | "balanced" | "quality"


@dataclass
class RuntimeConstraints:
    """Runtime resource constraints."""
    max_latency_ms: int = 5000
    available_workers: int = 4
    memory_budget_mb: int = 512
    llm_available: bool = False


@dataclass
class ChunkResult:
    """Result of applying a chunk strategy to a DocumentNode."""
    nodes: List[DocumentNode]
    strategy_name: str
    latency_ms: float = 0.0


class ChunkStrategy(ABC):
    """Abstract base for document chunking strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy identifier."""

    @property
    @abstractmethod
    def quality_score(self) -> float:
        """Quality rating (0.0–1.0)."""

    @property
    @abstractmethod
    def latency_ms(self) -> float:
        """Typical latency in milliseconds."""

    @property
    def supported_types(self) -> set[str]:
        """File types this strategy can handle."""
        return {"markdown", "text", "code"}

    @abstractmethod
    def apply(self, node: DocumentNode, **kwargs: Any) -> ChunkResult:
        """Apply chunking to a DocumentNode, return resulting sub-nodes."""

    def can_handle(self, context: TaskContext, constraints: RuntimeConstraints) -> bool:
        """Check if this strategy is viable given constraints."""
        if context.file_type not in self.supported_types:
            return False
        if self.latency_ms > constraints.max_latency_ms:
            return False
        return True


class FixedSizeChunkStrategy(ChunkStrategy):
    """Fast fixed-size chunking — for emergency / high-throughput paths."""

    DEFAULT_SIZE = 1024

    def __init__(self, chunk_size: int = DEFAULT_SIZE):
        self._chunk_size = chunk_size

    @property
    def name(self) -> str:
        return "fixed_size"

    @property
    def quality_score(self) -> float:
        return 0.6

    @property
    def latency_ms(self) -> float:
        return 5.0

    def apply(self, node: DocumentNode, **kwargs: Any) -> ChunkResult:
        text = node.raw_text
        size = kwargs.get("chunk_size", self._chunk_size)
        nodes: List[DocumentNode] = []
        start = 0
        idx = 0
        while start < len(text):
            end = min(start + size, len(text))
            chunk_text = text[start:end]
            chunk_node = DocumentNode(
                node_id=f"{node.node_id}_chunk_{idx}",
                source_path=node.source_path,
                heading_path=node.heading_path + [f"[chunk {idx}]"],
                level=node.level,
                raw_text=chunk_text,
                node_type=node.node_type,
                parent=node,
            )
            nodes.append(chunk_node)
            start = end
            idx += 1
        return ChunkResult(nodes=nodes, strategy_name=self.name, latency_ms=self.latency_ms)


class HeaderChunkStrategy(ChunkStrategy):
    """Structure-preserving chunking by heading hierarchy.

    For Markdown: each heading becomes a node; content under the heading
    is attached as children or raw_text depending on depth.
    """

    @property
    def name(self) -> str:
        return "header"

    @property
    def quality_score(self) -> float:
        return 0.8

    @property
    def latency_ms(self) -> float:
        return 20.0

    def apply(self, node: DocumentNode, **kwargs: Any) -> ChunkResult:
        """Return the node as-is (structure already preserved by parser).

        Future: could split oversized sections by sub-headings.
        """
        return ChunkResult(nodes=[node], strategy_name=self.name, latency_ms=self.latency_ms)


class SemanticChunkStrategy(ChunkStrategy):
    """Semantic boundary chunking — splits at paragraph / sentence boundaries."""

    @property
    def name(self) -> str:
        return "semantic"

    @property
    def quality_score(self) -> float:
        return 0.9

    @property
    def latency_ms(self) -> float:
        return 100.0

    @property
    def supported_types(self) -> set[str]:
        return {"markdown", "text"}

    def apply(self, node: DocumentNode, **kwargs: Any) -> ChunkResult:
        text = node.raw_text
        max_size = kwargs.get("max_chunk_size", 512)
        nodes: List[DocumentNode] = []
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        current_text = ""
        idx = 0
        for para in paragraphs:
            if len(current_text) + len(para) > max_size and current_text:
                chunk_node = DocumentNode(
                    node_id=f"{node.node_id}_sem_{idx}",
                    source_path=node.source_path,
                    heading_path=node.heading_path + [f"[semantic {idx}]"],
                    level=node.level,
                    raw_text=current_text.strip(),
                    node_type="paragraph",
                    parent=node,
                )
                nodes.append(chunk_node)
                current_text = para
                idx += 1
            else:
                current_text += "\n\n" + para if current_text else para
        if current_text.strip():
            chunk_node = DocumentNode(
                node_id=f"{node.node_id}_sem_{idx}",
                source_path=node.source_path,
                heading_path=node.heading_path + [f"[semantic {idx}]"],
                level=node.level,
                raw_text=current_text.strip(),
                node_type="paragraph",
                parent=node,
            )
            nodes.append(chunk_node)
        return ChunkResult(nodes=nodes, strategy_name=self.name, latency_ms=self.latency_ms)


class LLMChunkStrategy(ChunkStrategy):
    """LLM-assisted chunking — highest quality, requires LLM availability."""

    @property
    def name(self) -> str:
        return "llm"

    @property
    def quality_score(self) -> float:
        return 1.0

    @property
    def latency_ms(self) -> float:
        return 2000.0

    def can_handle(self, context: TaskContext, constraints: RuntimeConstraints) -> bool:
        if not constraints.llm_available:
            return False
        return super().can_handle(context, constraints)

    def apply(self, node: DocumentNode, **kwargs: Any) -> ChunkResult:
        """Stub: returns node as-is.  Real implementation would call LLM."""
        logger.warning("LLMChunkStrategy.apply() is a stub — returns node as-is")
        return ChunkResult(nodes=[node], strategy_name=self.name, latency_ms=self.latency_ms)


class ChunkStrategyRegistry:
    """Pluggable strategy registry for document chunking.

    Can be reused for retrieval strategy, LLM provider selection, etc.
    """

    def __init__(self):
        self._strategies: Dict[str, ChunkStrategy] = {}

    def register(self, strategy: ChunkStrategy) -> None:
        """Register a strategy."""
        self._strategies[strategy.name] = strategy

    def unregister(self, name: str) -> None:
        """Remove a strategy."""
        self._strategies.pop(name, None)

    def get(self, name: str) -> Optional[ChunkStrategy]:
        """Get strategy by name."""
        return self._strategies.get(name)

    def list_strategies(self) -> List[str]:
        """List registered strategy names."""
        return list(self._strategies.keys())

    def select(
        self,
        context: TaskContext,
        constraints: RuntimeConstraints,
    ) -> ChunkStrategy:
        """Select the best strategy given context and constraints.

        Selection logic (from design doc §3.2.4):
            1. Filter by supported_types & latency_budget.
            2. If BayesianOptimizer present, use it.
            3. Default: maximize quality_score / (latency_ms + 1).
        """
        candidates = [
            s for s in self._strategies.values()
            if s.can_handle(context, constraints)
        ]
        if not candidates:
            logger.warning("No viable chunk strategy found — falling back to FixedSizeChunkStrategy")
            return FixedSizeChunkStrategy()

        # Default: quality / latency trade-off
        best = max(candidates, key=lambda s: s.quality_score / (s.latency_ms + 1))
        logger.debug("Selected chunk strategy: %s (score=%.3f, latency=%.1fms)",
                     best.name, best.quality_score, best.latency_ms)
        return best


def default_registry() -> ChunkStrategyRegistry:
    """Factory: create a registry with all built-in strategies pre-registered."""
    reg = ChunkStrategyRegistry()
    reg.register(FixedSizeChunkStrategy())
    reg.register(HeaderChunkStrategy())
    reg.register(SemanticChunkStrategy())
    reg.register(LLMChunkStrategy())
    return reg
