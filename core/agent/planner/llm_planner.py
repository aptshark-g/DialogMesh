"""Planner LLM Patch — LLM-driven task decomposition."""

from __future__ import annotations
import json, re, logging

logger = logging.getLogger(__name__)


class LLMPlanner:
    """LLM-driven task planner: decomposes complex goals into executable steps.

    Integrates PCR route + MultiIntent + L4 temporal + Engineering tools
    → LLM synthesizes coordinated execution plan.
    """

    def __init__(self, llm=None):
        self.llm = llm

    def plan(self, goal: str, context: dict = None, llm=None) -> dict:
        """Decompose goal into executable steps with tool assignments.

        context: {"route": PCR result, "intents": MultiIntent result, 
                  "tools": Engineering state, "temporal": L4 prediction}
        """
        llm = llm or self.llm
        if not llm:
            return self._structural_plan(goal, context)

        ctx = context or {}
        prompt_ctx = {
            "goal": goal,
            "cognitive_zone": ctx.get("route", {}).get("zone", "MIXED"),
            "sub_intents": ctx.get("intents", {}).get("segments", [goal]),
            "available_tools": ctx.get("tools", {}).get("matching", []),
            "temporal_hint": ctx.get("temporal", {}).get("predictions", []),
        }

        prompt = f"""Decompose this user goal into executable steps.

CONTEXT: {json.dumps(prompt_ctx, ensure_ascii=False)}

Create an execution plan. Match tools to sub-tasks.
Output JSON: {{"steps": [{{"task": "...", "tool": "...", "parallel": true/false}}], 
               "confidence": 0.0-1.0, "fallback": "if fails..."}}"""

        try:
            resp = llm.generate(prompt, max_tokens=400, temperature=0.1)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(resp))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            s = cleaned.find('{'); e = cleaned.rfind('}')
            return json.loads(cleaned[s:e+1]) if s >= 0 and e > s else {"error": "parse"}
        except Exception as e:
            logger.debug("LLM planner failed: %s", e)
            return self._structural_plan(goal, context)

    def _structural_plan(self, goal: str, context: dict = None) -> dict:
        """Structural fallback: keyword-based step decomposition."""
        steps = []
        if "然后" in goal or "接着" in goal:
            for part in goal.replace("然后", "|").replace("接着", "|").split("|"):
                part = part.strip()
                if part:
                    steps.append({"task": part, "tool": "default", "parallel": False})
        if not steps:
            steps = [{"task": goal, "tool": "default", "parallel": False}]
        return {"steps": steps, "confidence": 0.5, "fallback": "sequential"}
