"""LLM Adapter — Layer B. Generates rules via LLM when symbolic rules don't match."""
import logging, json
from typing import Dict, Any, Optional
from .neuro_symbolic import Rule, RuleEngine

logger = logging.getLogger(__name__)


class LLMAdapter:
    def __init__(self, llm_provider=None, rule_engine=None):
        self._llm = llm_provider
        self._rule_engine = rule_engine

    def adapt(self, engine, state: Dict[str, Any]) -> Optional[Rule]:
        if not self._llm:
            return None
        try:
            prompt = self._build_prompt(state)
            response = self._llm.complete(prompt, max_tokens=200)
            rule = self._parse_response(response)
            if rule and self._rule_engine:
                self._rule_engine.register(rule)
                self._rule_engine.save()
                logger.info("L2: LLM generated rule '%s'", rule.name)
            return rule
        except Exception as e:
            logger.debug("LLM adapt skipped: %s", e)
            return None

    def _build_prompt(self, state: Dict[str, Any]) -> str:
        rules = list(self._rule_engine._rules.keys()) if self._rule_engine else []
        s = state.get('strengthen', 0)
        w = state.get('weaken', 0)
        r = state.get('reject', 0)
        c = state.get('avg_confidence', 0.7)
        mr = state.get('mind_relations', 0)
        pt = state.get('profile_tags', [])
        d = state.get('active_domains', [])

        return (
            "Based on this DialogMesh internal state, infer what rule should apply:\n\n"
            f"State:\n"
            f"  STRENGTHEN: {s}\n"
            f"  WEAKEN: {w}\n"
            f"  REJECT: {r}\n"
            f"  Confidence: {c:.2f}\n"
            f"  Mind Relations: {mr}\n"
            f"  Profile Tags: {pt}\n"
            f"  Domains: {d}\n\n"
            f"Existing rules: {rules}\n\n"
            "Respond with JSON ONLY:\n"
            '{"name": "rule_name", "premise": {"strengthen": {">=": N}}}\n'
            '{"conclusion": {"threshold": "S|W|R", "value": N, "action": "lower|raise|tag|warn"}}\n\n'
            "If no new rule needed, return {\"skip\": true}.\n"
            "Thresholds: S>=2=T-type, W>=3=F-type, R>=1=warn."
        )

    def _parse_response(self, response: str) -> Optional[Rule]:
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start < 0:
                return None
            data = json.loads(response[start:end])
            if data.get("skip"):
                return None
            return Rule(
                name=data.get("name", "llm_rule"),
                premise=data.get("premise", {}),
                conclusion=data.get("conclusion", {}),
                source="L2_llm",
                confidence=0.4,
            )
        except Exception:
            return None
