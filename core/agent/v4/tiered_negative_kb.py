"""TieredNegativeKB: keyword matching (fast) → semantic/fuse evaluation (slow)."""
from __future__ import annotations
import logging
from typing import Optional

from core.agent.v4.tiered_pipeline import Tier, TierResult, MultiTierPipeline
from core.agent.v3_2.negative_kb.negative_kb import NegativeKB
from core.agent.v3_2.negative_kb.models import NegativeLevel, NegativeResult, ContextualNegativeRule

logger = logging.getLogger(__name__)


class TieredNegativeKB:
    """Multi-tier negative knowledge base.

    Pipeline:
        Tier 0 (keyword): RuleStore pattern matching – sub-millisecond.
        Tier 1 (fuse):    FuseController hit-tracking + learned overrides.

    Tier 0 returns with high confidence when keyword match is unambiguous (HARD_BLOCK or
    no match at all).  Tier 1 is invoked only for WARN/SOFT_DISCOURAGE cases where
    the FuseController tracks repeated overrides.
    """

    def __init__(self, registry=None):
        self._kb = NegativeKB()

        keyword_tier = Tier(
            level=0,
            name="negative_kb.keyword",
            process=self._keyword_check,
            confidence_threshold=0.85,
            confidence_threshold_param="negative_kb.keyword_threshold",
            registry=registry,
            time_budget_ms=5,
        )

        fuse_tier = Tier(
            level=1,
            name="negative_kb.fuse",
            process=self._fuse_check,
            confidence_threshold=0.7,
            confidence_threshold_param="negative_kb.fuse_threshold",
            registry=registry,
            time_budget_ms=50,
        )

        self._pipeline = MultiTierPipeline(
            [keyword_tier, fuse_tier],
            name="negative_kb",
        )

    # ── public API ──────────────────────────────────────────────

    def check(self, ctx: str = "") -> NegativeResult:
        result = self._pipeline.execute(ctx)
        val = result.value
        return val if isinstance(val, NegativeResult) else NegativeResult()

    def register(self, rule: ContextualNegativeRule) -> None:
        self._kb.register(rule)

    def stats(self) -> dict:
        return self._pipeline.stats()

    # ── tier processors ─────────────────────────────────────────

    @staticmethod
    def _keyword_check(ctx: str, _context: dict) -> NegativeResult:
        """Fast path: only the RuleStore (no fuse tracking)."""
        store = NegativeKB().store
        level = store.get_highest(ctx)
        if level is None:
            return NegativeResult()
        for rule in store.applicable(ctx):
            if rule.level == level:
                if level == NegativeLevel.HARD_BLOCK and not rule.is_verified:
                    continue
                r = NegativeResult(level=rule.level, rule_id=rule.rule_id, message=rule.message,
                                   blocked=(level == NegativeLevel.HARD_BLOCK))
                r.confidence = _level_confidence(rule.level)
                return r
        return NegativeResult()

    def _fuse_check(self, ctx: str, _context: dict) -> NegativeResult:
        """Full path: go through FuseController for tracking / learned overrides."""
        return self._kb.check(ctx)


def _level_confidence(level: Optional[NegativeLevel]) -> float:
    if level == NegativeLevel.HARD_BLOCK:
        return 0.98
    if level == NegativeLevel.WARN:
        return 0.6
    if level == NegativeLevel.SOFT_DISCOURAGE:
        return 0.4
    return 0.5
