"""ObjectRuntime — behavioral layer for SemanticObject.

Design: docs/v3.0/DESIGN_SEMANTIC_OBJECT.md §4

Pure behavior. SemanticObject is pure data. ObjectRuntime handles
render, zoom, and composition expansion.
"""
from __future__ import annotations
from typing import Dict, List, Optional

from core.agent.v4.compiler.semantic_object import SemanticObject, LOD
from core.agent.v4.compiler.projection_resolver import ResolverRegistry
from core.agent.v4.compiler.content_provider import ContentProvider


class ObjectRuntime:
    """Renders SemanticObjects according to Perspective + LOD."""

    def __init__(self, registry: ResolverRegistry = None,
                 provider: ContentProvider = None,
                 object_store: Dict[str, SemanticObject] = None):
        self._registry = registry or ResolverRegistry
        self._provider = provider or ContentProvider()
        self._object_store = object_store or {}
        self._current: Optional[SemanticObject] = None

    # ---- public API ----

    def render(self, obj: SemanticObject, lod, perspective=None) -> dict:
        """Render object view by perspective + LOD.

        lod: LOD object or int
        Returns dict with keys: name, lod, design, composition, relations.
        """
        lod_val = lod.level if isinstance(lod, LOD) else float(lod)
        strategy = getattr(perspective, 'strategy', 'architecture') if perspective else 'architecture'

        result = {"name": obj.name, "lod": lod_val}
        view = self._view_for(strategy)
        proj_priority = self._projection_priority(strategy)

        # Render projections
        for proj_name in proj_priority:
            resolver_name = obj.projection_resolvers.get(proj_name)
            if not resolver_name:
                continue
            resolver = self._registry.get(resolver_name)
            if resolver:
                content = resolver.resolve(obj, view, self._provider)
                if content:
                    result[proj_name] = content[:500]

        # Expand composition by LOD
        if lod_val >= 2.0:
            depth = max(0, int(lod_val) - 1)
            result["composition"] = self._expand(obj, depth, lod_val, strategy)

        # Relations at deeper LOD
        if lod_val >= 3.0 and obj.relations:
            result["relations"] = [
                f"{r.get('source', '?')} --{r.get('type', '?')}--> {r.get('target', '?')}"
                for r in obj.relations[:8]
            ]

        return result

    def zoom(self, obj: SemanticObject, lod, perspective=None) -> dict:
        self._current = obj
        return self.render(obj, lod, perspective)

    def navigate(self, concept: str) -> Optional[SemanticObject]:
        if not self._current:
            return None
        for edge in self._current.composition_edges:
            if edge.target.lower() == concept.lower():
                return self._object_store.get(edge.target)
        return self._object_store.get(concept)

    # ---- internal ----

    def _expand(self, obj: SemanticObject, depth: int,
                lod_val: float, strategy: str) -> List[dict]:
        if depth <= 0 or not obj.composition_edges:
            return []
        view = self._view_for(strategy)
        result = []
        for edge in obj.composition_edges[:8]:
            child = self._object_store.get(edge.target)
            entry = {"name": edge.target, "type": edge.type}
            if child:
                for pn, rn in child.projection_resolvers.items():
                    resolver = self._registry.get(rn)
                    if resolver:
                        s = resolver.resolve(child, view, self._provider)
                        if s:
                            entry["summary"] = s[:250]
                            break
                if depth > 1:
                    kids = self._expand(child, depth - 1, lod_val, strategy)
                    if kids:
                        entry["children"] = kids
            result.append(entry)
        return result

    @staticmethod
    def _view_for(strategy: str) -> str:
        return {
            "architecture": "definition",
            "execution": "detail",
            "engineering": "full",
            "evolution": "history",
        }.get(strategy, "summary")

    @staticmethod
    def _projection_priority(strategy: str) -> List[str]:
        return {
            "architecture": ["design"],
            "execution": ["design", "knowledge"],
            "engineering": ["design", "code"],
            "evolution": ["design", "knowledge"],
        }.get(strategy, ["design"])

    @property
    def current(self) -> Optional[SemanticObject]:
        return self._current

    def set_store(self, store: Dict[str, SemanticObject]):
        self._object_store = store
