"""Unified Intent & Association Parser — one parse, five layers.

Replaces: v3_common IntentParser + separate Association Chain
Design:   BUSINESS_CHAIN_01_UNIFIED_INTENT.md
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import time

from core.agent.v4.classifier.structural_classifier import StructuralFeatures


@dataclass
class UnifiedResult:
    """Single output from unified pipeline — feeds all 10 chains."""
    # Tier 0
    expectation: str = "UNKNOWN"
    confidence: float = 0.0
    structural: Optional[StructuralFeatures] = None

    # Tier 1 / Layer 1-2
    entities: List[str] = field(default_factory=list)
    entity_types: Dict[str, str] = field(default_factory=dict)
    co_occurrence_pairs: List[tuple] = field(default_factory=list)

    # Layer 3: Behavior
    behavior_label: str = ""
    behavior_confidence: float = 0.0

    # Layer 4-5: Temporal/Causal
    causal_closure: Optional[str] = None
    markov_path: List[str] = field(default_factory=list)

    # Meta
    tier_used: int = 0
    latency_ms: float = 0.0
    llm_calibrated: bool = False


class UnifiedParser:
    """Unified Intent + Association Pipeline.

    Tier 0 (0.1ms): StructuralFeatures — grammar only, no keywords
    Tier 1 (3ms):    BGE/SVO — semantic matching
    Tier 2 (200ms):  LLM few-shot — local nemotron → remote DeepSeek
    """

    def __init__(self, llm_provider=None):
        self._llm_provider = llm_provider
        self._bias = {"TOOL": 0.0, "ADVISOR": 0.0, "COMPANION": 0.0, "UNKNOWN": 0.0}

    def parse(self, text: str, history=None, pcr_output=None) -> UnifiedResult:
        t0 = time.perf_counter()
        result = UnifiedResult()

        # ── Tier 0: Structural Features (0.1ms) ──
        sf = StructuralFeatures.extract(text)
        result.structural = sf
        expectation, conf = sf.expectation_hint()

        # Apply PCR bias
        if pcr_output:
            exp = getattr(pcr_output, 'expectation', None)
            if exp and exp in self._bias:
                conf += self._bias[exp] * 0.1

        # Layer 1: co-occurrence from structural
        if sf.entity_count > 0:
            result.entities = self._extract_entities(text, sf)
            result.co_occurrence_pairs = self._make_pairs(result.entities)

        result.expectation = expectation
        result.confidence = min(conf, 1.0)
        result.tier_used = 0

        # ── Tier 2: LLM fallback (only when conf < 0.6) ──
        if result.confidence < 0.6 and self._llm_provider:
            t2_start = time.perf_counter()
            try:
                llm_result = self._llm_fallback(text, result, history, pcr_output)
                if llm_result:
                    # Calibrate: LLM result updates Tier 0 bias
                    old_exp = result.expectation
                    result.expectation = llm_result.get("expectation", old_exp)
                    result.behavior_label = llm_result.get("behavior_label", "")
                    result.behavior_confidence = llm_result.get("confidence", 0.7)
                    result.causal_closure = llm_result.get("causal", None)
                    if result.expectation != old_exp:
                        self._bias[result.expectation] += 0.05
                        self._bias[old_exp] -= 0.02
                        result.llm_calibrated = True
                    result.tier_used = 2
                    result.confidence = max(result.confidence, 0.7)
            except Exception:
                pass
            result.latency_ms = (time.perf_counter() - t2_start) * 1000
        else:
            result.latency_ms = (time.perf_counter() - t0) * 1000

        return result

    def _extract_entities(self, text: str, sf: StructuralFeatures) -> List[str]:
        import re
        entities = []
        entities.extend(re.findall(r'\b0x[0-9a-fA-F]+\b', text))
        entities.extend(re.findall(r'\b\d+\b', text))
        entities.extend(re.findall(r'[A-Z][a-z]+(?:\.[A-Z][a-z]+)+', text))
        return entities[:10]

    def _make_pairs(self, entities: List[str]) -> List[tuple]:
        pairs = []
        for i in range(len(entities)):
            for j in range(i + 1, min(i + 4, len(entities))):
                pairs.append((entities[i], entities[j]))
        return pairs

    def _llm_fallback(self, text: str, result: UnifiedResult, history, pcr_output) -> Optional[dict]:
        from core.agent.llm_providers.base import GenerateRequest
        prompt = (
            f"User: '{text[:300]}'\n"
            f"Current classification: {result.expectation} (conf={result.confidence:.2f})\n"
            f"Entities: {result.entities}\n\n"
            "Respond in JSON:\n"
            '{"expectation": "TOOL|ADVISOR|COMPANION|UNKNOWN", '
            '"behavior_label": "short phrase", "confidence": 0.8, '
            '"causal": "if-then reasoning or null"}'
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
