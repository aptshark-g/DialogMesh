"""Mood Classifier V2 — soft-coded BGE vector library, zero hardcoded keywords.

Replaces: MoodClassifier V1 (hardcoded Chinese/English word lists)
Design:   config/mood_profiles.yaml → BGE embeddings → cosine nearest-neighbor

Add new mood categories by editing mood_profiles.yaml — no code change needed.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import yaml
import logging

logger = logging.getLogger(__name__)


class MoodVectorLibrary:
    """Mood classification via BGE descriptor vector matching.

    Loads mood_profiles.yaml, encodes descriptors into BGE vectors,
    classifies input text by cosine nearest-neighbor to mood categories.
    """

    def __init__(self, config_path: Optional[str] = None):
        self._config_path = config_path or str(
            Path(__file__).parent.parent.parent.parent / "config" / "mood_profiles.yaml"
        )
        self._profiles: Dict[str, dict] = {}
        self._descriptors: List[str] = []
        self._categories: List[str] = []
        self._z_values: Dict[str, float] = {}
        self._bge = None
        self._descriptor_vectors = None  # (N, 768) numpy array when BGE loaded
        self._load_config()

    def _load_config(self):
        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
        except Exception:
            logger.warning("mood_profiles.yaml not found, using empty library")
            return

        self._profiles = config.get("profiles", {})
        for category, profile in self._profiles.items():
            for desc in profile.get("descriptors", []):
                self._descriptors.append(desc)
                self._categories.append(category)
            self._z_values[category] = profile.get("z_value", 0.0)

    def load_bge(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        """Lazy-load BGE model for vector matching."""
        try:
            from sentence_transformers import SentenceTransformer
            self._bge = SentenceTransformer(model_name)
            self._build_vectors()
            logger.info("MoodVectorLibrary: BGE loaded, %d descriptors", len(self._descriptors))
        except Exception as e:
            logger.warning("BGE not available, falling back to descriptor text matching: %s", e)

    def _build_vectors(self):
        import numpy as np
        if not self._bge or not self._descriptors:
            return
        self._descriptor_vectors = np.array([
            self._bge.encode(d, normalize_embeddings=True)
            for d in self._descriptors
        ])

    def classify(self, text: str, has_question: bool = False,
                 has_imperative: bool = False) -> float:
        """Classify text → Z-axis value via BGE cosine nearest-neighbor.

        Returns: Z value (float) in [-1, 1] range.
        """
        if not text or not text.strip():
            return 0.0

        # BGE path: encode → cosine → nearest category
        if self._bge and self._descriptor_vectors is not None:
            import numpy as np
            text_vec = self._bge.encode(text, normalize_embeddings=True)
            similarities = np.dot(self._descriptor_vectors, text_vec)
            best_idx = int(np.argmax(similarities))
            best_category = self._categories[best_idx]
            return self._z_values.get(best_category, 0.0)

        # Fallback: simple descriptor text overlap (still config-driven)
        return self._fallback_classify(text, has_question, has_imperative)

    def _fallback_classify(self, text: str, has_question: bool,
                           has_imperative: bool) -> float:
        """Text overlap fallback — driven by mood_profiles.yaml descriptors."""
        text_lower = text.lower()
        best_score = 0.0
        best_category = "neutral"

        for category, profile in self._profiles.items():
            score = 0.0
            for desc in profile.get("descriptors", []):
                desc_lower = desc.lower()
                # Simple word overlap between input and descriptor
                desc_words = set(desc_lower.split())
                text_words = set(text_lower.split())
                overlap = len(desc_words & text_words) / max(len(desc_words), 1)
                score += overlap
            score /= max(len(profile.get("descriptors", [])), 1)
            if score > best_score:
                best_score = score
                best_category = category

        # Syntactic signals as secondary input
        z = self._z_values.get(best_category, 0.0)

        # Adjust by syntactic mood (secondary, not primary)
        if has_question and best_category == "neutral":
            z += 0.1
        if has_imperative and z >= 0:
            z = max(z, 0.3)

        return max(-1.0, min(1.0, z))

    @property
    def categories(self) -> List[str]:
        return list(self._profiles.keys())
