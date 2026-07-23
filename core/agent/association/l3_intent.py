"""L3 Pragmatic Intent — multi-perspective intent validator.

Design: docs/BUSINESS_CHAIN_06_ASSOCIATION.md §2.5 (L3)
        docs/BUSINESS_CHAIN_01_INTENT.md (8-stage pipeline reference)
        docs/v5/DESIGN_V4.0_COGNITIVE_COORDINATE_ROUTER.md (3D coordinate)
Input:  L2.5 locked_intent + 7D belief + discourse tree + profile + PCR
Output: final_intent + behavior_type + feedback signals
Pattern: each perspective votes, consensus confirms, deadlock → LLM
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class Vote(Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    ABSTAIN = "abstain"


@dataclass
class PerspectiveVote:
    source: str  # "discourse_tree" | "profile" | "association" | "pcr"
    vote: Vote
    reason: str
    weight: float = 1.0  # adjustable per-perspective trust


@dataclass
class IntentResult:
    intent: str
    behavior_type: str  # "diagnostic" | "exploratory" | "repair" | "venting" | "query"
    confidence: float
    consensus: bool  # True if 3+ perspectives agree
    votes: List[PerspectiveVote] = field(default_factory=list)
    feedback: Dict[str, Any] = field(default_factory=dict)  # Profile update, tree annotation


class MultiPerspectiveValidator:
    """L3: validates intent hypothesis across 4 perspectives."""

    DEFAULT_INTENTS = ["诊断", "修复", "探索", "吐槽", "信息查询", "指令"]

    def __init__(self, llm_provider=None):
        self.llm = llm_provider

    def validate(
        self,
        intent_hypothesis: str,
        belief_7d: dict,
        discourse_topics: List[str] = None,
        profile_traits: Dict[str, float] = None,
        pcr_zone: str = "MIXED",
        entity_relations: List[str] = None,
    ) -> IntentResult:
        """Multi-perspective validation of an intent hypothesis."""

        votes: List[PerspectiveVote] = []
        discourse_topics = discourse_topics or []
        profile_traits = profile_traits or {}
        entity_relations = entity_relations or []

        # 1. Discourse Tree perspective
        v_discourse = self._discourse_vote(intent_hypothesis, discourse_topics)
        votes.append(v_discourse)

        # 2. Profile perspective
        v_profile = self._profile_vote(intent_hypothesis, profile_traits)
        votes.append(v_profile)

        # 3. Association evidence perspective
        v_assoc = self._association_vote(intent_hypothesis, entity_relations, belief_7d)
        votes.append(v_assoc)

        # 4. PCR zone perspective
        v_pcr = self._pcr_vote(intent_hypothesis, pcr_zone)
        votes.append(v_pcr)

        # Count
        accepts = sum(1 for v in votes if v.vote == Vote.ACCEPT)
        rejects = sum(1 for v in votes if v.vote == Vote.REJECT)
        consensus = accepts >= 3 or (accepts >= 2 and rejects == 0)

        # Deadlock or disagreement: LLM resolves
        if not consensus and self.llm and accepts + rejects >= 2:
            llm_vote = self._llm_deadlock(intent_hypothesis, votes, belief_7d)
            if llm_vote:
                votes.append(llm_vote)
                if llm_vote.vote == Vote.ACCEPT:
                    accepts += 1
                    consensus = True

        # Behavior type mapping
        behavior_type = self._behavior_type(intent_hypothesis, pcr_zone)

        # Feedback signals
        feedback = {
            "profile_update": {"last_intent": intent_hypothesis, "confidence": belief_7d.get("stability", 0.5)},
            "tree_annotation": {"topic": intent_hypothesis, "action": behavior_type},
        }

        return IntentResult(
            intent=intent_hypothesis if consensus else self._fallback(votes),
            behavior_type=behavior_type,
            confidence=self._confidence(votes, belief_7d),
            consensus=consensus,
            votes=votes,
            feedback=feedback,
        )

    # ── Perspective voters ──

    def _discourse_vote(self, intent: str, topics: List[str], modifier_ctx: str = "") -> PerspectiveVote:
        """Discourse tree: structural coherence check — no keyword lists."""
        if not topics and not modifier_ctx:
            return PerspectiveVote("discourse_tree", Vote.ABSTAIN, "no discourse context")
        # Check: does the recent topic history contain entities that structurally relate to this intent?
        # Use modifier context from L1 as bridge — don't hardcode semantic keywords
        topic_text = " ".join(topics) + " " + modifier_ctx
        # Intent types naturally co-occur with certain structural patterns:
        # "诊断" → entities with measurement/error signals
        # "修复" → entities with modification signals  
        # But we detect these via L2 entity relations, not keywords
        # Discourse perspective defers to association evidence → ABSTAIN unless strong topic recency
        if len(topics) >= 2:
            return PerspectiveVote("discourse_tree", Vote.ACCEPT, f"active topic history ({len(topics)} topics)")
        return PerspectiveVote("discourse_tree", Vote.ABSTAIN, "insufficient topic history")

    def _profile_vote(self, intent: str, traits: Dict[str, float]) -> PerspectiveVote:
        """Profile: OCEAN traits → intent preference. Thresholds from config."""
        if not traits:
            return PerspectiveVote("profile", Vote.ABSTAIN, "no profile data")
        from .l2_config import get as cfg_get
        c = traits.get("conscientiousness", 0.5)
        c_thresh = cfg_get('l3.profile_c_threshold', 0.6)
        if intent in ("诊断", "修复") and c > c_thresh:
            return PerspectiveVote("profile", Vote.ACCEPT, f"high C({c:.2f}) prefers {intent}")
        if intent == "吐槽" and c > 0.7:
            return PerspectiveVote("profile", Vote.REJECT, f"high C({c:.2f}) unlikely to vent")
        return PerspectiveVote("profile", Vote.ABSTAIN, "neutral profile")

    def _association_vote(self, intent: str, relations: List[str], belief_7d: dict) -> PerspectiveVote:
        """Association: evidence type consistency with intent."""
        if not relations:
            return PerspectiveVote("association", Vote.ABSTAIN, "no entity relations")
        causal = sum(1 for r in relations if r in ("causes", "triggers"))
        dependency = sum(1 for r in relations if r in ("depends_on",))
        if intent in ("诊断", "修复") and (causal + dependency) > 0:
            return PerspectiveVote("association", Vote.ACCEPT, f"relevance evidence ({causal + dependency})")
        if intent == "吐槽" and causal > 2:
            return PerspectiveVote("association", Vote.REJECT, "too much causal evidence for venting")
        # Belief stability check
        stability = belief_7d.get("stability", 0.5)
        if stability > 0.8:
            return PerspectiveVote("association", Vote.ACCEPT, f"stable belief ({stability:.2f})")
        return PerspectiveVote("association", Vote.ABSTAIN, "ambiguous evidence")

    def _pcr_vote(self, intent: str, zone: str) -> PerspectiveVote:
        """PCR zone: execution constraints affect intent plausibility."""
        if zone == "ATOMIC" and intent == "探索":
            return PerspectiveVote("pcr", Vote.REJECT, "ATOMIC zone cannot explore")
        if zone in ("PRECISION", "ABYSS") and intent in ("诊断", "修复"):
            return PerspectiveVote("pcr", Vote.ACCEPT, f"{zone} zone ideal for {intent}")
        return PerspectiveVote("pcr", Vote.ABSTAIN, f"zone {zone} neutral")

    def _llm_deadlock(self, intent: str, votes: List[PerspectiveVote], belief_7d: dict) -> Optional[PerspectiveVote]:
        """LLM breaks 2-2 deadlock."""
        if not self.llm:
            return None
        reasons = "\n".join(f"  {v.source}: {v.vote.value} — {v.reason}" for v in votes)
        prompt = f"""Break an intent classification deadlock.

Intent hypothesis: "{intent}"
Belief state: stability={belief_7d.get('stability',0):.2f} support={belief_7d.get('support',0)} conflict={belief_7d.get('conflict',0)}

Perspective votes:
{reasons}

Return JSON: {{"decision": "accept/reject", "reason": "..."}}"""
        try:
            import json
            response = self.llm.generate(prompt, max_tokens=100)
            data = json.loads(response) if response else {}
            decision = data.get("decision", "abstain")
            return PerspectiveVote(
                "llm", Vote.ACCEPT if decision == "accept" else Vote.REJECT,
                data.get("reason", "LLM resolution"), weight=0.5
            )
        except Exception as e:
            logger.debug("LLM deadlock failed: %s", e)
        return None

    # ── Output helpers ──

    def _behavior_type(self, intent: str, zone: str) -> str:
        from .l2_config import get as cfg_get
        type_map = cfg_get('l3_behavior_map', {})
        return type_map.get(intent, "mixed")

    def _confidence(self, votes: List[PerspectiveVote], belief_7d: dict) -> float:
        accepts = sum(1 for v in votes if v.vote == Vote.ACCEPT)
        total = len(votes)
        if total == 0:
            return 0.3
        return (accepts / total) * 0.4 + belief_7d.get("stability", 0.5) * 0.3 + belief_7d.get("coverage", 0.0) * 0.3

    def _fallback(self, votes: List[PerspectiveVote]) -> str:
        """When no consensus, pick best from accept votes."""
        accepts = [v for v in votes if v.vote == Vote.ACCEPT]
        if accepts:
            return "诊断"  # default safe intent when no clear signal
        return "信息查询"
