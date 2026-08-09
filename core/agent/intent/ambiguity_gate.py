"""AmbiguityGate + AmbiguityResolver — 5 triggers / 5-level resolution (D-11).

Design: ENGINEERING_MULTI_INTENT_SPLIT
  - AmbiguityGate 5 triggers: high entropy, low confidence, cross-chain
    disagreement, multi-intent conflict, clarification needed.
  - AmbiguityResolver 5 levels (cost-ascending):
      1. context inheritance (60-80%)
      2. behavior-chain inference (50-70%)
      3. profile inference (40-60%)
      4. LLM resolution (80-95%)
      5. ask_user (100%)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .models import AmbiguityDecision, SubIntent


@dataclass
class AmbiguitySignals:
    """Signals consumed by the gate — populated by the intent pipeline."""
    entropy: float = 0.0                # belief distribution entropy
    confidence: float = 1.0             # best hypothesis confidence
    chain_disagreement: float = 0.0     # 0..1 disagreement ratio
    multi_intent_conflict: bool = False # split candidates conflict
    needs_clarification: bool = False   # sub-intent explicitly ambiguous
    pcr_noise: float = 0.0              # PCR noise level


class AmbiguityGate:
    """Five-trigger gate → AmbiguityDecision (pass/auto_resolve/llm_resolve/ask_user)."""

    ENTROPY_THRESHOLD = 0.5
    CONFIDENCE_THRESHOLD = 0.4
    DISAGREEMENT_THRESHOLD = 0.5

    def evaluate(self, signals: AmbiguitySignals) -> AmbiguityDecision:
        triggers = []
        if signals.entropy > self.ENTROPY_THRESHOLD:
            triggers.append("high_entropy")
        if signals.confidence < self.CONFIDENCE_THRESHOLD:
            triggers.append("low_confidence")
        if signals.chain_disagreement > self.DISAGREEMENT_THRESHOLD:
            triggers.append("chain_disagreement")
        if signals.multi_intent_conflict:
            triggers.append("multi_intent_conflict")
        if signals.needs_clarification:
            triggers.append("needs_clarification")

        score = min(1.0, len(triggers) / 5.0 + signals.pcr_noise * 0.2)
        if not triggers:
            return AmbiguityDecision(trigger="", score=0.0, action="pass")
        if score < 0.4:
            action = "auto_resolve"
        elif score < 0.7:
            action = "llm_resolve"
        else:
            action = "ask_user"
        return AmbiguityDecision(
            trigger="+".join(triggers),
            score=round(score, 3),
            action=action,
            fallback="",
        )


class AmbiguityResolver:
    """Five-level cost-ascending resolution chain."""

    def __init__(self, llm=None, behavior=None, profile=None, history: List[str] = None):
        self.llm = llm
        self.behavior = behavior      # behavior-chain context (A→B sequences)
        self.profile = profile        # OCEAN profile / preferences
        self.history = history or []

    def resolve(self, text: str, decision: AmbiguityDecision,
                sub_intents: List[SubIntent] = None) -> dict:
        """Run resolution levels in ascending order; first confident hit wins."""
        if decision.action == "pass":
            return {"resolved": True, "method": "none", "confidence": 1.0, "answer": text}

        # Level 1: context inheritance (previous turn topic continues)
        if self.history:
            topic = str(self.history[-1])[:120]
            if topic and topic != text:
                return {"resolved": True, "method": "context_inheritance",
                        "confidence": 0.7, "answer": f"{topic} / {text}"}

        # Level 2: behavior-chain inference (recent A→B sequence)
        if self.behavior is not None:
            try:
                seq = getattr(self.behavior, "get_recent_chain", lambda n=5: [])()
                if seq:
                    return {"resolved": True, "method": "behavior_inference",
                            "confidence": 0.6, "answer": text}
            except Exception:
                pass

        # Level 3: profile inference
        if self.profile is not None:
            return {"resolved": True, "method": "profile_inference",
                    "confidence": 0.5, "answer": text}

        # Level 4: LLM resolution
        if self.llm:
            answer = self._llm_resolve(text, sub_intents)
            if answer:
                return {"resolved": True, "method": "llm", "confidence": 0.85,
                        "answer": answer}

        # Level 5: ask_user — cannot resolve internally.
        return {"resolved": False, "method": "ask_user", "confidence": 0.0,
                "answer": "", "question": f"想确认一下：你的意思是……（{text[:80]}）"}

    def _llm_resolve(self, text: str, sub_intents: List[SubIntent]) -> str:
        candidates = "\n".join(
            f"  {i + 1}. {s.text}" for i, s in enumerate(sub_intents or [])
        ) or "  (single)"
        prompt = (
            f"用户消息含歧义:\n{text[:300]}\n候选意图:\n{candidates}\n"
            "请给出最合理的单一理解，直接输出一句话。"
        )
        try:
            resp = self.llm.generate(prompt, max_tokens=200, temperature=0.2)
            return str(resp).strip()
        except Exception:
            return ""
