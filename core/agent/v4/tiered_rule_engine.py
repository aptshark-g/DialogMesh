"""TieredRuleEngine: rule-based constraint matching (fast) → LLM fallback (slow)."""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Tuple

from core.agent.v4.tiered_pipeline import Tier, MultiTierPipeline
from core.agent.v3_2.compiler.rule_engine import RuleConstraintEngine, FrameLibrary
from core.agent.v3_2.compiler.models import ConstraintRule

logger = logging.getLogger(__name__)


class TieredRuleEngine:
    """Multi-tier rule evaluation.

    Pipeline:
        Tier 0 (rule):  RuleConstraintEngine.evaluate()  — deterministic keyword matching.
        Tier 1 (llm):   LLM-based frame extraction        — invoked when rule confidence is low.

    The rule tier handles ~90% of domain-specific queries with zero LLM cost.
    The LLM tier covers novel or ambiguous expressions.
    """

    def __init__(self, llm_provider=None, registry=None):
        self._llm_provider = llm_provider
        library = FrameLibrary.load_default()
        self._engine = RuleConstraintEngine(library)

        rule_tier = Tier(
            level=0,
            name="rule_engine.rule",
            process=self._rule_evaluate,
            confidence_threshold=0.7,
            confidence_threshold_param="rule_engine.rule_threshold",
            registry=registry,
            time_budget_ms=5,
        )

        llm_tier = Tier(
            level=1,
            name="rule_engine.llm",
            process=self._llm_evaluate,
            confidence_threshold=0.5,
            confidence_threshold_param="rule_engine.llm_threshold",
            registry=registry,
            time_budget_ms=2000,
        )

        self._pipeline = MultiTierPipeline(
            [rule_tier, llm_tier],
            name="rule_engine",
        )

    def evaluate(self, text: str) -> Tuple[bool, float, Any]:
        ctx = {"text": text}
        result = self._pipeline.execute(ctx)
        val = result.value
        return (val.get("matched", False), val.get("confidence", 0.0), val.get("rule"))

    def stats(self) -> dict:
        return self._pipeline.stats()

    def _rule_evaluate(self, input_data: dict, _context: dict) -> dict:
        text: str = input_data["text"]
        matched, confidence, rule = self._engine.evaluate(text)
        return {"matched": matched, "confidence": confidence, "rule": rule, "source": "rule"}

    def _llm_evaluate(self, input_data: dict, _context: dict) -> dict:
        text: str = input_data["text"]
        if not self._llm_provider:
            hint = _context.get("tier_0_result")
            if hint and hasattr(hint, "value") and hint.value:
                hint.value["source"] = "rule(fallback_no_llm)"
                return hint.value
            return {"matched": False, "confidence": 0.0, "rule": None, "source": "no_llm"}

        try:
            prompt = (
                "Extract the semantic frame from this text. "
                "Output JSON with 'frame_type' (one of: cause, action, agent, patient), "
                "'value', and 'confidence' (0-1).\n\n"
                f'Text: "{text}"\n\nJSON:'
            )
            response = self._llm_provider.complete(prompt)
            import json
            data = json.loads(response)
            frame_type = data.get("frame_type", "action")
            value = data.get("value", text)
            conf = float(data.get("confidence", 0.6))
            return {"matched": True, "confidence": conf,
                    "rule": ConstraintRule(f"{frame_type}({value})", frame_type, [value]),
                    "source": "llm"}
        except Exception:
            logger.exception("LLM rule evaluation failed")
            return {"matched": False, "confidence": 0.0, "rule": None, "source": "llm_error"}
