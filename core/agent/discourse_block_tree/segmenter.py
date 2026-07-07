"""?????? ? ?? LCseg/TextTiling ????????"""
from typing import List, Optional
from .models import EDU, DiscourseBlock, CohesionScore
from .macro_micro_quantizer import QUANTIZER


class Segmenter:
    """
    ??????? EDU ??? cohesion ????? DiscourseBlock ???
    ?? LCseg / TextTiling ?????????
    """

    def __init__(self, global_split_threshold: float = 0.5):
        self.global_split_threshold = global_split_threshold

    def segment(self, edus: List[EDU], scores: Optional[List[CohesionScore]] = None,
                context_entities: Optional[list] = None) -> List[DiscourseBlock]:
        """??: ? EDU ??? cohesion ????? DiscourseBlock ??"""
        if not edus:
            return []
        if scores is None or len(scores) != len(edus) - 1:
            scores = QUANTIZER.score_all(edus)

        cohesion_values = [s.total_score for s in scores]

        # 1. ?? cohesion ?? (????? + ????)
        boundaries = []
        for i, score in enumerate(cohesion_values):
            left = cohesion_values[i - 1] if i > 0 else 1.0
            right = cohesion_values[i + 1] if i < len(cohesion_values) - 1 else 1.0
            is_local_min = score < left and score < right
            if is_local_min and score < self.global_split_threshold:
                boundaries.append(i)  # ? i ? i+1 ????

        # 2. ?????
        blocks = []
        start = 0
        for b in boundaries:
            block_edus = edus[start : b + 1]
            blocks.append(self._create_block(block_edus, context_entities))
            start = b + 1
        blocks.append(self._create_block(edus[start:], context_entities))

        # 3. ???: ???? (??????)
        blocks = self._merge_isolated(blocks)

        return blocks

    def _create_block(self, edus: List[EDU], context_entities: Optional[list] = None) -> DiscourseBlock:
        """? EDU ???? DiscourseBlock"""
        import hashlib
        first = edus[0]
        raw = " ".join(e.raw_text for e in edus)
        block_id = hashlib.md5(raw.encode()).hexdigest()[:12]
        name = first.predicate + " " + first.obj if first.predicate and first.obj else first.raw_text[:30]

        block = DiscourseBlock(block_id=block_id, name=name)
        for edu in edus:
            block.add_edu(edu)
        block.primary_intent = first.predicate or "unknown"
        block.summary.v1_raw = raw[:200]
        block.cohesion_internal = 1.0 if len(edus) == 1 else 0.8
        return block

    def _merge_isolated(self, blocks: List[DiscourseBlock], min_size: int = 2) -> List[DiscourseBlock]:
        """????: ???????? EDU ??????????????"""
        if len(blocks) < 3:
            return blocks
        result = [blocks[0]]
        for i in range(1, len(blocks)):
            if len(blocks[i].atomic_units) < min_size and len(result[-1].atomic_units) < min_size:
                # ??????
                for edu in blocks[i].atomic_units:
                    result[-1].add_edu(edu)
                result[-1].atomic_units.extend(blocks[i].atomic_units)
            else:
                result.append(blocks[i])
        return result

    def set_threshold(self, threshold: float):
        """????????"""
        self.global_split_threshold = max(0.1, min(0.9, threshold))


SEGMENTER = Segmenter()
