"""ContextAssembler: aggregates and ranks context from multiple sources."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List

from core.agent.v4.context.source import ContextSource, ContextItem, CrossDomainContext


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

    @property
    def source_count(self) -> int:
        return len(self._sources)
