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



class VectorKnowledgeSource(KnowledgeSource):
    """Retrieves from Knowledge nodes using vector similarity.

    Requires a VectorStore with pre-computed embeddings.
    Falls back to keyword matching if no embedding for a node.
    """

    def __init__(self, nodes=None, vector_store=None, embedder=None):
        super().__init__(nodes)
        self._vector_store = vector_store
        self._embedder = embedder

    @property
    def name(self) -> str:
        return "knowledge_vector"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        # If no vector store or embedder, fall back to keyword matching
        if self._vector_store is None or self._embedder is None:
            return super().retrieve(query, top_k, **kwargs)

        try:
            query_vec = self._embedder.encode(query)
            if isinstance(query_vec, list):
                query_vec = __import__('numpy').array(query_vec)

            # Search vector store
            results = self._vector_store.search(query_vec, top_k)
            items = []
            for node_id, score in results:
                # Find matching KnowledgeNode
                for node in self._nodes:
                    if hasattr(node, 'knowledge_id') and node.knowledge_id == node_id:
                        items.append(ContextItem(
                            source=self.name,
                            content=node,
                            relevance=float(score),
                        ))
                        break
            return items
        except Exception:
            return super().retrieve(query, top_k, **kwargs)


class TieredVectorStore:
    """Auto-switches between SQLite and Milvus based on vector count.

    Design: SQLite is source of truth. Milvus is optional accelerator.
    When vector count exceeds threshold, new vectors are also written to Milvus.
    Old vectors are never migrated -- Milvus warms up naturally over time.
    """

    def __init__(self, sqlite_store, milvus_store=None, threshold: int = 100_000):
        self._sqlite = sqlite_store
        self._milvus = milvus_store
        self._threshold = threshold

    def put(self, node_id: str, vector, metadata=None):
        self._sqlite.put(node_id, vector, metadata)
        if self._milvus and self._sqlite.count > self._threshold:
            self._milvus.put(node_id, vector, metadata)

    def search(self, query_vector, top_k=10):
        if self._milvus and self._sqlite.count > self._threshold:
            return self._milvus.search(query_vector, top_k)
        return self._sqlite.search(query_vector, top_k)

    @property
    def count(self):
        return self._sqlite.count
