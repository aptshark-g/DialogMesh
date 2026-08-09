"""Multi-Intent Splitter — LLM-first coordinator.

Agent-native: LLM decides split points. Algorithms only provide struct hints.

R3 (2026-08-03): Step 2 no longer trusts the LLM blindly. Each candidate
segment is verified across 5 chains (literal/profile/association/discourse/
engineering), fused by FusionDecider, and ambiguity-gated by AmbiguityGate.
Without an LLM, the splitter degrades explicitly to the structural path
(logged, never silent).
"""

from __future__ import annotations
import logging
from typing import List, Optional
from .models import (
    SubIntent, MultiIntentResult, ChainVote, ChainVotes, VerifyContext,
    AmbiguityDecision,
)
from .literal_chain import LiteralChainVerifier
from .fusion_decider import FusionDecider
from .ambiguity_gate import AmbiguityGate, AmbiguitySignals

logger = logging.getLogger(__name__)


# PCR zone → complexity/noise priors (tunable, A18 parameter registry).
# Zone is a 3D coordinate label; we map it to the two scalar signals the
# fusion/ambiguity layers consume. Defaults are neutral unless evidence
# exists; adjust via l2_config later.
ZONE_COMPLEXITY = {
    "ABYSS": 0.85, "PRECISION": 0.75, "ATOMIC": 0.5,
    "PSYCHE": 0.35, "MIXED": 0.5, "": 0.5,
}
ZONE_NOISE = {
    "ABYSS": 0.8, "PRECISION": 0.6, "ATOMIC": 0.4,
    "PSYCHE": 0.3, "MIXED": 0.5, "": 0.5,
}


class MultiIntentSplitter:
    """LLM-first multi-intent decomposer.

    Pi-like: LLM makes all intent decisions. Hints are optional context.
    """

    def __init__(self, llm=None, profile=None, association=None,
                 discourse=None, engineering=None):
        self.llm = llm
        self.literal = LiteralChainVerifier(llm=llm)
        self._profile = profile
        self._association = association
        self._discourse = discourse
        self._engineering = engineering

    def split(self, text: str, entities: List[str] = None,
              pcr_zone: str = "MIXED", history: List[str] = None) -> MultiIntentResult:
        """LLM-first split, then 5-chain verification + fusion + ambiguity gate.

        R3 pipeline:
          Step 1: LLM (or structural fallback) decides multi-intent segments.
          Step 2: each candidate verified by 5 chains (literal via LLM; the
                  rest are zero-cost algorithm chains), fused by FusionDecider.
          Step 3: AmbiguityGate evaluates aggregate signals → upgrade path.

        Without an LLM the splitter logs the degradation and falls back to
        the structural path (single segment, explicit trace), never silently
        returning an unverified multi-split.
        """
        entities = entities or []
        history = history or []

        # Step 1: LLM decides if multi-intent (not algorithm)
        if self.llm:
            segments = self._llm_split(text, history)
        else:
            logger.warning(
                "MultiIntentSplitter: no LLM — structural-only fallback, "
                "T1 verification skipped (degraded, not silent)"
            )
            segments = self._structural_split(text)

        if not segments or len(segments) <= 1:
            return MultiIntentResult(
                sub_intents=[SubIntent(id="s0", text=text, entities=entities, confidence=1.0)],
                is_multi=False, split_confidence=1.0, fusion_method="single",
                trace={"degraded": self.llm is None},
            )

        # No LLM → structural split is the terminal result. 5-chain
        # verification needs an LLM to adjudicate; without one, every chain
        # abstains and fusion would reject everything. Return the structural
        # segments explicitly marked degraded (never silently).
        if self.llm is None:
            return MultiIntentResult(
                sub_intents=[
                    SubIntent(id=f"s{i}", text=seg, entities=entities[:3], confidence=0.5)
                    for i, seg in enumerate(segments)
                ],
                is_multi=len(segments) > 1,
                split_confidence=0.5,
                fusion_method="structural",
                trace={"segments": segments, "degraded": True},
            )

        # Step 2: 5-chain verification per candidate, fused by FusionDecider.
        pcr_complexity = ZONE_COMPLEXITY.get(pcr_zone or "", 0.5)
        pcr_noise = ZONE_NOISE.get(pcr_zone or "", 0.5)
        context = VerifyContext(
            profile=getattr(self, "_profile", None),
            association=getattr(self, "_association", None),
            discourse=getattr(self, "_discourse", None),
            literal=text,  # original text → literal chain treats each candidate as a fragment
            engineering=getattr(self, "_engineering", None),
            history=history,
        )

        decider = FusionDecider(llm=self.llm)
        gate = AmbiguityGate()
        accepted: List[SubIntent] = []
        ambiguities: List[AmbiguityDecision] = []
        all_votes: List[ChainVote] = []

        for i, seg in enumerate(segments):
            candidate = SubIntent(
                id=f"s{i}", text=seg, entities=entities[:3], confidence=0.85,
            )
            votes = self._verify_candidate(candidate, context)
            all_votes.extend(v for v in votes.votes.values())
            result = decider.decide(
                candidate, votes,
                pcr_complexity=pcr_complexity, pcr_noise=pcr_noise,
            )
            if result.sub_intents:
                accepted.extend(result.sub_intents)

        # Step 3: ambiguity gate on aggregate chain signals.
        if all_votes:
            signals = self._aggregate_ambiguity_signals(
                all_votes, accepted, pcr_noise, context
            )
            gate_decision = gate.evaluate(signals)
            if gate_decision.action != "pass":
                ambiguities.append(gate_decision)
                if gate_decision.action == "ask_user" and accepted:
                    accepted[0].needs_clarification = True
                    accepted[0].clarification_question = (
                        "你的消息可能包含多个意图，需要确认一下主次。"
                    )

        return MultiIntentResult(
            sub_intents=accepted,
            is_multi=len(accepted) > 1,
            split_confidence=sum(c.confidence for c in accepted) / max(1, len(accepted)),
            fusion_method=result.fusion_method if accepted else "rejected_all",
            ambiguities=ambiguities,
            trace={
                "segments": segments,
                "accepted": len(accepted),
                "rejected": len(segments) - len(accepted),
                "degraded": self.llm is None,
            },
        )

    def _verify_candidate(self, candidate: SubIntent, context: VerifyContext) -> ChainVotes:
        """Run 5 chains for one candidate. Literal is LLM-driven; the rest are
        zero-cost algorithm chains (R3: algorithm gives hints, LLM decides)."""
        votes = ChainVotes()
        votes.votes["literal"] = self.literal.verify(candidate, context)
        votes.votes["profile"] = self._profile_chain(candidate, context)
        votes.votes["association"] = self._association_chain(candidate, context)
        votes.votes["discourse"] = self._discourse_chain(candidate, context)
        votes.votes["engineering"] = self._engineering_chain(candidate, context)
        return votes

    def _profile_chain(self, candidate: SubIntent, context: VerifyContext) -> ChainVote:
        """Algorithm chain: OCEAN C/O → structured/exploratory split preference."""
        profile = context.profile
        if profile is None:
            return ChainVote(chain="profile", confidence=0.5, decision="pass",
                             reason="profile: no profile data")
        dims = getattr(profile, "dims", {}) or {}
        c = float(dims.get("C", 0.5))
        o = float(dims.get("O", 0.5))
        if c > 0.6:
            return ChainVote(chain="profile", confidence=min(1.0, c),
                             decision="accept",
                             reason=f"profile: high C({c:.2f}) favors structured multi-request")
        if o > 0.7:
            return ChainVote(chain="profile", confidence=min(1.0, o),
                             decision="accept",
                             reason=f"profile: high O({o:.2f}) favors exploratory multi-intent")
        return ChainVote(chain="profile", confidence=0.5, decision="pass",
                         reason="profile: neutral traits")

    def _association_chain(self, candidate: SubIntent, context: VerifyContext) -> ChainVote:
        """Algorithm chain: candidate entities across domains → separate intent."""
        assoc = context.association
        if not assoc or not isinstance(assoc, dict):
            return ChainVote(chain="association", confidence=0.5, decision="pass",
                             reason="association: no substrate data")
        known = set(str(e).lower() for e in (assoc.get("entities") or []))
        cand = set(str(e).lower() for e in (candidate.entities or []))
        if not known or not cand:
            return ChainVote(chain="association", confidence=0.5, decision="pass",
                             reason="association: no entity overlap data")
        overlap = len(known & cand)
        if overlap == 0 and cand:
            return ChainVote(chain="association", confidence=0.65, decision="accept",
                             reason="association: candidate entities outside known cluster")
        return ChainVote(chain="association", confidence=0.5, decision="pass",
                         reason="association: entities within known cluster")

    def _discourse_chain(self, candidate: SubIntent, context: VerifyContext) -> ChainVote:
        """Algorithm chain: candidate topic vs recent history → new thread?"""
        history = context.history or []
        if not history:
            return ChainVote(chain="discourse", confidence=0.5, decision="pass",
                             reason="discourse: no history")
        import re
        cand_tokens = {t for t in re.split(r"\W+", candidate.text.lower()) if len(t) >= 2}
        last = str(history[-1])[:200].lower()
        overlap = sum(1 for t in cand_tokens if t in last)
        if cand_tokens and overlap == 0:
            return ChainVote(chain="discourse", confidence=0.6, decision="accept",
                             reason="discourse: candidate is a new thread")
        return ChainVote(chain="discourse", confidence=0.5, decision="pass",
                         reason="discourse: follows recent topic")

    def _engineering_chain(self, candidate: SubIntent, context: VerifyContext) -> ChainVote:
        """Interface chain: EngineeringContext is nullable; abstain until wired."""
        eng = context.engineering
        if eng is None:
            return ChainVote(chain="engineering", confidence=0.5, decision="pass",
                             reason="engineering: context not wired")
        return ChainVote(chain="engineering", confidence=0.5, decision="pass",
                         reason="engineering: interface present, no constraints")

    def _aggregate_ambiguity_signals(
        self, votes: List[ChainVote], accepted: List[SubIntent],
        pcr_noise: float, context: VerifyContext,
    ) -> AmbiguitySignals:
        """Aggregate per-chain votes into AmbiguityGate inputs."""
        import math
        n = len(votes)
        accepts = sum(1 for v in votes if v.decision == "accept")
        rejects = sum(1 for v in votes if v.decision == "reject")
        confidences = [v.confidence for v in votes]
        avg_conf = sum(confidences) / n if n else 1.0
        # Entropy of accept/reject/pass distribution — 0 = deterministic.
        counts = [accepts, rejects, n - accepts - rejects]
        entropy = 0.0
        for c in counts:
            if c > 0:
                p = c / n
                entropy -= p * math.log2(p)
        max_entropy = math.log2(3) if n else 1.0
        norm_entropy = entropy / max_entropy if max_entropy else 0.0
        disagreement = (rejects / n) if n else 0.0
        needs_clarification = bool(
            accepted and accepted[0].needs_clarification
        )
        return AmbiguitySignals(
            entropy=round(norm_entropy, 3),
            confidence=round(avg_conf, 3),
            chain_disagreement=round(disagreement, 3),
            multi_intent_conflict=len(accepted) > 1,
            needs_clarification=needs_clarification,
            pcr_noise=pcr_noise,
        )

    def _llm_split(self, text: str, history: List[str]) -> List[str]:
        """LLM decides: where to split the text into sub-intents."""
        hist_str = "\n".join(f"  {h}" for h in history[-3:]) if history else "(none)"

        prompt = f"""You are a conversation agent. Analyze this user message and determine if it contains multiple independent intents that should be handled separately.

USER: "{text[:500]}"
RECENT HISTORY: {hist_str}

If this is a SINGLE intent, output: {{"multi": false}}
If MULTIPLE intents, output: {{"multi": true, "segments": ["first sub-intent", "second sub-intent", ...]}}

Rules:
- Split when the user asks for different things (e.g. "first X then Y", "X and also Y")
- Split when there's a clear causal/logical boundary between clauses
- Don't split trivial adjuncts (e.g. "帮我看看这个问题" is one intent)
- A true multi-intent has different goals/actions/entities per segment"""

        try:
            import json, re
            response = self.llm.generate(prompt, max_tokens=300, temperature=0.1)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(response))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            data = json.loads(cleaned)
            if data.get("multi"):
                segs = data.get("segments", [])
                return [s.strip() for s in segs if s.strip()]
            return [text]
        except Exception:
            return self._structural_split(text) or [text]

    def _structural_split(self, text: str) -> List[str]:
        """Minimal structural split — zero hardcoded keywords.

        Uses Stanza dependency parse to find clause boundaries.
        Falls back to sentence boundaries.
        """
        # Try Stanza clause detection
        segs = self.literal._stanza_segment(text)
        if segs:
            return segs

        # Fallback: split on Chinese/English punctuation boundaries
        import re
        clauses = re.split(r'[，,；;。！!？?]', text)
        clauses = [c.strip() for c in clauses if len(c.strip()) > 2]

        # If only 1-2 clauses, it's probably single-intent
        if len(clauses) <= 2:
            return [text]

        return clauses
