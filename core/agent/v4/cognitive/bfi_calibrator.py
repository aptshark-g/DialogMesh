"""BFI-10 Calibration — anchor LLM OCEAN ratings to literature standard.

Big Five Inventory-10 (Rammstedt & John, 2007):
  10-item ultra-short Big Five measure with validated psychometrics.
  Published: Journal of Research in Personality, 41, 203-212.
  Reliability: test-retest r=0.75, convergent with NEO-PI-R r=0.81.

Usage: LLM rates user on BFI-10 items → maps to OCEAN → calibrates full OCEAN.

This gives the LLM a GROUNDED REFERENCE FRAME instead of free-floating 0-1 ratings.
"""
from __future__ import annotations
import json, logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# BFI-10 items (Rammstedt & John, 2007) — validated psychometric instrument
# Each item: (factor, polarity, "I see myself as someone who...")
BFI10_ITEMS = [
    # Extraversion
    ("E", +1, "is outgoing, sociable"),
    ("E", -1, "is reserved"),
    # Agreeableness
    ("A", +1, "is generally trusting"),
    ("A", -1, "tends to find fault with others"),
    # Conscientiousness
    ("C", +1, "does a thorough job"),
    ("C", -1, "tends to be lazy"),
    # Neuroticism
    ("N", +1, "gets nervous easily"),
    ("N", -1, "is relaxed, handles stress well"),
    # Openness
    ("O", +1, "has an active imagination"),
    ("O", -1, "has few artistic interests"),
]

# BFI-10 scoring: mean of 2 items per factor, reverse-coded for negative items
# Population norms (US adults, N=12,000): mean ± sd per factor
BFI10_NORMS = {
    "E": {"mean": 3.4, "sd": 0.8},
    "A": {"mean": 3.7, "sd": 0.7},
    "C": {"mean": 3.6, "sd": 0.7},
    "N": {"mean": 2.8, "sd": 0.8},
    "O": {"mean": 3.5, "sd": 0.8},
}

# BFI-10 → OCEAN 0-1 mapping (from Likert 1-5 to normalized)
def bfi_to_ocean(bfi_score: float, factor: str) -> float:
    """Map BFI-10 score (1-5 Likert) to OCEAN 0-1 continuous."""
    norm = BFI10_NORMS.get(factor, {"mean": 3.0, "sd": 1.0})
    # Z-score then sigmoid to [0,1]
    z = (bfi_score - norm["mean"]) / norm["sd"]
    return 1.0 / (1.0 + 2.71828 ** (-z))  # logistic function

# OCEAN 0-1 → MBTI mapping (literature: McCrae & Costa, 1989; Furnham, 1996)
# Meta-analysis correlations between Big Five and MBTI
OCEAN_MBTI_CORRELATIONS = {
    "E": {"E": 0.74, "I": -0.74},
    "O": {"N": 0.72, "S": -0.72},
    "A": {"F": 0.44, "T": -0.44},
    "C": {"J": 0.49, "P": -0.49},
    "N": {"P": 0.15},  # weak, mostly uncorrelated
}


class BFICalibrator:
    """Calibrate LLM OCEAN ratings using BFI-10 as reference frame.

    Flow:
      1. LLM rates user on BFI-10 items → calibrated 0-1 OCEAN
      2. LLM rates user on full OCEAN → compare with BFI-10 baseline
      3. Conflict → BFI-10 wins (literature-validated)
      4. Surprise → recorded for later analysis
    """

    def __init__(self, llm_provider=None):
        self._llm = llm_provider
        self._bfi_history: List[Dict] = []
        self._calibration_quality: Dict[str, float] = {}

    def calibrate(self, engine, turn_text: str, llm_response: str) -> Dict[str, Any]:
        """Run BFI-10 rating alongside OCEAN. Returns calibrated profile."""
        if not self._llm:
            return {}

        # 1. Rate user on BFI-10 items
        bfi_scores = self._rate_bfi10(turn_text, llm_response)
        if not bfi_scores:
            return {}

        # 2. Map to OCEAN 0-1
        bfi_ocean = {}
        for factor in ["E", "A", "C", "N", "O"]:
            if factor in bfi_scores:
                bfi_ocean[factor] = bfi_to_ocean(bfi_scores[factor], factor)

        # 3. Compare with LLM's direct OCEAN rating (if available)
        from core.agent.v4.cognitive.ocean_profile import OCEANProfileAnalyst
        analyst = OCEANProfileAnalyst(self._llm)
        llm_ocean = analyst.analyze(engine, turn_text, llm_response)

        comparison = self._compare(bfi_ocean, llm_ocean.get("dimensions", {}))

        # 4. Store for calibration quality tracking
        self._bfi_history.append({
            "bfi_scores": bfi_scores,
            "bfi_ocean": bfi_ocean,
            "llm_ocean": {k: round(v, 2) for k, v in llm_ocean.get("dimensions", {}).items()},
            "divergence": comparison,
        })

        return {
            "bfi10_scores": bfi_scores,
            "calibrated_ocean": bfi_ocean,
            "llm_direct_ocean": llm_ocean.get("dimensions", {}),
            "divergence": comparison,
            "mbti_literature": self._oceAN_to_mbti_literature(bfi_ocean),
        }

    def _rate_bfi10(self, turn_text: str, llm_response: str) -> Dict[str, float]:
        """Ask LLM to rate user on BFI-10 items based on conversation."""
        items_text = "\n".join(
            f'  {factor}{"+" if pol>0 else "-"}: "{desc}"'
            for factor, pol, desc in BFI10_ITEMS
        )
        prompt = f"""Based on this conversation, rate the user on BFI-10 items.

BFI-10 (Big Five Inventory, Rammstedt & John 2007):
  Rate each item 1-5 (1=disagree strongly, 5=agree strongly)
  Base your rating on HOW the user communicates, not what they say.
{items_text}

CONVERSATION:
  User: "{turn_text[:300]}"
  System: "{llm_response[:200]}"

Respond with JSON ONLY:
{{"scores": {{"E+":4,"E-":2,"A+":3,"A-":3,"C+":4,"C-":1,"N+":2,"N-":4,"O+":4,"O-":2}}}}

For each item, give your rating. Be honest — the BFI-10 is a validated instrument.
A score of 5 on "tends to be lazy" means the user appears lazy in conversation."""

        try:
            from core.agent.llm_providers.base import GenerateRequest
            req = GenerateRequest(prompt=prompt, max_tokens=300, temperature=0.2)
            result = self._llm.generate(req)
            text = result.text if hasattr(result, 'text') else str(result)

            # Parse JSON
            start = text.find('{')
            end = text.rfind('}') + 1
            if start < 0:
                return {}
            data = json.loads(text[start:end])
            raw = data.get("scores", data)

            # Calculate factor scores: mean of 2 items, reverse negative
            scores = {}
            for factor in ["E", "A", "C", "N", "O"]:
                plus = float(raw.get(f"{factor}+", 3))
                minus = float(raw.get(f"{factor}-", 3))
                scores[factor] = (plus + (6 - minus)) / 2  # BFI-10 scoring formula
            return scores
        except Exception as e:
            logger.debug("BFI-10 rating failed: %s", e)
            return {}

    def _compare(self, bfi: Dict, llm: Dict) -> Dict:
        """Compare BFI-calibrated vs LLM direct ratings."""
        divergences = {}
        for factor in ["E", "A", "C", "N", "O"]:
            b = bfi.get(factor, 0.5)
            l = llm.get(factor, 0.5)
            if abs(b - l) > 0.15:
                divergences[factor] = {"bfi": round(b, 2), "llm": round(l, 2), "delta": round(b - l, 2)}
        total_divergence = sum(abs(d["delta"]) for d in divergences.values())
        return {"diverging_factors": divergences, "total_divergence": round(total_divergence, 2)}

    def _oceAN_to_mbti_literature(self, ocean: Dict) -> str:
        """Map OCEAN to MBTI using literature correlations."""
        if not ocean:
            return "?"
        ei = "E" if ocean.get("E", 0.5) > 0.5 else "I"
        sn = "N" if ocean.get("O", 0.5) > 0.5 else "S"
        tf = "F" if ocean.get("A", 0.5) > 0.5 else "T"
        jp = "J" if ocean.get("C", 0.5) > 0.5 else "P"
        return f"{ei}{sn}{tf}{jp}"

    def calibration_report(self) -> Dict:
        """Quality report: how well does LLM OCEAN match BFI-10 baseline?"""
        if not self._bfi_history:
            return {"status": "no data"}
        total_div = sum(h["divergence"]["total_divergence"] for h in self._bfi_history)
        avg_div = total_div / len(self._bfi_history)
        return {
            "samples": len(self._bfi_history),
            "avg_divergence": round(avg_div, 3),
            "interpretation": "good calibration" if avg_div < 0.5 else "moderate" if avg_div < 1.0 else "poor",
            "latest": self._bfi_history[-1] if self._bfi_history else {},
        }
