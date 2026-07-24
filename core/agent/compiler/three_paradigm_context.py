"""Three-Paradigm LLM Context — temperature × distance × information_value.

Agent-native: LLM receives structured compass tags, decides attention routing itself.
Not algorithm-decides → LLM-navigates.
"""

from __future__ import annotations
from typing import List, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


class ThreeParadigmContext:
    """Builds LLM prompt context with temperature/distance/value compass tags.

    Usage:
        compass = ThreeParadigmContext(summary_engine, topic_tree)
        prompt = compass.build(blocks, current_text="延迟飙升",
                              max_tokens=3000)
        # → LLM receives tagged, prioritized context blocks
    """

    def __init__(self, summary_engine=None, topic_tree=None):
        self.engine = summary_engine
        self.topic_tree = topic_tree
        self._entity_freq: Dict[str, int] = {}
        self._total_blocks: int = 0
        self._intent_history: List[str] = []

    def build(self, blocks: list, current_text: str = "",
              max_tokens: int = 3000) -> str:
        """Build prioritized LLM context with compass tags.

        Returns: formatted prompt with [Temp·Dist·Value] tags per block.
        """
        if not blocks:
            return ""

        # Compute three paradigms for each block
        scored = []
        for b in blocks:
            temp = self._temperature(b)            # 0-3
            value = self._information_value(b)     # 0-1
            dist = self._distance(b, current_text) # 0-1

            # Priority: temperature recency + info value + inverse distance
            priority = (0.25 * (3 - temp) / 3 +
                       0.40 * value +
                       0.35 * (1 - dist))
            scored.append((priority, b, temp, value, dist))

        # Sort: highest priority first (most important → least)
        scored.sort(key=lambda x: -x[0])

        # Build tagged context
        parts = []
        for pri, b, temp, value, dist in scored:
            tag = self._format_tag(temp, value, dist)
            text = self._block_text(b)
            if text:
                parts.append(f"{tag} {text}")

        return "\n".join(parts)[:max_tokens]

    def _temperature(self, block) -> int:
        """0=Hot, 1=Warm, 2=Cold, 3=Frozen."""
        if self.engine:
            return self.engine._temperature(block)
        status = getattr(block, 'status', 'active')
        return {"active": 0, "paused": 1, "cold": 2, "frozen": 3}.get(status, 0)

    def _information_value(self, block) -> float:
        """Shannon self-info: rare entities + novel intents + deviant actions.

        Returns 0-1, higher = more valuable.
        """
        entities = getattr(block, 'entities', [])
        intent = getattr(block, 'primary_intent', '')
        edus = getattr(block, 'atomic_units', [])

        # Entity rarity
        if entities and self._total_blocks > 0:
            rarities = []
            for e in entities:
                name = e.name if hasattr(e, 'name') else str(e)
                freq = self._entity_freq.get(name, 0)
                rarity = 1.0 - (freq / max(1, self._total_blocks))
                rarities.append(rarity)
            entity_rarity = sum(rarities) / len(rarities) if rarities else 0.3
        else:
            entity_rarity = 0.3

        # Intent novelty
        if intent and self._intent_history:
            recent = self._intent_history[-5:]
            intent_novelty = 0.8 if intent not in recent else 0.2
        else:
            intent_novelty = 0.5

        # Action deviation
        action_count = len(edus)
        avg_actions = (sum(len(getattr(b, 'atomic_units', [])) 
                          for b in self._intent_history[:1] if hasattr(b, 'atomic_units'))
                       / max(1, len(self._intent_history))) if self._intent_history else action_count
        action_deviation = abs(action_count - avg_actions) / max(1, avg_actions) if avg_actions > 0 else 0.3

        return min(1.0, 0.3 * entity_rarity + 0.35 * intent_novelty + 0.35 * action_deviation)

    def _distance(self, block, current_text: str) -> float:
        """Cognitive distance: how far is this block from current context?

        0=familiar/same topic, 1=completely different domain.
        """
        if not self.topic_tree or not current_text:
            return 0.5  # neutral

        try:
            # Entity overlap as proxy for topic distance
            block_entities = set()
            for e in getattr(block, 'entities', []):
                block_entities.add(e.name if hasattr(e, 'name') else str(e))

            # Current text entities (simple extraction)
            current_lower = current_text.lower()
            overlap = sum(1 for e in block_entities if e.lower() in current_lower)

            if block_entities:
                return 1.0 - (overlap / len(block_entities))
            return 0.5
        except Exception:
            return 0.5

    def _block_text(self, block) -> str:
        """Get best available text for a block."""
        text = (getattr(block, 'raw_text', '') or
                getattr(getattr(block, 'summary', None), 'v3_milestone', '') or
                getattr(getattr(block, 'summary', None), 'v2_entity', ''))
        return text[:250].replace('\n', ' ').strip()

    def _format_tag(self, temperature: int, value: float, distance: float) -> str:
        """Format compass tag: [Temp·Value·Dist]."""
        temp_labels = ["Hot", "Warm", "Cold", "Frozen"]
        t_label = temp_labels[min(temperature, 3)]

        if value > 0.7:
            v_label = "★★★"
        elif value > 0.4:
            v_label = "★★"
        else:
            v_label = "★"

        if distance > 0.7:
            d_label = "Far"
        elif distance > 0.3:
            d_label = "Mid"
        else:
            d_label = "Near"

        return f"[{t_label}·{v_label}·{d_label}]"

    def update_stats(self, blocks: list, intents: List[str] = None):
        """Update entity frequency and intent history for information value."""
        for b in blocks:
            for e in getattr(b, 'entities', []):
                name = e.name if hasattr(e, 'name') else str(e)
                self._entity_freq[name] = self._entity_freq.get(name, 0) + 1
            self._total_blocks += 1

        if intents:
            self._intent_history.extend(intents)
            self._intent_history = self._intent_history[-50:]  # keep last 50
