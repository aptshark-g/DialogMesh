"""PatternLearner — accumulates trace patterns and learns effective responses.

Learns: "When we see pattern X, policy Y has effectiveness Z"
This replaces static if-else rules with learned pattern→response mappings.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import time, hashlib


@dataclass
class Pattern:
    """A learned trace pattern with associated policy response."""

    id: str = ""
    description: str = ""                     # human-readable pattern name
    occurrence_count: int = 0
    last_seen: float = 0.0

    # ── Associated policy ──
    best_policy_response: Dict[str, Any] = field(default_factory=dict)
    policy_effectiveness: float = 0.5         # how well the policy worked

    # ── Learning ──
    policy_trials: int = 0                    # total policy applications
    policy_successes: int = 0                 # times policy improved situation


class PatternLearner:
    """Learns which ReasoningPolicy responses work for which trace patterns.

    Usage:
        learner = PatternLearner()
        # After detecting a pattern and applying a policy:
        pattern_id = learner.register_pattern("连续REJECT", trace)
        learner.record_outcome(pattern_id, policy, successful=True)
        # Later:
        policy = learner.suggest_policy(pattern_id)
    """

    def __init__(self, max_patterns: int = 50):
        self._patterns: Dict[str, Pattern] = {}
        self._max_patterns = max_patterns

    def register_pattern(
        self,
        description: str,
        meta_advice: Dict[str, Any],
    ) -> str:
        """Register a newly detected pattern. Returns pattern_id."""
        key = hashlib.md5(description.encode()).hexdigest()[:10]

        if key in self._patterns:
            p = self._patterns[key]
            p.occurrence_count += 1
            p.last_seen = time.time()
        else:
            self._evict_oldest()
            self._patterns[key] = Pattern(
                id=key,
                description=description,
                occurrence_count=1,
                last_seen=time.time(),
            )
        return key

    def record_outcome(
        self,
        pattern_id: str,
        policy: Any,           # ReasoningPolicy
        successful: bool,
        effectiveness_delta: float = 0.0,
    ):
        """Record whether a policy response worked for this pattern."""
        p = self._patterns.get(pattern_id)
        if p is None:
            return

        p.policy_trials += 1
        if successful:
            p.policy_successes += 1

        # EMA update effectiveness
        alpha = 0.2
        p.policy_effectiveness = (
            (1 - alpha) * p.policy_effectiveness + alpha * (1.0 if successful else 0.2)
        )

        # Store best policy
        if successful and policy and hasattr(policy, '__dict__'):
            p.best_policy_response = {
                "perspective": getattr(policy, 'perspective', None),
                "explanation_mode": getattr(policy, 'explanation_mode', None),
                "depth_adjust": getattr(policy, 'depth_adjust', 0),
                "focus_objects": getattr(policy, 'focus_objects', []),
            }

    def suggest_policy(self, pattern_id: str) -> Optional[Dict[str, Any]]:
        """Suggest a policy response for a known pattern."""
        p = self._patterns.get(pattern_id)
        if p is None or p.policy_trials < 2:
            return None
        if p.policy_effectiveness > 0.5:
            return p.best_policy_response
        return None

    def get_patterns_for_current_context(
        self,
        meta_advice: Dict[str, Any],
        similarity_threshold: float = 0.6,
    ) -> List[Tuple[str, Pattern]]:
        """Find similar historical patterns for the current context."""
        warnings = meta_advice.get("warnings", [])
        matches = []
        for pid, p in self._patterns.items():
            # Simple keyword overlap matching
            desc_words = set(p.description.lower().split())
            warn_words = set(" ".join(warnings).lower().split())
            if desc_words and warn_words:
                overlap = len(desc_words & warn_words) / max(1, len(desc_words | warn_words))
                if overlap > similarity_threshold:
                    matches.append((pid, p))
        return sorted(matches, key=lambda x: x[1].policy_effectiveness, reverse=True)

    def stats(self) -> Dict[str, Any]:
        return {
            "total_patterns": len(self._patterns),
            "learned_patterns": sum(1 for p in self._patterns.values() if p.policy_trials > 0),
            "avg_effectiveness": sum(p.policy_effectiveness for p in self._patterns.values()) / max(1, len(self._patterns)),
            "most_common": max(self._patterns.values(), key=lambda p: p.occurrence_count).description if self._patterns else "none",
        }

    def _evict_oldest(self):
        if len(self._patterns) >= self._max_patterns:
            oldest = min(self._patterns.values(), key=lambda p: p.last_seen)
            del self._patterns[oldest.id]
