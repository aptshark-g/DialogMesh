"""TieredContextCompiler: RULE_ONLY → HYBRID → LLM_ONLY progression."""
from __future__ import annotations
import logging
from typing import Any, Dict, List

from core.agent.v4.tiered_pipeline import Tier, MultiTierPipeline

logger = logging.getLogger(__name__)


class TieredContextCompiler:
    """Multi-tier context compilation.

    Pipeline:
        Tier 0 (rule):    CompilationMode.RULE_ONLY   — deterministic regex rules,  sub-ms.
        Tier 1 (hybrid):  CompilationMode.HYBRID      — rule + LLM verification, ~50ms.
        Tier 2 (llm):     CompilationMode.LLM_ONLY    — full LLM compilation,    ~500ms.

    The tier decision is driven by confidence: if RULE_ONLY produces high-confidence
    outputs (all entities matched deterministically), skip HYBRID and LLM_ONLY.
    """

    def __init__(self, llm_provider=None, registry=None):
        self._llm_provider = llm_provider

        rule_tier = Tier(
            level=0,
            name="context.rule",
            process=self._rule_compile,
            confidence_threshold=0.8,
            confidence_threshold_param="context.rule_threshold",
            registry=registry,
            time_budget_ms=10,
        )

        hybrid_tier = Tier(
            level=1,
            name="context.hybrid",
            process=self._hybrid_compile,
            confidence_threshold=0.65,
            confidence_threshold_param="context.hybrid_threshold",
            registry=registry,
            time_budget_ms=100,
        )

        llm_tier = Tier(
            level=2,
            name="context.llm",
            process=self._llm_compile,
            confidence_threshold=0.5,
            confidence_threshold_param="context.llm_threshold",
            registry=registry,
            time_budget_ms=2000,
        )

        self._pipeline = MultiTierPipeline(
            [rule_tier, hybrid_tier, llm_tier],
            name="context_compiler",
        )

    def compile(self, query: str, targets: List[Any] = None) -> Any:
        ctx = {"query": query, "targets": targets or []}
        result = self._pipeline.execute(ctx)
        return result.value

    def stats(self) -> dict:
        return self._pipeline.stats()

    @staticmethod
    def _get_compiler():
        from core.agent.context_compiler import ContextCompiler
        return ContextCompiler()

    def _rule_compile(self, input_data: dict, _context: dict) -> dict:
        try:
            from core.agent.context_compiler import CompilationMode
            compiler = self._get_compiler()
            result = compiler.compile(
                input_data["query"],
                input_data["targets"],
                mode=CompilationMode.RULE_ONLY,
            )
            return {"result": result, "confidence": 0.9, "source": "rule"}
        except Exception:
            logger.exception("Rule compile failed")
            return {"result": None, "confidence": 0.0, "source": "rule_error"}

    def _hybrid_compile(self, input_data: dict, _context: dict) -> dict:
        try:
            from core.agent.context_compiler import CompilationMode
            compiler = self._get_compiler()
            result = compiler.compile(
                input_data["query"],
                input_data["targets"],
                mode=CompilationMode.HYBRID,
            )
            return {"result": result, "confidence": 0.75, "source": "hybrid"}
        except Exception:
            logger.exception("Hybrid compile failed")
            return {"result": None, "confidence": 0.0, "source": "hybrid_error"}

    def _llm_compile(self, input_data: dict, _context: dict) -> dict:
        if not self._llm_provider:
            hint = _context.get("tier_1_result")
            if hint and hasattr(hint, "value") and hint.value:
                hint.value["source"] = "hybrid(fallback_no_llm)"
                return hint.value
            return {"result": None, "confidence": 0.0, "source": "no_llm"}
        try:
            from core.agent.context_compiler import CompilationMode
            compiler = self._get_compiler()
            result = compiler.compile(
                input_data["query"],
                input_data["targets"],
                mode=CompilationMode.LLM_ONLY,
            )
            return {"result": result, "confidence": 0.85, "source": "llm"}
        except Exception:
            logger.exception("LLM compile failed")
            return {"result": None, "confidence": 0.0, "source": "llm_error"}
