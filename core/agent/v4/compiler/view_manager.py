"""ViewManager — persistent viewport over the SemanticPath hierarchy.

Design: docs/v3.0/DESIGN_PERSPECTIVE_PLANNER.md §5

The ViewManager maintains a camera position in the SemanticPath DAG.
Like Google Maps: SemanticPath = coordinates, Horizon = zoom level,
zoom_in/out = scroll wheel, pan = drag, reframe = search.

This replaces the old query→result model with a persistent worldview
that survives across turns.
"""
from __future__ import annotations
import logging
from typing import Dict, List, Optional

from core.agent.v4.compiler.semantic_path import SemanticIndex, SemanticPath
from core.agent.v4.compiler.content_index import ContentIndex
from core.agent.v4.context.source import ContextItem

logger = logging.getLogger(__name__)


class View:
    """Current observation window into the concept hierarchy."""

    def __init__(self):
        self.path: Optional[SemanticPath] = None   # camera position
        self.depth: int = 2                         # current horizon
        self.visible: List[str] = []                # visible concept names
        self.content: Dict[str, str] = {}           # concept → rendered content
        self.children: List[SemanticPath] = []       # children at current depth

    def summary(self) -> str:
        if not self.path:
            return "No view"
        segs = "/".join(self.path.segments[-3:]) if len(self.path.segments) > 3 else "/".join(self.path.segments)
        return f"View({segs} depth={self.depth} visible={len(self.visible)})"


class ViewManager:
    """Maintains a persistent camera over the SemanticPath hierarchy.

    Usage:
        vm = ViewManager(semantic_index, content_index)
        vm.reframe(query="DialogMesh", strategy="architecture", depth=2)
        # LLM: "Show me more about Runtime"
        vm.zoom_in("Runtime")
        # LLM: "Go back to overview"
        vm.zoom_out()
    """

    def __init__(self, semantic: SemanticIndex, content: ContentIndex):
        self._semantic = semantic
        self._content = content
        self._current: Optional[View] = None
        self._view_history: List[View] = []  # for zoom_out undo

    # ---- API ----

    def reframe(self, query: str, strategy: str = "architecture",
                depth: int = 2, top_k: int = 15) -> View:
        """Set the camera to a new position based on query.

        Searches for the best matching SemanticPath and builds a view
        at the specified depth.
        """
        view = View()
        view.depth = depth

        # Find the anchor concept for this query
        anchor = self._find_anchor(query)
        if not anchor:
            self._current = view
            return view

        # Locate its SemanticPath
        path = self._semantic.locate(anchor)
        if not path:
            self._current = view
            return view

        view.path = path

        # Render children at specified depth
        view.children = self._render_children(path, depth)
        view.visible = [self._segments_key(c) for c in view.children]

        # Fetch content for visible concepts
        view.content = self._fetch_content(view.visible, top_k)

        self._view_history.append(self._current) if self._current else None
        self._current = view
        logger.info("ViewManager reframed: %s", view.summary())
        return view

    def zoom_in(self, concept: str) -> Optional[View]:
        """Zoom into a child concept. Descends one level in hierarchy."""
        if not self._current or not self._current.path:
            return None

        # Find the child SemanticPath matching this concept
        target = None
        for child in self._current.children:
            if concept.lower() in "/".join(child.segments).lower():
                target = child
                break

        if not target:
            # Try locating directly
            target = self._semantic.locate(concept)

        if not target:
            return None

        view = View()
        view.path = target
        view.depth = self._current.depth
        view.children = self._render_children(target, self._current.depth)
        view.visible = [self._segments_key(c) for c in view.children]
        view.content = self._fetch_content(view.visible)

        self._view_history.append(self._current)
        self._current = view
        logger.info("ViewManager zoom_in(%s): %s", concept, view.summary())
        return view

    def zoom_out(self) -> Optional[View]:
        """Zoom out to previous view. Like browser back button."""
        if not self._view_history:
            return self._current

        prev = self._view_history.pop()
        self._current = prev
        logger.info("ViewManager zoom_out → %s", prev.summary())
        return prev

    def to_context_items(self, top_k: int = 12) -> List[ContextItem]:
        """Convert current view to ContextItems for the assembler."""
        if not self._current or not self._current.visible:
            return []

        items = []
        for concept_name in self._current.visible[:top_k]:
            content = self._current.content.get(concept_name, "")
            path = self._semantic.locate(concept_name)
            depth_label = len(path.segments) if path else 0

            relevance = 0.8 if depth_label <= 2 else (
                0.6 if depth_label <= 3 else 0.4
            )

            items.append(ContextItem(
                source="view",
                content={"concept": concept_name, "depth": depth_label},
                text=f"[LEVEL {depth_label}] {concept_name}\n{content[:300]}",
                relevance=relevance,
            ))

        items.sort(key=lambda x: x.relevance, reverse=True)
        return items

    @property
    def current(self) -> Optional[View]:
        return self._current

    # ---- internal ----

    def _find_anchor(self, query: str) -> Optional[str]:
        """Find best concept match for a query."""
        query_lower = query.lower()
        # Try exact match first
        for concept in self._semantic._concept_map:
            if concept.lower() == query_lower or concept.lower() in query_lower:
                return concept
        # Try CamelCase tokenization: "context compiler" → "ContextCompiler"
        tokens = query_lower.split()
        for concept in self._semantic._concept_map:
            c_lower = concept.lower()
            if all(t in c_lower for t in tokens if len(t) > 2):
                return concept
        # Try keyword search via ContentIndex
        items = self._content.query(query, top_k=3, strategy="keyword")
        for item in items:
            text = item.text.lower()
            for concept in self._semantic._concept_map:
                if concept.lower() in text:
                    return concept
        return None

    def _render_children(self, path: SemanticPath, depth: int) -> List[SemanticPath]:
        """Render children at specified depth from a SemanticPath node."""
        result = [path]
        if depth <= 1:
            return result

        frontier = list(self._semantic.children_of(path.path_hash))
        for _ in range(depth - 1):
            next_frontier = []
            for child in frontier[:5]:  # limit breadth per level
                grandchildren = self._semantic.children_of(child.path_hash)
                next_frontier.extend(grandchildren[:3])
                result.append(child)
            frontier = next_frontier
            if not frontier:
                break

        return result

    def _fetch_content(self, concepts: List[str], top_k: int = 12) -> Dict[str, str]:
        """Fetch rendered content for a list of concepts."""
        content = {}
        seen = set()
        for c in concepts[:top_k]:
            if c in seen:
                continue
            seen.add(c)
            path = self._semantic.locate(c)
            if path:
                docs = path.document_refs[:2]
                content[c] = f"[{len(path.children)} children] from {', '.join(docs)}"
            else:
                content[c] = ""
        return content

    @staticmethod
    def _segments_key(path: SemanticPath) -> str:
        return "/".join(path.segments[-3:] if len(path.segments) > 3 else path.segments)

    @staticmethod
    def _extract_concept(text: str) -> Optional[str]:
        """Extract a concept name from text."""
        words = text.split()
        for w in words:
            w = w.strip("[]():;.,")
            if len(w) >= 4 and w[0].isupper():
                return w
        return None
