"""Fusion layer — combines Track A + Track B into structured LLM context.

Design: docs/v3.0/design_cognitive_profile_v2.md §2.1 (Fusion Layer)
  Track A provides dynamic weights → Track B provides prior anchors → LLM input
"""
from __future__ import annotations
from typing import Dict, List

from .models import CognitiveProfileV2
from .convergence import ConvergenceEngine


class FusionContext:
    """Renders CognitiveProfileV2 into ContextItem text blocks."""

    @staticmethod
    def render_track_a(dynamics, engine: ConvergenceEngine = None) -> str:
        """Render Track A dynamics as structured text."""
        d = dynamics
        parts = ["[User Cognitive Profile — Track A]"]

        # Core values
        parts.append(f"  Inertia: cog={d.cognitive_inertia:.2f} bhv={d.behavior_inertia:.2f}")
        parts.append(f"  Trust={d.trust_score:.2f} | Emotion-entropy={d.emotional_entropy:.2f}")
        parts.append(f"  Attention-anchor={d.attention_anchor:.2f} | Expect-deviation={d.expectation_deviation:.2f}")
        parts.append(f"  Memory-points={d.memory_point_count} | Self-value={d.self_value_score:.2f}")
        parts.append(f"  Cog-resource={d.cognitive_resource:.2f}")

        # Stability info
        if d.observation_count > 0:
            parts.append(f"  Observations={d.observation_count} | "
                        f"Stability={d.stability:.3f} | "
                        f"Frozen={'/'.join(d.frozen_dimensions) if d.frozen_dimensions else 'none'}")

        # Behavioral hints for LLM
        if d.cognitive_inertia > 0.7:
            parts.append("  [Hint] High cognitive inertia — user prefers consistent style")
        if d.behavior_inertia < 0.3:
            parts.append("  [Hint] Low behavior inertia — expect questions/clarifications")
        if d.trust_score < 0.3:
            parts.append("  [Hint] Low trust — provide evidence/reasoning, avoid direct suggestions")
        if d.emotional_entropy > 0.7:
            parts.append("  [Hint] High emotional diversity — user may be in exploratory mode")
        if d.cognitive_resource < 0.3:
            parts.append("  [Hint] Low cognitive resource — keep responses concise and direct")

        # Convergence stats
        if engine:
            stats = engine.stats()
            parts.append(f"  [Convergence] α={stats['alpha']:.3f} frozen={stats['frozen']}")

        return "\n".join(parts)

    @staticmethod
    def render_track_b(tags: Dict[str, any]) -> str:
        """Render Track B tags as structured text."""
        if not tags:
            return "[Tags — Track B]\n  (no tags yet)"

        parts = ["[Tags — Track B]"]
        # Sort by confidence
        sorted_tags = sorted(tags.values(), key=lambda t: (t.get('confidence', getattr(t, 'confidence', 0.5)) if isinstance(t, dict) else t.confidence), reverse=True)
        for tag in sorted_tags[:10]:
            if isinstance(tag, dict):
                name = tag.get('name', '?')
                val = tag.get('value', tag.get('confidence', 0.5))
                conf = tag.get('confidence', 0.5)
                src = tag.get('source', '?')
            else:
                name = tag.name; val = tag.value; conf = tag.confidence; src = tag.source
            conf_bar = "█" * int(conf * 10) + "░" * (10 - int(conf * 10))
            parts.append(f"  {name}: {val} |{conf_bar}| {conf:.2f} ({src})")

        return "\n".join(parts)

    @staticmethod
    def render_style_hints(dynamics) -> str:
        """Generate LLM response style hints from dynamics."""
        hints = []
        d = dynamics

        if d.divergence if hasattr(d, 'divergence') else d.emotional_entropy > 0.6:
            hints.append("Prefer broad, exploratory responses with multiple options")
        elif hasattr(d, 'divergence') and d.divergence < 0.2:
            hints.append("Prefer focused, deep, single-topic responses")

        if d.cognitive_resource < 0.3:
            hints.append("Keep responses short and structured (user has limited bandwidth)")

        if d.trust_score > 0.7:
            hints.append("High trust — can make direct recommendations without heavy justification")

        if not hints:
            return ""
        return "[Style Hints]\n" + "\n".join(f"  • {h}" for h in hints)

    def render(self, profile: CognitiveProfileV2,
               engine: ConvergenceEngine = None) -> str:
        """Full fusion: Track A + Track B + Style hints."""
        sections = [
            self.render_track_a(profile.track_a, engine),
            self.render_track_b(profile.track_b),
            self.render_style_hints(profile.track_a),
        ]
        return "\n".join(s for s in sections if s)
