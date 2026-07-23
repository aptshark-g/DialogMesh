"""Unified Intent & Association Parser — structural-first, no keyword hardcoding.

Design:   BUSINESS_CHAIN_01_UNIFIED_INTENT.md
Strategy: Tier 0 grammar structure → Tier 1 BGE/SVO → Tier 2 LLM
          ALL entity/behavior labeling deferred to Tier 1 (BGE) or Tier 2 (LLM).
          NO domain keyword matching anywhere.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import time
import logging

from core.agent.classifier.structural_classifier import StructuralFeatures

logger = logging.getLogger(__name__)


@dataclass
class UnifiedResult:
    expectation: str = "UNKNOWN"
    confidence: float = 0.0
    structural: Optional[StructuralFeatures] = None
    entities: List[str] = field(default_factory=list)
    entity_types: Dict[str, str] = field(default_factory=dict)
    behavior_label: str = ""
    behavior_confidence: float = 0.0
    causal_closure: Optional[str] = None
    tier_used: int = 0
    latency_ms: float = 0.0
    llm_calibrated: bool = False

    def monitor_data(self) -> dict:
        """Export structured monitoring data — no domain knowledge assumed."""
        return {
            "expectation": self.expectation,
            "confidence": self.confidence,
            "tier_used": self.tier_used,
            "latency_ms": self.latency_ms,
            "entity_count": len(self.entities),
            "behavior_label": self.behavior_label or None,
            "llm_calibrated": self.llm_calibrated,
            "word_count": self.structural.word_count if self.structural else 0,
            "has_question": self.structural.has_question_mark if self.structural else False,
            "has_imperative": self.structural.has_imperative if self.structural else False,
            "repetition_ratio": self.structural.repetition_ratio if self.structural else 0,
        }


class UnifiedParser:
    """Pure structural parser. No domain keywords. Layer 1-5 via BGE/LLM only."""

    def __init__(self, llm_provider=None):
        self._llm_provider = llm_provider
        self._bias = {"TOOL": 0.0, "ADVISOR": 0.0, "COMPANION": 0.0, "UNKNOWN": 0.0}
        self._monitor: List[dict] = []  # rolling monitoring log

    def parse(self, text: str, history=None, pcr_output=None) -> UnifiedResult:
        t0 = time.perf_counter()
        result = UnifiedResult()

        # Tier 0: structural grammar (zero keywords)
        sf = StructuralFeatures.extract(text)
        result.structural = sf
        result.expectation, result.confidence = sf.expectation_hint()

        if pcr_output:
            exp = getattr(pcr_output, 'expectation', None)
            if exp and exp in self._bias:
                result.confidence = min(result.confidence + self._bias[exp] * 0.1, 1.0)

        result.tier_used = 0

        # Tier 2: LLM fallback (low confidence only)
        if result.confidence < 0.6 and self._llm_provider:
            try:
                llm_result = self._llm_fallback(text, result, history, pcr_output)
                if llm_result:
                    old_exp = result.expectation
                    result.expectation = llm_result.get("expectation", old_exp)
                    result.behavior_label = llm_result.get("behavior_label", "")
                    result.confidence = max(result.confidence, 0.7)
                    if result.expectation != old_exp:
                        self._bias[result.expectation] += 0.05
                        self._bias[old_exp] -= 0.02
                        result.llm_calibrated = True
                    result.tier_used = 2
            except Exception as e:
                logger.debug("LLM fallback failed: %s", e)

        result.latency_ms = (time.perf_counter() - t0) * 1000

        # Monitoring
        self._monitor.append(result.monitor_data())
        if len(self._monitor) > 1000:
            self._monitor = self._monitor[-500:]

        return result

    def _llm_fallback(self, text: str, result: UnifiedResult, history, pcr_output) -> Optional[dict]:
        from core.agent.llm_providers.base import GenerateRequest
        prompt = (
            f"Classify this user input:\n"
            f"'{text[:300]}'\n\n"
            f"Structural analysis: expectation={result.expectation} (conf={result.confidence:.2f})\n"
            f"Respond in JSON:\n"
            '{"expectation": "TOOL|ADVISOR|COMPANION|UNKNOWN", '
            '"behavior_label": "short descriptive phrase", "confidence": 0.8}'
        )
        req = GenerateRequest(prompt=prompt, temperature=0.1, max_tokens=200)
        resp = self._llm_provider.generate(req)
        raw = getattr(resp, 'text', '') or ''
        try:
            import json
            raw = raw.strip()
            if raw.startswith('```'):
                raw = raw.split('\n', 1)[-1].rsplit('\n```', 1)[0]
            return json.loads(raw)
        except Exception:
            return None

    def monitor_report(self) -> dict:
        """Aggregated monitoring report over recent inputs."""
        if not self._monitor:
            return {}
        total = len(self._monitor)
        tier0 = sum(1 for m in self._monitor if m["tier_used"] == 0)
        tier2 = sum(1 for m in self._monitor if m["tier_used"] == 2)
        calibrations = sum(1 for m in self._monitor if m["llm_calibrated"])
        avg_latency = sum(m["latency_ms"] for m in self._monitor) / total

        return {
            "total_parses": total,
            "tier0_only_pct": round(tier0 / total * 100, 1),
            "tier2_fallback_pct": round(tier2 / total * 100, 1),
            "calibration_rate": round(calibrations / max(tier2, 1) * 100, 1),
            "avg_latency_ms": round(avg_latency, 2),
            "expectation_dist": {
                exp: sum(1 for m in self._monitor if m["expectation"] == exp)
                for exp in ["TOOL", "ADVISOR", "COMPANION", "UNKNOWN"]
            },
            "bias_state": dict(self._bias),
        }
