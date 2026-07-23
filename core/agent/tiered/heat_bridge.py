"""TierHeatBridge: MultiTierPipeline stats -> GraphTierManager heat signals."""
from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class HeatSignal:
    """Aggregated heat score for a domain-tag group."""
    domain_tag: str
    heat_score: float
    dominant_tier: int
    correction_trend: str  # "rising", "falling", "stable"
    suggestion: str  # "promote", "demote", "keep"
    sample_count: int = 0


class TierHeatBridge:
    """Bridge between MultiTierPipeline runtime stats and GraphTierManager GC.

    Collects per-pipeline tier statistics, computes domain-level heat scores,
    and generates promote/demote suggestions that feed into GraphTierManager.
    Does not modify GraphTierManager directly — suggestions are applied via
    apply_to_manager().
    """

    def __init__(self, registry=None):
        self._registry = registry
        self._pipelines: Dict[str, Dict[str, Any]] = {}  # name -> {pipeline, domain_tags}
        self._snapshots: List[Dict] = []
        self._last_collect = 0.0

    # ── registration ─────────────────────────────────────────────

    def register_pipeline(self, pipeline, domain_tags: List[str]):
        """Register a MultiTierPipeline for heat collection."""
        name = getattr(pipeline, "name", str(id(pipeline)))
        self._pipelines[name] = {"pipeline": pipeline, "domain_tags": domain_tags}

    # ── collection ────────────────────────────────────────────────

    def collect(self) -> List[HeatSignal]:
        """Fetch stats from all registered pipelines and compute heat signals."""
        now = time.time()
        collect_interval = self._get_param("heat.collect_interval_ms", 60000) / 1000.0
        if now - self._last_collect < collect_interval:
            return self._evaluate_from_cache()

        self._last_collect = now
        all_signals: List[HeatSignal] = []

        for name, entry in self._pipelines.items():
            pipeline = entry["pipeline"]
            domain_tags = entry["domain_tags"]
            stats = pipeline.stats()
            tiers = stats.get("tiers", [])

            for tag in domain_tags:
                signal = self._compute_heat(tag, tiers)
                if signal.sample_count >= self._get_param("heat.min_samples", 50):
                    all_signals.append(signal)

        self._snapshots.append({"time": now, "signals": all_signals})
        return all_signals

    def _compute_heat(self, domain_tag: str, tiers: List[dict]) -> HeatSignal:
        """Compute heat score from tier-level pass_rate and correction_rate."""
        score = 0.0
        total_calls = 0
        dominant_tier = -1
        max_pass = 0.0

        for t in tiers:
            level = t.get("level", 0)
            pass_rate = t.get("pass_rate", 0.5)
            correction_rate = t.get("corrections", 0) / max(1, t.get("calls", 1))
            calls = t.get("calls", 0)
            total_calls += calls

            weight = 1.0 / max(1, level + 1)
            penalty = 0.5 * (level + 1)
            score += pass_rate * weight - correction_rate * penalty

            if pass_rate > max_pass:
                max_pass = pass_rate
                dominant_tier = level

        # Normalize to [-1, 1]
        score = max(-1.0, min(1.0, score / max(1, len(tiers))))

        trend = "stable"
        if self._snapshots:
            prev = self._snapshots[-1].get("signals", [])
            for ps in prev:
                if ps.domain_tag == domain_tag:
                    if score > ps.heat_score + 0.1:
                        trend = "rising"
                    elif score < ps.heat_score - 0.1:
                        trend = "falling"
                    break

        promote_thresh = self._get_param("heat.promote_threshold", 0.6)
        demote_thresh = self._get_param("heat.demote_threshold", -0.4)

        if score > promote_thresh:
            suggestion = "promote"
        elif score < demote_thresh:
            suggestion = "demote"
        else:
            suggestion = "keep"

        return HeatSignal(
            domain_tag=domain_tag,
            heat_score=round(score, 3),
            dominant_tier=dominant_tier,
            correction_trend=trend,
            suggestion=suggestion,
            sample_count=total_calls,
        )

    def _evaluate_from_cache(self) -> List[HeatSignal]:
        if self._snapshots:
            return self._snapshots[-1].get("signals", [])
        return []

    # ── application ───────────────────────────────────────────────

    def apply_to_manager(self, manager) -> List[str]:
        """Apply heat signals to a GraphTierManager. Returns list of changed node IDs."""
        signals = self.collect()
        changed: List[str] = []

        for sig in signals:
            if sig.suggestion == "promote":
                manager.promote_node(sig.domain_tag)
                changed.append(f"promote:{sig.domain_tag}")
            elif sig.suggestion == "demote":
                manager.demote_node(sig.domain_tag)
                changed.append(f"demote:{sig.domain_tag}")

        return changed

    def stats(self) -> dict:
        signals = self._evaluate_from_cache()
        return {
            "pipelines": len(self._pipelines),
            "signals": len(signals),
            "last_collect": self._last_collect,
            "details": [
                {"tag": s.domain_tag, "score": s.heat_score, "suggestion": s.suggestion}
                for s in signals
            ],
        }

    # ── helpers ──────────────────────────────────────────────────

    def _get_param(self, key: str, default: float) -> float:
        if self._registry:
            try:
                return self._registry.value(key)
            except Exception:
                pass
        return default
