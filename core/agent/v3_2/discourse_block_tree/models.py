"""Discourse Block Tree models — DiscourseBlock, CrossReference, GroupReference"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CrossReference:
    target_id: str
    ref_type: str
    strength: float = 0.5


@dataclass
class GroupReference:
    group_id: str
    block_ids: list[str] = field(default_factory=list)
    ref_type: str = "analogy"
    strength: float = 0.5
    context_summary: str = ""
    created_at_turn: int = 0


@dataclass
class DiscourseBlock:
    block_id: str
    turn_range: tuple[int, int] = (0, 0)
    summary: str = ""
    cross_refs: list[CrossReference] = field(default_factory=list)
    group_refs: list[GroupReference] = field(default_factory=list)
    embedding: Optional[list[float]] = None


class DiscourseBlockTreeManager:
    def __init__(self):
        self.blocks: dict[str, DiscourseBlock] = {}
        self.group_ref_index: dict[str, GroupReference] = {}

    def add_block(self, block: DiscourseBlock) -> None:
        self.blocks[block.block_id] = block

    def add_group_reference(self, group_ref: GroupReference) -> None:
        """Register a GroupReference in the index and attach it to all member blocks."""
        self.group_ref_index[group_ref.group_id] = group_ref
        for bid in group_ref.block_ids:
            block = self.blocks.get(bid)
            if block is not None:
                # Avoid duplicates
                existing_ids = {g.group_id for g in block.group_refs}
                if group_ref.group_id not in existing_ids:
                    block.group_refs.append(group_ref)

    def find_activated_groups(self, block_id: str) -> list[GroupReference]:
        """Return all groups that contain the given block_id."""
        activated = []
        for gr in self.group_ref_index.values():
            if block_id in gr.block_ids:
                activated.append(gr)
        return activated
