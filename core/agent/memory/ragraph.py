"""Phase 0 — RAG + Graph integration bridge.

Connects: HNSW vector search → EntityNode → 2-hop graph diffusion → context assembly.
"""

from __future__ import annotations
from typing import List, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


class RAGraphBridge:
    """RAG anchoring + graph expansion for context retrieval.

    Usage:
        bridge = RAGraphBridge(hnsw_index, entity_graph, embedding_fn)
        context = bridge.retrieve("上次AES密钥问题怎么解决的")
        # → {anchor: "AES_KEY_ROTATION_v2", entities: [...], context: "..."}
    """

    def __init__(self, hnsw_index=None, entity_graph=None, embedding_fn=None,
                 max_hops: int = 2, top_k_anchors: int = 5):
        self.hnsw = hnsw_index
        self.graph = entity_graph
        self.embed = embedding_fn  # text → 768d vector
        self.max_hops = max_hops
        self.top_k = top_k_anchors

    def retrieve(self, query: str, token_budget: int = 2000) -> dict:
        """RAG anchor → graph expand → context.

        Returns: {anchors: [...], expanded_entities: [...], context: str}
        """
        if not self.hnsw or not self.graph or not self.embed:
            return {"anchors": [], "expanded_entities": [], "context": ""}

        # ── RAG: vector search for anchors ──
        try:
            vec = self.embed(query)
            anchors = self.hnsw.search(vec, self.top_k)
        except Exception as e:
            logger.debug("HNSW search failed: %s", e)
            return {"anchors": [], "expanded_entities": [], "context": ""}

        # ── Graph: 2-hop expansion from anchors ──
        seen = set()
        context_parts = []

        for node_id, score in anchors:
            if node_id in seen:
                continue
            seen.add(node_id)

            node = self.graph.get(node_id) if hasattr(self.graph, 'get') else None
            if not node:
                # Try looking up by name
                for n in getattr(self.graph, 'nodes', {}).values():
                    if getattr(n, 'name', '') == node_id:
                        node = n
                        break
            if not node:
                continue

            # Add anchor node
            context_parts.append(self._format_node(node, score, depth=0))

            # 2-hop expansion
            relations = getattr(node, 'get_relations', lambda *a, **kw: [])(max_hops=2)
            for rel in relations[:5]:  # top 5 neighbors
                if len(context_parts) * 100 > token_budget:
                    break
                target = rel.get("target") if isinstance(rel, dict) else getattr(rel, 'target', None)
                if target and target not in seen:
                    seen.add(target)
                    # Get target node
                    target_node = self.graph.get(target) if hasattr(self.graph, 'get') else None
                    context_parts.append(self._format_node(target_node or target, 0, depth=1,
                                         relation=rel.get("kind", "")))

        context = "\n".join(context_parts)[:token_budget]
        return {
            "anchors": [a[0] for a in anchors],
            "expanded_entities": list(seen),
            "context": context,
            "anchor_count": len(anchors),
        }

    def _format_node(self, node, score: float, depth: int, relation: str = "") -> str:
        """Format a node for LLM context."""
        if isinstance(node, str):
            return f"[depth={depth}] {node}"

        name = getattr(node, 'name', '') or getattr(node, 'entity_id', '') or str(node)
        summary = getattr(node, 'summary', '') or ''
        evidence = getattr(node, 'evidence', '') or ''

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
