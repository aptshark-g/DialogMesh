"""MetaCognition — LLM self-reflection on CognitiveWorkspace state.

Design: docs/v3.0/DESIGN_COGNITIVE_RUNTIME.md §4

Not code rules. Not if-else. LLM evaluates its own reasoning quality
and decides what to do next. Returns structured MetaReflection.
"""
from __future__ import annotations
import json, re, logging, time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MetaReflection:
    """LLM's self-assessment of current reasoning state."""

    # Self-evaluation
    confidence_self: float = 0.5
    gaps: List[str] = field(default_factory=list)

    # Next action decision
    next_action: str = "REASON"    # RETRIEVE | EXPAND | REASON | COMMIT
    action_target: Optional[str] = None
    action_reason: str = ""

    # Whether to go deeper
    need_expand: bool = False
    expand_targets: List[str] = field(default_factory=list)

    # Reasoning quality
    has_contradiction: bool = False
    contradiction_desc: str = ""

    # Raw LLM response for trace
    raw_response: str = ""


META_PROMPT = """You are a Meta-Cognition module. Your job is to evaluate the current state
of an LLM's reasoning workspace and decide what to do next.

Current workspace state:
{workspace_text}

Evaluate:
1. How confident should we be in the current reasoning? (0.0-1.0)
2. What's missing? (gaps in knowledge, missing relations, too few hypotheses)
3. What should we do next?
   - RETRIEVE: need more facts/relations from the knowledge graph
   - EXPAND: need to understand a specific concept in more depth
   - REASON: need to continue reasoning (current info is sufficient)
   - COMMIT: reasoning is complete, ready to finalize
4. Should we expand into any specific sub-concepts?
5. Are there contradictions in the current hypotheses?

Return ONLY a JSON object:
{{
  "confidence_self": 0.7,
  "gaps": ["missing relation details", "only one hypothesis"],
  "next_action": "RETRIEVE",
  "action_target": "RelationSubstrate",
  "action_reason": "current reasoning lacks specific dependency edges",
  "need_expand": false,
  "expand_targets": [],
  "has_contradiction": false,
  "contradiction_desc": ""
}}

JSON:"""


class MetaCognition:
    """LLM-driven self-reflection on reasoning quality.

    Usage:
        mc = MetaCognition(llm_provider)
        reflection = mc.reflect(workspace)
        # reflection.next_action tells Scheduler what to do
    """

    def __init__(self, llm_provider=None):
        self._llm = llm_provider

    def set_llm(self, provider):
        self._llm = provider

    def reflect(self, workspace) -> MetaReflection:
        """Ask LLM to evaluate its own reasoning workspace.

        Returns MetaReflection from LLM, or fallback if LLM unavailable/fails.
        """
        if self._llm is None:
            return self._fallback_reflection(workspace)

        ws_text = self._serialize_workspace(workspace)

        try:
            from core.agent.llm_providers.base import GenerateRequest
            prompt = META_PROMPT.format(workspace_text=ws_text)
            request = GenerateRequest(
                prompt=prompt,
                max_tokens=400,
                temperature=0.1,
                # No response_format="json" — not all providers support it
            )
            result = self._llm.generate(request)
            text = result.text if hasattr(result, 'text') else str(result)

            # Try JSON parse, fall back to markdown-json extraction
            reflection = self._parse(text)
            reflection.raw_response = text

            if reflection.next_action != "REASON":
                logger.info("MetaCognition (LLM): action=%s confidence=%.2f reason=%s",
                           reflection.next_action, reflection.confidence_self,
                           reflection.action_reason[:80])
            return reflection

        except Exception as e:
            logger.info("MetaCognition LLM failed (%s), using fallback", type(e).__name__)
            return self._fallback_reflection(workspace)

    def _serialize_workspace(self, workspace) -> str:
        """Build a text summary of the workspace for LLM consumption."""
        if workspace is None:
            return "(empty workspace)"

        lines = [
            f"Goal: {getattr(workspace, 'goal', 'answer user question')}",
            f"Active objects: {getattr(workspace, 'active_objects', [])}",
            f"Active relations: {len(getattr(workspace, 'active_relations', []))} edges",
            f"Hypotheses: {len(getattr(workspace, 'hypotheses', []))}",
            f"Current confidence: {getattr(workspace, 'confidence', 0.5):.2f}",
            f"Conflicts: {getattr(workspace, 'conflicts', [])}",
            f"Reasoning depth: {getattr(workspace, 'reasoning_depth', 0)}/{getattr(workspace, 'max_reasoning_depth', 3)}",
            f"State: {getattr(workspace, 'state', 'unknown')}",
        ]

        # Include hypothesis summaries
        for i, hyp in enumerate(getattr(workspace, 'hypotheses', [])[:3]):
            if isinstance(hyp, dict):
                lines.append(f"  H{i+1}: {hyp.get('content', str(hyp))[:120]}")
            else:
                lines.append(f"  H{i+1}: {str(hyp)[:120]}")

        return "\n".join(lines)

    def _parse(self, text: str) -> MetaReflection:
        """Parse LLM JSON response into MetaReflection.

        Handles: raw JSON, markdown ```json blocks, and broken JSON fragments.
        """
        # Try markdown code fence first
        fence_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
        if fence_match:
            json_text = fence_match.group(1).strip()
        else:
            # Fallback to raw JSON extraction
            json_match = re.search(r'\{[\s\S]*\}', text)
            if not json_match:
                return self._fallback_reflection(None)
            json_text = json_match.group()

        if not json_text:
            return self._fallback_reflection(None)

        try:
            data = json.loads(json_text)
            return MetaReflection(
                confidence_self=float(data.get("confidence_self", 0.5)),
                gaps=data.get("gaps", []),
                next_action=data.get("next_action", "REASON"),
                action_target=data.get("action_target"),
                action_reason=data.get("action_reason", ""),
                need_expand=data.get("need_expand", False),
                expand_targets=data.get("expand_targets", []),
                has_contradiction=data.get("has_contradiction", False),
                contradiction_desc=data.get("contradiction_desc", ""),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.debug("MetaCognition parse failed: %s", e)
            return self._fallback_reflection(None)

    def _fallback_reflection(self, workspace) -> MetaReflection:
        """Deterministic fallback when LLM is unavailable."""
        if workspace is None:
            return MetaReflection(next_action="REASON", action_reason="no workspace, default to reason")

        conf = getattr(workspace, 'confidence', 0.5)
        hyp_count = len(getattr(workspace, 'hypotheses', []))
        depth = getattr(workspace, 'reasoning_depth', 0)
        max_depth = getattr(workspace, 'max_reasoning_depth', 3)

        if conf > 0.7 and hyp_count >= 1:
            return MetaReflection(
                confidence_self=conf,
                next_action="COMMIT",
                action_reason="high confidence with sufficient hypotheses",
            )
        if conf < 0.3:
            return MetaReflection(
                confidence_self=conf,
                gaps=["confidence too low"],
                next_action="RETRIEVE",
                action_reason="confidence below 0.3, need more information",
            )
        if hyp_count <= 1 and depth < max_depth:
            return MetaReflection(
                confidence_self=conf,
                gaps=["too few hypotheses"],
                next_action="EXPAND",
                action_reason=f"only {hyp_count} hypothesis, should explore deeper",
            )
        return MetaReflection(
            confidence_self=conf,
            next_action="REASON",
            action_reason="continue reasoning",
        )
