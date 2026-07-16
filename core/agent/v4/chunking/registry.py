"""ChunkStrategyRegistry: pluggable strategy registry for document chunking.

Extends the general strategy selection framework used by PathAwareScheduler.
Can be reused for retrieval strategy, LLM provider selection, etc.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TaskContext:
    """Context describing the current ingestion task."""

    source_path: str = ""
    file_type: str = ""
    content_length: int = 0
    heading_depth: int = 0
    priority: int = 0


@dataclass
class RuntimeConstraints:
    """Runtime constraints that influence strategy selection."""

    latency_budget_ms: float = 5000.0
    quality_threshold: float = 0.7
    max_chunk_size: int = 2048
    min_chunk_size: int = 128
    allow_llm: bool = True


@dataclass
class StrategyMetadata:
    """Metadata for a registered strategy."""

    name: str
    supported_types: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    quality_score: float = 0.0
    config: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class ChunkStrategy(ABC):
    """Abstract base for document chunking strategies.

    Each strategy implements a different trade-off between speed and quality.
    """

    def __init__(self, metadata: Optional[StrategyMetadata] = None):
        self.metadata = metadata or StrategyMetadata(name=self.__class__.__name__)

    @abstractmethod
    def chunk(self, text: str, context: TaskContext) -> List[str]:
        """Split *text* into chunks according to this strategy.

        Args:
            text: Raw document text to chunk.
            context: Task context for adaptive behaviour.

        Returns:
            List of text chunks.
        """
        ...

    @abstractmethod
    def supports(self, file_type: str) -> bool:
        """Return ``True`` if this strategy can handle *file_type*."""
        ...

    def estimate_latency(self, content_length: int) -> float:
        """Estimate latency (ms) for *content_length* characters."""
        return self.metadata.latency_ms

    def estimate_quality(self, context: TaskContext) -> float:
        """Estimate quality score [0, 1] for *context*."""
        return self.metadata.quality_score


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ChunkStrategyRegistry:
    """Pluggable strategy registry for document chunking.

    NOT just for chunking — general strategy selection framework.
    Can be reused for retrieval strategy, LLM provider selection, etc.
    """

    def __init__(self, optimizer: Optional[Any] = None):
        self._strategies: Dict[str, ChunkStrategy] = {}
        self._optimizer = optimizer

    def register(self, strategy: ChunkStrategy) -> None:
        """Register a *strategy* under its metadata name."""
        name = strategy.metadata.name
        if name in self._strategies:
            logger.warning("Overwriting existing strategy: %s", name)
        self._strategies[name] = strategy
        logger.debug("Registered chunk strategy: %s", name)

    def unregister(self, name: str) -> None:
        """Remove strategy *name* from the registry."""
        if name not in self._strategies:
            logger.warning("Strategy not found for unregister: %s", name)
            return
        del self._strategies[name]
        logger.debug("Unregistered chunk strategy: %s", name)

    def get(self, name: str) -> Optional[ChunkStrategy]:
        """Retrieve strategy by *name*."""
        return self._strategies.get(name)

    def list_strategies(self) -> List[str]:
        """Return names of all registered strategies."""
        return list(self._strategies.keys())

    def select(
        self,
        task: TaskContext,
        constraints: Optional[RuntimeConstraints] = None,
    ) -> ChunkStrategy:
        """Select the best strategy for *task* under *constraints*.

        Selection logic (in order):

        1. Filter by supported file type and latency budget.
        2. If a BayesianOptimizer is attached, use its quality prediction.
        3. Fallback: maximise quality / (latency + 1).

        Args:
            task: Current ingestion task context.
            constraints: Runtime constraints (defaults to generous defaults).

        Returns:
            The selected ``ChunkStrategy``.

        Raises:
            ValueError: No strategy matches the constraints.
        """
        constraints = constraints or RuntimeConstraints()

        candidates: List[ChunkStrategy] = []
        for strategy in self._strategies.values():
            if not strategy.supports(task.file_type):
                continue
            est_latency = strategy.estimate_latency(task.content_length)
            if est_latency > constraints.latency_budget_ms:
                continue
            candidates.append(strategy)

        if not candidates:
            raise ValueError(
                f"No chunk strategy matches task={task} constraints={constraints}"
            )

        # BayesianOptimizer weighted selection
        if self._optimizer is not None:
            try:
                scores = self._optimizer.predict_quality(
                    [c.metadata.name for c in candidates], task
                )
                best = max(candidates, key=lambda c: scores.get(c.metadata.name, 0.0))
                logger.debug("Optimizer selected strategy: %s", best.metadata.name)
                return best
            except Exception as e:
                logger.warning("Optimizer selection failed: %s; falling back", e)

        # Default: quality / latency trade-off
        def _score(strategy: ChunkStrategy) -> float:
            quality = strategy.estimate_quality(task)
            latency = strategy.estimate_latency(task.content_length)
            return quality / (latency + 1.0)

        best = max(candidates, key=_score)
        logger.debug("Fallback selected strategy: %s", best.metadata.name)
        return best

    def __len__(self) -> int:
        return len(self._strategies)

    def __contains__(self, name: str) -> bool:
        return name in self._strategies
