"""ContentIndex — unified retrieval hub for all knowledge domains.

Design ref: docs/v3.0/DESIGN_V4_CONTEXT_ENGINEERING.md §4.4

Replaces the ad-hoc collection of ContextSources with a single query interface.
Routes to keyword (Tier 1), graph (Tier 2), or hybrid backend.

Layers:
  Keyword: per-paragraph keyword match against ingested docs
  Graph:   BFS subgraph compilation from concept graph
  Hybrid:  keyword + graph merged by relevance
"""
from __future__ import annotations
import logging
from typing import List

from core.agent.v4.context.source import ContextItem, _keyword_score
from core.agent.v4.context.graph_source import ConceptGraph

logger = logging.getLogger(__name__)


class ContentIndex:
    """Unified content index spanning document pool + concept graph."""

    def __init__(self, observation_pool=None):
        self._pool = observation_pool
        self._graph = ConceptGraph()
        self._built = False

    def build(self) -> dict:
        """Build all indexes. Call after pool is populated with documents."""
        if self._pool is None:
            return {"status": "no_pool"}
        n = self._graph.build_from_pool(self._pool)
        self._built = True
        stats = {"graph_nodes": n, "graph_edges": len(self._graph._edges)}
        logger.info("ContentIndex built: %s", stats)
        return stats

    def query(self, text: str, top_k: int = 10,
              strategy: str = "hybrid") -> List[ContextItem]:
        """Unified query routing.

        strategy: "keyword" | "graph" | "hybrid" (default)
        """
        if strategy == "keyword":
            return self._keyword_query(text, top_k)
        elif strategy == "graph":
            return self._graph_query(text, top_k)
        else:
            kw = self._keyword_query(text, top_k // 2 + 1)
            gr = self._graph_query(text, top_k // 2 + 1)
            merged = kw + gr
            merged.sort(key=lambda x: x.relevance, reverse=True)
            return merged[:top_k]

    # ---- backends ----

    def _keyword_query(self, text: str, top_k: int) -> List[ContextItem]:
        """Per-paragraph keyword match (Tier 1)."""
        if self._pool is None:
            return []
        query_words = text.lower().split()
        seen_ids = set()
        items: List[ContextItem] = []

        for domain in self._pool.stats().get("by_domain", {}):
            bundles = self._pool.get_by_domain(domain)
            for bundle in bundles:
                if bundle.bundle_id in seen_ids:
                    continue
                seen_ids.add(bundle.bundle_id)

                best_score = 0.0
                scored_paras: List[tuple] = []
                for dom_obs in getattr(bundle, "domain_observations", {}).values():
                    for interp in getattr(dom_obs, "interpretations", []):
                        if isinstance(interp, dict):
                            summary = interp.get("summary", "")
                        else:
                            summary = getattr(interp, "summary", "")
                        if not summary or len(summary) < 15:
                            continue
                        s = _keyword_score(query_words, summary)
                        if s > best_score:
                            best_score = s
                        if s > 0:
                            scored_paras.append((s, summary))
                if best_score < 0.25:
                    continue
                scored_paras.sort(key=lambda x: x[0], reverse=True)
                context_text = " | ".join(p[1][:300] for p in scored_paras[:3])
                items.append(ContextItem(
                    source="keyword", content=bundle, text=context_text,
                    relevance=best_score,
                    metadata={"bundle_id": bundle.bundle_id, "domain": domain},
                ))

        items.sort(key=lambda x: x.relevance, reverse=True)
        return items[:top_k]

    def _graph_query(self, text: str, top_k: int) -> List[ContextItem]:
        """BFS subgraph compilation (Tier 2)."""
        if not self._built:
            return []
        seeds = self._graph.find_seeds(text, top_k=3)
        if not seeds:
            return []
        seed_names = [s[0] for s in seeds]
        node_set, edge_list = self._graph.expand_subgraph(
            seed_names, max_hops=1, max_nodes=15)

        items = []
        for node_name in node_set:
            if node_name not in self._graph._nodes:
                continue
            node = self._graph._nodes[node_name]
            parts = [f"[CONCEPT] {node_name}"]
            for obs in node["observations"][:3]:
                parts.append(f"  {obs[:250]}")
            docs = list(node["docs"])[:3]
            if docs:
                parts.append(f"  Sources: {', '.join(docs)}")
            related = []
            for e in edge_list:
                if e["source"] == node_name:
                    related.append(f"-> {e['type']} {e['target']}")
                elif e["target"] == node_name:
                    related.append(f"<- {e['type']} {e['source']}")
            if related:
                parts.append(f"  Relations: {'; '.join(related[:6])}")
            seed_score = next((s[1] for s in seeds if s[0] == node_name), 0.3)
            relevance = min(1.0, seed_score + min(0.3, len(node["relations"]) * 0.05))
            items.append(ContextItem(
                source="graph",
                content={"concept": node_name},
                text="\n".join(parts),
                relevance=relevance,
            ))
        items.sort(key=lambda x: x.relevance, reverse=True)
        return items[:top_k]

    @property
    def graph_stats(self) -> dict:
        return self._graph.stats() if self._built else {}

    @property
    def pool_stats(self) -> dict:
        return self._pool.stats() if self._pool else {}
