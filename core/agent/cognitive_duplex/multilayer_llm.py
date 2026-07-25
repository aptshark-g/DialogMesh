"""Multilayer LLM Engine — 6 LLM instances (ENGINEERING_MULTILAYER_LLM §7-11).

Cognitive Duplex: 6 specialized LLMs operate in parallel, sharing a Cognitive Tree.
Fusion Engine: weighted merge of algorithm + LLM outputs with conflict detection.

6 instances:
  pcr_llm       — Pre-Cognitive Router: expectation inference, noise assessment
  intent_llm    — Intent Parser: task decomposition, entity extraction
  meta_llm      — Meta-Cognitive: review, retrospection, correction
  planning_llm  — Planning: strategy selection, TaskGraph generation
  answer_llm    — Penetration Layer: final user-facing response
  reflective_llm — Reflective Layer: long-term pattern analysis, self-improvement
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class LLMInstance:
    """One specialized LLM instance with role, prompt template, and access control."""
    name: str
    role: str
    system_prompt: str
    llm_provider: Any = None  # DeepSeek or other provider
    max_tokens: int = 300
    temperature: float = 0.1
    can_write_tree: bool = False  # Access control: can write to Cognitive Tree?
    priority: int = 5  # 1-10, lower = higher priority for scheduling


class MultiLayerLLMEngine:
    """ENGINEERING_MULTILAYER_LLM §7: 6 LLM instances + fusion.

    Usage:
        engine = MultiLayerLLMEngine(llm=deepseek_provider)
        pcr_output = engine.pcr_llm("user text", context={...})
        intent_output = engine.intent_llm("user text", pcr_output)
    """

    # ═══ Instance Definitions ═══

    INSTANCES = {
        "pcr": LLMInstance(
            name="pcr_llm",
            role="Pre-Cognitive Router",
            system_prompt="""You are a cognitive router. Analyze the user's input and output:
{
  "expectation": "TOOL|ADVISOR|COMPANION|UNKNOWN",
  "noise_level": 0.0-1.0,
  "complexity": 0.0-1.0,
  "cognitive_style": {"metacognition": 0.0-1.0, "divergence": 0.0-1.0},
  "reasoning": "one-line justification"
}""",
            temperature=0.1, can_write_tree=False, priority=1
        ),
        "intent": LLMInstance(
            name="intent_llm",
            role="Intent Parser",
            system_prompt="""You are an intent parser. Given the user's text and cognitive route, 
decompose the task into sub-intents and extract entities. Output:
{
  "category": "SINGLE|MULTI|UNKNOWN",
  "sub_intents": [{"text": "...", "confidence": 0.0-1.0}],
  "entities": [{"type": "ENTITY_TYPE", "value": "...", "confidence": 0.0-1.0}],
  "ambiguities": [{"type": "MISSING|AMBIGUOUS|CONFLICT", "description": "..."}],
  "reasoning": "one-line justification"
}""",
            temperature=0.2, can_write_tree=True, priority=2
        ),
        "planning": LLMInstance(
            name="planning_llm",
            role="Task Planner",
            system_prompt="""You are a task planner. Given the intent parse result and available tools,
create an execution plan. Output:
{
  "strategy": "RULE_BASED|TEMPLATE|HYBRID|LLM_DRIVEN",
  "steps": [{"action": "...", "tool": "...", "params": {}, "reason": "..."}],
  "confidence": 0.0-1.0,
  "reasoning": "one-line justification"
}""",
            temperature=0.15, can_write_tree=True, priority=3
        ),
        "meta": LLMInstance(
            name="meta_llm",
            role="Meta-Cognitive Reviewer",
            system_prompt="""You are a meta-cognitive reviewer. Analyze the pipeline output for errors,
inconsistencies, and improvement opportunities. Output:
{
  "anomalies": [{"type": "...", "severity": 0.0-1.0, "description": "..."}],
  "corrections": [{"target": "pcr|intent|planning|profile", "action": "..."}],
  "confidence": 0.0-1.0,
  "reasoning": "one-line justification"
}""",
            temperature=0.1, can_write_tree=False, priority=4
        ),
        "answer": LLMInstance(
            name="answer_llm",
            role="Answer Generator",
            system_prompt="""You are a helpful AI assistant. Given the compiled context and execution plan,
generate a clear, accurate response for the user. Be concise and direct.""",
            temperature=0.3, max_tokens=800, can_write_tree=False, priority=5
        ),
        "reflective": LLMInstance(
            name="reflective_llm",
            role="Reflective Analyst",
            system_prompt="""You are a reflective analyst. Review the entire session for long-term patterns,
user preference shifts, and system improvement opportunities. Output:
{
  "patterns": [{"name": "...", "frequency": 0.0-1.0, "significance": 0.0-1.0}],
  "drift_alerts": [{"target": "profile|behavior|preference", "magnitude": 0.0-1.0}],
  "improvements": [{"module": "...", "suggestion": "..."}],
  "reasoning": "one-line justification"
}""",
            temperature=0.2, can_write_tree=False, priority=6
        ),
    }

    def __init__(self, llm=None):
        self._llm = llm
        self._instances: Dict[str, LLMInstance] = {}
        self._load_instances()

    def _load_instances(self):
        for key, inst in self.INSTANCES.items():
            inst.llm_provider = self._llm
            self._instances[key] = inst

    @property
    def is_available(self) -> bool:
        return self._llm is not None

    def call(self, instance_name: str, user_text: str, context: dict = None,
             max_tokens: int = None, temperature: float = None) -> dict:
        """Call one LLM instance with structured output parsing.

        Returns parsed JSON dict, or {"raw": response, "error": msg} on parse failure.
        """
        inst = self._instances.get(instance_name)
        if not inst or not inst.llm_provider:
            return {"error": f"instance {instance_name} not available"}

        try:
            import json
            prompt = inst.system_prompt
            if context:
                prompt = f"{inst.system_prompt}\n\nCONTEXT: {json.dumps(context, ensure_ascii=False)}"
            prompt = f"{prompt}\n\nUSER INPUT: {user_text}\n\nOutput JSON only:"

            raw = inst.llm_provider.generate(
                prompt,
                max_tokens=max_tokens or inst.max_tokens,
                temperature=temperature if temperature is not None else inst.temperature,
            )
            if not raw:
                return {"raw": "", "error": "empty response"}

            # Parse JSON
            import re
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', raw)
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            s = cleaned.find('{')
            e = cleaned.rfind('}')
            if s >= 0 and e > s:
                return json.loads(cleaned[s:e + 1])
            return {"raw": raw, "error": "json parse failed"}
        except Exception as e:
            logger.debug("%s call failed: %s", instance_name, e)
            return {"error": str(e)}

    # ═══ Shortcut methods ═══

    def pcr(self, text: str, ctx: dict = None) -> dict:
        return self.call("pcr", text, ctx)

    def intent(self, text: str, ctx: dict = None) -> dict:
        return self.call("intent", text, ctx)

    def planning(self, text: str, ctx: dict = None) -> dict:
        return self.call("planning", text, ctx)

    def meta(self, text: str, ctx: dict = None) -> dict:
        return self.call("meta", text, ctx)

    def answer(self, text: str, ctx: dict = None) -> dict:
        return self.call("answer", text, ctx, max_tokens=800, temperature=0.3)

    def reflective(self, text: str, ctx: dict = None) -> dict:
        return self.call("reflective", text, ctx)

    def get_status(self) -> dict:
        return {
            "available": self.is_available,
            "instances": list(self._instances.keys()),
            "priorities": {k: v.priority for k, v in self._instances.items()},
        }
