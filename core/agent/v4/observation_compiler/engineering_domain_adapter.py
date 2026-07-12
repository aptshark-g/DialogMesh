"""Engineering domain adapter for TieredActionResolver."""
from core.agent.v4.tiered_action_resolver import DomainAdapter, EmbeddingIndex


def create_engineering_adapter() -> DomainAdapter:
    return DomainAdapter(
        domain="engineering",
        rules={
            "reorder": ["reorder", "rearrange", "move", "shift", "drag", "drop",
                        "before", "after", "position"],
            "add": ["add", "create", "new", "insert", "append", "generate", "build"],
            "remove": ["delete", "remove", "drop", "uninstall", "unlink", "destroy"],
            "configure": ["configure", "setup", "config", "set", "initialize"],
            "deploy": ["deploy", "release", "publish", "push", "install", "launch"],
            "rollback": ["rollback", "revert", "undo", "restore", "recover"],
            "connect": ["connect", "link", "wire", "attach", "join", "bind"],
            "disconnect": ["disconnect", "detach", "separate", "unlink", "unbind"],
            "query_status": ["inspect", "check", "query", "examine", "status", "view"],
            "optimize": ["optimize", "improve", "enhance", "speed", "tune"],
        },
        action_index=EmbeddingIndex(dim=32),
        default_action="query_status",
    )
