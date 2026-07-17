"""Mind — unified persistent cognitive structure.

Integrates RelationPrior + AttentionPrior + MistakeMemory into
a single interface that:
  1. Initializes Workspace with learned priors
  2. Learns from every turn's trace/profile/warnings
  3. Persists/loads all three components atomically
  4. Drives the Observer's starting state each session
"""
from __future__ import annotations
import json, os, time
from typing import Any, Dict, List, Optional

from core.agent.v4.cognitive.mind_relation import MindRelation
from core.agent.v4.cognitive.mind_attention import MindAttention
from core.agent.v4.cognitive.mind_mistakes import MindMistakes


class Mind:
    """Long-term cognitive structure surviving Workspace destruction.

    Mind is NOT a cache — it's a controller. It drives Workspace
    initialization, deciding what the system should pay attention to
    before any reasoning begins.

    State hierarchy (lifespan):
      Snapshot (seconds) → Workspace (conversation) → Mind (months) → Knowledge (forever)
    """

    def __init__(self, persist_dir: str = "data"):
        self.relations = MindRelation(persist_path=os.path.join(persist_dir, "mind_relation.json"))
        self.attention = MindAttention(persist_path=os.path.join(persist_dir, "mind_attention.json"))
        self.mistakes = MindMistakes(persist_path=os.path.join(persist_dir, "mind_mistakes.json"))
        self._persist_dir = persist_dir
        self._total_turns = 0

    # ── Lifecycle ──

    def load(self) -> bool:
        """Restore all three components from disk."""
        r = self.relations.load()
        a = self.attention.load()
        m = self.mistakes.load()
        return r or a or m  # True if ANY had data

    def save(self):
        """Persist all three components."""
        os.makedirs(self._persist_dir, exist_ok=True)
        self.relations.save()
        self.attention.save()
        self.mistakes.save()

    # ── Learning ──

    def learn(self, engine) -> int:
        """Learn from one turn's worth of engine state.

        Pulls from trace, profile, and MetaConsumer in one call.
        Returns total learned items.
        """
        learned = 0
        self._total_turns += 1

        # Relations from trace
        if hasattr(engine, '_trace_v3') and engine._trace_v3:
            transitions = engine._trace_v3.transitions
            self.relations.learn(transitions[-10:])
            if hasattr(engine, '_interaction_graph') and engine._interaction_graph:
                self.relations.apply(engine._interaction_graph)

        # Attention from profile
        if hasattr(engine, '_cognitive_profile') and engine._cognitive_profile:
            ta = engine._cognitive_profile.track_a
            learned += self.attention.learn(ta)

        # Mistakes from MetaConsumer
        if hasattr(engine, '_meta_consumer') and engine._meta_consumer:
            mc = engine._meta_consumer
            if hasattr(mc, '_last_advice') and mc._last_advice:
                advice = mc._last_advice
                warnings = advice.get("warnings", [])
                if warnings:
                    ctx = {
                        "perspective": getattr(getattr(engine, '_active_policy', None), 'perspective', '') or '',
                        "depth": getattr(getattr(engine, '_active_policy', None), 'depth_adjust', 0) or 0,
                    }
                    learned += self.mistakes.learn(warnings, advice.get("suggestions", []), ctx)
                    if hasattr(engine, '_active_policy') and engine._active_policy:
                        self.mistakes.apply(engine._active_policy, ctx)

        # Periodic save every 5 turns
        if self._total_turns % 5 == 0:
            self.save()

        return learned

    # ── Workspace Initialization ──

    def initialize_workspace(self, engine) -> dict:
        """Drive Workspace initialization with learned priors.

        Called at the start of each conversation session.
        Sets observer attention, relation priorities, and avoidance rules.
        """
        init = {
            "attention_prior": {},
            "relation_prior": [],
            "avoidance_rules": [],
        }

        # Seed Observer attention weights
        for name, weight in self.attention.prior.top_anchors():
            init["attention_prior"][name] = weight
            if hasattr(engine, '_cognitive_observer') and engine._cognitive_observer:
                try:
                    engine._cognitive_observer.set_attention_weight(name, weight)
                except Exception:
                    pass

        # Pre-activate high-priority relations
        if hasattr(engine, '_interaction_graph') and engine._interaction_graph:
            n = self.relations.apply(engine._interaction_graph)
            init["relation_prior"] = self.relations.stats().get("top_5", [])

        # Apply avoidance rules to default policy
        init["avoidance_rules"] = list(self.mistakes.memory._avoidance_rules.values())

        return init

    def stats(self) -> dict:
        """Aggregate statistics across all three components."""
        return {
            "turns": self._total_turns,
            "relations": self.relations.stats(),
            "attention": self.attention.stats(),
            "mistakes": self.mistakes.stats(),
        }
