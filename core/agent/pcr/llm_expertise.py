"""LLM-Driven Expertise Probe — zero hardcoded terminology lists.

Replaces v3_common/expertise_probe.py (703L of keyword matching).
Design: LLM extracts 5-dimensional expertise signal in one call.
Feeds into PCR V2 Z-axis for routing modulation.

5 dimensions:
  1. terminology_density   — domain-specific jargon ratio (LLM judgment)
  2. parameter_precision   — exact addresses/types/values (structural regex + LLM verify)
  3. query_complexity      — syntactic depth, condition chains (structural fallback)
  4. language_style        — imperative/diagnostic/exploratory/venting (LLM judgment)
  5. expert_confidence     — overall expertise level (LLM synthesis)
"""

from __future__ import annotations
from typing import Dict, Optional
import json, re, logging

logger = logging.getLogger(__name__)


class LLMExpertiseProbe:
    """LLM-driven expertise assessment. Zero hardcoded terms.

    Usage:
        probe = LLMExpertiseProbe(llm=deepseek)
        expertise = probe.analyze("用gadget链构造ROP利用ROPgadget", history=[])
        # → {terminology_density: 0.9, expert_confidence: 0.85, ...}
    """

    def __init__(self, llm=None):
        self.llm = llm

    def analyze(self, text: str, history: list = None,
                pcr_coords: dict = None, llm=None) -> dict:
        """LLM-driven 5-dimension expertise assessment."""
        llm = llm or self.llm

        if not llm:
            return self._structural_fallback(text)

        # Build structured context
        ctx = {
            "user_text": text,
            "text_length": len(text),
            "has_precise_params": bool(re.findall(r'0x[0-9a-fA-F]+|[0-9]{2,}\.[0-9]{2,}\.[0-9]{2,}|[A-Z]{2,8}-\d{2,}', text)),
            "has_code_blocks": '`' in text or '```' in text,
            "history_summary": (history[-3:] if history else [])[-3:],
            "pcr_zone": pcr_coords.get("zone", "MIXED") if pcr_coords else None,
        }

        prompt = f"""Analyze this user message for expertise level. Rate 5 dimensions (0-1).

CONTEXT: {json.dumps(ctx, ensure_ascii=False)}

Dimensions:
1. terminology_density: ratio of domain jargon (0=none, 1=all jargon)
2. parameter_precision: exact addresses/types/values present (0=none, 1=precise)
3. query_complexity: syntactic/structural depth (0=simple, 1=deep/nested)
4. language_style: category (diagnostic/implementation/exploratory/venting)
5. expert_confidence: overall expertise (0=novice, 1=expert)

Consider: concise directives + precise params = expert. Hand-holding questions = novice.
Rare terms + structural commands = likely expert regardless of length.

Output JSON: {{"terminology_density": 0.X, "parameter_precision": 0.X, "query_complexity": 0.X, "language_style": "category", "expert_confidence": 0.X, "reasoning": "one sentence"}}"""

        try:
            resp = llm.generate(prompt, max_tokens=200, temperature=0.1)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(resp))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            s = cleaned.find('{'); e = cleaned.rfind('}')
            if s >= 0 and e > s:
                result = json.loads(cleaned[s:e+1])
                result["source"] = "llm"
                return result
        except Exception as e:
            logger.debug("LLM expertise probe failed: %s", e)

        return self._structural_fallback(text)

    def _structural_fallback(self, text: str) -> dict:
        """Structural fallback: zero keyword lists, pure pattern detection."""
        has_hex = bool(re.findall(r'0x[0-9a-fA-F]{2,}', text))
        has_version = bool(re.findall(r'\d+\.\d+\.\d+', text))
        has_code_ids = bool(re.findall(r'[A-Z]{2,8}-\d{2,}', text))
        has_code = '```' in text or '`' in text
        word_count = len(text.split())
        is_short = word_count < 8

        param_precision = 0.3
        if has_hex: param_precision += 0.2
        if has_version: param_precision += 0.2
        if has_code_ids: param_precision += 0.2

        complexity = min(1.0, word_count / 50)
        
        # Concise + precise params → likely expert (structural)
        expert_score = 0.3
        if is_short and param_precision > 0.3:
            expert_score = 0.65
        if has_code and param_precision > 0.3:
            expert_score = 0.75

        return {
            "terminology_density": 0.3 if has_code else 0.1,
            "parameter_precision": round(param_precision, 2),
            "query_complexity": round(complexity, 2),
            "language_style": "unknown",
            "expert_confidence": round(expert_score, 2),
            "source": "structural",
            "reasoning": "structural fallback (no LLM)",
        }

    def modulate_pcr_z(self, expertise: dict, pcr_z: float) -> float:
        """Modulate PCR Z-axis with expertise signal.

        Expert → shift toward PRECISION/ATOMIC (z>0)
        Novice → shift toward EXPLORE (z≈0)
        Venting → shift toward PSYCHE (z<0)
        """
        conf = expertise.get("expert_confidence", 0.5)
        style = expertise.get("language_style", "")

        if style == "venting":
            return pcr_z - 0.3  # toward PSYCHE
        if conf > 0.7:
            return pcr_z + 0.2  # toward PRECISION
        if conf < 0.3:
            return pcr_z - 0.1  # softer, toward EXPLORE

        return pcr_z
