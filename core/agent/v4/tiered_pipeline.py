"""TieredPipeline: configurable precision-compute spectrum pipeline."""
from __future__ import annotations
import time, logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TierStats:
    calls: int = 0; pass_through: int = 0; upgraded: int = 0
    corrections: int = 0; total_latency_ms: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(1, self.calls)

    @property
    def pass_rate(self) -> float:
        return self.pass_through / max(1, self.calls)


@dataclass
class TierResult:
    value: Any; confidence: float; tier_level: int
    tier_name: str; latency_ms: float = 0.0


class Tier:
    def __init__(self, level: int, name: str, process: Callable,
                 confidence_threshold: float = 0.7,
                 confidence_threshold_param: str = None,
                 registry = None, time_budget_ms: int = 100,
                 enabled: bool = True):
        self.level = level; self.name = name; self.process = process
        self.time_budget_ms = time_budget_ms; self.enabled = enabled
        self.stats = TierStats()
        self._correction_buffer: List[dict] = []
        self.confidence_threshold_param = confidence_threshold_param
        self._registry = registry
        if registry and confidence_threshold_param:
            try:
                self.confidence_threshold = registry.value(confidence_threshold_param)
            except Exception:
                self.confidence_threshold = confidence_threshold
        else:
            self.confidence_threshold = confidence_threshold

    def run(self, input_data: Any, context: dict) -> TierResult:
        if not self.enabled:
            return TierResult(value=None, confidence=0.0, tier_level=self.level,
                              tier_name=self.name + "(off)")
        start = time.perf_counter()
        try:
            value = self.process(input_data, context)
        except Exception:
            logger.exception("Tier %s failed", self.name)
            self.stats.calls += 1
            return TierResult(value=None, confidence=0.0, tier_level=self.level,
                              tier_name=self.name + "(err)")
        elapsed = (time.perf_counter() - start) * 1000
        self.stats.calls += 1
        self.stats.total_latency_ms += elapsed
        return TierResult(value=value, confidence=self._extract_confidence(value),
                          tier_level=self.level, tier_name=self.name, latency_ms=elapsed)

    def apply_correction(self, correction: dict):
        self._correction_buffer.append(correction)
        if self._registry and self.confidence_threshold_param:
            try:
                direction = 1.0 if self.stats.corrections / max(1, self.stats.calls) > 0.3 else -1.0
                self._registry.apply_signal(self.confidence_threshold_param, direction * 0.01)
                self.confidence_threshold = self._registry.value(self.confidence_threshold_param)
            except Exception:
                pass
        self.stats.corrections += 1

    @staticmethod
    def _extract_confidence(value: Any) -> float:
        if hasattr(value, 'confidence'): return value.confidence
        if isinstance(value, dict): return value.get('confidence', 0.5)
        return 0.5


class UpgradePolicy:
    @staticmethod
    def should_upgrade(result: TierResult, tier: Tier,
                       budget_remaining_ms: float = None) -> bool:
        if result.confidence >= tier.confidence_threshold:
            tier.stats.pass_through += 1
            return False
        tier.stats.upgraded += 1
        return True


class MultiTierPipeline:
    def __init__(self, tiers: List[Tier], upgrade_policy: UpgradePolicy = None,
                 name: str = "pipeline"):
        self._tiers = tiers; self.name = name
        self._policy = upgrade_policy or UpgradePolicy()
        self.total_calls = 0; self.total_latency_ms = 0.0

    def add_tier(self, tier: Tier):
        self._tiers.append(tier); self._tiers.sort(key=lambda t: t.level)

    def execute(self, input_data: Any, context: dict = None) -> TierResult:
        ctx = context or {}; start = time.perf_counter()
        last_result = None
        for tier in self._tiers:
            result = tier.run(input_data, ctx)
            if last_result is not None:
                ctx[f"tier_{tier.level-1}_result"] = last_result
            if self._policy.should_upgrade(result, tier):
                last_result = result
            else:
                self._record(result, start)
                return result
        final = last_result or TierResult(value=None, confidence=0.0, tier_level=-1, tier_name="no_tiers")
        self._record(final, start)
        return final

    def _record(self, result: TierResult, start: float):
        self.total_calls += 1
        self.total_latency_ms += (time.perf_counter() - start) * 1000

    def stats(self) -> dict:
        return {
            "pipeline": self.name, "total_calls": self.total_calls,
            "avg_latency_ms": self.total_latency_ms / max(1, self.total_calls),
            "tiers": [
                {"level": t.level, "name": t.name,
                 "calls": t.stats.calls, "pass_rate": round(t.stats.pass_rate, 2),
                 "corrections": t.stats.corrections, "avg_ms": round(t.stats.avg_latency_ms, 2)}
                for t in self._tiers
            ],
        }
