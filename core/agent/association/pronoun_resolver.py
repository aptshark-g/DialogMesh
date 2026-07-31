"""Pronoun resolution for L1 ModifierExtractor — Phase 2.

Resolves pronouns (it/this/that/they/它/这/那/他们) to actual entities
using context window tracking. Produces enriched text for GranularityRegulator.

Design: ARCHITECTURE_AUDIT §12-B: raw → resolve() → enriched → cut()
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# Pronoun → placeholder pattern (both EN and CN)
PRONOUN_MAP: Dict[str, str] = {
    # English
    "it": "it", "its": "it", "this": "this", "that": "that",
    "these": "these", "those": "those", "they": "they", "them": "them",
    # Chinese
    "它": "它", "它们": "它们", "这": "这", "这个": "这个",
    "那": "那", "那个": "那个", "这些": "这些", "那些": "那些",
    "他": "他", "她": "她", "他们": "他们", "她们": "她们",
    # Referential
    "该": "该", "其": "其", "此": "此",
}


class PronounResolver:
    """Resolves pronouns to actual entities using context window tracking.

    Algorithm:
      1. Track entities from each sentence/turn
      2. On pronoun encounter, resolve to most recent matching entity
      3. Produce enriched text: [entity,depends_on=context] replaces pronoun
    """

    def __init__(self, window_size: int = 10):
        self.window_size = window_size
        self._entity_history: List[Tuple[str, str]] = []  # [(entity, type), ...]
        self._turn_count = 0

    def resolve(self, text: str, current_entities: List[str] = None) -> str:
        """Resolve pronouns in text and return enriched version.

        Args:
            text: Raw text to process
            current_entities: Entities found in this turn (for context)
        Returns:
            Enriched text with pronouns replaced by [entity,depends_on=context]
        """
        if current_entities:
            for entity in current_entities:
                self._entity_history.append((entity, "current"))
                if len(self._entity_history) > self.window_size:
                    self._entity_history.pop(0)

        enriched = text
        for pronoun, _ in PRONOUN_MAP.items():
            if pronoun not in text.lower():
                continue
            # Find most recent entity
            entity = self._find_referent(pronoun)
            if entity:
                # Replace with [entity] inline — preserves chunkability
                pattern = re.compile(rf"\b{re.escape(pronoun)}\b", re.IGNORECASE)
                replacement = f"[{entity}]"
                enriched = pattern.sub(replacement, enriched)

        self._turn_count += 1
        return enriched

    def _find_referent(self, pronoun: str) -> Optional[str]:
        """Find the most recent entity referent for a pronoun."""
        # Walk history backwards
        for entity, etype in reversed(self._entity_history):
            # Simple heuristic: return most recent non-pronoun entity
            if entity.lower() not in PRONOUN_MAP:
                return entity
        return None

    def add_entity(self, entity: str, etype: str = "extracted") -> None:
        """Manually add an entity to the context window."""
        self._entity_history.append((entity, etype))
        if len(self._entity_history) > self.window_size:
            self._entity_history.pop(0)

    @property
    def recent_entities(self) -> List[str]:
        """Last N entities in window."""
        return [e for e, _ in self._entity_history[-self.window_size:]]
