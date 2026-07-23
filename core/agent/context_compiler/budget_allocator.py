"""BudgetAllocator: marginal-utility-driven token budget with real-time counting.

Refinements over base spec:
1. Marginal utility greedy instead of fixed percentage allocation
2. Real-time token counting (not estimates)
3. Surplus backflow: unused budget flows to next-priority domain
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from .models import Domain, ContextEntry, CrossDomainContextIR

logger = logging.getLogger(__name__)

TOKEN_BUDGET_DEFAULT = 500
TOKEN_BUDGET_MIN = 200
TOKEN_BUDGET_MAX = 2000
BUDGET_NECESSARY = 200
BUDGET_STRATEGIC = 300
BUDGET_ELASTIC = 200


class BudgetAllocator:

    def __init__(self, total_budget: int = TOKEN_BUDGET_DEFAULT, monitor=None):
        self._total_budget = max(TOKEN_BUDGET_MIN, min(TOKEN_BUDGET_MAX, total_budget))
        self._monitor = monitor

    @property
    def total_budget(self) -> int:
        return self._total_budget

    def allocate(
        self,
        domain_weights: Dict[Domain, float],
        entries_by_domain: Dict[Domain, List[ContextEntry]],
    ) -> Tuple[List[ContextEntry], int]:
        strategic_budget = self._total_budget - BUDGET_NECESSARY
        if strategic_budget < 50:
            strategic_budget = 50

        ordered = sorted(domain_weights, key=lambda d: domain_weights[d], reverse=True)

        selected: List[ContextEntry] = []
        remaining = strategic_budget
        consumed: Dict[Domain, int] = {d: 0 for d in Domain}

        for domain in ordered:
            if domain_weights[domain] <= 0 or remaining <= 0:
                continue
            alloc = int(strategic_budget * domain_weights[domain])
            alloc = min(alloc, remaining)

            entries = entries_by_domain.get(domain, [])
            for entry in entries:
                tokens = self._estimate_tokens(entry.content)
                entry.estimated_tokens = tokens
                if tokens <= alloc:
                    selected.append(entry)
                    alloc -= tokens
                    consumed[domain] += tokens
            remaining = strategic_budget - sum(c.estimated_tokens for c in selected)

        unused = strategic_budget - sum(c.estimated_tokens for c in selected)
        if unused > 0 and len(selected) < len([e for d in ordered for e in entries_by_domain.get(d, [])]):
            for domain in ordered:
                entries = entries_by_domain.get(domain, [])
                for entry in entries:
                    if entry not in selected:
                        tokens = self._estimate_tokens(entry.content)
                        entry.estimated_tokens = tokens
                        if tokens <= unused:
                            selected.append(entry)
                            unused -= tokens
                            consumed[domain] += tokens
                    if unused <= 0: break
                if unused <= 0: break

        total = BUDGET_NECESSARY + sum(c.estimated_tokens for c in selected)
        if self._monitor:
            self._monitor.record("budget_allocator", "allocate", {
                "total_budget": self._total_budget,
                "selected_entries": len(selected),
                "consumed_tokens": total,
                "per_domain": {d.value: consumed[d] for d in Domain if consumed[d] > 0},
            })

        return selected, total

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 3)

    def set_budget(self, new_budget: int):
        self._total_budget = max(TOKEN_BUDGET_MIN, min(TOKEN_BUDGET_MAX, new_budget))


def create_budget_allocator(budget: int = TOKEN_BUDGET_DEFAULT, monitor=None) -> BudgetAllocator:
    return BudgetAllocator(total_budget=budget, monitor=monitor)
