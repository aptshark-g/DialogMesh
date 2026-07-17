"""PolicyPrompt — LLM-driven dynamic policy generation.

Replaces hardcoded if-else rules with LLM analysis of trace patterns.
LLM receives trace summary + current state, returns structured ReasoningPolicy.
"""
from __future__ import annotations
import json, re, logging
from typing import Any, Dict, Optional

from core.agent.v4.cognitive.reasoning_policy import ReasoningPolicy

logger = logging.getLogger(__name__)


POLICY_PROMPT = """You are a reasoning policy optimizer for an AI agent system.

Current state:
- Turn count: {turn_count}
- Trace summary: {trace_summary}
- Current policy: {current_policy}
- Meta warnings: {meta_warnings}

Based on the trace patterns, decide what reasoning policy change would MOST improve
the next reasoning cycle. Choose ONE primary adjustment:

1. PERSPECTIVE: switch to different viewpoint (architecture/engineering/evolution/execution)
2. EXPLANATION_MODE: change how to explain (via_relation/step_by_step/analogy/top_down)
3. DEPTH: go deeper (+1) or shallower (-1, -2)
4. FOCUS: prioritize specific objects (e.g., Runtime, Observer, Workspace)
5. RELATIONS: expand specific relation types (causal, depends_on, contains)

Return ONLY this JSON:
{{
  "primary_action": "PERSPECTIVE|EXPLANATION_MODE|DEPTH|FOCUS|RELATIONS|NONE",
  "perspective": null,
  "explanation_mode": null,
  "depth_adjust": 0,
  "focus_objects": [],
  "expand_relations": [],
  "temperature_mod": 0.0,
  "reason": "one sentence why this change",
  "confidence": 0.5
}}

JSON:"""


class LLMPolicyGenerator:
    """LLM analyzes trace patterns and generates ReasoningPolicy."""

    def __init__(self, llm_provider=None):
        self._llm = llm_provider
        self._last_policy: Optional[ReasoningPolicy] = None

    def set_llm(self, provider):
        self._llm = provider

    def generate(
        self,
        meta_advice: Dict[str, Any],
        trace_summary: str = "",
        turn_count: int = 0,
    ) -> ReasoningPolicy:
        """Generate policy via LLM. Falls back to rule-based PolicyGenerator."""
        if self._llm is None:
            return self._fallback(meta_advice)

        prompt = POLICY_PROMPT.format(
            turn_count=turn_count,
            trace_summary=trace_summary[:400] or "(no trace yet)",
            current_policy=str(self._last_policy.__dict__ if self._last_policy else "none"),
            meta_warnings="; ".join(meta_advice.get("warnings", [])),
        )

        try:
            from core.agent.llm_providers.base import GenerateRequest
            result = self._llm.generate(GenerateRequest(
                prompt=prompt, max_tokens=200, temperature=0.2,
            ))
            text = result.text if hasattr(result, 'text') else str(result)
            match = re.search(r'\{[\s\S]*\}', text)
            if not match:
                return self._fallback(meta_advice)

            data = json.loads(match.group())
            policy = ReasoningPolicy(
                perspective=data.get("perspective"),
                explanation_mode=data.get("explanation_mode"),
                depth_adjust=data.get("depth_adjust", 0),
                focus_objects=data.get("focus_objects", []),
                expand_relations=data.get("expand_relations", []),
                temperature_mod=data.get("temperature_mod", 0.0),
                reason=data.get("reason", ""),
                source="llm_policy",
            )
            if policy.is_significant():
                self._last_policy = policy
                logger.info("LLM Policy: %s → %s", policy.reason[:60], data.get("primary_action"))
            return policy
        except Exception as e:
            logger.debug("LLM Policy failed: %s", e)
            return self._fallback(meta_advice)

    def _fallback(self, meta_advice: Dict[str, Any]) -> ReasoningPolicy:
        """Rule-based fallback when LLM unavailable."""
        from core.agent.v4.cognitive.reasoning_policy import PolicyGenerator
        return PolicyGenerator().generate(meta_advice)
