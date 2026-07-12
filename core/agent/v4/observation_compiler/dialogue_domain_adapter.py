"""Dialogue domain adapter for TieredActionResolver."""
from core.agent.v4.tiered_action_resolver import DomainAdapter, EmbeddingIndex


def create_dialogue_adapter() -> DomainAdapter:
    return DomainAdapter(
        domain="dialogue",
        rules={
            "ask": ["how", "what", "why", "when", "where", "?", "？",
                    "how to", "what is", "explain", "tell me"],
            "confirm": ["yes", "ok", "okay", "confirm", "agree", "right",
                        "correct", "good", "that works"],
            "reject": ["no", "not", "reject", "disagree", "wrong",
                       "incorrect", "don't", "cannot"],
            "clarify": ["what do you mean", "explain", "clarify",
                        "elaborate", "can you explain", "detail"],
            "request_change": ["change", "modify", "update", "fix",
                               "add", "remove", "delete", "replace",
                               "move", "put", "set", "configure"],
            "inform": ["i have", "there is", "it is", "currently",
                       "already", "the problem is", "i found"],
            "summarize": ["summarize", "recap", "summary", "overview",
                          "brief", "tldr"],
        },
        action_index=EmbeddingIndex(dim=32),
        default_action="inform",
    )
