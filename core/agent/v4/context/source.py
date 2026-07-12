"""ContextSource: abstract interface for context retrieval from knowledge domains.

Design: Source -> Rank -> Assemble pipeline.
Each source independently retrieves from its domain.
The ContextAssembler aggregates and ranks results.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ContextItem:
    """A single context item from a knowledge source."""
    source: str
    content: Any
    relevance: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class CrossDomainContext:
    """Aggregated context from multiple sources."""
    intent: str
    items: List[ContextItem] = field(default_factory=list)
    source_stats: Dict[str, int] = field(default_factory=dict)
    total_items: int = 0

    def by_source(self, source_name: str) -> List[ContextItem]:
        return [i for i in self.items if i.source == source_name]

    def top_k(self, k: int) -> List[ContextItem]:
        return sorted(self.items, key=lambda x: x.relevance, reverse=True)[:k]


class ContextSource(ABC):
    """Abstract interface for context retrieval.

    Each source represents one knowledge domain:
    Observation, Knowledge, Skill, World, Engineering, etc.

    Key principle: ContextSelector doesn't need to know
    what Observation is. It calls source.retrieve(query).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable source name."""

    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        """Retrieve relevant context items for a query."""


class ObservationSource(ContextSource):
    """Retrieves from ObservationPool."""

    def __init__(self, pool=None):
        self._pool = pool

    @property
    def name(self) -> str:
        return "observation"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        if self._pool is None:
            return []
        try:
            bundles = self._pool.get_by_domain("all")
            items = []
            for bundle in bundles[-top_k:]:
                items.append(ContextItem(
                    source=self.name,
                    content=bundle,
                    relevance=0.5,  # Simple recency bias
                ))
            return items
        except Exception:
            return []


class KnowledgeSource(ContextSource):
    """Retrieves from frozen Knowledge nodes."""

    def __init__(self, knowledge_nodes: List[Any] = None):
        self._nodes = knowledge_nodes or []

    @property
    def name(self) -> str:
        return "knowledge"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        keywords = query.lower().split()
        scored = []
        for node in self._nodes:
            if hasattr(node, 'statement'):
                text = node.statement.lower()
                score = sum(1 for kw in keywords if kw in text)
                if score > 0:
                    scored.append(ContextItem(
                        source=self.name,
                        content=node,
                        relevance=min(1.0, score / len(keywords)),
                    ))
        scored.sort(key=lambda x: x.relevance, reverse=True)
        return scored[:top_k]


class SkillSource(ContextSource):
    """Retrieves from SkillPool."""

    def __init__(self, skill_pool=None):
        self._pool = skill_pool

    @property
    def name(self) -> str:
        return "skill"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        if self._pool is None:
            return []
        try:
            skills = getattr(self._pool, 'list_all', lambda: [])()
            keywords = query.lower().split()
            items = []
            for skill in skills:
                name = getattr(skill, 'name', str(skill)).lower()
                score = sum(1 for kw in keywords if kw in name)
                if score > 0:
                    items.append(ContextItem(
                        source=self.name,
                        content=skill,
                        relevance=min(1.0, score / max(1, len(keywords))),
                    ))
            items.sort(key=lambda x: x.relevance, reverse=True)
            return items[:top_k]
        except Exception:
            return []


class WorldSource(ContextSource):
    """Retrieves from StructuralWorldGraph via ContextCompiler."""

    def __init__(self, world_graph=None):
        self._graph = world_graph

    @property
    def name(self) -> str:
        return "world"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        if self._graph is None:
            return []
        try:
            from core.agent.v4.world.compiler import StructuralContextCompiler
            compiler = StructuralContextCompiler()
            subgraph = compiler.compile_subgraph(self._graph, intent=query, max_nodes=top_k * 2)
            items = []
            for node in subgraph.nodes[:top_k]:
                items.append(ContextItem(
                    source=self.name,
                    content=node,
                    relevance=node.backbone_score if node.backbone_score > 0 else 0.3,
                ))
            return items
        except Exception:
            return []


class EngineeringSource(ContextSource):
    """Retrieves from Engineering chain (stub)."""

    @property
    def name(self) -> str:
        return "engineering"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        # Stub: Engineering chain not yet fully integrated
        return []
