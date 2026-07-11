"""TieredCognitiveCompiler: degradation (_rule_only) → full LLM pipeline."""
from __future__ import annotations
import asyncio
import concurrent.futures
import logging
from typing import Any, Dict

from core.agent.v4.tiered_pipeline import Tier, MultiTierPipeline
from core.agent.v3_2.compiler.hybrid_compiler import HybridCompiler
from core.agent.v3_2.compiler.models import ParseResult, ParseContext

logger = logging.getLogger(__name__)


def _sync_run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result(timeout=30)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


class TieredCognitiveCompiler:
    """Multi-tier cognitive compilation.

    Pipeline:
        Tier 0 (rule_only):  DegradationManager.rule_parse()  — pure rule, sub-ms.
        Tier 1 (full):       HybridCompiler.process()         — LLM + rule engine + scorer.
    """

    def __init__(self, llm_provider=None, registry=None):
        self._llm_provider = llm_provider

        rule_tier = Tier(
            level=0,
            name="cognitive.rule_only",
            process=self._run_rule_only,
            confidence_threshold=0.75,
            confidence_threshold_param="cognitive.rule_threshold",
            registry=registry,
            time_budget_ms=20,
        )

        full_tier = Tier(
            level=1,
            name="cognitive.full",
            process=self._run_full,
            confidence_threshold=0.6,
            confidence_threshold_param="cognitive.full_threshold",
            registry=registry,
            time_budget_ms=2000,
        )

        self._pipeline = MultiTierPipeline(
            [rule_tier, full_tier],
            name="cognitive_compiler",
        )

    def process(self, sentence: str, context: Any = None) -> ParseResult:
        ctx = {"sentence": sentence, "context": context or ParseContext()}
        result = self._pipeline.execute(ctx)
        val = result.value
        if isinstance(val, ParseResult):
            return val
        return ParseResult(slots={}, stability={}, undefined=True)

    def stats(self) -> dict:
        return self._pipeline.stats()

    @staticmethod
    def _run_rule_only(input_data: dict, _context: dict) -> ParseResult:
        sentence = input_data["sentence"]
        ctx = input_data["context"]
        from core.agent.v3_2.compiler.rule_engine import RuleConstraintEngine, FrameLibrary
        from core.agent.v3_2.compiler.stability_scorer import StabilityScorer
        from core.agent.v3_2.compiler.degradation_manager import DegradationManager
        library = FrameLibrary.load_default()
        rule_engine = RuleConstraintEngine(library)
        dm = DegradationManager(max_retries=1)
        scorer = StabilityScorer()

        slots = dm.rule_parse(sentence, library)
        if slots:
            slots = rule_engine.refine(slots, ctx)
        stability = scorer.score(slots)
        result = ParseResult(slots=slots, stability=stability, degraded=True,
                             undefined=scorer.is_undefined(stability))
        result.confidence = 1.0 - (0.5 if result.undefined else 0.0)
        return result

    def _run_full(self, input_data: dict, _context: dict) -> ParseResult:
        if not self._llm_provider:
            hint = _context.get("tier_0_result")
            if hint and hasattr(hint, "value") and isinstance(hint.value, ParseResult):
                return hint.value
            return ParseResult(slots={}, stability={}, undefined=True)
        compiler = HybridCompiler(self._llm_provider)
        return _sync_run(compiler.process(input_data["sentence"], input_data["context"]))
