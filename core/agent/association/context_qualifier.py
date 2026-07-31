"""Context qualifier for L2 BeliefAccumulator — Phase 2.

Replaces hardcoded depends_on dict with dynamic dependency injection.
Produces enriched text: [entity, depends_on=X, confidence=Y%]

Design: ARCHITECTURE_AUDIT §12-B: raw → qualify() → enriched → cut()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Dependency:
    """A qualified dependency between entities."""
    entity: str
    depends_on: str
    confidence: float = 0.5
    source: str = "heuristic"  # heuristic / llm / user


class ContextQualifier:
    """Dynamically qualifies entities with dependency context.

    Replaces L2's hardcoded static dict with per-turn dynamic injection.
    """

    def __init__(self):
        self._belief_graph: Dict[str, List[Dependency]] = {}
        self._confidence_decay: float = 0.95  # per-turn decay

    def qualify(self, enriched_text: str, entities: List[str],
                recent_deps: List[Dependency] = None) -> str:
        """Inject dependency context into enriched text.

        Args:
            enriched_text: Text already processed by PronounResolver
            entities: Entities found in current turn
            recent_deps: Recent dependencies from previous turns
        Returns:
            Text with [entity, depends_on=X, confidence=Y%] injected
        """
        if not entities:
            return enriched_text

        # Decay old confidences
        for entity in self._belief_graph:
            for dep in self._belief_graph[entity]:
                dep.confidence *= self._confidence_decay

        # Inject dependencies
        for entity in entities:
            deps = self._belief_graph.get(entity, [])
            if deps:
                dep_str = ", ".join(
                    f"depends_on={d.depends_on},confidence={d.confidence:.0%}"
                    for d in deps[:3]  # top 3
                )
                enriched_text = enriched_text.replace(
                    f"[{entity}]", f"[{entity}, {dep_str}]"
                )

        return enriched_text

    def add_dependency(self, entity: str, depends_on: str,
                       confidence: float = 0.5, source: str = "heuristic") -> None:
        """Add a dependency to the belief graph."""
        dep = Dependency(entity=entity, depends_on=depends_on,
                        confidence=confidence, source=source)
        if entity not in self._belief_graph:
            self._belief_graph[entity] = []
        self._belief_graph[entity].append(dep)

    def get_dependencies(self, entity: str) -> List[Dependency]:
        """Get all dependencies for an entity."""
        return self._belief_graph.get(entity, [])

    def stats(self) -> dict:
        return {
            "entities_with_deps": len(self._belief_graph),
            "total_deps": sum(len(d) for d in self._belief_graph.values()),
            "avg_confidence": (
                sum(d.confidence for deps in self._belief_graph.values() for d in deps)
                / max(1, sum(len(d) for d in self._belief_graph.values()))
            ),
        }
