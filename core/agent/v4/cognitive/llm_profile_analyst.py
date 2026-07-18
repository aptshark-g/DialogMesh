"""LLM Profile Analyst — three-source fusion for personality extraction.

Three sources → LLM synthesis → Profile (compressed memory).

Sources:
  1. Conversation content (what the user actually said)
  2. TrackB signals (WEAKEN/STRENGTHEN/REJECT from trace)
  3. Previous profile (what the system already believes)

LLM resolves conflicts, detects semantic patterns, and produces:
  - Synthesized personality assessment (natural language)
  - Confidence-calibrated tags
  - Surprise signals (where TrackB conflicts with LLM analysis)
  - Subgraph: what to pay attention to next turn
"""
from __future__ import annotations
import json, logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class LLMProfileAnalyst:
    """LLM-driven profile fusion — replaces signal-only TrackB.

    The LLM sees all three data sources and produces a synthesized
    personality assessment. TrackB signals become EVIDENCE, not answers.
    """

    def __init__(self, llm_provider=None):
        self._llm = llm_provider
        self._history: List[Dict] = []

    def analyze(self, engine, turn_text: str, llm_response: str) -> Dict[str, Any]:
        """Fuse three sources into profile update."""
        if not self._llm:
            return self._signal_fallback(engine)

        # Gather three sources
        trace_signals = self._extract_trace_signals(engine)
        previous_profile = self._extract_previous_profile(engine)
        recent_context = self._extract_recent_context(engine)

        prompt = self._build_fusion_prompt(
            turn_text, llm_response, trace_signals, previous_profile, recent_context
        )

        try:
            from core.agent.llm_providers.base import GenerateRequest
            req = GenerateRequest(prompt=prompt, max_tokens=400, temperature=0.3)
            result = self._llm.generate(req)
            result_text = result.text if hasattr(result, 'text') else str(result)
            result = self._parse_fusion_result(result_text)
            self._history.append(result)
            return result
        except Exception as e:
            logger.debug("LLM fusion skipped: %s", e)
            return self._signal_fallback(engine)

    def _extract_trace_signals(self, engine) -> Dict:
        if not hasattr(engine, '_trace_v3') or not engine._trace_v3:
            return {}
        m = engine._trace_v3.meta_analyze()
        rd = m.get("reason_distribution", {})
        window = 3
        transitions = getattr(engine._trace_v3, 'transitions', [])
        recent = transitions[-window*4:]
        from core.agent.v4.state.state_object import TransitionReason
        return {
            "total_strengthen": rd.get("strengthen", 0),
            "total_weaken": rd.get("weaken", 0),
            "total_reject": rd.get("reject", 0),
            "recent_strengthen": sum(1 for t in recent if getattr(t, 'reason', None) == TransitionReason.STRENGTHEN),
            "recent_weaken": sum(1 for t in recent if getattr(t, 'reason', None) == TransitionReason.WEAKEN),
            "avg_confidence": m.get("avg_confidence", 0.7),
            "mind_relations": getattr(getattr(engine, '_mind', None), 'stats', lambda: {})().get("active_relations", 0),
        }

    def _extract_previous_profile(self, engine) -> Dict:
        profile = getattr(engine, '_cognitive_profile', None)
        if not profile:
            return {}
        tb = getattr(profile, 'track_b', {})
        return {
            "tags": list(tb.keys()),
            "tag_details": {k: (v if isinstance(v, dict) else {"name": getattr(v, 'name', k)})
                           for k, v in tb.items()},
        }

    def _extract_recent_context(self, engine) -> List[str]:
        # Last 3 user messages
        if hasattr(engine, '_event_buffer'):
            return [getattr(e, 'text', '')[:200] for e in engine._event_buffer[-3:]]
        return []

    def _build_fusion_prompt(self, turn_text, llm_response, signals, profile, context) -> str:
        return f"""You are a cognitive profile analyst. Fuse three data sources to update the user's personality assessment.

THREE SOURCES:
1. TRACE SIGNALS (quantitative):
   STRENGTHEN(total): {signals.get('total_strengthen',0)} (recent: {signals.get('recent_strengthen',0)})
   WEAKEN(total): {signals.get('total_weaken',0)} (recent: {signals.get('recent_weaken',0)})
   REJECT: {signals.get('total_reject',0)}
   Avg Confidence: {signals.get('avg_confidence',0.7):.2f}

2. CURRENT PROFILE: {json.dumps(profile, ensure_ascii=False)}

3. CONVERSATION:
   User said: "{turn_text[:300]}"
   System responded: "{llm_response[:300]}"

IMPORTANT: WEAKEN can come from TWO sources:
  - Analytical/skeptical users (T-type): they challenge with logic, producing WEAKEN
  - Emotional/feeling users (F-type): they express value conflict, also producing WEAKEN
  You MUST distinguish these based on the CONTENT of what the user says, not the signal.

Respond with JSON ONLY:
{{"personality": "one-line assessment",
  "tags": {{"tag_name": confidence_0_to_1}},
  "T_vs_F": "analytical|emotional|unclear",
  "surprise": "any conflict between signals and content",
  "confidence": 0.5,
  "next_attention": ["what", "to", "watch", "for"]}}"""

    def _parse_fusion_result(self, text: str) -> Dict[str, Any]:
        try:
            start = text.find('{')
            end = text.rfind('}') + 1
            if start < 0:
                return {}
            return json.loads(text[start:end])
        except Exception:
            return {"personality": text[:200], "tags": {}, "T_vs_F": "unclear", "confidence": 0.3}

    def _signal_fallback(self, engine) -> Dict[str, Any]:
        """Fallback: use signals only when LLM unavailable."""
        signals = self._extract_trace_signals(engine)
        sw = signals.get("recent_strengthen", 0)
        w = signals.get("recent_weaken", 0)
        if sw >= 2 and w < 3:
            t = "analytical"
        elif w >= 3:
            t = "emotional"
        else:
            t = "unclear"
        return {"T_vs_F": t, "tags": {}, "confidence": 0.5, "source": "signal_fallback"}

    def get_subgraph(self, profile_result: Dict) -> List[str]:
        """Generate subgraph from profile for next-turn context injection."""
        attn = profile_result.get("next_attention", [])
        tags = list(profile_result.get("tags", {}).keys())
        personality = profile_result.get("personality", "")
        surprise = profile_result.get("surprise", "")

        subgraph = []
        if personality:
            subgraph.append(f"[PROFILE] {personality}")
        if surprise:
            subgraph.append(f"[CONFLICT] {surprise}")
        if tags:
            subgraph.append(f"[TAGS] {', '.join(f'{t}' for t in tags[:5])}")
        subgraph.extend(f"[ATTN] {a}" for a in attn[:3])

        return subgraph


def fuse_profile(engine, turn_text: str, llm_response: str, llm_provider=None) -> Dict:
    """One-call fusion: analyze + update profile + return subgraph."""
    analyst = LLMProfileAnalyst(llm_provider)
    result = analyst.analyze(engine, turn_text, llm_response)

    # Update profile with LLM's synthesis
    profile = getattr(engine, '_cognitive_profile', None)
    if profile and hasattr(profile, 'track_b'):
        # Store LLM fusion result as compressed profile entry
        profile.track_b["_llm_fusion"] = {
            "personality": result.get("personality", ""),
            "T_vs_F": result.get("T_vs_F", "unclear"),
            "confidence": result.get("confidence", 0.5),
            "surprise": result.get("surprise", ""),
            "tags": result.get("tags", {}),
            "source": "llm_fusion",
        }

    subgraph = analyst.get_subgraph(result)
    return {"result": result, "subgraph": subgraph}
