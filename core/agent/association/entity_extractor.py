"""Entity extractor with gleaning — iterative refinement from GraphRAG pattern.

Gleaning: LLM checks "any missed entities?" for up to max_gleanings rounds.
90% of entities found in round 0; gleaning catches the remaining 10%.
Early stop when no new entities found.

Design: OPENSOURCE_DEEP_READ §2, ARCHITECTURE_AUDIT §12-A.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger("dm.entity_extractor")


class EntityExtractor:
    """Iterative entity extraction with gleaning refinement.

    Replaces single-pass extraction with multi-round LLM verification.
    Each gleaning round asks: "any missed entities of type X?"

    Cost: +1 LLM call per gleaning round. Max 2 rounds (90%+ found in round 0).
    Early stop when no new entities found.
    """

    GLEANING_PROMPT = """Analyze this text and identify all entities of type {entity_types}.

Previous round found: {previous_entities}

Your task: find any ADDITIONAL entities that were MISSED.
Return ONLY newly discovered entities. If none found, return empty list.

Text: {text}

Format: {{"entities": [{{"name": "...", "type": "...", "description": "..."}}, ...]}}
JSON:"""

    INITIAL_PROMPT = """Extract all entities from this text.

Entity types: module, function, class, config, token, api, dependency, protocol, concept

Text: {text}

Format: {{"entities": [{{"name": "...", "type": "...", "description": "..."}}]}}
JSON:"""

    DEFAULT_ENTITY_TYPES = [
        "module", "function", "class", "config", "token", "api",
        "dependency", "protocol", "concept", "endpoint", "service"
    ]

    def __init__(self, max_gleanings: int = 2, gateway=None):
        self.max_gleanings = max_gleanings
        self._gateway = gateway
        self._total_rounds = 0
        self._total_gleaned = 0  # entities found via gleaning

    def extract(self, text: str, entity_types: List[str] = None,
                block_id: str = "") -> List[Dict]:
        """Extract entities with iterative gleaning.

        Returns list of {name, type, description, confidence}.
        """
        if not self._gateway:
            return self._rule_based_fallback(text)

        types = entity_types or self.DEFAULT_ENTITY_TYPES
        all_entities: List[Dict] = []

        # Round 0: initial extraction
        initial = self._ask_llm(
            self.INITIAL_PROMPT.format(text=text)
        )
        entities = self._parse_entities(initial)
        all_entities.extend(entities)
        self._total_rounds = 1

        # Rounds 1..max_gleanings: gleaning
        for round_num in range(self.max_gleanings):
            previous = [e["name"] for e in all_entities]
            gleaning_result = self._ask_llm(
                self.GLEANING_PROMPT.format(
                    text=text,
                    entity_types=", ".join(types),
                    previous_entities=", ".join(previous) if previous else "none",
                )
            )
            new_entities = self._parse_entities(gleaning_result)

            if not new_entities:
                logger.debug("Gleaning round %d: no new entities — early stop", round_num + 1)
                break

            all_entities.extend(new_entities)
            self._total_gleaned += len(new_entities)
            self._total_rounds += 1
            logger.debug("Gleaning round %d: found %d new entities",
                         round_num + 1, len(new_entities))

        # Assign confidence based on round
        for i, entity in enumerate(all_entities):
            entity.setdefault("block_id", block_id)
            if "confidence" not in entity:
                # Round 0 entities have higher confidence
                if i < len(all_entities) - self._total_gleaned:
                    entity["confidence"] = 0.8
                else:
                    entity["confidence"] = 0.5  # gleaned

        return all_entities

    def _ask_llm(self, prompt: str) -> str:
        """Send prompt to LLM gateway. Falls back gracefully."""
        try:
            return self._gateway.ask(prompt)
        except Exception as e:
            logger.warning("LLM extraction failed: %s", e)
            return ""

    @staticmethod
    def _parse_entities(response: str) -> List[Dict]:
        """Parse JSON response from LLM."""
        import json
        import re

        if not response:
            return []

        try:
            json_match = re.search(r'\{[^{}]*"entities"[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("entities", [])
        except (json.JSONDecodeError, KeyError):
            pass

        return []

    def _rule_based_fallback(self, text: str) -> List[Dict]:
        """Regex fallback when no LLM available."""
        import re

        entities = []
        # Technical entity patterns — structural, not hardcoded word lists
        patterns = [
            (r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b', 'class'),       # CamelCase
            (r'\b([a-z]+(?:_[a-z]+)+)\b', 'identifier'),            # snake_case
            (r'\b([A-Z]{2,}(?:_[A-Z]+)*)\b', 'constant'),           # CONSTANTS
            (r'(?:def|function|fn)\s+(\w+)', 'function'),           # functions
            (r'(?:import|from)\s+(\S+)', 'module'),                 # imports
        ]
        seen = set()
        for pattern, etype in patterns:
            for match in re.finditer(pattern, text):
                name = match.group(1)
                if name not in seen and len(name) > 1:
                    entities.append({
                        "name": name, "type": etype,
                        "description": "", "confidence": 0.4
                    })
                    seen.add(name)

        return entities

    def stats(self) -> dict:
        return {
            "total_rounds": self._total_rounds,
            "total_gleaned": self._total_gleaned,
            "max_gleanings": self.max_gleanings,
        }
