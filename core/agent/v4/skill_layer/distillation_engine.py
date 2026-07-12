"""DistillationEngine: scan v4 storage for repeatable patterns -> SkillCandidates."""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from .models import CapabilityBlueprint, ActionNode, SkillBelief, SkillCandidate

logger = logging.getLogger(__name__)


class DistillationEngine:
    """Scan v4 data sources for repeatable patterns and convert to SkillCandidates."""

    def __init__(self, registry=None):
        self._registry = registry
        self._id_counter = 0

    def scan(self, constraint_store=None, knowledge_store=None,
             behavior_store=None, hypothesis_engine=None) -> List[SkillCandidate]:
        candidates: List[SkillCandidate] = []
        if constraint_store: candidates += self._cluster_constraints(constraint_store)
        if knowledge_store: candidates += self._cluster_knowledge(knowledge_store)
        if behavior_store: candidates += self._find_behavior_patterns(behavior_store)
        if hypothesis_engine: candidates += self._consensus_hypotheses(hypothesis_engine)
        return candidates

    # ?? constraint clustering ??????????????????????????????????

    def _cluster_constraints(self, store) -> List[SkillCandidate]:
        candidates: List[SkillCandidate] = []
        if not hasattr(store, "get_all"): return candidates
        constraints = store.get_all() or []
        if len(constraints) < 3: return candidates

        groups = self._group_by_overlap(constraints)
        for group in groups:
            if len(group) < self._p("skill.distill.min_knowledge_cluster", 3):
                continue
            refs = [c.get("id", c.get("constraint_id", "")) for c in group]
            action = ActionNode(action_id=f"constraint_{self._next_id()}",
                                action="apply_constraints", input_refs=refs)
            bp = CapabilityBlueprint(
                blueprint_id=f"bp_skill_{self._next_id()}",
                goal=f"Apply {len(group)} shared constraints",
                constraints=refs,
                action_graph=[action],
                domain="engineering",
            )
            belief = SkillBelief(support=len(group), generality=0.7,
                                 coverage=0.5, stability=0.8)
            candidates.append(SkillCandidate(
                candidate_id=f"c_skill_{self._next_id()}",
                blueprint=bp, belief=belief, source="internal",
                references=refs, domain="engineering",
            ))
        return candidates

    def _group_by_overlap(self, items) -> List[List[dict]]:
        threshold = self._p("skill.distill.min_constraint_overlap", 0.70)
        groups: List[List[dict]] = []
        used: set = set()
        for i, a in enumerate(items):
            if i in used: continue
            group = [a]
            for j, b in enumerate(items):
                if j <= i or j in used: continue
                if self._obj_overlap(self._get_objects(a), self._get_objects(b)) >= threshold:
                    group.append(b)
                    used.add(j)
            if len(group) >= 2:
                groups.append(group)
                used.add(i)
        return groups

    # ?? knowledge clustering ???????????????????????????????????

    def _cluster_knowledge(self, store) -> List[SkillCandidate]:
        candidates: List[SkillCandidate] = []
        if not hasattr(store, "get_by_domain"): return candidates
        kn_items = store.get_by_domain("") or []
        min_n = self._p("skill.distill.min_knowledge_cluster", 3)
        if len(kn_items) < min_n: return candidates

        groups = self._group_by_overlap(kn_items)
        for group in groups:
            if len(group) < min_n: continue
            refs = [k.get("id", k.get("knowledge_id", "")) for k in group]
            bp = CapabilityBlueprint(
                blueprint_id=f"bp_kn_{self._next_id()}",
                goal=f"Pattern from {len(group)} knowledge freezes",
                strategy_refs=refs, domain="engineering",
            )
            belief = SkillBelief(support=len(group), generality=0.65,
                                 coverage=0.4, stability=0.85)
            candidates.append(SkillCandidate(
                candidate_id=f"c_kn_{self._next_id()}",
                blueprint=bp, belief=belief, source="internal",
                references=refs, domain="engineering",
            ))
        return candidates

    # ?? behavior pattern detection ?????????????????????????????

    def _find_behavior_patterns(self, store) -> List[SkillCandidate]:
        candidates: List[SkillCandidate] = []
        if not hasattr(store, "get_sequences"): return candidates
        sequences = store.get_sequences() or []
        min_seq = self._p("skill.distill.min_behavior_sequence", 5)
        if len(sequences) < min_seq: return candidates

        # Detect repeated action sequences
        pattern_counts: Dict[str, int] = {}
        for seq in sequences:
            actions = tuple(seq.get("actions", []))
            if len(actions) >= 2:
                key = str(actions)
                pattern_counts[key] = pattern_counts.get(key, 0) + 1

        for key, count in pattern_counts.items():
            if count >= min_seq:
                import ast
                try: action_list = list(ast.literal_eval(key))
                except Exception: continue
                action_nodes = [ActionNode(action_id=f"bh_{self._next_id()}", action=a)
                                for a in action_list]
                bp = CapabilityBlueprint(
                    blueprint_id=f"bp_bh_{self._next_id()}",
                    goal=f"Behavior pattern ({count}x): {' -> '.join(action_list[:3])}",
                    action_graph=action_nodes, domain="behavior",
                )
                belief = SkillBelief(support=count, generality=0.6,
                                     coverage=0.3, stability=0.75)
                candidates.append(SkillCandidate(
                    candidate_id=f"c_bh_{self._next_id()}",
                    blueprint=bp, belief=belief, source="internal",
                    references=[], domain="behavior",
                ))
        return candidates

    # ?? hypothesis consensus ???????????????????????????????????

    def _consensus_hypotheses(self, engine) -> List[SkillCandidate]:
        candidates: List[SkillCandidate] = []
        if not hasattr(engine, "_hypotheses"): return candidates
        hypotheses = list(engine._hypotheses.values()) if engine._hypotheses else []
        if isinstance(hypotheses, dict): hypotheses = list(hypotheses.values())
        if not hypotheses: return candidates

        threshold = self._p("skill.distill.min_hypothesis_consensus", 0.75)
        for h in hypotheses:
            if not hasattr(h, "belief_state"): continue
            bs = h.belief_state
            support_ratio = bs.get("support", 0) / max(1, bs.get("support", 0) + bs.get("conflict", 0))
            consensus = len(getattr(h, "domain_signals", {}))
            if support_ratio >= threshold and consensus >= 2:
                action = ActionNode(
                    action_id=f"hyp_{self._next_id()}",
                    action="apply_hypothesis",
                    input_refs=[getattr(h, "hypothesis_id", "")],
                )
                bp = CapabilityBlueprint(
                    blueprint_id=f"bp_hyp_{self._next_id()}",
                    goal=f"Hypothesis: {getattr(h, 'statement', '')[:80]}",
                    action_graph=[action], domain=getattr(h, "domain", ""),
                )
                belief = SkillBelief(support=bs.get("support", 0), generality=0.8,
                                     coverage=support_ratio, stability=bs.get("stability", 0.8))
                candidates.append(SkillCandidate(
                    candidate_id=f"c_hyp_{self._next_id()}",
                    blueprint=bp, belief=belief, source="internal",
                    references=[getattr(h, "hypothesis_id", "")],
                    domain=getattr(h, "domain", ""),
                ))
        return candidates

    # ?? helpers ?????????????????????????????????????????????????

    def _next_id(self) -> int:
        self._id_counter += 1
        return self._id_counter

    @staticmethod
    def _obj_overlap(a: list, b: list) -> float:
        sa, sb = set(a), set(b)
        if not sa or not sb: return 0.0
        return len(sa & sb) / len(sa | sb)

    @staticmethod
    def _get_objects(item: dict) -> List[str]:
        for key in ("objects", "objects_ids", "targets"):
            v = item.get(key, [])
            if v: return v
        return []

    def _p(self, key: str, default: float) -> float:
        if self._registry:
            try: return self._registry.value(key)
            except Exception: pass
        return default
