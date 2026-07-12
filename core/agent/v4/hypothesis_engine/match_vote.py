"""MatchVoteEngine: Match Evidence to Hypotheses, cast Support/Conflict/Neutral votes."""
from __future__ import annotations
import logging
from typing import Dict, List, Optional

from .models import HypothesisNode, VoteRecord, ReasonSession

logger = logging.getLogger(__name__)

DEFAULT_SUPPORTING_PATTERNS: Dict[str, List[str]] = {
    "engineering": ["modify", "add", "reorder", "configure", "deploy"],
    "dialogue": ["ask", "request", "confirm", "clarify"],
    "behavior": ["drag", "click", "select", "hover", "double-click"],
}

DEFAULT_CONFLICTING_PATTERNS: Dict[str, List[str]] = {
    "engineering": ["revert", "rollback", "undo", "remove"],
    "dialogue": ["reject", "disagree", "wrong", "no"],
    "behavior": ["deselect", "cancel", "close", "dismiss"],
}


class MatchVoteEngine:
    """Match Evidence to Hypotheses, then cast discrete votes."""

    def __init__(self):
        self._hypotheses: Dict[str, HypothesisNode] = {}
        self._votes: List[VoteRecord] = []

    def register(self, hypothesis: HypothesisNode) -> None:
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis

    def unregister(self, hypothesis_id: str) -> None:
        self._hypotheses.pop(hypothesis_id, None)

    def process(self, evidence: dict, session: Optional[ReasonSession] = None) -> List[VoteRecord]:
        matched = self._match(evidence)
        votes: List[VoteRecord] = []
        for h in matched:
            v = self._vote(evidence, h)
            self._apply_vote(h, v)
            votes.append(v)
            if session is not None:
                session.votes.append(v)
        self._votes.extend(votes)
        return votes

    def _match(self, evidence: dict) -> List[HypothesisNode]:
        objs = evidence.get("objects", []) or []
        topic = evidence.get("topic", "")
        domain = evidence.get("domain", "")
        matched: List[HypothesisNode] = []
        for h in self._hypotheses.values():
            if h.status == "frozen":
                continue
            if objs and any(o in h.objects for o in objs):
                matched.append(h)
            elif topic and h.topic == topic:
                matched.append(h)
            elif domain and h.domain == domain:
                matched.append(h)
        return matched

    def _vote(self, evidence: dict, h: HypothesisNode) -> VoteRecord:
        desc = str(evidence.get("description", "")).lower()
        domain = evidence.get("domain", h.domain)
        patterns_sup = DEFAULT_SUPPORTING_PATTERNS.get(domain, [])
        patterns_con = DEFAULT_CONFLICTING_PATTERNS.get(domain, [])

        if any(p in desc for p in patterns_sup):
            vote_type = "support"
        elif any(p in desc for p in patterns_con):
            vote_type = "conflict"
        else:
            vote_type = "neutral"

        return VoteRecord(
            evidence_id=evidence.get("evidence_id", ""),
            hypothesis_id=h.hypothesis_id,
            vote=vote_type,
            domain=domain,
        )

    def _apply_vote(self, h: HypothesisNode, v: VoteRecord) -> None:
        import time
        bs = h.belief_state
        if v.vote == "support":
            bs["support"] += 1
            h.domain_signals[v.domain] = "support"
        elif v.vote == "conflict":
            bs["conflict"] += 1
        h.last_vote_at = time.time()

    @property
    def hypothesis_count(self) -> int:
        return len(self._hypotheses)

    @property
    def vote_count(self) -> int:
        return len(self._votes)
