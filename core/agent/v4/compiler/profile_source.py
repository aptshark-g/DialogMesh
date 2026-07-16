"""ProfileContextSource — injects CognitiveProfileV2 into Context IR.

Design ref: docs/v3.0/design_cognitive_profile_v2.md
Supports both old v3_2 CognitiveProfile and new v2 dual-track profile.
"""
from __future__ import annotations
from typing import List, Optional

from core.agent.v4.context.source import ContextSource, ContextItem
from core.agent.v4.cognitive.models import CognitiveProfileV2
from core.agent.v4.cognitive.convergence import ConvergenceEngine
from core.agent.v4.cognitive.fusion import FusionContext


class ProfileContextSource(ContextSource):
    """User cognitive profile for P (Profile) domain.

    Supports:
      - CognitiveProfileV2 (dual-track: Track A dynamics + Track B tags)
      - v3_2 CognitiveProfile (backward compatible: Big5 + expertise + preferences)
    """

    name = "profile"

    def __init__(self, profile=None):
        self._profile = profile
        self._engine: Optional[ConvergenceEngine] = None
        self._fusion = FusionContext()

    def set_engine(self, engine: ConvergenceEngine):
        self._engine = engine

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        items = []
        p = self._profile
        if p is None:
            return items

        # V2 dual-track profile
        if isinstance(p, CognitiveProfileV2):
            text = self._fusion.render(p, self._engine)
            if text:
                items.append(ContextItem(
                    source="profile",
                    content={"profile_v2": p, "track_a": p.track_a, "track_b": p.track_b},
                    text=text,
                    relevance=0.9,
                ))
            return items

        # Fallback: v3_2 CognitiveProfile
        return self._render_v3(p)

    def _render_v3(self, p) -> List[ContextItem]:
        items = []
        parts = ["[Cognitive Profile]"]
        expertise = getattr(p, 'expertise', {})
        if expertise:
            top = sorted(expertise.items(), key=lambda x: x[1], reverse=True)[:3]
            parts.append(f"  Expertise: {', '.join(f'{k}({v:.1f})' for k,v in top)}")
        traits = getattr(p, 'stable_traits', {})
        if traits:
            tl = [f"{k}={traits[k]:.1f}" for k in ['openness','conscientiousness','extraversion','agreeableness','neuroticism','risk_tolerance','technical_depth','verbosity'] if k in traits]
            if tl: parts.append(f"  Traits: {', '.join(tl[:6])}")
        meta = getattr(p, 'metacognition', 0)
        div = getattr(p, 'divergence', 0)
        conf = getattr(p, 'confidence', 0)
        parts.append(f"  Dynamics: metacog={meta:.1f} divergence={div:.1f} confidence={conf:.1f}")
        items.append(ContextItem(source="profile", content={"profile": p}, text="\n".join(parts), relevance=0.9))
        if div > 0.6:
            items.append(ContextItem(source="profile", content={"type":"hint"}, text="[Style Hint] High divergence — prefer exploratory responses", relevance=0.5))
        elif div < 0.2:
            items.append(ContextItem(source="profile", content={"type":"hint"}, text="[Style Hint] Low divergence — prefer focused answers", relevance=0.5))
        return items

    @property
    def profile(self):
        return self._profile

    def set_profile(self, profile):
        self._profile = profile
