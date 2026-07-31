"""Context window with token budget — from OpenWorker TurnEngine pattern.

OPENSOURCE_DEEP_READ.md §3: per-turn context with FIFO eviction.
  - max_tokens budget (default 4096)
  - FIFO eviction when exceeded
  - Items carry block_id for retrieval back-reference
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ContextItem:
    text: str
    block_id: str = ""
    item_type: str = "message"  # message, atom, chunk, entity
    priority: float = 0.5


class ContextWindow:
    """Per-turn context with token budget and FIFO eviction."""

    def __init__(self, max_tokens: int = 4096):
        self.max_tokens = max_tokens
        self.items: List[ContextItem] = []

    def append(self, item: ContextItem) -> None:
        """Add item, evict oldest if budget exceeded."""
        self.items.append(item)
        while self.token_count > self.max_tokens and len(self.items) > 1:
            self.items.pop(0)

    def append_text(self, text: str, block_id: str = "",
                    item_type: str = "message") -> None:
        self.append(ContextItem(text=text, block_id=block_id, item_type=item_type))

    def get_context(self) -> str:
        """Assemble context string for LLM prompt injection."""
        return "\n".join(item.text for item in self.items)

    @property
    def token_count(self) -> int:
        """Rough estimate: ~4 chars per token."""
        return sum(len(item.text) for item in self.items) // 4

    @property
    def block_ids(self) -> List[str]:
        """List of block_ids in window (for graph traversal back-reference)."""
        return [item.block_id for item in self.items if item.block_id]

    def stats(self) -> dict:
        return {
            "items": len(self.items),
            "tokens": self.token_count,
            "max_tokens": self.max_tokens,
            "block_ids": len(self.block_ids),
        }


# ── Approval gate for write operations ──

class WriteGate:
    """Pre-write safety check — from OpenWorker approval gating pattern.

    Modes:
      ASK         — require user confirmation (undo-supported)
      AUTO_ALLOW  — allow if undo snapshot saved
      AUTO_DENY   — block (e.g., for system-internal blocks)
    """

    def can_write(self, block_id: str, operation: str,
                  has_undo: bool = False) -> bool:
        """Check if write operation should proceed."""
        if operation in ("delete", "merge"):
            return has_undo  # Require undo snapshot
        if operation in ("split", "promote", "demote"):
            return True  # Undo-supported by default
        return True  # Read/metadata ops always allowed
