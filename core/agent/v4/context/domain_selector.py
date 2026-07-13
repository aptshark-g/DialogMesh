"""DomainSelector: intent-aware domain selection matrix (~100 lines).

Maps IntentCategory -> (primary, aux1, aux2) with budget weights.
Design ref: docs/v3.0/DESIGN_CROSS_DOMAIN_CONTEXT.md §4.2
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class IntentCategory(Enum):
    TASK = "task"; QUERY = "query"; CORRECTION = "correction"
    DISCUSSION = "discussion"; CASUAL = "casual"; TOPIC_SWITCH = "topic_switch"


class Domain(Enum):
    ENGINEERING = "E"; CONVERSATION = "C"; PROFILE = "P"; BEHAVIOR = "B"; CAUSAL = "K"


class DomainRole(Enum):
    PRIMARY = "primary"; AUXILIARY = "auxiliary"


@dataclass(frozen=True)
class DomainAllocation:
    domain: Domain; role: DomainRole; budget_pct: float
    def to_ir(self) -> dict:
        return {"domain": self.domain.value, "role": self.role.value, "budget_pct": self.budget_pct}


@dataclass
class DomainSelection:
    intent_category: IntentCategory
    allocations: List[DomainAllocation] = field(default_factory=list)
    strategy: str = "balanced"
    @property
    def primary_domain(self) -> Optional[Domain]:
        return next((a.domain for a in self.allocations if a.role == DomainRole.PRIMARY), None)
    def budget_for(self, domain: Domain) -> float:
        return next((a.budget_pct for a in self.allocations if a.domain == domain), 0.0)
    def to_ir(self) -> dict:
        return {"intent_category": self.intent_category.value,
                "domain_allocation": [a.to_ir() for a in self.allocations], "strategy": self.strategy}


# intent -> (primary, aux1, aux2, strategy)
_MATRIX: Dict[IntentCategory, Tuple[Domain, Optional[Domain], Optional[Domain], str]] = {
    IntentCategory.TASK:         (Domain.ENGINEERING,  Domain.BEHAVIOR,    Domain.PROFILE,  "primary_deep"),
    IntentCategory.QUERY:        (Domain.CONVERSATION, Domain.ENGINEERING, Domain.PROFILE,  "topic_anchor"),
    IntentCategory.CORRECTION:   (Domain.BEHAVIOR,     Domain.ENGINEERING, Domain.CAUSAL,   "causal_backtrack"),
    IntentCategory.DISCUSSION:   (Domain.PROFILE,      Domain.CONVERSATION, Domain.ENGINEERING, "breadth_diverge"),
    IntentCategory.CASUAL:       (Domain.CONVERSATION, Domain.PROFILE,     None,            "lightweight"),
    IntentCategory.TOPIC_SWITCH: (Domain.CONVERSATION, Domain.BEHAVIOR,    Domain.PROFILE,  "struct_rebuild"),
}
_DEFAULT_SPLIT = (0.60, 0.25, 0.15)
_INTENT_MAP = {"task": "TASK", "query": "QUERY", "question": "QUERY", "correction": "CORRECTION",
               "fix": "CORRECTION", "discussion": "DISCUSSION", "casual": "CASUAL", "chat": "CASUAL",
               "topic_switch": "TOPIC_SWITCH", "switch": "TOPIC_SWITCH"}


class DomainSelector:
    """Selects domains based on intent. Usage:
        sel = DomainSelector().select(IntentCategory.TASK)
        assert sel.primary_domain == Domain.ENGINEERING
        assert sel.budget_for(Domain.BEHAVIOR) == 0.25
    """

    def __init__(self, split: Tuple[float, float, float] = _DEFAULT_SPLIT):
        self._split = split

    def select(self, intent: IntentCategory, excluded: Optional[List[Domain]] = None,
               strategy_override: Optional[str] = None) -> DomainSelection:
        primary, a1, a2, strategy = _MATRIX.get(intent, (Domain.CONVERSATION, None, None, "balanced"))
        strategy = strategy_override or strategy
        ex = set(excluded or [])
        allocs: List[DomainAllocation] = []
        if primary not in ex:
            allocs.append(DomainAllocation(primary, DomainRole.PRIMARY, self._split[0]))
        if a1 and a1 not in ex:
            allocs.append(DomainAllocation(a1, DomainRole.AUXILIARY, self._split[1]))
        if a2 and a2 not in ex:
            allocs.append(DomainAllocation(a2, DomainRole.AUXILIARY, self._split[2]))
        total = sum(a.budget_pct for a in allocs)
        if total and total != 1.0:
            allocs = [DomainAllocation(a.domain, a.role, round(a.budget_pct / total, 4)) for a in allocs]
        return DomainSelection(intent, allocs, strategy)

    def select_from_string(self, intent_str: str, **kwargs) -> DomainSelection:
        cat = getattr(IntentCategory, _INTENT_MAP.get(intent_str.lower().strip(), "QUERY"))
        return self.select(cat, **kwargs)

    def with_boost(self, base: DomainSelection, domain: Domain, budget: float = 0.20) -> DomainSelection:
        """Adaptive override: boost a domain into selection (Phase 3 hook)."""
        allocs = [DomainAllocation(a.domain, a.role, budget if a.domain == domain else a.budget_pct)
                  for a in base.allocations] if domain in {a.domain for a in base.allocations} else \
                 list(base.allocations) + [DomainAllocation(domain, DomainRole.AUXILIARY, budget)]
        total = sum(a.budget_pct for a in allocs)
        allocs = [DomainAllocation(a.domain, a.role, round(a.budget_pct / total, 4)) for a in allocs]
        return DomainSelection(base.intent_category, allocs, base.strategy)
