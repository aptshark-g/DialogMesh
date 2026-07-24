"""Multi-Perspective Intent Analyzer — each perspective reasons independently.

Pattern: Multi-Agent Debate → Master LLM synthesizes.
Each perspective: decision + reasoning chain + confidence.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class PerspectiveAnalysis:
    perspective: str           # profile/association/discourse/literal
    decision: str              # accept/reject/undecided
    confidence: float
    reasoning: str             # full reasoning chain


@dataclass
class MultiPerspectiveResult:
    is_multi: bool
    segments: List[str] = field(default_factory=list)
    confidence: float = 0.0
    analyses: List[PerspectiveAnalysis] = field(default_factory=list)
    synthesis: str = ""        # Master LLM's synthesis reasoning


class MultiPerspectiveAnalyzer:
    """Each perspective's LLM reasons independently → Master LLM synthesizes.

    Usage:
        analyzer = MultiPerspectiveAnalyzer(llm=deepseek)
        result = analyzer.analyze(
            text="先定位延迟然后修复",
            profile={"OCEAN": {"C": 4.5}},
            association={"entities": ["延迟","监控"]},
            history=["上次讨论性能优化..."],
        )
    """

    def __init__(self, llm=None):
        self.llm = llm

    def analyze(self, text: str, profile: dict = None,
                association: dict = None, history: List[str] = None) -> MultiPerspectiveResult:
        """Multi-perspective analysis → Master synthesis."""
        if not self.llm:
            return MultiPerspectiveResult(is_multi=False, segments=[text], confidence=1.0)

        profile = profile or {}
        association = association or {}
        history = history or []

        # Step 1: Each perspective's LLM reasons independently
        analyses = []
        analyses.append(self._literal_perspective(text))
        if profile:
            analyses.append(self._profile_perspective(text, profile))
        if association:
            analyses.append(self._association_perspective(text, association))
        if history:
            analyses.append(self._discourse_perspective(text, history))

        # Step 2: Master LLM synthesizes all perspectives
        return self._master_synthesis(text, analyses)

    def _literal_perspective(self, text: str) -> PerspectiveAnalysis:
        return self._call_perspective("literal", f"""Analyze ONLY the linguistic structure of this message.

TEXT: "{text[:300]}"

Does the STRUCTURE indicate multiple independent intents? Consider:
- Multiple verb phrases with different objects
- Conjunctions that separate clauses ("然后","接着","并且","顺便")
- Different entities targeted by different clauses

Output JSON: {{"decision": "accept"/"reject"/"undecided", "confidence": 0.0-1.0, "reasoning": "your analysis chain"}}""")

    def _profile_perspective(self, text: str, profile: dict) -> PerspectiveAnalysis:
        import json as _json
        ocean = profile.get("OCEAN", {})
        desc = f"O={ocean.get('O',0):.1f} C={ocean.get('C',0):.1f} E={ocean.get('E',0):.1f} A={ocean.get('A',0):.1f} N={ocean.get('N',0):.1f}"

        return self._call_perspective("profile", f"""Analyze from the USER PROFILE perspective.

USER PERSONALITY (OCEAN): {desc}
USER MESSAGE: "{text[:300]}"

Given this user's personality traits, would they likely express multiple intents as one message?
- High C (conscientiousness): prefers structured, sequential requests
- High N (neuroticism): may vent and ask for help in same message
- High O (openness): explores tangentially, may combine unrelated ideas

Output JSON: {{"decision": "accept"/"reject"/"undecided", "confidence": 0.0-1.0, "reasoning": "your chain of thought from profile traits to decision"}}""")

    def _association_perspective(self, text: str, association: dict) -> PerspectiveAnalysis:
        ents = association.get("entities", [])
        edges = association.get("recent_edges", [])

        return self._call_perspective("association", f"""Analyze from the ENTITY/KNOWLEDGE perspective.

KNOWN ENTITIES: {', '.join(ents[:15])}
RECENT RELATIONS: {', '.join(str(e) for e in edges[:5])}
USER MESSAGE: "{text[:300]}"

Do the entities in this message span different knowledge domains suggesting separate intents?
- Entities in different relation clusters → likely separate intents
- Entities in the same cluster → probably one intent
- Entity relationships from history suggest how these concepts connect

Output JSON: {{"decision": "accept"/"reject"/"undecided", "confidence": 0.0-1.0, "reasoning": "your entity-based reasoning chain"}}""")

    def _discourse_perspective(self, text: str, history: list) -> PerspectiveAnalysis:
        hist = "\n".join(f"  {str(h)[:100]}" for h in history[-5:])

        return self._call_perspective("discourse", f"""Analyze from the CONVERSATION FLOW perspective.

RECENT HISTORY:
{hist}

CURRENT MESSAGE: "{text[:300]}"

Is this message a natural follow-up to one topic, or does it introduce multiple new threads?
- Topic continuity → single intent
- Topic shift in the middle → multiple intents
- Reference to different prior messages → likely multi-intent

Output JSON: {{"decision": "accept"/"reject"/"undecided", "confidence": 0.0-1.0, "reasoning": "your discourse-based reasoning chain"}}""")

    def _call_perspective(self, name: str, prompt: str) -> PerspectiveAnalysis:
        """Call LLM for one perspective's analysis."""
        try:
            import json, re
            response = self.llm.generate(prompt, max_tokens=250, temperature=0.1)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(response))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            cleaned = cleaned.replace("\\'", "'")
            s = cleaned.find('{'); e = cleaned.rfind('}')
            if s >= 0 and e > s:
                cleaned = cleaned[s:e+1]
            data = json.loads(cleaned)
            return PerspectiveAnalysis(
                perspective=name,
                decision=data.get("decision", "undecided"),
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", ""),
            )
        except Exception as ex:
            logger.debug("Perspective %s failed: %s", name, ex)
            return PerspectiveAnalysis(
                perspective=name, decision="undecided", confidence=0.3,
                reasoning=f"LLM unavailable: {ex}",
            )

    def _master_synthesis(self, text: str,
                          analyses: List[PerspectiveAnalysis]) -> MultiPerspectiveResult:
        """Master LLM reviews all perspectives and synthesizes final decision."""
        import json, re

        persp_summary = "\n".join(
            f"  {a.perspective}: {a.decision} (conf={a.confidence:.2f})\n    Reasoning: {a.reasoning[:150]}"
            for a in analyses
        )
        accept_count = sum(1 for a in analyses if a.decision == "accept")
        reject_count = sum(1 for a in analyses if a.decision == "reject")

        prompt = f"""Synthesize these independent analyses into a final decision.

ORIGINAL MESSAGE: "{text[:300]}"

PERSPECTIVE ANALYSES:
{persp_summary}

Summary: {accept_count} accept, {reject_count} reject, {len(analyses)-accept_count-reject_count} undecided.

Consider: where perspectives disagree, weigh the reasoning. Which perspective has the strongest evidence?

Output JSON:
{{"multi": true/false, "segments": ["sub-intent1", "sub-intent2"], "confidence": 0.0-1.0, "synthesis": "your synthesis reasoning, explaining which perspectives you weighted and why"}}"""

        try:
            response = self.llm.generate(prompt, max_tokens=400, temperature=0.1)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(response))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            cleaned = cleaned.replace("\\'", "'")
            s = cleaned.find('{'); e = cleaned.rfind('}')
            if s >= 0 and e > s:
                cleaned = cleaned[s:e+1]
            data = json.loads(cleaned)
            return MultiPerspectiveResult(
                is_multi=data.get("multi", False),
                segments=data.get("segments", [text]),
                confidence=float(data.get("confidence", 0.5)),
                analyses=analyses,
                synthesis=data.get("synthesis", ""),
            )
        except Exception as ex:
            logger.debug("Master synthesis failed: %s", ex)
            is_multi = accept_count > reject_count
            return MultiPerspectiveResult(
                is_multi=is_multi, segments=[text],
                confidence=max(0.5, accept_count / max(1, len(analyses))),
                analyses=analyses,
                synthesis=f"Fallback majority: {accept_count}vs{reject_count}",
            )
