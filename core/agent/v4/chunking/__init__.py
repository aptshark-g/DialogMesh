"""Chunking module: registry + strategies for Document Ingestion Layer."""
from .strategies import (
    ChunkStrategy,
    ChunkStrategyRegistry,
    RuntimeConstraints,
    TaskContext,
    FixedSizeChunkStrategy,
    HeaderChunkStrategy,
    LLMChunkStrategy,
    SemanticChunkStrategy,
    default_registry,
)

__all__ = [
    # Registry
    "ChunkStrategy",
    "ChunkStrategyRegistry",
    "RuntimeConstraints",
    "TaskContext",
    # Strategies
    "FixedSizeChunkStrategy",
    "HeaderChunkStrategy",
    "SemanticChunkStrategy",
    "LLMChunkStrategy",
    "default_registry",
]
