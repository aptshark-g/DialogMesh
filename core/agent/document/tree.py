"""DocumentTree: static structure tree for external documents.

Design principle:
    - DocumentTree is NOT a DiscourseBlockTree.
    - Structure comes from heading hierarchy, not cohesion scores.
    - Static: parsed once, does not evolve over time.
    - Enters cognitive chain via ObservationExtractor → DocumentObservationBundle.
"""
from __future__ import annotations
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Relation:
    """Typed relation between concepts extracted from a document node."""
    source: str
    target: str
    relation_type: str  # e.g. "depends_on", "leads_to", "contains"
    confidence: float = 1.0


@dataclass
class DocumentNode:
    """Static structure tree node — NOT a discourse block.

    Attributes:
        node_id: hash(source_path + heading_path) for stable identity.
        source_path: Original file path.
        heading_path: Hierarchical headings, e.g. ["# DialogMesh", "## v4"].
        level: Heading depth (1, 2, 3, ...); 0 for root.
        raw_text: Full text of this section.
        node_type: "heading" | "paragraph" | "code" | "table" | "list".
        children: Sub-nodes.
        parent: Parent node (None for root).
        observed_concepts: Concepts detected by ObservationExtractor.
        observed_relations: Relations detected by ObservationExtractor.
        observation_type: "definition" | "constraint" | "procedure" | "example" | "relation" | "parameter" | "".
        confidence: Extraction confidence (0.0–1.0).
    """
    node_id: str
    source_path: str
    heading_path: List[str] = field(default_factory=list)
    level: int = 0
    raw_text: str = ""
    node_type: str = "heading"
    children: List["DocumentNode"] = field(default_factory=list)
    parent: Optional["DocumentNode"] = None

    # Cognitive metadata (populated by ObservationExtractor)
    observed_concepts: List[str] = field(default_factory=list)
    observed_relations: List[Relation] = field(default_factory=list)
    observation_type: str = ""
    confidence: float = 0.0

    def full_path(self) -> str:
        """Return the full heading path as a single string."""
        return " > ".join(self.heading_path) if self.heading_path else self.source_path

    def add_child(self, node: "DocumentNode") -> None:
        """Add a child and set its parent reference."""
        node.parent = self
        self.children.append(node)

    def walk(self) -> List["DocumentNode"]:
        """Pre-order traversal of the entire subtree."""
        result = [self]
        for child in self.children:
            result.extend(child.walk())
        return result

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict (for persistence / debugging)."""
        return {
            "node_id": self.node_id,
            "source_path": self.source_path,
            "heading_path": self.heading_path,
            "level": self.level,
            "raw_text": self.raw_text,
            "node_type": self.node_type,
            "observation_type": self.observation_type,
            "confidence": self.confidence,
            "observed_concepts": self.observed_concepts,
            "children": [c.to_dict() for c in self.children],
        }


class DocumentTree:
    """Wrapper around a DocumentNode root with utility methods."""

    def __init__(self, root: DocumentNode):
        self.root = root

    def all_nodes(self) -> List[DocumentNode]:
        """Return all nodes in the tree."""
        return self.root.walk()

    def nodes_by_type(self, node_type: str) -> List[DocumentNode]:
        """Return all nodes of a given type."""
        return [n for n in self.all_nodes() if n.node_type == node_type]

    def nodes_by_level(self, level: int) -> List[DocumentNode]:
        """Return all nodes at a given heading level."""
        return [n for n in self.all_nodes() if n.level == level]

    def find_by_path(self, heading_path: List[str]) -> Optional[DocumentNode]:
        """Find a node by its exact heading path."""
        for node in self.all_nodes():
            if node.heading_path == heading_path:
                return node
        return None

    def stats(self) -> Dict[str, Any]:
        """Return tree statistics."""
        nodes = self.all_nodes()
        return {
            "total_nodes": len(nodes),
            "by_type": {
                t: len(self.nodes_by_type(t))
                for t in {"heading", "paragraph", "code", "table", "list"}
            },
            "max_level": max((n.level for n in nodes), default=0),
            "source_path": self.root.source_path,
        }


def make_node_id(source_path: str, heading_path: List[str]) -> str:
    """Stable node ID from source path + heading path."""
    key = f"{source_path}::{' > '.join(heading_path)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
