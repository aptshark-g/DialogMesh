"""Index builder with 20% rebuild trigger threshold."""
from typing import List
import numpy as np

from .models import EmbeddingConfig
from .composite_embedder import CompositeEmbedder
from .prototype_manager import PrototypeManager


class IndexBuilder:
    """Build and maintain a vector index for behavior embeddings.
    Rebuilds when cumulative delta exceeds 20% of index size.
    """

    REBUILD_THRESHOLD = 0.20

    def __init__(self, config: EmbeddingConfig = None, composite: CompositeEmbedder = None):
        self.cfg = config or EmbeddingConfig()
        self._composite = composite or CompositeEmbedder(self.cfg)
        self._index: np.ndarray = np.zeros((0, self.cfg.dimension), dtype=np.float32)
        self._keys: List[str] = []
        self._delta_count = 0

    def add(self, key: str, action: str, action_type: str = ""):
        emb = self._composite.embed(action, action_type).vector
        if self._index.shape[0] == 0:
            self._index = emb.reshape(1, -1)
            self._keys = [key]
        else:
            self._index = np.vstack([self._index, emb])
            self._keys.append(key)
        self._delta_count += 1
        if self._should_rebuild():
            self.rebuild()

    def search(self, query_action: str, action_type: str = "", top_k: int = 5) -> List[str]:
        if self._index.shape[0] == 0:
            return []
        qvec = self._composite.embed(query_action, action_type).vector
        sims = np.array([
            PrototypeManager.cosine_sim(qvec, self._index[i])
            for i in range(self._index.shape[0])
        ])
        top_idx = np.argsort(sims)[::-1][:top_k]
        return [self._keys[i] for i in top_idx if sims[i] >= self.cfg.cosine_threshold]

    def _should_rebuild(self) -> bool:
        if self._index.shape[0] == 0:
            return False
        return (self._delta_count / max(self._index.shape[0], 1)) >= self.REBUILD_THRESHOLD

    def rebuild(self):
        """Normalize index and reset delta counter."""
        if self._index.shape[0] == 0:
            return
        norms = np.linalg.norm(self._index, axis=1, keepdims=True)
        norms = np.where(norms < 1e-10, 1.0, norms)
        self._index = self._index / norms
        self._delta_count = 0

    def stats(self) -> dict:
        return {
            "size": self._index.shape[0],
            "dimension": self.cfg.dimension,
            "delta_count": self._delta_count,
            "threshold": self.REBUILD_THRESHOLD,
        }
