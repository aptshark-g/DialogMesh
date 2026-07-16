"""IndexSource — wraps ContentIndex as a ContextSource for the assembler."""
from __future__ import annotations
from typing import List
from core.agent.v4.context.source import ContextSource, ContextItem
from core.agent.v4.compiler.content_index import ContentIndex


class IndexSource(ContextSource):
    """Wraps ContentIndex as a single ContextSource.

    name="knowledge" so DomainSelector's K domain finds it.
    The assembler treats this as one source; internally it routes
    to keyword or graph backend via ContentIndex.query().
    """

    def __init__(self, content_index: ContentIndex):
        self._index = content_index

    @property
    def name(self) -> str:
        return "knowledge"

    def retrieve(self, query: str, top_k: int = 10, **kwargs) -> List[ContextItem]:
        return self._index.query(query, top_k=top_k, strategy="hybrid")
