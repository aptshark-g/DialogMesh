"""MindRelation — learns which relations increase confidence.

Extracts from ExecutionTrace transitions: when edge (A→B) is present
and confidence increases, that edge gets a priority boost.

Feeds back: on workspace init, high-priority edges are pre-activated
in InteractionGraph, guiding the Observer's initial attention.
"""
from __future__ import annotations
import json, os
from collections import defaultdict
from typing import Dict, List, Tuple

from core.agent.v4.state.state_object import TransitionReason


class RelationPrior:
    """Learned priority: (source, relation_type, target) → score.

    High score = this relation, when activated, consistently leads
    to confidence gains in subsequent transitions.
    """

    def __init__(self):
        self._scores: Dict[Tuple[str, str, str], float] = defaultdict(float)
        self._observation_count: Dict[Tuple[str, str, str], int] = defaultdict(int)

    def learn_from_trace(self, transitions: list) -> int:
        """Extract relation→confidence patterns from trace transitions.

        For each INFER and STRENGTHEN transition, check if
        prior ACTIVATE or OBSERVE transitions mention relation edges.
        If confidence increased, boost those edges.

        Returns: number of edges learned this cycle.
        """
        learned = 0
        confidence_trend = 0.5  # running EMA

        for i, t in enumerate(transitions):
            reason = getattr(t, 'reason', '')
            evidence = getattr(t, 'evidence', [])

            # Track confidence trend
            conf = getattr(t, 'confidence', 0.5)
            confidence_trend = 0.7 * confidence_trend + 0.3 * conf

            # ACTIVE/CONTAINS/DEPENDS_ON edges from evidence
            if reason in (TransitionReason.OBSERVE, TransitionReason.ACTIVATE):
                for ev in (evidence or []):
                    if isinstance(ev, str) and '→' in ev:
                        # Parse "Runtime→Scheduler" pattern
                        parts = ev.split('→')
                        if len(parts) == 2:
                            source, target = parts[0].strip(), parts[1].strip()
                            edge_key = (source, 'relates_to', target)
                            self._observation_count[edge_key] += 1

            # If confidence rose after edge activation, boost
            if reason in (TransitionReason.INFER, TransitionReason.STRENGTHEN):
                if conf > confidence_trend - 0.05:  # confidence increasing
                    # Boost all recently observed edges
                    for ek, count in list(self._observation_count.items()):
                        if count > 0:
                            alpha = 0.3 / max(1, count)  # decay with repetition
                            self._scores[ek] = self._scores[ek] * (1 - alpha) + 0.7 * alpha
                            learned += 1
                            self._observation_count[ek] = 0  # reset counter

        return learned

    def learn_from_profile(self, track_a, track_b_tags: list) -> int:
        """Boost relations mentioned in profile tags.

        TrackB tags like 'prefers_architecture' or 'likes_relations'
        indicate user's preferred relation patterns.
        """
        learned = 0
        tag_to_relation = {
            'prefers_architecture': ('architecture', 'contains'),
            'likes_relations': ('relation_substrate', 'depends_on'),
            'bottom_up': ('observer', 'activates'),
            'deep_dive': ('workspace', 'expands'),
        }
        for tag in track_b_tags:
            if tag in tag_to_relation:
                source, rtype = tag_to_relation[tag]
                ek = (source, rtype, '*')
                self._scores[ek] = max(self._scores[ek], 0.6)
                learned += 1
        return learned

    def best_relations(self, top_k: int = 5) -> List[Tuple[str, str, str, float]]:
        """Top-K highest priority relations."""
        sorted_items = sorted(self._scores.items(), key=lambda x: x[1], reverse=True)
        return [(s, r, t, sc) for (s, r, t), sc in sorted_items[:top_k] if sc > 0.3]

    def apply_to_graph(self, interaction_graph) -> int:
        """Pre-activate high-priority edges in InteractionGraph."""
        applied = 0
        for source, rtype, target, score in self.best_relations():
            if score < 0.4:
                continue
            try:
                from core.agent.v4.state.interaction_graph import InteractionType
                itype = {
                    'contains': InteractionType.CONTAINS,
                    'depends_on': InteractionType.DEPENDS_ON,
                    'causal': InteractionType.CAUSAL,
                    'supports': InteractionType.SUPPORTS,
                }.get(rtype, InteractionType.RELATES_TO)
                interaction_graph.add_edge(source, target if target != '*' else 'any', itype, score)
                applied += 1
            except Exception:
                pass
        return applied

    def save(self, path: str = "data/mind_relation.json"):
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        data = {
            'scores': {f"{s}|{r}|{t}": sc for (s, r, t), sc in self._scores.items()},
            'version': 1,
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load(self, path: str = "data/mind_relation.json") -> bool:
        if not os.path.exists(path):
            return False
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for key, score in data.get('scores', {}).items():
            parts = key.split('|')
            if len(parts) == 3:
                self._scores[(parts[0], parts[1], parts[2])] = score
        return True


class MindRelation:
    """Top-level Mind component — relation learning + persistence.

    Usage:
        mind = MindRelation()
        mind.load()  # restore from previous sessions
        # ... per turn ...
        mind.learn(engine._trace_v3.transitions)
        # ... every 5 turns ...
        mind.apply(engine._interaction_graph)
        mind.save()
    """

    def __init__(self, persist_path: str = "data/mind_relation.json"):
        self.prior = RelationPrior()
        self._persist_path = persist_path
        self._total_learned = 0

    def load(self) -> bool:
        return self.prior.load(self._persist_path)

    def learn(self, trace_transitions: list, profile_track_a=None, profile_tags: list = None) -> int:
        n = self.prior.learn_from_trace(trace_transitions)
        if profile_tags:
            n += self.prior.learn_from_profile(profile_track_a, profile_tags)
        self._total_learned += n
        return n

    def apply(self, interaction_graph) -> int:
        return self.prior.apply_to_graph(interaction_graph)

    def save(self):
        self.prior.save(self._persist_path)

    def stats(self) -> dict:
        return {
            "total_learned": self._total_learned,
            "active_relations": len([s for s in self.prior._scores.values() if s > 0.3]),
            "top_5": self.prior.best_relations(5),
        }
