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
        entities = [
            getattr(e, "text", "") or getattr(e, "name", "")
            for e in getattr(block, 'entities', [])
        ][:5]
        intent = getattr(block, 'primary_intent', '')
        block.summary.version = 2
        block.summary.v2_entity = f"entities: {', '.join(entities)} | intent: {intent}"
        block.summary.last_updated_turn = turn

    def _v3_upgrade(self, block, turn: int):
        milestones = self._extract_milestones(block)
        block.summary.version = 3
        block.summary.v3_evolution = " → ".join(milestones[:5])
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
        """Algorithm extracts structure → LLM compresses with context."""
        if not self.llm:
            return None
        try:
            # Algorithm pre-processing: extract structured context
            entities = [e.name for e in getattr(block, 'entities', [])][:5]
            intent = getattr(block, 'primary_intent', '')
            edus = getattr(block, 'atomic_units', [])
            actions = [getattr(e, 'predicate', '') or getattr(e, 'raw_text', '')[:20]
                      for e in edus[-5:] if getattr(e, 'predicate', '')]
            
            v3 = (getattr(block.summary, 'v3_evolution', '') or
                  getattr(block.summary, 'v3_milestone', '') or
                  getattr(block.summary, 'v2_entity', '') or
                  getattr(block.summary, 'v1_raw', '')[:200])
            
            # Structured context for LLM
            struct = f"intent: {intent} | entities: {', '.join(entities)} | actions: {' → '.join(actions[:3])}"
            
            prompt = f"""Compress this conversation block to one sentence (<80 chars). Use the structured context to preserve key semantics.

CONTEXT: {struct}
CONTENT: {v3[:200]}

Output only the compressed sentence."""
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
        for b in sorted(blocks, key=lambda b: self._temperature(b)):
            t = self._temperature(b)
            if t == 0:   # Hot
                text = getattr(b, 'raw_text', '') or ''
                parts.append(f"[Hot] {text[:200]}")
            elif t == 1:  # Warm
                v2 = getattr(getattr(b, 'summary', None), 'v2_entity', '') or ''
                parts.append(f"[Warm] {v2[:150]}")
            elif t == 2:  # Cold
                v3 = (getattr(getattr(b, 'summary', None), 'v3_evolution', '') or
                      getattr(getattr(b, 'summary', None), 'v3_milestone', '') or '')
                parts.append(f"[Cold] {v3[:100]}")
            # Frozen (t=3): skip — retrieval only

        return "\n".join(parts)[:max_tokens]
    
    def _temperature(self, block) -> int:
        """Map block status to temperature tier."""
        status = getattr(block, 'status', 'active')
        return {"active": 0, "paused": 1, "cold": 2, "frozen": 3}.get(status, 0)

    def semantic_wake(self, blocks: dict, query: str) -> int:
        """C4 (R6): BGE>0.8 semantic wake — frozen/cold blocks return to Hot.

        A query that is semantically close to a sleeping block (cosine > 0.8)
        wakes it back to ``active`` so the temperature field behaves like a
        multi-factor field (time×access×semantics) instead of a pure clock.
        Returns the number of blocks woken. Best-effort: a missing encoder
        (broken numpy, no model) silently degrades to zero wakes.
        """
        if not query or not blocks:
            return 0
        woken = 0
        try:
            candidates = [
                bid for bid, b in blocks.items()
                if getattr(b, "status", "active") in ("frozen", "cold")
            ]
            if not candidates:
                return 0
            # 7.7 统一预加载: 复用 ModelService 全局单例（避免每轮重建 encoder，
            # 100 轮压测从 ~18s 降到模型一次加载 + 热查询）。
            enc = self._get_encoder()
            if enc is None:
                return 0
            texts = []
            for bid in candidates:
                b = blocks[bid]
                texts.append(
                    str(getattr(getattr(b, "summary", None), "v3_evolution", "") or "")
                    or str(getattr(b, "name", ""))
                )
            qv = enc.encode(query)[0]
            if not texts:
                return 0
            bvs = enc.encode(texts)
            import numpy as np
            for idx, bid in enumerate(candidates):
                sim = float(np.dot(qv, bvs[idx]))
                if sim > 0.8:
                    blocks[bid].status = "active"
                    woken += 1
        except Exception as e:
            logger.debug("Semantic wake skipped: %s", e)
        return woken

    def _get_encoder(self):
        """惰性复用全局编码器单例（对齐 7.7 统一异步预加载）。"""
        if getattr(self, "_semantic_encoder", None) is None:
            try:
                # 2026-08-16: 全局单例 get_encoder（原注释说单例但用
                # SemanticEncoder() 新建 → 每实例独立加载 ~2GB 模型）。
                from core.agent.compiler.semantic_encoder import get_encoder
                self._semantic_encoder = get_encoder()
            except Exception:
                self._semantic_encoder = False
        return self._semantic_encoder or None


SUMMARY_ENGINE = SummaryEngine()
