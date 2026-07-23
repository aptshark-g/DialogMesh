"""v4 BehaviorGraph adapter package."""
from core.agent.behavior.adapter import (
    BehaviorGraphAdapter,
    BehaviorContextItem,
    BehaviorChainResult,
)
from core.agent.behavior.causal_adapter import (
    CausalSubstrateAdapter,
    CausalInsight,
)
from core.agent.behavior.runtime_hook import (
    BehaviorGraphRuntimeHook,
    register_with_engine,
)

__all__ = [
    "BehaviorGraphAdapter",
    "BehaviorContextItem",
    "BehaviorChainResult",
    "CausalSubstrateAdapter",
    "CausalInsight",
    "BehaviorGraphRuntimeHook",
    "register_with_engine",
]
