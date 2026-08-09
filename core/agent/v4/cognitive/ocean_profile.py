"""OCEAN + Cognitive Profile — 10-dimension user modeling.

Literature-backed dimensions:

OCEAN (Big Five) — continuous 0-1:
  O: Openness        — preference for novelty, complexity, abstraction
  C: Conscientiousness — preference for order, structure, thoroughness
  E: Extraversion     — energy from social interaction vs solitude
  A: Agreeableness   — cooperative vs challenging communication
  N: Neuroticism     — emotional reactivity vs stability

Cognitive Dimensions:
  NC: Need for Cognition — analytical depth preference
  CS: Communication Style — analytical/narrative/interrogative/declarative
  DK: Domain Knowledge  — technical/architectural/philosophical depth
  MS: Meta-cognitive   — self-referential thinking, recursion
  CL: Curiosity Level  — exploration vs exploitation in questioning

Detection: LLM Profile Analyst rates each dimension 0-1 per turn.
Aggregation: exponential moving average (more weight to recent turns).

Refs:
  - Majumder et al., "Deep Learning for Personality Detection from Text"
  - Cacioppo & Petty, "Need for Cognition" (1982)
  - Park et al., "Generative Agents" (2023)
  - Zheng et al., "Judging LLM-as-a-Judge" (2023)
"""
from __future__ import annotations
import json, logging, os, time
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# 10 dimensions with descriptions for LLM prompting
DIMENSIONS = {
    "O": "Openness to experience — 0=prefers concrete facts, 1=seeks abstract theory and novelty",
    "C": "Conscientiousness — 0=spontaneous/flexible, 1=structured/systematic/rigorous",
    "E": "Extraversion — 0=reserved/introspective, 1=outgoing/expressive",
    "A": "Agreeableness — 0=challenging/critical, 1=cooperative/harmonious",
    "N": "Neuroticism — 0=calm/composed, 1=reactive/emotionally expressive",
    "NC": "Need for Cognition — 0=intuitive/quick decisions, 1=enjoys deep analytical thinking",
    "CS": "Communication Style — 0=narrative/descriptive, 1=analytical/interrogative",
    "DK": "Domain Knowledge — 0=general/broad, 1=deep/technical/specialized",
    "MS": "Meta-Cognition — 0=task-focused, 1=self-referential/recursive thinking",
    "CL": "Curiosity Level — 0=satisfied/stays on topic, 1=explores/tangents/deep dives",
}

# Dimensional reduction for MBTI mapping
OCEAN_TO_MBTI = {
    # High O + High NC → N (intuition)
    # Low O + Low NC → S (sensing)
    # High A + Low C → F (feeling)
    # Low A + High C + High NC → T (thinking)
    # O>0.6 and NC>0.5 → N, else S
    # A>0.6 → F, else if C>0.5 and NC>0.5 → T
}


class OCEANProfile:
    """10-dimension continuous profile with EMA aggregation."""

    def __init__(self, alpha: float = 0.3):
        self.dims: Dict[str, float] = {k: 0.5 for k in DIMENSIONS}
        self.alpha = alpha  # EMA smoothing: alpha * new + (1-alpha) * old
        self.turn_count = 0
        self.history: List[Dict] = []

    def update(self, ratings: Dict[str, float]) -> None:
        """EMA update: smooths personality estimates over time."""
        self.turn_count += 1
        for dim, new_val in ratings.items():
            if dim in self.dims:
                self.dims[dim] = self.alpha * new_val + (1 - self.alpha) * self.dims[dim]
        self.history.append({"turn": self.turn_count, "ratings": ratings})

    def top_dimensions(self, n: int = 3) -> List[str]:
        """Return top N dimensions by deviation from neutral (0.5)."""
        deviated = {k: abs(v - 0.5) for k, v in self.dims.items()}
        return sorted(deviated, key=deviated.get, reverse=True)[:n]

    def to_mbti(self) -> str:
        """Approximate MBTI from OCEAN dimensions."""
        d = self.dims
        # E/I
        ei = "E" if d["E"] > 0.55 else "I"
        # S/N
        sn = "N" if d["O"] > 0.55 and d["NC"] > 0.5 else "S"
        # T/F
        if d["A"] < 0.45 and d["NC"] > 0.55:
            tf = "T"
        elif d["A"] > 0.55:
            tf = "F"
        else:
            tf = "T" if d["NC"] > 0.5 else "F"
        # J/P
        jp = "J" if d["C"] > 0.55 else "P"
        return f"{ei}{sn}{tf}{jp}"

    def to_dict(self) -> dict:
        return {"dims": self.dims, "turn_count": self.turn_count, "mbti_approx": self.to_mbti(),
                "history_len": len(self.history)}

    def save(self, path: str = "data/profile/ocean_profile.json") -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str = "data/profile/ocean_profile.json", alpha: float = 0.3) -> "OCEANProfile":
        if not os.path.exists(path):
            return cls(alpha=alpha)
        with open(path) as f:
            data = json.load(f)
        profile = cls(alpha=alpha)
        profile.dims = data.get("dims", {k: 0.5 for k in DIMENSIONS})
        profile.turn_count = data.get("turn_count", 0)
        return profile

    def to_llm_context(self) -> str:
        """Render profile as structured context for LLM injection."""
        top = self.top_dimensions(6)
        lines = [f"User Profile (10-dim OCEAN+Cognitive, EMA α={self.alpha}):"]
        for dim in top:
            v = self.dims[dim]
            bar = "█" * int(v * 10) + "░" * (10 - int(v * 10))
            lines.append(f"  {dim}({DIMENSIONS[dim][:40]}): {v:.2f} {bar}")
        lines.append(f"  MBTI(approx): {self.to_mbti()}")
        return "\n".join(lines)


class OCEANProfileAnalyst:
    """LLM-driven 10-dimension profile analysis.

    Each turn, LLM rates all 10 dimensions based on:
      1. What the user said (content)
      2. Trace signals (quantitative evidence)
      3. Previous profile (continuity)
    """

    def __init__(self, llm_provider=None):
        self._llm = llm_provider
        self.profile = OCEANProfile()

    def analyze(self, engine, turn_text: str, llm_response: str) -> Dict[str, Any]:
        """Rate all 10 dimensions based on this turn's conversation."""
        if not self._llm:
            return {"dimensions": {}, "error": "no_llm"}

        # Gather signals
        signals = self._extract_signals(engine)
        prev = self.profile.dims

        prompt = self._build_rating_prompt(turn_text, llm_response, signals, prev)

        try:
            from core.agent.llm_providers.base import GenerateRequest
            req = GenerateRequest(prompt=prompt, max_tokens=300, temperature=0.3)
            result = self._llm.generate(req)
            result_text = result.text if hasattr(result, 'text') else str(result)
            ratings = self._parse_ratings(result_text)
            self.profile.update(ratings)
            return {
                "dimensions": self.profile.dims,
                "this_turn": ratings,
                "mbti": self.profile.to_mbti(),
            }
        except Exception as e:
            logger.debug("OCEAN rating skipped: %s", e)
            return {"dimensions": prev, "error": str(e)[:100]}

    def _extract_signals(self, engine) -> Dict:
        if not hasattr(engine, '_trace_v3') or not engine._trace_v3:
            return {}
        m = engine._trace_v3.meta_analyze()
        rd = m.get("reason_distribution", {})
        return {"S": rd.get("strengthen", 0), "W": rd.get("weaken", 0),
                "R": rd.get("reject", 0), "conf": m.get("avg_confidence", 0.7)}

    def _build_rating_prompt(self, text: str, response: str, signals: Dict, prev: Dict) -> str:
        dim_desc = "\n  ".join(f"{k}: {v}" for k, v in DIMENSIONS.items())
        bfi_hint = ""
        if hasattr(self, '_last_bfi_scores'):
            bfi = self._last_bfi_scores
            bfi_hint = f"\nBFI-10 calibrated scores from validated instrument:\n  {json.dumps(bfi)}"
        return f"""You are a psychometric analyst. Rate this user on 10 dimensions using Chain-of-Thought.

DIMENSIONS:
  {dim_desc}

EVIDENCE FROM THIS TURN:
  User: "{text[:300]}"
  System replied: "{response[:200]}"
  Trace: S={signals.get('S',0)} W={signals.get('W',0)} R={signals.get('R',0)}
{bfi_hint}
Previous EMA estimates: {json.dumps({k: round(v,2) for k,v in prev.items()})}

STEP 1 — Extract evidence:
  For EACH dimension, quote a specific phrase or behavior from the user's text that supports your rating.
  If no evidence, say "insufficient data — use prior".

STEP 2 — Distinguish intent from style:
  - Topic flexibility ≠ low Conscientiousness (exploring ≠ undisciplined)
  - Critical questioning ≠ low Agreeableness (analytical ≠ hostile)
  - Meta-cognitive questions ≠ Neuroticism (self-awareness ≠ anxiety)
  - Short messages ≠ low Openness (concise ≠ uninterested)

STEP 3 — Rate each dimension 0-1:
  Respond with JSON ONLY after your reasoning:
{{"reasoning": "brief justification per dimension",
  "ratings": {{"O":0.5,"C":0.5,"E":0.5,"A":0.5,"N":0.5,"NC":0.5,"CS":0.5,"DK":0.5,"MS":0.5,"CL":0.5}}}}"""

    def _parse_ratings(self, text: str) -> Dict[str, float]:
        try:
            start = text.find('{')
            end = text.rfind('}') + 1
            if start < 0:
                return {}
            data = json.loads(text[start:end])
            # Handle both formats: {"ratings": {...}} or direct {...}
            raw = data.get("ratings", data)
            return {k: float(raw.get(k, 0.5)) for k in DIMENSIONS}
        except Exception:
            return {k: 0.5 for k in DIMENSIONS}

    def analyze_with_bfi_override(self, engine, turn_text: str, llm_response: str,
                                   bfi_scores: Dict = None) -> Dict[str, Any]:
        """OCEAN analysis with BFI-10 calibration.

        BFI corrects the per-turn rating BEFORE EMA, not after.
        divergence > 0.25 → BFI value wins as THIS turn's rating.
        EMA still smooths normally, just with corrected input.
        """
        result = self.analyze(engine, turn_text, llm_response)
        dims = result.get("this_turn", {})

        if bfi_scores:
            from core.agent.v4.cognitive.bfi_calibrator import bfi_to_ocean
            self._last_bfi_scores = bfi_scores
            overrides = 0
            corrected = dict(dims)
            for factor, score in bfi_scores.items():
                if factor in dims:
                    bfi_val = bfi_to_ocean(score, factor)
                    if abs(bfi_val - dims[factor]) > 0.25:
                        corrected[factor] = bfi_val  # BFI corrects this turn's rating
                        overrides += 1
            if overrides:
                # Re-apply EMA with corrected ratings
                self.profile.update(corrected)
                result["this_turn"] = corrected
                result["dimensions"] = dict(self.profile.dims)
                result["bfi_overrides"] = overrides

        return result

    def get_subgraph(self) -> List[str]:
        """Generate context subgraph from current profile."""
        p = self.profile
        top = p.top_dimensions(5)
        lines = [f"[PROFILE] MBTI≈{p.to_mbti()}"]
        for dim in top[:5]:
            v = p.dims[dim]
            direction = "↑" if v > 0.55 else "↓" if v < 0.45 else "→"
            lines.append(f"[{dim}{direction}] {v:.2f}")
        return lines

    # ── P11: analyst-level facade (CLI dead-command fixes) ─────────────

    def update_dimension(self, dim: str, value: float) -> Dict[str, Any]:
        """P11: directly set one OCEAN dimension (white-box edit, A19).

        CLI ``dm profile edit <dim> <value>`` lands here instead of the
        ``else: not available`` dead branch. The analyst owns the EMA
        profile, so the edit is applied to the live profile and persisted.
        """
        if dim not in DIMENSIONS:
            return {"error": f"unknown dimension: {dim}", "valid": list(DIMENSIONS)}
        self.profile.dims[dim] = max(0.0, min(1.0, float(value)))
        self.profile.turn_count += 1
        try:
            self.profile.save()
        except Exception:
            pass  # 无持久化路径时白盒编辑仍生效（A17 记录由调用方负责）
        return {"status": "updated", "dimension": dim, "value": self.profile.dims[dim]}

    def snapshot(self) -> Dict[str, Any]:
        """P11: full analyst snapshot for CLI ``dm profile traits``."""
        return {
            "dims": dict(self.profile.dims),
            "mbti": self.profile.to_mbti(),
            "turn_count": self.profile.turn_count,
            "top_dimensions": self.profile.top_dimensions(5),
            "history_len": len(self.profile.history),
        }

    def history(self, limit: int = 20) -> List[Dict]:
        """P11: recent per-turn rating history (white-box A19)."""
        return self.profile.history[-limit:] if self.profile.history else []

    def reset(self) -> Dict[str, Any]:
        """P11: reset the EMA profile back to neutral."""
        self.profile = OCEANProfile()
        try:
            self.profile.save()
        except Exception:
            pass
        return {"status": "reset"}

    def save(self) -> Dict[str, Any]:
        """P11: persist the live OCEAN profile (``OCEANProfile.save`` caller)."""
        try:
            self.profile.save()
            return {"status": "saved", "path": "data/profile/ocean_profile.json"}
        except Exception as e:
            return {"error": str(e)[:100]}
