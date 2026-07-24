"""Summary Engine — Progressive 4-level summary: v1(raw)→v2(entity)→v3(milestone)→v4(LLM).

Design: docs/v3.0/design_discourse_block_tree_v2.md §7
Temperature: Hot(v1) → Warm(v2) → Cold(v3) → Frozen(v4)
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class SummaryEngine:
    """Progressive summary — 4 temperature levels.

    Hot(t=0):  v1 raw text — full detail
    Warm(t=1): v2 entity summary — key entities + intents
    Cold(t=2): v3 milestone — key events/outcomes
    Frozen(t=3): v4 LLM compress — minimal, retrieval only
    """

    def __init__(self, llm=None):
        self.llm = llm

    def check_upgrade(self, block, current_turn: int) -> bool:
        """Check and apply summary upgrade if conditions met."""
        version = getattr(block.summary, 'version', 1) if hasattr(block, 'summary') else 1

        if version < 2 and len(getattr(block, 'atomic_units', [])) > 3:
            self._v2_upgrade(block, current_turn)
            return True

        if version < 3 and (current_turn - getattr(block, 'created_at_turn', 0)) > 5:
            self._v3_upgrade(block, current_turn)
            return True

        if version < 4 and getattr(block, 'status', '') == 'cold' and self.llm:
            self._v4_upgrade(block, current_turn)
            return True

        return False

    def _v2_upgrade(self, block, turn: int):
        entities = [e.name for e in getattr(block, 'entities', [])][:5]
        intent = getattr(block, 'primary_intent', '')
        block.summary.version = 2
        block.summary.v2_entity = f"entities: {', '.join(entities)} | intent: {intent}"
        block.summary.last_updated_turn = turn

    def _v3_upgrade(self, block, turn: int):
        milestones = self._extract_milestones(block)
        block.summary.version = 3
        block.summary.v3_milestone = " → ".join(milestones[:5])
        block.summary.last_updated_turn = turn

    def _v4_upgrade(self, block, turn: int):
        compressed = self._llm_compress(block)
        if compressed:
            block.summary.version = 4
            block.summary.v4_compressed = compressed
            block.summary.last_updated_turn = turn
            block.status = 'frozen'

    def _extract_milestones(self, block) -> List[str]:
        milestones = []
        for edu in getattr(block, 'atomic_units', []):
            if getattr(edu, 'negation', False) or getattr(edu, 'uncertainty', False):
                m = f"!{getattr(edu, 'predicate', '') or getattr(edu, 'raw_text', '')[:15]}"
                if m not in milestones: milestones.append(m)
            if getattr(edu, 'imperative', False) and getattr(edu, 'obj', ''):
                m = f">{getattr(edu, 'predicate', '')} {edu.obj}"
                if m not in milestones: milestones.append(m)
        if not milestones:
            milestones.append(getattr(block, 'primary_intent', '') or 
                            getattr(block, 'name', 'topic')[:20])
        return milestones[:5]

    def _llm_compress(self, block) -> Optional[str]:
        if not self.llm:
            return None
        try:
            text = (getattr(block.summary, 'v3_milestone', '') or
                    getattr(block.summary, 'v2_entity', '') or
                    getattr(block.summary, 'v1_raw', '')[:200])
            prompt = f"Compress to one sentence (<80 chars) preserving key actions/entities:\n{text}"
            resp = self.llm.generate(prompt, max_tokens=100, temperature=0.1)
            return resp[:150] if resp else None
        except Exception as e:
            logger.debug("LLM compress failed: %s", e)
            return None

    def build_context(self, blocks: list, max_tokens: int = 2000) -> str:
        """Build LLM context from blocks by temperature level.

        Hot blocks: full text | Warm: entity summary | Cold: milestone | Frozen: skip.
        """
        parts = []
        for b in sorted(blocks, key=lambda b: getattr(b, 'temperature', 0)):
            t = getattr(b, 'temperature', 0)
            if t == 0:   # Hot
                text = getattr(b, 'raw_text', '') or ''
                parts.append(f"[Hot] {text[:200]}")
            elif t == 1:  # Warm
                v2 = getattr(getattr(b, 'summary', None), 'v2_entity', '') or ''
                parts.append(f"[Warm] {v2[:150]}")
            elif t == 2:  # Cold
                v3 = getattr(getattr(b, 'summary', None), 'v3_milestone', '') or ''
                parts.append(f"[Cold] {v3[:100]}")
            # Frozen (t=3): skip — retrieval only

        return "\n".join(parts)[:max_tokens]
