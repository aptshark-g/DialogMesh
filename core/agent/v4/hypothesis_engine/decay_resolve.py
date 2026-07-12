"""DecayResolveEngine: time decay + resolve (freeze/merge/stale)."""
from __future__ import annotations
import logging
import time
from typing import Dict, List, Optional

from .models import HypothesisNode, KnowledgeNode

logger = logging.getLogger(__name__)


class DecayResolveEngine:
    """Periodic decay of BeliefState and resolve of Hypothesis status."""

    def __init__(self):
        self._hypotheses: Dict[str, HypothesisNode] = {}
        self._knowledge: List[KnowledgeNode] = []

    def register(self, hypothesis: HypothesisNode) -> None:
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis

    def decay_all(self, now: float = 0.0, half_life_days: float = 7.0) -> int:
        t = now or time.time()
        count = 0
        for h in self._hypotheses.values():
            if h.status == "frozen":
                continue
            bs = h.belief_state
            age = (t - (h.last_vote_at or h.created_at)) / 86400.0
            factor = 2.0 ** (-age / half_life_days)
            bs["support"] = int(bs["support"] * factor)
            bs["conflict"] = int(bs["conflict"] * factor)
            bs["recency"] = max(0.0, bs["recency"] - age * 0.1)
            count += 1
        return count

    def resolve(self, params: dict = None) -> Dict[str, list]:
        p = params or {}
        result = {"frozen": [], "merged": [], "stale": []}

        for h in list(self._hypotheses.values()):
            if h.status == "frozen":
                continue

            # Freeze
            if h.should_freeze(p):
                h.status = "frozen"
                kn = KnowledgeNode(
                    knowledge_id=f"kn_{h.hypothesis_id}",
                    hypothesis_ref=h.hypothesis_id,
                    statement=h.statement,
                    domain=h.domain,
                    belief_score=h.belief_score(p),
                    belief_snapshot=dict(h.belief_state),
                )
                self._knowledge.append(kn)
                result["frozen"].append(kn.knowledge_id)

            # Stale: very low support + very old
            elif h.belief_state["support"] <= 1 and h.belief_state["recency"] < 0.1:
                h.status = "stale"
                result["stale"].append(h.hypothesis_id)

        return result

    def merge_candidates(self, threshold: float = 0.9) -> List[dict]:
        """Find pairs of hypotheses with highly overlapping statements for merging."""
        active = [h for h in self._hypotheses.values() if h.status == "active"]
        merged: List[dict] = []
        seen: set = set()
        for i, a in enumerate(active):
            if a.hypothesis_id in seen:
                continue
            for b in active[i + 1:]:
                if b.hypothesis_id in seen:
                    continue
                overlap = self._obj_overlap(a.objects, b.objects)
                if overlap >= threshold:
                    if a.belief_state["support"] >= b.belief_state["support"]:
                        b.status = "stale"
                        b.merged_into = a.hypothesis_id
                        seen.add(b.hypothesis_id)
                        merged.append({"from": b.hypothesis_id, "to": a.hypothesis_id, "overlap": overlap})
                    else:
                        a.status = "stale"
                        a.merged_into = b.hypothesis_id
                        seen.add(a.hypothesis_id)
                        merged.append({"from": a.hypothesis_id, "to": b.hypothesis_id, "overlap": overlap})
        return merged

    def compute_support_score(self, a: HypothesisNode, b: HypothesisNode, params: dict = None) -> float:
        """Compute reference-based support between two hypotheses (Phase 4)."""
        p = params or {}
        shared_obj = len(set(a.objects) & set(b.objects))
        total_obj = len(set(a.objects) | set(b.objects)) or 1
        shared_ref = self._count_shared_references(a, b)
        return (
            (shared_obj / total_obj) * p.get("ref_weight_object", 0.30)
            + shared_ref * p.get("ref_weight_constraint", 0.40)
        )

    @staticmethod
    def _obj_overlap(a: list[str], b: list[str]) -> float:
        sa, sb = set(a), set(b)
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    @staticmethod
    def _count_shared_references(a: HypothesisNode, b: HypothesisNode) -> int:
        refs_a = {e.target_id for e in a.edges if e.type == "references"}
        refs_b = {e.target_id for e in b.edges if e.type == "references"}
        return len(refs_a & refs_b)

    @property
    def knowledge_count(self) -> int:
        return len(self._knowledge)

    @property
    def hypothesis_count(self) -> int:
        return len(self._hypotheses)
