"""Behavior domain adapter."""
from core.agent.v4.tiered_action_resolver import DomainAdapter, EmbeddingIndex


def create_behavior_adapter() -> DomainAdapter:
    return DomainAdapter(
        domain="behavior",
        rules={
            "drag": ["drag", "move", "pull", "slide", "swipe"],
            "click": ["click", "press", "tap", "push"],
            "select": ["select", "highlight", "choose", "pick", "focus"],
            "hover": ["hover", "mouseover", "dwell", "linger"],
            "double_click": ["double", "dblclick", "double-click"],
            "deselect": ["deselect", "unselect", "clear", "unfocus"],
            "cancel": ["cancel", "dismiss", "close", "abort", "escape"],
            "type": ["type", "input", "enter", "write", "keypress"],
            "scroll": ["scroll", "wheel", "navigate"],
        },
        action_index=EmbeddingIndex(dim=32),
        default_action="click",
    )
