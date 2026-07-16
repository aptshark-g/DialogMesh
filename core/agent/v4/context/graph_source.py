"""ConceptGraphSource: graph-based subgraph compilation for context retrieval.

Multi-tier concept matching:
  Tier 0: Regex concept extraction (built at ingest time, free at query)
  Tier 1: Keyword overlap scoring (fast, good recall)
  Tier 2: Semantic embedding similarity (requires embedder, high precision)
  Tier 3: Co-occurrence graph traversal (BFS subgraph expansion)

Uses existing infrastructure:
  - SemanticEncoder (BGE-small-zh) for Tier 2 embedding
  - VectorStore (SQLite) for embedding cache + fast cosine lookup
  - HybridIndex pattern for weighted merge (semantic × keyword)
"""
from __future__ import annotations
import logging
import math
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np

from core.agent.v4.context.source import (
    ContextSource, ContextItem, _keyword_score, _extract_bundle_text,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Concept graph builder
# ============================================================================

class ConceptGraph:
    """In-memory concept graph with optional semantic embedding support.

    Built from ObservationPool document observations.
    Supports multi-tier seed finding: keyword (fast) → semantic (precise).
    """

    def __init__(self, embedder: Callable[[str], Any] = None):
        self._nodes: Dict[str, dict] = {}
        self._edges: List[dict] = []
        self._embeddings: Dict[str, np.ndarray] = {}  # concept_name -> vector
        self._embedder = embedder
        self._built = False

    @property
    def has_embeddings(self) -> bool:
        return len(self._embeddings) > 0

    def _get_concepts_from_interp(self, interp) -> list:
        if isinstance(interp, dict):
            return interp.get("concepts", [])
        return getattr(interp, "concepts", [])

    def _get_relations_from_interp(self, interp) -> list:
        if isinstance(interp, dict):
            return interp.get("relations", [])
        return getattr(interp, "relations", [])

    def _get_summary_from_interp(self, interp) -> str:
        if isinstance(interp, dict):
            return interp.get("summary", "")
        return getattr(interp, "summary", "")

    def _encode(self, text: str) -> Optional[np.ndarray]:
        if self._embedder is None or not text.strip():
            return None
        try:
            vec = self._embedder.encode(text)
            if isinstance(vec, list):
                vec = np.asarray(vec, dtype=np.float32)
            elif not isinstance(vec, np.ndarray):
                return None
            # BGE returns (1,512) — flatten to (512,)
            if vec.ndim == 2 and vec.shape[0] == 1:
                vec = vec.flatten()
            norm = np.linalg.norm(vec)
            return vec / norm if norm > 0 else vec
        except Exception:
            return None

    def build_from_pool(self, pool) -> int:
        if pool is None:
            return 0
        document_bundles = pool.get_by_domain("document")
        if not document_bundles:
            return 0

        for bundle in document_bundles:
            dom_obs = getattr(bundle, "domain_observations", {}).get("document")
            if dom_obs is None:
                continue
            meta = getattr(dom_obs, "meta", {}) or {}
            source_path = getattr(bundle, "bundle_id", meta.get("source_path", "unknown"))

            # Phase 1: register nodes and explicit relation edges
            for interp in getattr(dom_obs, "interpretations", []):
                concepts = self._get_concepts_from_interp(interp)
                relations = self._get_relations_from_interp(interp)
                raw_text = self._get_summary_from_interp(interp)

                for concept in concepts:
                    c = concept.strip()
                    if not c or len(c) < 3:  # skip too-short tokens
                        continue
                    # Skip noise: code snippets, file paths, URLs, pure digits, CLI commands
                    if any(ch in c for ch in ('/', '\\\\', '://', ':', '|', '{', '}')):
                        continue
                    if c.replace('.', '').replace('-', '').replace('_', '').isdigit():
                        continue
                    if c not in self._nodes:
                        self._nodes[c] = {"relations": [], "observations": [], "docs": set()}
                    node = self._nodes[c]
                    node["observations"].append(raw_text)
                    node["docs"].add(source_path)

                for rel in relations:
                    src = rel.get("source", "") if isinstance(rel, dict) else getattr(rel, "source", "")
                    tgt = rel.get("target", "") if isinstance(rel, dict) else getattr(rel, "target", "")
                    rel_type = rel.get("relation_type", "related_to") if isinstance(rel, dict) else getattr(rel, "relation_type", "related_to")
                    conf = rel.get("confidence", 0.5) if isinstance(rel, dict) else getattr(rel, "confidence", 0.5)
                    if src and tgt:
                        self._edges.append({
                            "source": src, "target": tgt, "type": rel_type,
                            "confidence": conf, "source_doc": source_path,
                        })
                        if src in self._nodes:
                            self._nodes[src]["relations"].append({"target": tgt, "type": rel_type, "confidence": conf})
                        if tgt in self._nodes:
                            self._nodes[tgt]["relations"].append({"target": src, "type": f"rev_{rel_type}", "confidence": conf})

        # Phase 2: co-occurrence edges
        cooccur = set()
        for bundle in document_bundles:
            dom_obs = getattr(bundle, "domain_observations", {}).get("document")
            if dom_obs is None:
                continue
            for interp in getattr(dom_obs, "interpretations", []):
                concepts = self._get_concepts_from_interp(interp)
                cleaned = [c.strip() for c in concepts if c.strip() and len(c.strip()) >= 2]
                for i in range(len(cleaned)):
                    for j in range(i + 1, len(cleaned)):
                        pair = tuple(sorted([cleaned[i], cleaned[j]]))
                        if pair not in cooccur:
                            cooccur.add(pair)
                            for a, b in [(cleaned[i], cleaned[j]), (cleaned[j], cleaned[i])]:
                                if a in self._nodes and b in self._nodes:
                                    self._edges.append({
                                        "source": a, "target": b, "type": "co_occurs",
                                        "confidence": 0.3, "source_doc": source_path,
                                    })
                                    self._nodes[a]["relations"].append({"target": b, "type": "co_occurs", "confidence": 0.3})

        # Phase 3: pre-compute semantic embeddings (Tier 2)
        if self._embedder is not None:
            count = 0
            for name in list(self._nodes.keys()):
                vec = self._encode(name)
                if vec is not None:
                    self._embeddings[name] = vec
                    count += 1
            logger.info("ConceptGraph: %d/%d nodes embedded", count, len(self._nodes))

        self._built = True
        logger.info("ConceptGraph: %d nodes, %d edges (%d co-occurrence), %d embeddings",
                    len(self._nodes), len(self._edges), len(cooccur), len(self._embeddings))
        return len(self._nodes)

    # ---- Multi-tier seed finding ----

    def find_seeds(self, query: str, top_k: int = 5,
                   semantic_weight: float = 0.7, keyword_weight: float = 0.3) -> List[Tuple[str, float]]:
        """Multi-tier seed finding: keyword (Tier 1) + semantic (Tier 2).

        Tier 1: keyword overlap — free, always runs.
        Tier 2: cosine similarity — requires embedder, runs if embeddings available.
        Both scores are weighted and merged.
        """
        query_words = query.lower().split()
        has_semantic = self.has_embeddings and self._embedder is not None

        query_vec = None
        if has_semantic:
            query_vec = self._encode(query)

        scored = []
        for name, node in self._nodes.items():
            # Tier 1: keyword score
            kw = _keyword_score(query_words, name.lower())

            # Tier 2: semantic score
            sem = 0.0
            if query_vec is not None and name in self._embeddings:
                sem = float(np.dot(query_vec, self._embeddings[name]))
                sem = max(0.0, sem)  # cosine ∈ [0, 1] for normalized vectors

            # Weighted merge
            if has_semantic and query_vec is not None:
                score = semantic_weight * sem + keyword_weight * kw
            else:
                score = kw  # pure keyword when no embedder

            # Structural boost: well-connected concepts are more important
            degree = len(node["relations"])
            struct_boost = min(0.3, degree * 0.03)
            score = min(1.0, score + struct_boost)

            if score > 0.01:
                scored.append((name, score))

        # Filter: only consider concepts with connections
        scored = [(n, s) for n, s in scored if len(self._nodes[n]["relations"]) > 0 or s > 0.7]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    # ---- Subgraph expansion ----

    def expand_subgraph(self, seeds: List[str], max_hops: int = 2,
                        max_nodes: int = 30) -> Tuple[Set[str], List[dict]]:
        visited: Set[str] = set()
        edges: List[dict] = []
        frontier = set(seeds)

        for hop in range(max_hops):
            next_frontier = set()
            for node_name in frontier:
                if node_name not in self._nodes:
                    continue
                visited.add(node_name)
                for rel in self._nodes[node_name]["relations"]:
                    target = rel["target"]
                    edges.append({
                        "source": node_name, "target": target,
                        "type": rel["type"], "confidence": rel.get("confidence", 0.5), "hop": hop,
                    })
                    if target not in visited and target not in frontier:
                        next_frontier.add(target)
                if len(visited) + len(next_frontier) >= max_nodes:
                    break
            frontier = next_frontier
            if not frontier or len(visited) >= max_nodes:
                break
        visited.update(frontier)
        return visited, edges

    def compile_context(self, query: str, top_k: int = 10,
                        max_hops: int = 2, max_nodes: int = 30) -> List[ContextItem]:
        if not self._built:
            return []

        seeds = self.find_seeds(query, top_k=3)
        if not seeds:
            return []

        seed_names = [s[0] for s in seeds]
        node_set, edge_list = self.expand_subgraph(seed_names, max_hops, max_nodes)

        items = []
        for node_name in node_set:
            if node_name not in self._nodes:
                continue
            node = self._nodes[node_name]
            parts = [f"[CONCEPT] {node_name}"]
            for i, obs_text in enumerate(node["observations"][:5]):
                parts.append(f"  {obs_text[:300]}")
            parts.append(f"  Sources: {', '.join(list(node['docs'])[:3])}")

            related = []
            for e in edge_list:
                if e["source"] == node_name:
                    related.append(f"→ {e['type']} {e['target']}")
                elif e["target"] == node_name:
                    related.append(f"← {e['type']} {e['source']}")
            if related:
                parts.append(f"  Relations: {'; '.join(related[:8])}")

            content = "\n".join(parts)
            seed_score = next((s[1] for s in seeds if s[0] == node_name), 0.3)
            degree = len(node["relations"])
            relevance = min(1.0, seed_score + min(0.5, degree * 0.1))

            items.append(ContextItem(
                source="graph",
                content={"concept": node_name, "observations": node["observations"]},
                text=content,
                relevance=relevance,
            ))

        items.sort(key=lambda x: x.relevance, reverse=True)
        return items[:top_k]

    def stats(self) -> dict:
        return {
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "embeddings": len(self._embeddings),
            "built": self._built,
        }


# ============================================================================
# ConceptGraphSource
# ============================================================================

class ConceptGraphSource(ContextSource):
    """Graph-based subgraph compilation source with multi-tier matching.

    name="knowledge" — DomainSelector's K domain finds this source.

    Matching tiers:
      Tier 0: Concept extraction (regex) — built at ingest time
      Tier 1: Keyword overlap — always available
      Tier 2: Semantic embedding (BGE) — active when embedder provided
      Tier 3: Co-occurrence graph traversal (BFS expansion)

    Falls back to DocumentSource (keyword) if graph isn't built.
    """

    def __init__(self, observation_pool=None, max_hops: int = 2, max_nodes: int = 30,
                 embedder: Callable[[str], Any] = None,
                 semantic_weight: float = 0.7, keyword_weight: float = 0.3):
        self._pool = observation_pool
        self._graph = ConceptGraph(embedder=embedder)
        self._max_hops = max_hops
        self._max_nodes = max_nodes
        self._semantic_weight = semantic_weight
        self._keyword_weight = keyword_weight

    @property
    def name(self) -> str:
        return "knowledge"

    def build_graph(self) -> int:
        if self._pool is None:
            return 0
        return self._graph.build_from_pool(self._pool)

    def retrieve(self, query: str, top_k: int = 10, **kwargs) -> List[ContextItem]:
        if not self._graph._built:
            self.build_graph()
        if self._graph._built and len(self._graph._nodes) > 0:
            items = self._graph.compile_context(query, top_k=top_k,
                                                max_hops=self._max_hops,
                                                max_nodes=self._max_nodes)
            if items:
                return items
        from core.agent.v4.context.source import DocumentSource
        return DocumentSource(observation_pool=self._pool).retrieve(query, top_k=top_k, **kwargs)

    def stats(self) -> dict:
        return self._graph.stats()
