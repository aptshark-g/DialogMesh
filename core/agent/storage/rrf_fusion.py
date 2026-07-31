"""RRF (Reciprocal Rank Fusion) for hybrid vector + graph retrieval.

Merges ChromaDB vector search results with RelationGraph traversal results.
Algorithm: rank-based reciprocal fusion — no parameter tuning needed.

Design: ARCHITECTURE_AUDIT §12-C, OPENSOURCE_DEEP_READ §2+3.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# Default RRF constant — from TREC best practices
RRF_K = 60


def reciprocal_rank_fusion(
    vector_results: List[Tuple[str, float]],
    graph_results: List[str],
    k: int = RRF_K,
    top_n: int = 10,
) -> List[Tuple[str, float]]:
    """Fuse vector and graph results using RRF.

    Args:
        vector_results: [(block_id, similarity_score), ...] from ChromaDB
        graph_results: [entity_id, ...] from RelationGraph.traverse()
        k: RRF constant (default 60, from TREC)
        top_n: number of results to return

    Returns:
        [(block_id, fused_score), ...] sorted by score descending
    """
    scores: Dict[str, float] = {}

    # Vector results — higher rank = higher RRF score
    for rank, (block_id, _) in enumerate(vector_results):
        scores[block_id] = scores.get(block_id, 0) + 1.0 / (k + rank + 1)

    # Graph results — all get same base score (graph has no ranking)
    for entity_id in graph_results:
        scores[entity_id] = scores.get(entity_id, 0) + 1.0 / k

    # Sort by score descending
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked[:top_n]


def fused_retrieve(
    query: str,
    chunk_store,
    relation_graph,
    top_k: int = 10,
    graph_depth: int = 2,
) -> List[Tuple[str, float]]:
    """Hybrid retrieval: vector search → graph traversal → RRF fusion.

    Pipeline:
      1. ChromaDB vector search on query
      2. Top 5 vector results → graph traversal (find connected entities)
      3. RRF fusion of vector + graph results

    Args:
        query: Search query text
        chunk_store: ChunkStore instance (ChromaDB)
        relation_graph: RelationGraph instance
        top_k: Number of results to return
        graph_depth: BFS depth for graph traversal

    Returns:
        [(block_id, fused_score), ...]
    """
    # Vector search
    atoms = chunk_store.search(query, top_k=20)
    vector_results = [(a.block_id, a.priority) for a in atoms if a.block_id]

    # Graph traversal from top vector hits
    graph_results: List[str] = []
    for block_id, _ in vector_results[:5]:
        if block_id:
            entities = relation_graph.traverse(block_id, depth=graph_depth)
            graph_results.extend(entities)

    # Dedup graph results
    graph_results = list(set(graph_results))

    # RRF fusion
    return reciprocal_rank_fusion(
        vector_results=vector_results,
        graph_results=graph_results,
        top_n=top_k,
    )
