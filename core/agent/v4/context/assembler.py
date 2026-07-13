"""ContextAssembler: aggregates and ranks context from multiple sources."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List

from core.agent.v4.context.source import ContextSource, ContextItem, CrossDomainContext
from core.agent.v4.context.cross_domain_ir import CrossDomainContextIR
from core.agent.v4.context.domain_selector import DomainSelector
from core.agent.v4.context.budget_allocator import BudgetAllocator


class ContextAssembler:
    """Aggregates context from multiple sources and ranks by relevance.

    Usage:
        sources = [ObservationSource(pool), KnowledgeSource(nodes), WorldSource(graph)]
        assembler = ContextAssembler(sources)
        ctx = assembler.assemble("gateway monitoring", top_k=10)
        top = ctx.top_k(5)  # Top 5 most relevant items across all sources
    """

    def __init__(self, sources: List[ContextSource] = None):
        self._sources = sources or []

    def add_source(self, source: ContextSource) -> None:
        self._sources.append(source)

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

        Args:
            intent: User/agent intent string.
            top_k: Max total items across all domains.
            token_budget: Total token budget.
            domain_boosts: Optional per-domain boost factors.

        Returns:
            CrossDomainContextIR with domain-allocated entries and budget info.
        """
        # Step 1: Select domains
        selector = DomainSelector()
        if domain_boosts:
            selector = selector.with_boost(domain_boosts)
        selection = selector.select_from_string(intent)

        # Step 2: Allocate budget
        allocator = BudgetAllocator(token_budget, min_per_domain=80)
        budget_plan = allocator.allocate(selection)

        # Step 3: Retrieve from each domain within budget
        ir = CrossDomainContextIR(intent=intent)
        for alloc in selection.allocations:
            source = self._find_source(alloc.domain)
            if source is None:
                continue
            domain_budget = budget_plan.budget_for(alloc.domain)
            # Convert token budget to item count (rough: ~5 tokens per item)
            item_limit = max(1, domain_budget // 5)
            items = source.retrieve(intent, top_k=min(top_k, item_limit))
            for item in items:
                ir.add_entry(alloc.domain, item)

        ir.recalc_total()
        return ir

    def _find_source(self, domain_name: str):
        """Find a ContextSource by domain name."""
        domain_map = {
            'observation': 'observation',
            'knowledge': 'knowledge',
            'skill': 'skill',
            'world': 'world',
            'engineering': 'engineering',
        }
        target = domain_map.get(domain_name, domain_name)
        for source in self._sources:
            if source.name == target:
                return source
        return None

    @property
    def source_count(self) -> int:
        return len(self._sources)
