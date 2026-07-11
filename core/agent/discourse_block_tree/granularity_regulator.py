"""?????? ? BDI (Block Density Index) + BOR (Boundary Overlap Ratio)"""
from typing import Dict, List
from .models import DiscourseBlock


class GranularityRegulator:
    """
    ????????
    BDI: ?????????????
    BOR: ???????????????
    ??? 5 ????????????????
    """

    def __init__(self, optimal_blocks_per_topic: int = 5,
                 global_split_threshold: float = 0.5):
        self.optimal = optimal_blocks_per_topic
        self.global_split_threshold = global_split_threshold
        self._last_regulation_turn = 0

    def regulate(self, blocks: Dict[str, DiscourseBlock], current_turn: int) -> List[str]:
        """
        ??: ??????????
        ??: ???? block_id ??
        """
        if current_turn - self._last_regulation_turn < 5:
            return []  # ???

        modified = []
        all_blocks = list(blocks.values())
        if len(all_blocks) < 3:
            return modified

        # 1. ????: ???? (?? cohesion ??? EDU ?)
        for block in all_blocks:
            if block.cohesion_internal > 0.9 and len(block.atomic_units) > block.capacity:
                sub_blocks = self._split_block(block)
                if len(sub_blocks) > 1:
                    modified.append(block.block_id)
                    self._last_regulation_turn = current_turn
                    return modified  # ???????

        # 2. ????: ???? (??? -> ??)
        children_by_parent = self._group_by_parent(blocks)
        for parent_id, children in children_by_parent.items():
            if len(children) > 8:
                for i in range(len(children) - 1):
                    if children[i].cohesion_boundary > 0.75:
                        modified.append(children[i].block_id)
                        modified.append(children[i + 1].block_id)
                        self._last_regulation_turn = current_turn
                        return modified

        # 3. BOR ???????
        self._adapt_threshold(all_blocks)
        self._last_regulation_turn = current_turn
        return modified

    def _split_block(self, block: DiscourseBlock) -> List[DiscourseBlock]:
        """?????: ? cohesion ??"""
        from .segmenter import SEGMENTER
        edus = block.atomic_units
        if len(edus) < 3:
            return [block]
        # ??? segmenter ??????????
        old_threshold = SEGMENTER.global_split_threshold
        SEGMENTER.set_threshold(0.3)  # ??????
        new_blocks = SEGMENTER.segment(edus)
        SEGMENTER.set_threshold(old_threshold)
        return new_blocks if len(new_blocks) > 1 else [block]

    def _group_by_parent(self, blocks: Dict[str, DiscourseBlock]) -> Dict[str, List[DiscourseBlock]]:
        result = {}
        for b in blocks.values():
            pid = b.parent_id or "root"
            if pid not in result:
                result[pid] = []
            result[pid].append(b)
        return result

    def _adapt_threshold(self, all_blocks: List[DiscourseBlock]):
        """BOR ???: ???? / ????"""
        children_by_parent = self._group_by_parent({b.block_id: b for b in all_blocks})
        total_children = sum(len(c) for c in children_by_parent.values())
        total_parents = max(len(children_by_parent), 1)
        actual_boundaries = total_children - total_parents
        expected_boundaries = total_children * 0.5
        bor = actual_boundaries / expected_boundaries if expected_boundaries > 0 else 1.0
        if bor > 1.5:
            self.global_split_threshold = min(self.global_split_threshold * 1.2, 0.9)
        elif bor < 0.6:
            self.global_split_threshold = max(self.global_split_threshold * 0.8, 0.1)

    def get_config(self) -> dict:
        return {"threshold": round(self.global_split_threshold, 3),
                "last_regulation": self._last_regulation_turn}


REGULATOR = GranularityRegulator()
