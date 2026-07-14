"""StructuralContextCompiler: embedding-based subgraph compilation from World Model.

Replaces Phase 4 keyword-based stub with embedding-driven intent-to-subgraph mapping.
Uses the v3.2 embedding infrastructure (composite_embedder, index_builder) for
semantic matching between user intent and graph nodes.

Design ref: docs/v3.0/DESIGN_V4_KNOWLEDGE_REFINEMENT.md §3.2
"""
from __future__ import annotations
import logging
from typing import Dict, List, Optional, Tuple

from core.agent.v4.world.schema import (
    StructuralWorldGraph, SubgraphResult, ReferenceUnit, StructuralEdge,
)

logger = logging.getLogger(__name__)


class StructuralContextCompiler:
    """Compile a local subgraph from the World Model for a given intent.

    Embedding-based implementation:
    1. Encode intent text to embedding vector
    2. Semantic search against graph node embeddings (or fallback to keyword)
    3. Expand from semantic seeds via BFS with backbone prioritization
    4. Apply token budget constraints
    """

    def __init__(
        self,
        fallback_seed_count: int = 5,
        semantic_seed_count: int = 10,
        token_base: int = 500,
        token_per_node: int = 5,
        backbone_top_n: int = 10,
        embedding_dim: int = 768,
        similarity_threshold: float = 0.5,
    ):
        self._fallback_seed_count = fallback_seed_count
        self._semantic_seed_count = semantic_seed_count
        self._token_base = token_base
        self._token_per_node = token_per_node
        self._backbone_top_n = backbone_top_n
        self._embedding_dim = embedding_dim
        self._similarity_threshold = similarity_threshold

        # Lazy-loaded embedder
        self._embedder = None
        self._node_embeddings: Dict[str, List[float]] = {}

    # ---- Public API ----

    def compile_subgraph(
        self,
        graph: StructuralWorldGraph,
        intent: str = "",
        max_nodes: int = 300,
    ) -> SubgraphResult:
        """Cut a local subgraph for the given intent.

        Args:
            graph: The full StructuralWorldGraph.
            intent: User/agent intent string for relevance matching.
            max_nodes: Maximum nodes in the returned subgraph.

        Returns:
            SubgraphResult with nodes, edges, backbone units, and token estimate.
        """
        if graph.node_count == 0:
            return SubgraphResult()

        # Step 1: Find intent-relevant seed nodes (embedding-based)
        seeds = self._find_seeds(graph, intent)

        # Step 2: Expand from seeds via BFS until max_nodes
        subgraph_nodes = self._expand_from_seeds(graph, seeds, max_nodes)

        # Step 3: Collect edges among subgraph nodes
        subgraph_node_ids = {u.unit_id for u in subgraph_nodes}
        subgraph_edges = [
            e for e in graph.edges
            if e.source_id in subgraph_node_ids and e.target_id in subgraph_node_ids
        ]

        # Step 4: Identify backbone units in subgraph
        backbone_units = sorted(
            subgraph_node_ids,
            key=lambda uid: graph.backbone.get(uid, 0.0),
            reverse=True,
        )[:self._backbone_top_n]

        # Step 5: Estimate tokens
        token_estimate = min(2000, self._token_base + len(subgraph_nodes) * self._token_per_node)

        logger.info(
            "Compiled subgraph: %d nodes, %d edges, %d backbone, ~%d tokens",
            len(subgraph_nodes), len(subgraph_edges), len(backbone_units), token_estimate,
        )

        return SubgraphResult(
            nodes=subgraph_nodes,
            edges=subgraph_edges,
            backbone_units=backbone_units,
            total_tokens_estimate=token_estimate,
        )

    def build_node_embeddings(self, graph: StructuralWorldGraph) -> Dict[str, List[float]]:
        """Pre-compute embeddings for all nodes in the graph.

        Call this after graph construction for fast semantic search.
        """
        embedder = self._get_embedder()
        if embedder is None:
            logger.warning("No embedder available, skipping embedding build")
            return {}

        self._node_embeddings = {}
        for uid, unit in graph.units.items():
            text = f"{unit.name} {unit.unit_type} {unit.language}"
            try:
                emb = embedder.embed(text)
                self._node_embeddings[uid] = emb.tolist() if hasattr(emb, "tolist") else list(emb)
            except Exception as e:
                logger.debug("Failed to embed node %s: %s", uid, e)

        logger.info("Built embeddings for %d/%d nodes", len(self._node_embeddings), graph.node_count)
        return self._node_embeddings

    # ---- Private: Seed Finding ----

    def _find_seeds(
        self, graph: StructuralWorldGraph, intent: str
    ) -> List[str]:
        """Find seed nodes matching the intent.

        Priority:
        1. Embedding-based semantic search (if embeddings available)
        2. Keyword-based fallback (if no embeddings or embedder unavailable)
        3. Top backbone nodes (if no intent provided)
        """
        if not intent:
            return self._fallback_seeds(graph)

        # Try embedding-based search first
        if self._node_embeddings:
            semantic_seeds = self._semantic_search(graph, intent)
            if semantic_seeds:
                return semantic_seeds

        # Fallback to keyword matching
        return self._keyword_search(graph, intent)

    def _semantic_search(
        self, graph: StructuralWorldGraph, intent: str
    ) -> List[str]:
        """Embedding-based semantic search against pre-computed node embeddings."""
        embedder = self._get_embedder()
        if embedder is None or not self._node_embeddings:
            return []

        try:
            intent_emb = embedder.embed(intent)
            intent_vec = intent_emb.tolist() if hasattr(intent_emb, "tolist") else list(intent_emb)
        except Exception as e:
            logger.debug("Failed to embed intent: %s", e)
            return []

        # Cosine similarity against all node embeddings
        scored: List[Tuple[str, float]] = []
        for uid, node_emb in self._node_embeddings.items():
            sim = _cosine_similarity(intent_vec, node_emb)
            if sim >= self._similarity_threshold:
                # Boost by backbone score
                backbone_bonus = graph.backbone.get(uid, 0.0) * 0.2
                scored.append((uid, sim + backbone_bonus))

        scored.sort(key=lambda x: x[1], reverse=True)
        seeds = [uid for uid, _ in scored[:self._semantic_seed_count]]
        logger.debug("Semantic search: %d seeds from %d candidates", len(seeds), len(scored))
        return seeds

    def _keyword_search(
        self, graph: StructuralWorldGraph, intent: str
    ) -> List[str]:
        """Keyword-based fallback matching."""
        keywords = intent.lower().split()
        scored: List[Tuple[str, float]] = []

        for uid, unit in graph.units.items():
            name_lower = unit.name.lower()
            match_count = sum(1 for kw in keywords if kw in name_lower)
            if match_count > 0 or any(kw in uid.lower() for kw in keywords):
                backbone_bonus = graph.backbone.get(uid, 0.0)
                scored.append((uid, match_count + backbone_bonus))

        scored.sort(key=lambda x: x[1], reverse=True)
        seeds = [uid for uid, _ in scored[:self._semantic_seed_count]]
        logger.debug("Keyword search: %d seeds", len(seeds))
        return seeds

    def _fallback_seeds(self, graph: StructuralWorldGraph) -> List[str]:
        """No intent: use top backbone nodes as seeds."""
        sorted_backbone = sorted(
            graph.backbone.items(), key=lambda x: x[1], reverse=True
        )
        seeds = [uid for uid, _ in sorted_backbone[:self._fallback_seed_count]]
        if not seeds:
            seeds = [
                uid for uid, u in graph.units.items()
                if u.unit_type == "file"
            ][:5]
        return seeds

    # ---- Private: Expansion ----

    def _expand_from_seeds(
        self, graph: StructuralWorldGraph, seeds: List[str], max_nodes: int
    ) -> List[ReferenceUnit]:
        """BFS expand from seed nodes until max_nodes reached.

        Expansion prioritizes:
        1. Backbone score (structural importance)
        2. Edge weight (relationship strength)
        3. Node type (files > classes > functions)
        """
        if not seeds:
            sorted_ids = sorted(
                graph.units.keys(),
                key=lambda uid: graph.backbone.get(uid, 0.0),
                reverse=True,
            )
            return [graph.units[uid] for uid in sorted_ids[:max_nodes]]

        visited: set[str] = set()
        queue: List[str] = list(seeds)
        result: List[ReferenceUnit] = []

        while queue and len(result) < max_nodes:
            # Sort queue by priority before popping
            queue.sort(
                key=lambda nid: (
                    graph.backbone.get(nid, 0.0),
                    self._node_type_priority(graph.units.get(nid)),
                ),
                reverse=True,
            )

            uid = queue.pop(0)
            if uid in visited or uid not in graph.units:
                continue
            visited.add(uid)
            result.append(graph.units[uid])

            if len(result) >= max_nodes:
                break

            # Add neighbors prioritized by edge weight + backbone
            neighbors = graph.get_neighbors(uid)
            neighbor_scores: Dict[str, float] = {}
            for nid in neighbors:
                if nid in visited:
                    continue
                # Score = backbone + max edge weight
                edges = [e for e in graph.get_edges_for(uid) if e.target_id == nid or e.source_id == nid]
                max_weight = max((e.effective_weight() for e in edges), default=0.0)
                neighbor_scores[nid] = graph.backbone.get(nid, 0.0) + max_weight

            sorted_neighbors = sorted(neighbor_scores.items(), key=lambda x: x[1], reverse=True)
            for nid, _ in sorted_neighbors:
                if nid not in visited and nid not in queue:
                    queue.append(nid)

        return result

    # ---- Private: Helpers ----

    def _get_embedder(self):
        """Lazy-load the composite embedder."""
        if self._embedder is not None:
            return self._embedder

        try:
            from core.agent.v3_2.embedding.composite_embedder import CompositeEmbedder
            self._embedder = CompositeEmbedder()
            logger.info("Loaded CompositeEmbedder for semantic search")
            return self._embedder
        except ImportError as e:
            logger.warning("CompositeEmbedder not available: %s", e)
            return None
        except Exception as e:
            logger.warning("Failed to load embedder: %s", e)
            return None

    @staticmethod
    def _node_type_priority(unit: Optional[ReferenceUnit]) -> int:
        """Priority score for node types during expansion."""
        if unit is None:
            return 0
        priorities = {
            "file": 4,
            "module": 3,
            "class": 2,
            "function": 1,
            "variable": 0,
        }
        return priorities.get(unit.unit_type, 0)


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
