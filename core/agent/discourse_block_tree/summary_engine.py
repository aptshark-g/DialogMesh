"""??????? ? v1(raw) -> v2(entity) -> v3(milestone) -> v4(LLM compressed)"""
import time
from typing import List, Optional
from .models import DiscourseBlock, DiscourseEntity


class SummaryEngine:
    """
    ????????????:
    v1: ???? (????)
    v2: ?????? (?? EDU > 3 ??)
    v3: ????? (?? > 5 ???)
    v4: LLM ????? (?? Cold ????)
    """

    def __init__(self, llm_provider=None):
        self.llm = llm_provider

    def check_upgrade(self, block: DiscourseBlock, current_turn: int) -> bool:
        """??????????????????"""
        version = block.summary.version

        # v1 -> v2: ?? EDU > 3
        if version < 2 and len(block.atomic_units) > 3:
            block.summary.upgrade_v2(block.entities, block.primary_intent)
            block.summary.last_updated_turn = current_turn
            return True

        # v2 -> v3: ?? > 5 ?
        if version < 3 and (current_turn - block.created_at_turn) > 5:
            milestones = self._extract_milestones(block)
            block.summary.upgrade_v3(milestones)
            block.summary.last_updated_turn = current_turn
            return True

        # v3 -> v4: ??? Cold ?? + ? LLM
        if version < 4 and block.status == "cold" and self.llm:
            compressed = self._llm_compress(block)
            if compressed:
                block.summary.upgrade_v4(compressed)
                block.summary.last_updated_turn = current_turn
                return True

        return False

    def _extract_milestones(self, block: DiscourseBlock) -> List[str]:
        """??????????/???"""
        milestones = []
        for edu in block.atomic_units:
            if edu.negation or edu.question:
                milestone = f"{edu.predicate or edu.raw_text[:15]}"
                if milestone not in milestones:
                    milestones.append(milestone)
            if edu.imperative and edu.obj:
                milestone = f"?{edu.predicate} {edu.obj}"
                if milestone not in milestones:
                    milestones.append(milestone)
        if not milestones:
            milestones.append(block.primary_intent or block.name[:20])
        return milestones[:5]

    def _llm_compress(self, block: DiscourseBlock) -> Optional[str]:
        """LLM ??????????"""
        if not self.llm:
            return None
        try:
            text = block.summary.v3_evolution or block.summary.v2_entity or block.summary.v1_raw[:200]
            prompt = f"?????????????50??????:\n{text}"
            result = self.llm(prompt) if callable(self.llm) else None
            return result[:100] if result else None
        except Exception:
            return None


SUMMARY_ENGINE = SummaryEngine()
