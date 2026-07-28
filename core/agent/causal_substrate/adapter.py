"""Bridge: core.agent.causal_substrate.adapter → actual implementations.

Avoids circular imports by defining CausalContextEntry inline rather than
importing from core.agent.v4.causal_substrate which imports back from us.
"""
from dataclasses import dataclass

from core.agent.behavior.causal_adapter import (
    CausalSubstrateAdapter,
    CausalInsight,
)


@dataclass
class CausalContextEntry:
    """Context entry with causal reasoning metadata. (replicated from v4)"""
    entry_id: str = ""
    source: str = "causal_substrate"
    content: str = ""
    insight: object = None
    confidence: float = 0.5


__all__ = ["CausalSubstrateAdapter", "CausalContextEntry", "CausalInsight"]
