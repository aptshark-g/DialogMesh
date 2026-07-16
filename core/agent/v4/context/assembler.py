"""ContextAssembler: aggregates and ranks context from multiple sources.

v4 enhancements:
    - HybridIndex integration for semantic + keyword retrieval
    - TieredVectorStore auto-switch (SQLite < 100K, Milvus >= 100K)
    - DomainSelector + BudgetAllocator for Context Engineering pipeline
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from core.agent.v4.context.source import (
    ContextSource, ContextItem, CrossDomainContext,
    HybridKnowledgeSource, HybridSkillSource,
    KnowledgeSource, SkillSource, ObservationSource, WorldSource, EngineeringSource,
)
from core.agent.v4.context.cross_domain_ir import CrossDomainContextIR, IREntry
from core.agent.v4.context.domain_selector import DomainSelector, Domain
from core.agent.v4.context.budget_allocator import BudgetAllocator
from core.agent.v4.persistence.vector_store import SQLiteVectorStore, VectorStore
from core.agent.v4.persistence.milvus_store import MilvusVectorStore
from core.agent.v4.persistence.hybrid_index import HybridIndex, KeywordIndex


class ContextAssembler:
    """Aggregates context from multiple sources and ranks by relevance.

    Usage (basic):
        sources = [ObservationSource(pool), KnowledgeSource(nodes), WorldSource(graph)]
        assembler = ContextAssembler(sources)
        ctx = assembler.assemble("gateway monitoring", top_k=10)

    Usage (hybrid):
        assembler = ContextAssembler.with_hybrid_index(
            knowledge_nodes=nodes,
            skill_pool=pool,
            embedder=embedder,
        )
        ctx = assembler.assemble("gateway monitoring", top_k=10)

    Usage (tiered vector store):
        assembler = ContextAssembler.with_tiered_store(
            knowledge_nodes=nodes,
            embedder=embedder,
            db_path="data/vectors.db",
            milvus_host="localhost",
        )
        ctx = assembler.assemble("gateway monitoring", top_k=10)
    """

    def __init__(self, sources: List[ContextSource] = None):
        self._sources = sources or []

    def add_source(self, source: ContextSource) -> None:
        self._sources.append(source)

    # ------------------------------------------------------------------ #
    # Factory methods for easy setup
    # ------------------------------------------------------------------ #

    @classmethod
    def with_hybrid_index(
        cls,
        knowledge_nodes: List[Any] = None,
        skill_pool=None,
        observation_pool=None,
        world_graph=None,
        embedder: Callable[[str], np.ndarray] = None,
        vector_store: VectorStore = None,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ) -> "ContextAssembler":
        """Create assembler with HybridIndex for knowledge and skill sources.

        Args:
            knowledge_nodes: List of knowledge nodes
            skill_pool: Skill pool instance
            observation_pool: Observation pool instance
            world_graph: World graph instance
            embedder: Callable that encodes string -> np.ndarray
            vector_store: Pre-built VectorStore (optional, creates SQLite if None)
            semantic_weight: Weight for semantic scores (default 0.7)
            keyword_weight: Weight for keyword scores (default 0.3)
        """
        sources = []

        # Build vector store if not provided
        if vector_store is None:
            sqlite_store = SQLiteVectorStore(":memory:")
            sqlite_store.open()
            vector_store = sqlite_store

        # Build HybridIndex for knowledge
        hybrid_index = None
        if knowledge_nodes and embedder:
            keyword_index = KeywordIndex()
            for node in knowledge_nodes:
                text = getattr(node, 'statement', str(node))
                node_id = getattr(node, 'knowledge_id', str(id(node)))
                keyword_index.add(node_id, text)
                # Pre-compute and store embedding if possible
                try:
                    vec = embedder(text)
                    vector_store.put(node_id, vec, metadata={"text": text})
                except Exception:
                    pass

            hybrid_index = HybridIndex(
                vector_store=vector_store,
                embedder=embedder,
                keyword_index=keyword_index,
                semantic_weight=semantic_weight,
                keyword_weight=keyword_weight,
            )
            sources.append(HybridKnowledgeSource(knowledge_nodes, hybrid_index))
        elif knowledge_nodes:
            sources.append(KnowledgeSource(knowledge_nodes))

        # Build HybridIndex for skills
        if skill_pool and embedder:
            keyword_index = KeywordIndex()
            try:
                skills = getattr(skill_pool, 'list_all', lambda: [])()
                for skill in skills:
                    name = getattr(skill, 'name', str(skill))
                    skill_id = getattr(skill, 'skill_id', name)
                    keyword_index.add(skill_id, name)
                    try:
                        vec = embedder(name)
                        vector_store.put(skill_id, vec, metadata={"text": name})
                    except Exception:
                        pass
            except Exception:
                pass

            hybrid_index_skill = HybridIndex(
                vector_store=vector_store,
                embedder=embedder,
                keyword_index=keyword_index,
                semantic_weight=semantic_weight,
                keyword_weight=keyword_weight,
            )
            sources.append(HybridSkillSource(skill_pool, hybrid_index_skill))
        elif skill_pool:
            sources.append(SkillSource(skill_pool))

        if observation_pool:
            sources.append(ObservationSource(observation_pool))
        if world_graph:
            sources.append(WorldSource(world_graph))
        sources.append(EngineeringSource())

        return cls(sources)

    @classmethod
    def with_tiered_store(
        cls,
        knowledge_nodes: List[Any] = None,
        skill_pool=None,
        observation_pool=None,
        world_graph=None,
        embedder: Callable[[str], np.ndarray] = None,
        db_path: str = None,
        milvus_host: str = None,
        milvus_port: int = 19530,
        milvus_threshold: int = 100_000,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
    ) -> "ContextAssembler":
        """Create assembler with TieredVectorStore (SQLite + optional Milvus).

        Milvus is only used when vector count exceeds threshold AND
        Milvus server is reachable. Otherwise, falls back to SQLite.
        """
        # SQLite store (always created)
        sqlite_store = SQLiteVectorStore(db_path or ":memory:")
        sqlite_store.open()

        # Milvus store (optional, lazy connection)
        milvus_store = None
        if milvus_host:
            milvus_store = MilvusVectorStore(
                host=milvus_host,
                port=milvus_port,
            )
            # Try to connect; if fails, milvus_store stays disconnected
            # TieredVectorStore will handle the fallback

        # Build TieredVectorStore
        from core.agent.v4.context.source import TieredVectorStore
        tiered_store = TieredVectorStore(
            sqlite_store=sqlite_store,
            milvus_store=milvus_store,
            threshold=milvus_threshold,
        )

        # Use the tiered store as the vector store for hybrid index
        return cls.with_hybrid_index(
            knowledge_nodes=knowledge_nodes,
            skill_pool=skill_pool,
            observation_pool=observation_pool,
            world_graph=world_graph,
            embedder=embedder,
            vector_store=tiered_store,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
        )

    # ------------------------------------------------------------------ #
    # Core API
    # ------------------------------------------------------------------ #

    def assemble(self, intent: str, top_k: int = 10, **kwargs) -> CrossDomainContext:
        """Retrieve and rank context from all sources.

        Args:
            intent: User/agent intent string.
            top_k: Max total items to return.
            **kwargs: Passed through to source.retrieve().

        Returns:
            CrossDomainContext with ranked items.
        """
        all_items: List[ContextItem] = []
        source_stats = {}

        for source in self._sources:
            per_source_k = max(3, top_k // max(1, len(self._sources)))
            items = source.retrieve(intent, top_k=per_source_k, **kwargs)
            all_items.extend(items)
            source_stats[source.name] = len(items)

        # Rank by relevance
        all_items.sort(key=lambda x: x.relevance, reverse=True)

        return CrossDomainContext(
            intent=intent,
            items=all_items[:top_k],
            source_stats=source_stats,
            total_items=len(all_items),
        )

    def assemble_ir(self, intent: str, top_k: int = 10,
                    token_budget: int = 2000,
                    domain_boosts: dict = None,
                    **kwargs) -> CrossDomainContextIR:
        """Assemble context using DomainSelector + BudgetAllocator.

        Full Context Engineering pipeline:
        1. DomainSelector: intent -> domain selection
        2. BudgetAllocator: allocate token budget per domain
        3. Source.retrieve(): each source fetches within its budget
        4. Build CrossDomainContextIR
        """
        # Step 1: Select domains
        selector = DomainSelector()
        selection = selector.select_from_string(intent)
        if domain_boosts:
            for domain_key, boost in domain_boosts.items():
                domain_map = {
                    "knowledge": Domain.CONVERSATION,
                    "engineering": Domain.ENGINEERING,
                    "world": Domain.ENGINEERING,
                    "skill": Domain.BEHAVIOR,
                }
                domain = domain_map.get(domain_key)
                if domain:
                    selection = selector.with_boost(selection, domain, budget=boost * 0.1)

        # Step 2: Allocate budget
        allocator = BudgetAllocator(
            mandatory_tokens=min(200, token_budget // 4),
            strategy_tokens=token_budget - min(200, token_budget // 4),
            flexible_tokens=0,
        )
        budget_plan = allocator.allocate(selection.intent_category.value)

        # Step 3: Retrieve from each domain within budget
        ir = CrossDomainContextIR(intent_category=selection.intent_category)
        for alloc in selection.allocations:
            source = self._find_source(alloc.domain)
            if source is None:
                continue
            # Find budget for this domain from BudgetPlan.strategy_plan
            domain_budget = 0
            domain_value = alloc.domain.value if hasattr(alloc.domain, 'value') else str(alloc.domain)
            for db in budget_plan.strategy_plan:
                if db.domain == domain_value:
                    domain_budget = db.budget_tokens
                    break
            if domain_budget == 0:
                domain_budget = budget_plan.strategy_tokens // max(1, len(selection.allocations))
            item_limit = max(1, domain_budget // 5)
            items = source.retrieve(intent, top_k=min(top_k, item_limit))
            # Filter noise: skip items below relevance floor
            min_relevance = 0.25
            items = [i for i in items if i.relevance >= min_relevance]
            # Deduplicate by content prefix (first 60 chars)
            seen = set()
            deduped = []
            for item in items:
                sig = item.text[:60] if item.text else str(item.content)[:60]
                if sig not in seen:
                    seen.add(sig)
                    deduped.append(item)
            items = deduped
            for item in items:
                # Use pre-extracted text from source (source is responsible for extraction)
                content_str = item.text or str(item.content)
                
                # Truncate content to reasonable length
                content_str = content_str[:1000] if len(content_str) > 1000 else content_str
                
                entry = IREntry(
                    domain=domain_value,
                    type=item.source or "context",
                    content=content_str,
                    confidence=item.relevance,
                    estimated_tokens=len(content_str) // 4,
                )
                ir.add_entry(domain_value, entry)

        ir.recalc_total()
        return ir

    def _find_source(self, domain):
        """Find a ContextSource by domain name or Domain enum.

        For 'knowledge' (K domain), prefers DocumentSource if available
        (document observations are the primary knowledge source in v4
        when no frozen KnowledgeNodes exist yet).
        """
        domain_map = {
            'observation': 'observation',
            'knowledge': 'knowledge',
            'knowledge_hybrid': 'knowledge',
            'knowledge_vector': 'knowledge',
            'skill': 'skill',
            'skill_hybrid': 'skill',
            'world': 'world',
            'engineering': 'engineering',
            'document': 'document',
            'E': 'engineering',
            'C': 'observation',
            'P': 'profile',
            'B': 'behavior',
            'K': 'knowledge',
        }
        # Handle both string and Domain enum
        domain_name = domain.value if hasattr(domain, 'value') else str(domain)
        target = domain_map.get(domain_name, domain_name)

        # For 'knowledge' domain: prefer graph/knowledge sources, document as fallback
        # ConceptGraphSource (name="knowledge") is the primary subgraph compiler
        if target == 'knowledge':
            for source in self._sources:
                if source.name in ('knowledge', 'knowledge_hybrid', 'knowledge_vector'):
                    return source
            for source in self._sources:
                if source.name == 'document':
                    return source
            return None

        for source in self._sources:
            if source.name == target or source.name == domain_name:
                return source
        return None

    @property
    def source_count(self) -> int:
        return len(self._sources)
