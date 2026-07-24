"""RAG + Graph — multi-threaded parallel anchor expansion.

HNSW search → parallel 2-hop graph expansion per anchor → merge + dedup.
"""

from __future__ import annotations
from typing import List, Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

logger = logging.getLogger(__name__)


class RAGraphBridge:
    """RAG anchoring + parallel graph expansion.

    Usage:
        bridge = RAGraphBridge(hnsw_index, entity_graph, embedding_fn)
        context = bridge.retrieve("AES密钥问题")
    """

    def __init__(self, hnsw_index=None, entity_graph=None, embedding_fn=None,
                 max_hops: int = 2, top_k_anchors: int = 5, max_workers: int = 4):
        self.hnsw = hnsw_index
        self.graph = entity_graph
        self.embed = embedding_fn
        self.max_hops = max_hops
        self.top_k = top_k_anchors
        self.max_workers = max_workers
        
        # Name index: avoid O(n²) lookups
        self._name_index: Dict[str, Any] = {}

    def _build_name_index(self):
        """Build entity name → node index for O(1) lookups."""
        if self._name_index:
            return
        for n in getattr(self.graph, 'nodes', {}).values():
            name = getattr(n, 'name', '')
            if name:
                self._name_index[name] = n

    def _get_node(self, node_id: str) -> Optional[Any]:
        """O(1) node lookup via name index + graph.get()."""
        # Direct graph get
        if hasattr(self.graph, 'get'):
            node = self.graph.get(node_id)
            if node:
                return node
        # Name index fallback
        self._build_name_index()
        return self._name_index.get(node_id)

    def retrieve(self, query: str, token_budget: int = 2000) -> dict:
        """RAG anchor → parallel graph expand → merge context."""
        if not self.hnsw or not self.graph or not self.embed:
            return {"anchors": [], "expanded_entities": [], "context": ""}

        # ── RAG: vector search for anchors ──
        try:
            vec = self.embed(query)
            anchors = self.hnsw.search(vec, self.top_k)
        except Exception as e:
            logger.debug("HNSW search failed: %s", e)
            return {"anchors": [], "expanded_entities": [], "context": ""}

        # ── Parallel graph expansion per anchor ──
        seen = set()
        all_results: List[Dict] = []

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(anchors))) as pool:
            futures = {}
            for node_id, score in anchors:
                if node_id in seen:
                    continue
                seen.add(node_id)
                futures[pool.submit(self._expand_anchor, node_id, score)] = (node_id, score)

            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        all_results.append(result)
                except Exception as e:
                    logger.debug("Anchor expansion failed: %s", e)

        # ── Merge: dedup + score-weighted ordering ──
        merged = self._merge_results(all_results, token_budget)
        return merged

    def _expand_anchor(self, node_id: str, score: float) -> Optional[dict]:
        """Expand one anchor: get node + 2-hop neighbors."""
        node = self._get_node(node_id)
        if not node:
            return None

        parts = []
        seen_local = {node_id}
        
        # Anchor node
        parts.append(self._format_node(node, score, depth=0, name_override=node_id))

        # 2-hop expansion
        relations = getattr(node, 'get_relations', lambda *a, **kw: [])(max_hops=self.max_hops)
        for rel in (relations if isinstance(relations, list) else [])[:5]:
            target = rel.get("target") if isinstance(rel, dict) else getattr(rel, 'target', None)
            if target and target not in seen_local:
                seen_local.add(target)
                target_node = self._get_node(target)
                parts.append(self._format_node(
                    target_node or target, 0, depth=1,
                    name_override=target,
                    relation=rel.get("kind", "") if isinstance(rel, dict) else ""
                ))

        return {
            "anchor": node_id,
            "score": score,
            "parts": parts,
            "entities": list(seen_local),
        }

    def _merge_results(self, results: List[dict], token_budget: int) -> dict:
        """Merge parallel results: dedup entities, score-weighted context."""
        all_anchors = []
        all_entities = set()
        scored_parts = []  # (priority, text)

        for r in results:
            all_anchors.append(r["anchor"])
            all_entities.update(r["entities"])
            base_prio = int(r["score"] * 100)
            for i, part in enumerate(r.get("parts", [])):
                priority = base_prio - i  # earlier parts higher priority
                scored_parts.append((priority, part))

        # Sort by priority (highest first)
        scored_parts.sort(key=lambda x: -x[0])

        # Build context within budget
        context_parts = []
        total_chars = 0
        for prio, part in scored_parts:
            if total_chars + len(part) > token_budget:
                break
            context_parts.append(part)
            total_chars += len(part) + 1

        return {
            "anchors": all_anchors,
            "expanded_entities": list(all_entities),
            "context": "\n".join(context_parts),
            "anchor_count": len(results),
        }

    def _format_node(self, node, score: float, depth: int, 
                     relation: str = "", name_override: str = "") -> str:
        """Format a node for LLM context."""
        name = name_override or getattr(node, 'name', '') or str(node)
        summary = getattr(node, 'summary', '') or '' if not isinstance(node, str) else ''

        if depth == 0:
            return f"[★ anchor · score={score:.2f}] {name}: {summary[:120]}"
        else:
            rel = f" ({relation})" if relation else ""
            return f"[depth={depth}{rel}] {name}: {summary[:100]}"

    def index_entity(self, entity_name: str, text: str, metadata: dict = None):
        """Index an entity for future RAG retrieval."""
        if not self.hnsw or not self.embed:
            return
        try:
            vec = self.embed(text)
            self.hnsw.add(entity_name, vec)
            if hasattr(self.hnsw, 'build'):
                self.hnsw.build()
        except Exception as e:
            logger.debug("Index entity failed: %s", e)
