"""Context Engineering: Source -> Rank -> Assemble pipeline."""
from core.agent.v4.context.source import (
    ContextSource, ContextItem, CrossDomainContext,
    ObservationSource, KnowledgeSource, SkillSource,
    WorldSource, EngineeringSource,
    CausalSource, CausalSubstrateAdapter,
)
from core.agent.v4.context.assembler import ContextAssembler
from core.agent.v4.context.cross_domain_ir import (
    CrossDomainContextIR, IREntry, CrossRef,
    DomainAllocation as IRDomainAllocation,
    IntentCategory as IRIntentCategory,
    DomainRole as IRDomainRole,
    CompileStrategy,
)
from core.agent.v4.context.domain_selector import (
    DomainSelector, IntentCategory, Domain, DomainRole,
    DomainAllocation, DomainSelection,
)
from core.agent.v4.context.budget_allocator import (
    BudgetAllocator, DomainBudget, BudgetPlan,
)
from core.agent.v4.context.cross_domain_expander import (
    CrossDomainExpander, DomainProjection, ExpandedEventNode,
)
from core.agent.v4.context.cross_ref_builder import (
    CrossRefBuilder, CrossRefPointer, ContextIREntry,
)
from core.agent.v4.context.pruner import (
    SubgraphPruner, PruningNode, PruningConfig,
)

__all__ = [
    # Legacy pipeline
    "ContextSource", "ContextItem", "CrossDomainContext",
    "ObservationSource", "KnowledgeSource", "SkillSource",
    "WorldSource", "EngineeringSource",
    "CausalSource", "CausalSubstrateAdapter",
    "ContextAssembler",
    # New v4 Context Engineering
    "CrossDomainContextIR", "IREntry", "CrossRef",
    "IRDomainAllocation", "IRIntentCategory", "IRDomainRole", "CompileStrategy",
    "DomainSelector", "IntentCategory", "Domain", "DomainRole",
    "DomainAllocation", "DomainSelection",
    "BudgetAllocator", "DomainBudget", "BudgetPlan",
    "CrossDomainExpander", "DomainProjection", "ExpandedEventNode",
    "CrossRefBuilder", "CrossRefPointer", "ContextIREntry",
    "SubgraphPruner", "PruningNode", "PruningConfig",
]
