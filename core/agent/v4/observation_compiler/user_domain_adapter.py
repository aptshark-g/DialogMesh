"""User profile domain adapter."""
from core.agent.v4.tiered_action_resolver import DomainAdapter, EmbeddingIndex


def create_user_adapter() -> DomainAdapter:
    return DomainAdapter(
        domain="user",
        rules={
            "preference_set": ["prefer", "like", "want", "choose", "set", "favorite"],
            "preference_get": ["what do I", "remember my", "my settings", "my config"],
            "style_aggressive": ["quick", "fast", "immediate", "auto"],
            "style_conservative": ["careful", "review", "confirm", "check first"],
            "expertise_high": ["expert", "advanced", "skip intro", "know how"],
            "expertise_low": ["beginner", "new to", "first time", "help me"],
        },
        action_index=EmbeddingIndex(dim=32),
        default_action="preference_set",
    )
