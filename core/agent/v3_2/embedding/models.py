"""Embedding layer data models."""
from dataclasses import dataclass, field
from typing import Optional, List
import numpy as np


@dataclass
class BehaviorEmbedding:
    """A behavior embedding vector with metadata."""
    vector: np.ndarray = field(default_factory=lambda: np.zeros(384, dtype=np.float32))
    action_type: str = ""
    predicate_class: str = ""
    argument_class: str = ""
    raw_text: str = ""

    def __post_init__(self):
        if self.vector is None:
            self.vector = np.zeros(384, dtype=np.float32)


@dataclass
class NeighborResult:
    """Result of a semantic neighbor query."""
    score: float = 0.0
    index: int = 0
    text: str = ""


@dataclass
class EmbeddingConfig:
    """Configuration for the embedding pipeline."""
    model_path: str = ""
    dimension: int = 384
    use_gpu: bool = False
    cache_size: int = 1000
    cosine_threshold: float = 0.6
    max_rules: int = 50
