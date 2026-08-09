"""v3.2 causal_substrate → merged to core.agent.association (canonical implementation)."""
from core.agent.association.causal_substrate import CausalSubstrate
from core.agent.association.models import MetaRole, SkeletonMatch, CausalConstraints

__all__ = ["CausalSubstrate", "MetaRole", "SkeletonMatch", "CausalConstraints"]
