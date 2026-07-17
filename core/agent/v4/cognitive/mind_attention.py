"""AttentionPrior — learns user attention patterns across sessions.

Extracts from CognitiveProfile TrackA.attention_anchor:
which objects/concepts the user consistently focuses on.

Feeds back: on workspace init, pre-seeds Observer's attention weights
so the system "knows what the user cares about" from turn 1.
"""
from __future__ import annotations
import json, os
from collections import defaultdict
from typing import Dict, List


class AttentionPrior:
    """Cross-session attention accumulation.

    Each turn's attention_anchor (e.g., "Runtime:0.7") updates
    an EMA. After sessions, the top anchors become permanent priors.
    """

    def __init__(self, alpha: float = 0.15):
        self._anchors: Dict[str, float] = defaultdict(lambda: 0.5)  # start neutral
        self._alpha = alpha
        self._total_updates = 0

    def feed(self, attention_anchor: str, weight: float):
        """Update one attention anchor with EMA."""
        old = self._anchors[attention_anchor]
        self._anchors[attention_anchor] = old * (1 - self._alpha) + weight * self._alpha
        self._total_updates += 1

    def feed_profile(self, track_a) -> int:
        """Extract attention_anchor from TrackA dynamics."""
        anchor = getattr(track_a, 'attention_anchor', None)
        if anchor and isinstance(anchor, (int, float)):
            label = getattr(track_a, 'attention_label', 'general')
            self.feed(str(label), float(anchor))
            return 1
        return 0

    def top_anchors(self, top_k: int = 5) -> List[tuple]:
        """Top-K attention anchors (above neutral 0.5)."""
        active = {k: v for k, v in self._anchors.items() if v > 0.55}
        return sorted(active.items(), key=lambda x: x[1], reverse=True)[:top_k]

    def apply_to_observer(self, observer) -> int:
        """Seed observer's initial attention weights."""
        applied = 0
        for name, weight in self.top_anchors():
            try:
                observer.set_attention_weight(name, weight)
                applied += 1
            except Exception:
                pass
        return applied

    def save(self, path: str = "data/mind_attention.json"):
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({
                'anchors': dict(self._anchors),
                'updates': self._total_updates,
                'version': 1,
            }, f, indent=2, ensure_ascii=False)

    def load(self, path: str = "data/mind_attention.json") -> bool:
        if not os.path.exists(path):
            return False
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self._anchors = defaultdict(lambda: 0.5, data.get('anchors', {}))
        self._total_updates = data.get('updates', 0)
        return True


class MindAttention:
    """Top-level Mind component — attention learning + persistence."""

    def __init__(self, persist_path: str = "data/mind_attention.json"):
        self.prior = AttentionPrior()
        self._persist_path = persist_path

    def load(self) -> bool:
        return self.prior.load(self._persist_path)

    def learn(self, track_a) -> int:
        return self.prior.feed_profile(track_a)

    def apply(self, observer) -> int:
        return self.prior.apply_to_observer(observer)

    def save(self):
        self.prior.save(self._persist_path)

    def stats(self) -> dict:
        return {
            "total_updates": self.prior._total_updates,
            "top_anchors": self.prior.top_anchors(),
        }
