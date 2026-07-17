"""ProfileSignalFilter — LLM-driven coordinator for TrackA + TrackB.

Design: replaces scattered BGE encoding + keyword matching with a single
LLM call that routes signals, assigns weights, and avoids redundancy.

One LLM call → structured JSON → apply to both tracks.
"""
from __future__ import annotations
import json, re, logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """LLM output: what to update, with what values."""
    update_track_a: bool = False
    track_a_updates: Dict[str, float] = field(default_factory=dict)

    update_track_b: bool = False
    track_b_tags: List[Dict[str, Any]] = field(default_factory=list)

    priority: str = "none"   # "track_a" | "track_b" | "both" | "none"
    signal_strength: float = 0.5
    raw_response: str = ""


FILTER_PROMPT = """You are a profile signal filter for an AI agent. Your job is to analyze
a user's message and decide what to update in their cognitive profile.

The profile has two tracks:
- Track A: temporal dynamics (inertia, trust, attention, emotional state)
  Update when: conversational pattern changes, trust signals, emotional tone shifts
- Track B: stable labels (personality traits, domain expertise, preferences)
  Update when: explicit personality expression, domain keywords, preference statements

Current profile:
{profile_state}

User message: "{user_text}"

Decide:
1. Should we update Track A? Why? What values?
2. Should we update Track B? What tags?
3. What's the priority? (track_a / track_b / both / none)
4. How strong is the signal? (0-1)

Return ONLY this JSON structure:
{{
  "update_track_a": true/false,
  "track_a_updates": {{"cognitive_inertia": 0.0, "trust_score": 0.0}},
  "update_track_b": true/false,
  "track_b_tags": [{{"name": "...", "value": "...", "confidence": 0.0}}],
  "priority": "track_a",
  "signal_strength": 0.5,
  "decision_reason": "one sentence why"
}}

JSON:"""


class ProfileSignalFilter:
    """LLM-driven coordinator for profile updates.

    Usage:
        filter = ProfileSignalFilter(llm_provider)
        result = filter.analyze(user_text, profile)
        if result.update_track_a: apply(result.track_a_updates)
    """

    def __init__(self, llm_provider=None):
        self._llm = llm_provider

    def set_llm(self, provider):
        self._llm = provider

    def analyze(self, user_text: str, profile=None) -> FilterResult:
        """LLM coordinates TrackA/TrackB decisions. Single call, no keywords."""
        if self._llm is None:
            return self._fallback(user_text)

        profile_state = self._serialize_profile(profile)
        prompt = FILTER_PROMPT.format(
            profile_state=profile_state,
            user_text=user_text[:500],
        )

        try:
            from core.agent.llm_providers.base import GenerateRequest
            result = self._llm.generate(GenerateRequest(
                prompt=prompt, max_tokens=300, temperature=0.1,
            ))
            text = result.text if hasattr(result, 'text') else str(result)

            # Parse JSON
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                data = json.loads(match.group())
                return FilterResult(
                    update_track_a=data.get("update_track_a", False),
                    track_a_updates=data.get("track_a_updates", {}),
                    update_track_b=data.get("update_track_b", False),
                    track_b_tags=data.get("track_b_tags", []),
                    priority=data.get("priority", "none"),
                    signal_strength=data.get("signal_strength", 0.5),
                    raw_response=text[:200],
                )
        except Exception as e:
            logger.debug("Filter LLM failed: %s", e)

        return self._fallback(user_text)

    def _serialize_profile(self, profile) -> str:
        if profile is None:
            return "(no profile yet)"

        lines = ["[Track A — Dynamics]"]
        if hasattr(profile, 'track_a'):
            ta = profile.track_a
            lines.append(f"  inertia={ta.cognitive_inertia:.2f} trust={ta.trust_score:.2f} entropy={ta.emotional_entropy:.2f} attention={ta.attention_anchor:.2f}")

        lines.append("[Track B — Tags]")
        if hasattr(profile, 'track_b') and profile.track_b:
            for name, tag in list(profile.track_b.items())[:5]:
                lines.append(f"  {tag.name}: {tag.value} (conf={tag.confidence:.2f})")
        else:
            lines.append("  (no tags yet)")

        return "\n".join(lines)

    def _fallback(self, user_text: str) -> FilterResult:
        """Minimal heuristic when LLM unavailable."""
        # Simple: if short text → TrackB, if emotional → TrackA
        if len(user_text) > 100:
            return FilterResult(
                update_track_a=True,
                track_a_updates={"cognitive_inertia": 0.02},
                priority="track_a",
                signal_strength=0.4,
            )
        return FilterResult(priority="none")
