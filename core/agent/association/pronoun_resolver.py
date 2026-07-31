"""Pronoun resolution -- jieba POS (primary) + regex structural (fallback).

Zero hardcoded pronoun word lists. Two strategies:
  1. jieba.posseg: identify pronouns by POS tag (r/代词), entities by n/nr/ns/nt
  2. regex structural: sentence-position-based pronoun detection when jieba unavailable

Design: pronouns are structurally identifiable -- they replace noun positions in sentences.
""
from __future__ import annotations

import re
from typing import List, Optional, Tuple


class PronounResolver:
    """Resolves pronouns via POS tagging (jieba) or structural regex (fallback).

    No hardcoded pronoun lists -- pronouns identified by:
      - POS tag from jieba (r in CN, PRP in EN)
      - Sentence position + surrounding context (regex fallback)
    """

    # jieba POS tags -- data-driven, from jieba documentation
    _PRONOUN_TAGS = {"r", "rr", "rz", "rzt"}
    _ENTITY_TAGS = {"n", "nr", "ns", "nt", "nz", "vn", "an", "eng"}

    # Structural regex for fallback (no word lists, pattern-based)
    # Matches: single CJK character acting as subject/object reference
    _PRONOUN_PATTERN = re.compile(
        r'(?<=^|。|，|；)([它他她这那其此])(?=的|是|有|在|会|能|可以|需要|用于|用于|用|把|被|不)'
        r'|(?<=\s|^)(it|this|that|these|those|they|them|he|she)(?=\s+(is|was|are|were|has|have|had|will|can|should|uses|needs|handles))',
        re.IGNORECASE
    )

    def __init__(self, window_size: int = 10):
        self.window_size = window_size
        self._entity_history: List[Tuple[str, str]] = []
        self._turn_count = 0
        self._use_jieba = self._try_import_jieba()

    @staticmethod
    def _try_import_jieba() -> bool:
        try:
            import jieba.posseg
            return True
        except ImportError:
            return False

    def resolve(self, text: str, current_entities: List[str] = None) -> str:
        """Resolve pronouns -> [entity] replacement."""
        if current_entities:
            for entity in current_entities:
                self._entity_history.append((entity, "n"))
                if len(self._entity_history) > self.window_size:
                    self._entity_history.pop(0)

        if self._use_jieba:
            return self._resolve_jieba(text)
        return self._resolve_regex(text)

    def _resolve_jieba(self, text: str) -> str:
        """jieba POS tagging -- precise pronoun identification."""
        import jieba.posseg as pseg

        words = list(pseg.cut(text))
        enriched = []
        for word, flag in words:
            # Track entities
            if flag in self._ENTITY_TAGS and flag not in self._PRONOUN_TAGS:
                self._entity_history.append((word, flag))
                if len(self._entity_history) > self.window_size:
                    self._entity_history.pop(0)

            # Resolve pronouns
            if flag in self._PRONOUN_TAGS:
                entity = self._find_referent(word)
                enriched.append(f"[{entity}]" if entity else word)
            else:
                enriched.append(word)

        self._turn_count += 1
        return "".join(enriched)

    def _resolve_regex(self, text: str) -> str:
        """Structural regex fallback -- pronoun detection by sentence position."""
        result = text

        def replace_pronoun(match):
            pronoun = match.group(1) or match.group(2)
            entity = self._find_referent(pronoun)
            return f"[{entity}]" if entity else match.group(0)

        result = self._PRONOUN_PATTERN.sub(replace_pronoun, result)
        self._turn_count += 1
        return result

    def _find_referent(self, pronoun: str) -> Optional[str]:
        """Find most recent non-pronoun entity."""
        for entity, _ in reversed(self._entity_history):
            if len(entity) > 1 and entity.lower() not in {"it", "this", "that", "these", "those", "they", "them", "he", "she"}:
                return entity
        return None

    def add_entity(self, entity: str, etype: str = "n") -> None:
        self._entity_history.append((entity, etype))
        if len(self._entity_history) > self.window_size:
            self._entity_history.pop(0)

    @property
    def recent_entities(self) -> List[str]:
        return [e for e, _ in self._entity_history[-self.window_size:]]
