"""Agent-Native Intent Coordinator — single LLM call with full context.

Pattern: One LLM call receives all perspectives, synthesizes in one pass.
ChatGPT/Claude-style: full context injection, not chained sub-calls.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class CoordinatorResult:
    is_multi: bool
    segments: List[str] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""


class IntentCoordinator:
    """Single-call LLM coordinator — all perspectives in one prompt.

    Usage:
        coord = IntentCoordinator(llm=nemotron)
        result = coord.analyze("先定位延迟然后修复",
                              profile={"OCEAN": {"C": 4.5}},
                              association={"entities": ["延迟","监控"]},
                              history=["上次讨论性能..."])
    """

    def __init__(self, llm=None):
        self.llm = llm

    def analyze(self, text: str, profile: dict = None,
                association: dict = None, history: List[str] = None) -> CoordinatorResult:
        """One LLM call — inject all context, LLM decides everything."""
        if not self.llm:
            return CoordinatorResult(is_multi=False, segments=[text], confidence=1.0)

        prompt = self._build_prompt(text, profile or {}, association or {}, history or [])
        try:
            import json, re
            response = self.llm.generate(prompt, max_tokens=400, temperature=0.1)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(response))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            # Handle escaped single quotes in JSON strings
            cleaned = cleaned.replace("\\'", "'")
            # Find JSON object boundaries
            start = cleaned.find('{')
            end = cleaned.rfind('}')
            if start >= 0 and end > start:
                cleaned = cleaned[start:end+1]
            data = json.loads(cleaned)
            return CoordinatorResult(
                is_multi=data.get("multi", False),
                segments=data.get("segments", [text]),
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", ""),
            )
        except Exception as e:
            logger.debug("Coordinator failed: %s", e)
            return CoordinatorResult(is_multi=False, segments=[text], confidence=0.3)

    def _build_prompt(self, text: str, profile: dict, association: dict,
                      history: list) -> str:
        """Build single-shot prompt with all context injected."""
        import json as _json

        parts = [f'USER MESSAGE: "{text[:500]}"\n']

        # Profile context — LLM decides relevance
        if profile:
            ocean = profile.get("OCEAN", {})
            prefs = profile.get("preferences", {})
            if ocean:
                parts.append(f"USER PERSONALITY: O={ocean.get('O',0):.2f} C={ocean.get('C',0):.2f} "
                           f"E={ocean.get('E',0):.2f} A={ocean.get('A',0):.2f} N={ocean.get('N',0):.2f}")
            if prefs:
                parts.append(f"USER PREFERENCES: {_json.dumps(prefs, ensure_ascii=False)}")

        # Association context — LLM decides relevance
        if association:
            ents = association.get("entities", [])
            if ents:
                parts.append(f"KNOWN ENTITIES: {', '.join(ents[:10])}")
            edges = association.get("recent_edges", [])
            if edges:
                parts.append(f"ENTITY RELATIONS: {', '.join(str(e) for e in edges[:5])}")

        # Discourse context
        if history:
            parts.append("RECENT CONVERSATION:")
            for h in history[-5:]:
                parts.append(f"  - {str(h)[:120]}")

        parts.append(f"""
Analyze whether this message contains multiple independent intents.
Consider:
- From PROFILE: does this user's personality suggest they'd phrase multiple requests as one?
- From ENTITIES: do the entities span different domains suggesting separate intents?
- From HISTORY: is this a natural follow-up or a new thread?

Output JSON:
{{"multi": true/false, "segments": ["intent1", "intent2"], "confidence": 0.0-1.0, "reasoning": "brief"}}""")

        return "\n".join(parts)
