"""LLM ????? ? Hot?? + Warm?? + Cold?? + Frozen??"""
from typing import Dict, List, Optional
from .models import DiscourseBlock


def _estimate_tokens(text: str) -> int:
    """???? token ? (??? 1.5 ? 1 token)"""
    return int(len(text) * 0.65) + 1


class ContextBuilder:
    """
    LLM ???????
    ????: ???????? + ??????? + ??????????
    4 ???:
      - Hot: ???? (?? 3-5 ?)
      - Warm: v3 ???? (???)
      - Cold: v4 ???? (????)
      - Frozen: ??? (????)
    """

    def __init__(self, max_tokens: int = 4096):
        self.max_tokens = max_tokens

    def build(self, blocks: Dict[str, DiscourseBlock],
              active_block_id: str) -> str:
        """??: ???? LLM ???????"""
        active = blocks.get(active_block_id)
        if not active:
            return ""

        parts = []
        total_tokens = 0
        root_map = self._build_root_map(blocks)

        # 1. Hot: ??????? (?? 3-5 ?)
        hot_text = self._get_hot_text(active)
        parts.append(f"??????\n{hot_text}")
        total_tokens += _estimate_tokens(hot_text)

        # 2. Warm: ??? v3 ??
        ancestor = blocks.get(active.parent_id) if active.parent_id else None
        while ancestor and total_tokens < self.max_tokens * 0.7:
            summary = ancestor.summary.get_best()
            label = root_map.get(ancestor.block_id, ancestor.name)
            parts.append(f"????? - {label}?{summary}")
            total_tokens += _estimate_tokens(summary)
            ancestor = blocks.get(ancestor.parent_id) if ancestor.parent_id else None

        # 3. Cold: ????? v4 ????
        if active.parent_id:
            parent = blocks.get(active.parent_id)
            if parent:
                siblings = [blocks[cid] for cid in parent.child_ids
                           if cid != active_block_id and cid in blocks]
                for sib in siblings[:3]:
                    if total_tokens >= self.max_tokens * 0.9:
                        break
                    summary = sib.summary.get_best()
                    parts.append(f"????? - {sib.name}?{summary}")
                    total_tokens += _estimate_tokens(summary)

        # 4. Frozen: ??? (????)

        return "\n\n".join(parts)

    def _get_hot_text(self, block: DiscourseBlock) -> str:
        """????????? (???? 5 ? EDU)"""
        recent = block.atomic_units[-5:]
        return "\n".join(e.raw_text for e in recent)

    def _build_root_map(self, blocks: Dict[str, DiscourseBlock]) -> Dict[str, str]:
        """?????? (block_id -> name)"""
        return {bid: b.name for bid, b in blocks.items()}

    def find_by_reference(self, blocks: Dict[str, DiscourseBlock],
                          reference: str) -> Optional[str]:
        """????: '????X' -> block_id"""
        ref_lower = reference.lower()
        for bid, block in blocks.items():
            if block.status == "frozen":
                continue
            name_lower = block.name.lower()
            if ref_lower in name_lower:
                return bid
            for edu in block.atomic_units:
                if ref_lower in edu.raw_text.lower():
                    return bid
            for ent in block.entities:
                if hasattr(ent, "text") and ref_lower in ent.text.lower():
                    return bid
        return None


CONTEXT_BUILDER = ContextBuilder()
