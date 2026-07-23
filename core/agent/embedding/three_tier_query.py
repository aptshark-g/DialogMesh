"""Three-tier weight query: exact match → semantic neighbors → LLM fallback."""
from typing import List, Tuple, Optional
import numpy as np

from .models import NeighborResult, EmbeddingConfig
from .composite_embedder import CompositeEmbedder
from .prototype_manager import PrototypeManager


class ThreeTierWeightQuery:
    """Query behavior weight with three-tier fallback."""

    def __init__(self, config: EmbeddingConfig = None, composite: CompositeEmbedder = None):
        self.cfg = config or EmbeddingConfig()
        self._composite = composite or CompositeEmbedder(self.cfg)
        self._prototypes = self._composite._prototypes
        self._llm = None

    def set_llm_fallback(self, llm_provider):
        self._llm = llm_provider

    def query_weight(
        self,
        from_action: str,
        to_action: str,
        behavior_graph: dict,
        action_type: str = "",
    ) -> Tuple[Optional[float], str]:
        """Return (weight, source). Source is 'exact', 'neighbor', or 'llm'."""
        # Tier 1: exact match in behavior_graph
        edge_key = f"{from_action}::{to_action}"
        edges = behavior_graph.get("edges", {}) if isinstance(behavior_graph, dict) else {}
        if edge_key in edges:
            e = edges[edge_key]
            w = e.get("weight", 0.0) if isinstance(e, dict) else getattr(e, "weight", 0.0)
            return (float(w), "exact")

        # Tier 2: semantic neighbors
        qvec = self._composite.embed(from_action, action_type).vector
        tvec = self._composite.embed(to_action, action_type).vector
        neighbors = self._find_semantic_neighbors(qvec, tvec, behavior_graph)
        if neighbors:
            avg_w = sum(n.score for n in neighbors) / len(neighbors)
            return (avg_w, "neighbor")

        # Tier 3: LLM fallback
        if self._llm and hasattr(self._llm, "generate"):
            try:
                prompt = f'Rate causal likelihood P("{to_action}" | "{from_action}") 0.0-1.0. Return only a number.'
                raw = self._llm.generate(prompt, max_tokens=10)
                w = float(raw.strip())
                return (max(0.0, min(1.0, w)), "llm")
            except Exception:
                pass
        return (None, "none")

    def _find_semantic_neighbors(
        self, qvec: np.ndarray, tvec: np.ndarray, behavior_graph: dict
    ) -> List[NeighborResult]:
        """Find top-K semantic neighbors in behavior graph edges."""
        results: List[NeighborResult] = []
        edges = behavior_graph.get("edges", {}) if isinstance(behavior_graph, dict) else {}
        for i, (ek, e) in enumerate(edges.items()):
            if not isinstance(e, dict):
                continue
            # Simple heuristic: compare from/to action summaries via embedding
            from_text = e.get("from", "")
            to_text = e.get("to", "")
            if not from_text or not to_text:
                continue
            e_from = self._composite.embed(from_text).vector
            e_to = self._composite.embed(to_text).vector
            sim = (PrototypeManager.cosine_sim(qvec, e_from) +
                   PrototypeManager.cosine_sim(tvec, e_to)) / 2.0
            if sim >= self.cfg.cosine_threshold:
                w = e.get("weight", 0.0)
                results.append(NeighborResult(score=sim * w, index=i, text=ek))
        results.sort(key=lambda x: -x.score)
        return results[:3]
