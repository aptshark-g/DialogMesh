"""CoordinateRouter V4.0 — stanza STC (Y-axis) + BGE mood (Z-axis) + coordinate routing.

Wires all three axes via lightweight computation:
  X: cognitive distance (SVO heuristic, BGE pending)
  Y: operational granularity (stanza STC)
  Z: feedback expectation (BGE mood vectors)

Routes to 6-zone strategy via 3D coordinate space.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
import time, logging

logger = logging.getLogger(__name__)


@dataclass
class Route:
    zone: str = "MIXED"
    strategy: str = "balanced"
    llm: str = "primary"
    cost_ms: int = 300
    max_recursion: int = 1
    temperature: float = 0.3

    @classmethod
    def from_zone(cls, zone: str) -> "Route":
        return {
            "ATOMIC":    cls("ATOMIC", "cache_or_rule", "none", 0, 0),
            "ABYSS":     cls("ABYSS", "react_cot_full", "primary", 1000, 5),
            "PSYCHE":    cls("PSYCHE", "empathetic", "local_small", 100, 0, forbid_technical=True),
            "PRECISION": cls("PRECISION", "planner_agent", "primary", 400, 1, output_format="json_plan"),
            "EXPLORE":   cls("EXPLORE", "socratic", "primary", 200, 1, temperature=0.7),
            "MIXED":     cls("MIXED", "balanced", "primary", 300, 1, temperature=0.3),
        }.get(zone, cls())


class RouterV4:
    """V4.0 Cognitive Coordinate Router — 3D → zone → strategy."""

    def __init__(self, stanza_nlp=None, bge_model=None):
        self._nlp = stanza_nlp
        self._bge = bge_model
        self._mood_vecs = None
        self._mood_cats = None
        self._mood_zv = None
        self._load_mood_profiles()

    def _load_mood_profiles(self):
        import yaml, numpy as np
        try:
            config = yaml.safe_load(open('config/mood_profiles.yaml', encoding='utf-8'))
            descs, cats, zv = [], [], {}
            for cat, prof in config['profiles'].items():
                for d in prof['descriptors']: descs.append(d); cats.append(cat)
                zv[cat] = prof.get('z_value', 0.0)
            if self._bge:
                self._mood_vecs = np.array([self._bge.encode(d, normalize_embeddings=True) for d in descs])
                self._mood_cats = cats
                self._mood_zv = zv
                logger.info("Mood vectors: %d descriptors loaded", len(descs))
        except Exception as e:
            logger.warning("Mood profiles not loaded: %s", e)

    def route(self, text: str, kurtosis: float = 0.5, fatigue: float = 0.3) -> Tuple[dict, Route]:
        import numpy as np, re, math

        x = y = z = 0.0
        result = {"x": 0.0, "y": 0.0, "z": 0.0}

        # ── Y-axis: Stanza STC ──
        if self._nlp:
            try:
                doc = self._nlp(text)
                max_depth = coord_count = 0
                for sent in doc.sentences:
                    for w in sent.words:
                        if w.deprel in ('conj', 'cc', 'parataxis'): coord_count += 1
                        d = 1; cur = w
                        while cur.head > 0 and d < 50: d += 1; cur = sent.words[cur.head-1]
                        max_depth = max(max_depth, d)
                raw = min(max_depth/5, 1.5)*0.4 + min(coord_count/3, 1.5)*0.4
                y = round(1.0/(1.0+math.exp(-(raw-0.3)*4.0)), 3)
            except: pass
        result["y"] = y

        # ── Z-axis: BGE Mood Vectors ──
        if self._mood_vecs is not None and text.strip():
            try:
                v = self._bge.encode(text, normalize_embeddings=True)
                best = int(np.argmax(np.dot(self._mood_vecs, v)))
                z = self._mood_zv[self._mood_cats[best]]
            except: pass
        result["z"] = z

        # ── X-axis: simple heuristic (BGE pending) ──
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+|0x[0-9a-fA-F]+', text)
        if len(tokens) >= 2:
            x = 0.5 if tokens[0].lower() != tokens[-1].lower() else 0.3
        result["x"] = x

        # ── Zone routing ──
        zone = "MIXED"
        if z < -0.5: zone = "PSYCHE"
        elif x < 0.3 and y < 0.3: zone = "ATOMIC"
        elif x > 0.6 and y > 0.6 and z > 0.3: zone = "ABYSS"
        elif x < 0.5 and y > 0.4 and z > 0: zone = "PRECISION"
        elif x > 0.4 and y < 0.4 and z <= 0: zone = "EXPLORE"

        route = Route.from_zone(zone)
        result["zone"] = zone
        result["strategy"] = route.strategy
        result["cost_ms"] = route.cost_ms

        return result, route
