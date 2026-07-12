"""Memory domain adapter."""
from core.agent.v4.tiered_action_resolver import DomainAdapter, EmbeddingIndex


def create_memory_adapter() -> DomainAdapter:
    return DomainAdapter(
        domain="memory",
        rules={
            "remember": ["remember", "memorize", "save", "keep", "store", "note"],
            "recall": ["recall", "retrieve", "fetch", "load", "get"],
            "forget": ["forget", "remove", "delete_memory", "clear"],
            "summarize": ["summarize", "compress", "distill", "condense"],
        },
        action_index=EmbeddingIndex(dim=32),
        default_action="remember",
    )
