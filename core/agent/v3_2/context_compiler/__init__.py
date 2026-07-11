"""ContextCompiler Phase 1: independent modules ready for testing."""

from .models import (
    Domain, IntentCategory, IntentEstimate, DomainSelection,
    DomainFeedback, ContextEntry, CrossRef, CrossDomainContextIR,
)
from .domain_selector import DomainSelector, create_domain_selector
from .budget_allocator import BudgetAllocator, create_budget_allocator
from .context_serializer import (
    ContextSerializer, create_context_serializer,
    StandardStrategy, CompactStrategy, PlainStrategy,
)
from .monitor import CompilerMonitor

__all__ = [
    "Domain", "IntentCategory", "IntentEstimate", "DomainSelection",
    "DomainFeedback", "ContextEntry", "CrossRef", "CrossDomainContextIR",
    "DomainSelector", "create_domain_selector",
    "BudgetAllocator", "create_budget_allocator",
    "ContextSerializer", "create_context_serializer",
    "StandardStrategy", "CompactStrategy", "PlainStrategy",
    "CompilerMonitor",
]
