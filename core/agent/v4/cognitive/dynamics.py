"""Track A — cognitive dynamics computation.

Design: docs/v3.0/design_cognitive_profile_v2.md §2.2
9 dimensions, each with a specific computation formula.
Updated via ConvergenceEngine EMA with dynamic alpha.

All functions accept (profile, observation_data) and return
computed values ∈ [0, 1] for EMA ingestion.
"""
from __future__ import annotations
import math
from typing import Dict, List
from collections import Counter


class DynamicsComputer:
    """Stateless computation functions for Track A dimensions."""

    @staticmethod
    def cognitive_inertia(last_style_scores: List[float]) -> float:
        """Pearson autocorrelation of style preference scores.

        style_scores: list of user response style scores (detail/precision/depth)
        Returns: correlation strength ∈ [0,1]
        """
        if len(last_style_scores) < 3:
            return 0.5
        n = len(last_style_scores)
        if n <= 1:
            return 0.5
        mean = sum(last_style_scores) / n
        if mean == 0:
            return 0.5
        num = sum((last_style_scores[i] - mean) * (last_style_scores[i-1] - mean)
                  for i in range(1, n))
        den = sum((x - mean) ** 2 for x in last_style_scores)
        if den == 0:
            return 0.5
        r = num / den
        return max(0.0, min(1.0, abs(r)))  # stability of style = |correlation|

    @staticmethod
    def behavior_inertia(accept: int, clarify: int, dispute: int) -> float:
        """Acceptance / total response rate to system suggestions.

        High = user tends to accept. Low = user tends to dispute/clarify.
        """
        total = accept + clarify + dispute
        if total == 0:
            return 0.5
        return accept / total

    @staticmethod
    def trust_score(commitments_fulfilled: int, total_commitments: int) -> float:
        """T(S,O): system commitment fulfillment rate."""
        if total_commitments == 0:
            return 0.5
        return commitments_fulfilled / total_commitments

    @staticmethod
    def emotional_entropy(recent_polarities: List[float]) -> float:
        """Shannon entropy of recent emotion polarities (bucketed into 5 bins).

        High entropy = diverse emotions. Low = monotone.
        Normalized to [0,1].
        """
        if not recent_polarities:
            return 0.5
        bins = [0] * 5  # [-1,-0.6], (-0.6,-0.2], (-0.2,0.2], (0.2,0.6], (0.6,1]
        for p in recent_polarities:
            if p <= -0.6:
                bins[0] += 1
            elif p <= -0.2:
                bins[1] += 1
            elif p <= 0.2:
                bins[2] += 1
            elif p <= 0.6:
                bins[3] += 1
            else:
                bins[4] += 1
        total = sum(bins)
        if total == 0:
            return 0.5
        entropy = 0.0
        for b in bins:
            if b > 0:
                p = b / total
                entropy -= p * math.log2(p)
        max_entropy = math.log2(5)  # ~2.32
        return min(1.0, entropy / max_entropy)

    @staticmethod
    def attention_anchor(topic_weights: Dict[str, float]) -> float:
        """Focus = max topic weight / total weight.

        High = focused on one topic. Low = scattered across many.
        """
        if not topic_weights:
            return 0.5
        total = sum(topic_weights.values())
        if total == 0:
            return 0.5
        return max(topic_weights.values()) / total

    @staticmethod
    def expectation_deviation(recent_satisfaction_deltas: List[float]) -> float:
        """Running average of (user_satisfaction - expected_satisfaction).

        Clamped and scaled to [0,1] where 0.5 = no deviation.
        """
        if not recent_satisfaction_deltas:
            return 0.0
        avg_dev = sum(recent_satisfaction_deltas) / len(recent_satisfaction_deltas)
        # Scale: deviation of ±1.0 → 0.0-1.0, center at 0.5
        return max(0.0, min(1.0, 0.5 + avg_dev * 0.5))

    @staticmethod
    def self_value_score(self_affirmation_count: int, total_turns: int) -> float:
        """Frequency of self-affirmation language (e.g., 'I did', 'I know').

        Scaled by log to dampen high frequencies.
        """
        if total_turns == 0:
            return 0.5
        ratio = self_affirmation_count / total_turns
        return min(1.0, ratio * math.log(1 + total_turns) * 0.5)

    @staticmethod
    def cognitive_resource(response_speed_sec: float,
                           response_length_chars: int,
                           query_complexity: float = 0.5) -> float:
        """Inferred user patience/bandwidth from response behavior.

        Fast short responses = low resource (rushed/impatient).
        Slow long responses = high resource (thoughtful/engaged).
        """
        # Response speed: 5s→1.0, 60s→0.2
        speed_score = max(0.1, min(1.0, 1.0 - (response_speed_sec - 5) / 60))
        # Length: 500 chars→1.0, 10 chars→0.1
        length_score = min(1.0, response_length_chars / 500.0)
        # Blend with query complexity
        return 0.4 * speed_score + 0.3 * length_score + 0.3 * query_complexity

    # ── Batch compute ──

    def compute_all(self, obs: dict) -> Dict[str, float]:
        """Compute all 9 dimensions from one observation dict.

        obs keys:
          style_scores, accept/clarify/dispute counts,
          commitments_fulfilled, total_commitments,
          recent_polarities, topic_weights,
          satisfaction_deltas, self_affirmation_count, total_turns,
          response_speed_sec, response_length_chars, query_complexity
        """
        return {
            "cognitive_inertia": self.cognitive_inertia(obs.get("style_scores", [])),
            "behavior_inertia": self.behavior_inertia(
                obs.get("accept", 0), obs.get("clarify", 0), obs.get("dispute", 0)),
            "trust_score": self.trust_score(
                obs.get("commitments_fulfilled", 0), obs.get("total_commitments", 0)),
            "emotional_entropy": self.emotional_entropy(obs.get("recent_polarities", [])),
            "attention_anchor": self.attention_anchor(obs.get("topic_weights", {})),
            "expectation_deviation": self.expectation_deviation(
                obs.get("satisfaction_deltas", [])),
            "self_value_score": self.self_value_score(
                obs.get("self_affirmation_count", 0), obs.get("total_turns", 1)),
            "cognitive_resource": self.cognitive_resource(
                obs.get("response_speed_sec", 30),
                obs.get("response_length_chars", 200),
                obs.get("query_complexity", 0.5)),
        }
