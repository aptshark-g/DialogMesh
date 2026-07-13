"""DialogueTreePersistenceAdapter: correction gateway for tree-to-graph persistence.
Re-classifies actions on write, performs structural validation.
"""
from __future__ import annotations
import uuid
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .annotation_store import NodeAnnotationStore, NodeAnnotation

logger = logging.getLogger(__name__)





@dataclass
class LoadResult:
    nodes: list = field(default_factory=list)
    annotations: dict = field(default_factory=dict)
    edges: list = field(default_factory=list)
    root: dict = None  # Reconstructed tree root when reconstruct=True


class DialogueTreePersistenceAdapter:
    """Correction gateway: persist tree nodes to graph with re-classification.

    On persist:
      1. Re-resolve action via TieredActionResolver
      2. Update NodeAnnotationStore
      3. Structural validation (action_shift / merged_from edges)
      4. Write to UnifiedGraphStore

    On load:
      1. Read from graph
      2. Split into tree structure + annotations
    """

    def __init__(self, store, resolver=None, annotation_store=None):
        self._store = store
        self._resolver = resolver
        self._annotations = annotation_store or NodeAnnotationStore()

    # ?? persist ???????????????????????????????????????????????

    def persist_node(self, tree_node: dict, conversation_id: str = "") -> str:
        """Persist a single tree node. Returns graph_node_id."""
        node_id = tree_node.get("node_id", tree_node.get("block_id", self._new_id("n")))
        text = tree_node.get("text", tree_node.get("summary", ""))
        parent_id = tree_node.get("parent_id", "")

        action_result = self._resolve_action(node_id, text)
        graph_id = self._new_id("g")

        graph_node = {
            "id": graph_id,
            "type": "dialogue_tree_node",
            "tier": "W",
            "data": {
                "tree_node_id": node_id,
                "summary": text,
                "parent_id": parent_id,
                "action": (action_result or {}).get("action", "unknown"),
                "action_version": (action_result or {}).get("version", 1),
                "action_source": (action_result or {}).get("source", "none"),
                "conversation_id": conversation_id,
                "created_at": tree_node.get("created_at", time.time()),
                "child_ids": tree_node.get("child_ids", []),
            },
            "metadata": {
                "domain": "dialogue",
                "annotation_version": (action_result or {}).get("version", 0),
            },
        }

        if self._store is not None:
            try:
                self._store.put_node(graph_node)
            except Exception:
                logger.exception("Failed to write node %s to store", graph_id)

        return graph_id

    def persist_tree(self, root: dict, conversation_id: str = "") -> list[str]:
        """Persist entire tree (DFS). Returns list of graph_node_ids."""
        ids: list[str] = []
        stack = [root]
        while stack:
            node = stack.pop()
            gid = self.persist_node(node, conversation_id)
            ids.append(gid)
            for child in node.get("children", []):
                stack.append(child)
        return ids

    # ?? load ??????????????????????????????????????????????????

    def load_node(self, graph_node_id: str) -> Optional[LoadResult]:
        """Load a single node from graph, splitting into tree + annotation."""
        if self._store is None:
            return None
        try:
            raw = self._store.load_node(graph_node_id)
        except Exception:
            return None
        if raw is None:
            return None

        data = raw.get("data", {})
        tree_node = {
            "node_id": data.get("tree_node_id", graph_node_id),
            "summary": data.get("summary", ""),
            "parent_id": data.get("parent_id", ""),
            "child_ids": data.get("child_ids", []),
            "created_at": data.get("created_at", 0),
        }
        annotation = self._annotations.put(
            node_id=tree_node["node_id"],
            domain="dialogue",
            data={
                "action": data.get("action", "unknown"),
                "action_source": data.get("action_source", "none"),
            },
            version=data.get("action_version", 1),
        )
        return LoadResult(
            nodes=[tree_node],
            annotations={tree_node["node_id"]: annotation},
            edges=list(raw.get("edges", [])),
        )

    def load_tree(self, conversation_id: str, reconstruct: bool = False) -> LoadResult:
        """Load all nodes for a conversation.

        Args:
            conversation_id: The conversation to load.
            reconstruct: If True, rebuild tree hierarchy from child_ids.
                        root node is stored in result.root.

        Returns:
            LoadResult with nodes, annotations, edges, and optional root.
        """
        if self._store is None:
            return LoadResult()
        try:
            if hasattr(self._store, "get_by_conversation"):
                raws = self._store.get_by_conversation(conversation_id)
            else:
                return LoadResult()
        except Exception:
            return LoadResult()

        nodes: list[dict] = []
        annotations: dict[str, NodeAnnotation] = {}
        edges: list[dict] = []

        for raw in (raws or []):
            data = raw.get("data", {})
            nid = data.get("tree_node_id", raw.get("id", ""))
            tn = {
                "node_id": nid,
                "summary": data.get("summary", ""),
                "parent_id": data.get("parent_id", ""),
                "child_ids": data.get("child_ids", []),
                "created_at": data.get("created_at", 0),
            }
            nodes.append(tn)
            ann = self._annotations.put(nid, "dialogue", {
                "action": data.get("action", "unknown"),
                "action_source": data.get("action_source", "none"),
            }, version=data.get("action_version", 1))
            annotations[nid] = ann
            for e in raw.get("edges", []):
                edges.append(e)

        root = None
        if reconstruct:
            root = self._reconstruct_tree(nodes)

        return LoadResult(nodes=nodes, annotations=annotations, edges=edges, root=root)

    # ?? structural validation ?????????????????????????????????

    def validate_adjacent(self, node_a: dict, node_b: dict) -> list[dict]:
        """Check two adjacent nodes for structural annotations.
        Returns list of extra edges (action_shift, merged_from, etc.).
        Does NOT modify tree topology.
        """
        edges: list[dict] = []
        a_ann = self._annotations.get(node_a.get("node_id", ""), "dialogue")
        b_ann = self._annotations.get(node_b.get("node_id", ""), "dialogue")

        a_action = a_ann.data.get("action", "") if a_ann else ""
        b_action = b_ann.data.get("action", "") if b_ann else ""
        a_summary = node_a.get("summary", "")
        b_summary = node_b.get("summary", "")

        # Same action + similar summary ? possible merge hint
        if a_action and a_action == b_action:
            if _text_similarity(a_summary, b_summary) > 0.60:
                edges.append({
                    "type": "merged_from",
                    "from": node_b.get("node_id", ""),
                    "to": node_a.get("node_id", ""),
                })

        # Different action ? action_shift edge
        if a_action and b_action and a_action != b_action:
            edges.append({
                "type": "action_shift",
                "from": node_a.get("node_id", ""),
                "to": node_b.get("node_id", ""),
                "from_action": a_action,
                "to_action": b_action,
            })

        return edges

    # ?? helpers ???????????????????????????????????????????????


    def _reconstruct_tree(self, nodes: list[dict]) -> dict:
        """Rebuild tree hierarchy from a flat node list using child_ids.

        Returns the root node (no parent). If multiple roots, returns
        a virtual root with children.
        """
        if not nodes:
            return {}

        node_map = {n["node_id"]: dict(n, children=[]) for n in nodes}

        roots = []
        for n in node_map.values():
            pid = n.get("parent_id", "")
            if pid and pid in node_map:
                node_map[pid]["children"].append(n)
            else:
                roots.append(n)

        if len(roots) == 1:
            return roots[0]
        elif len(roots) > 1:
            return {"node_id": "__virtual_root__", "summary": "[root]", "children": roots}
        return {}

    def _resolve_action(self, node_id: str, text: str) -> Optional[dict]:
        existing = self._annotations.get(node_id, "dialogue")
        if existing is not None and not existing.stale:
            return {
                "action": existing.data.get("action", "unknown"),
                "version": existing.version,
                "source": existing.data.get("action_source", "cached"),
            }
        if text and self._resolver is not None:
            try:
                results = self._resolver.resolve("dialogue", text)
                if results:
                    best = results[0]
                    ann = self._annotations.put(
                        node_id, "dialogue",
                        {"action": best.action, "action_source": best.source},
                        version=(existing.version + 1) if existing else 1,
                    )
                    return {
                        "action": best.action,
                        "version": ann.version,
                        "source": best.source,
                    }
            except Exception:
                logger.exception("Action resolution failed for node %s", node_id)
        ann = self._annotations.put(node_id, "dialogue", {"action": "unknown", "action_source": "none"})
        return {"action": "unknown", "version": ann.version, "source": "none"}

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _text_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)
