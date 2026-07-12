"""TieredIntentParser: rule-based classification (fast) → LLM classification (slow)."""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Tuple

from core.agent.v4.tiered.pipeline import Tier, TierResult, MultiTierPipeline
from core.agent.v3_common.intent_parser import IntentParser
from core.agent.prompts.intent_classifier import intent_classify_prompt, parse_intent_result
from core.agent.v3_common.models import (
    Intent, IntentCategory, Entity, ParseContext, IntentContext,
    ParseResult, ParserConfig,
)

logger = logging.getLogger(__name__)


class TieredIntentParser:
    """Multi-tier intent classification.
    Pipeline:
        Tier 0 (rule):   pattern-matching + entity coverage via IntentParser._classify_raw.
        Tier 1 (llm):    LLM-based intent_classifier prompt (only when rule is uncertain).
    """

    def __init__(self, llm_provider=None, registry=None):
        self._llm_provider = llm_provider
        self._parser = IntentParser(llm_provider=llm_provider)

        rule_tier = Tier(
            level=0,
            name="intent.rule",
            process=self._rule_classify,
            confidence_threshold=0.6,
            confidence_threshold_param="intent.rule_threshold",
            registry=registry,
            time_budget_ms=10,
        )

        llm_tier = Tier(
            level=1,
            name="intent.llm",
            process=self._llm_classify,
            confidence_threshold=0.5,
            confidence_threshold_param="intent.llm_threshold",
            registry=registry,
            time_budget_ms=2000,
        )

        self._pipeline = MultiTierPipeline(
            [rule_tier, llm_tier],
            name="intent_parser",
        )

    # ── public API ──────────────────────────────────────────────

    def classify(self, text: str, intent_context: IntentContext) -> Tuple[Any, float]:
        ctx = {"text": text, "intent_context": intent_context}
        result = self._pipeline.execute(ctx)
        val = result.value
        return (val.get("category", IntentCategory.UNKNOWN),
                val.get("confidence", 0.0))

    def stats(self) -> dict:
        return self._pipeline.stats()

    # ── tier processors ─────────────────────────────────────────

    def _rule_classify(self, input_data: dict, _context: dict) -> dict:
        """Tier 0: deterministic rule-based classification."""
        text: str = input_data["text"]
        intent_context: IntentContext = input_data["intent_context"]
        config = ParserConfig.from_intent_context(intent_context)

        entities: List[Entity] = self._parser._extract_entities(text, config, intent_context)
        candidates = self._parser._classify_raw(text, entities, intent_context, config)

        if not candidates and config.enable_synonym_expansion:
            expanded = self._parser._expand_synonyms(text)
            candidates = self._parser._classify_raw(expanded, entities, intent_context, config)

        if candidates:
            best_cat, best_conf, best_rule = candidates[0]
            return {
                "category": best_cat,
                "confidence": best_conf,
                "source": "rule",
                "rule_name": getattr(best_rule, "name", ""),
                "entities": entities,
            }
        return {"category": IntentCategory.UNKNOWN, "confidence": 0.0, "source": "rule", "entities": entities}

    def _llm_classify(self, input_data: dict, _context: dict) -> dict:
        """Tier 1: LLM-based fallback classification."""
        text: str = input_data["text"]

        if not self._llm_provider:
            hint = _context.get("tier_0_result")
            if hint and isinstance(hint, TierResult) and hint.value:
                hint.value["source"] = "rule(fallback_no_llm)"
                return hint.value
            return {"category": IntentCategory.UNKNOWN, "confidence": 0.0, "source": "no_llm"}

        prompt = intent_classify_prompt(text)
        try:
            response = self._llm_provider.complete(prompt)
            parsed = parse_intent_result(response)
            if parsed:
                label, conf = parsed
                return {"category": label, "confidence": conf, "source": "llm"}
        except Exception:
            logger.exception("LLM intent classification failed")

        return {"category": IntentCategory.UNKNOWN, "confidence": 0.0, "source": "llm_error"}
