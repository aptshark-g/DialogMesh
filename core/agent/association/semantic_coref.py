"""Semantic coreference scoring via sentence-transformers — Tier 2.

Uses pretrained multilingual embeddings to score mention-pair coreference likelihood.
Model: paraphrase-multilingual-MiniLM-L12-v2 (118MB, supports CN+EN).
Zero hardcoded — similarity learned from pretraining data.

Dep: sentence-transformers (already in requirements.txt)
"""
from __future__ import annotations

import logging
from typing import List, Tuple, Optional

import numpy as np

logger = logging.getLogger("dm.semantic_coref")


class SemanticCorefScorer:
    """Embedding-based mention pair scoring.

    Encodes mentions in shared context, computes cosine similarity.
    Higher score = more likely to corefer.

    Uses paraphrase-multilingual-MiniLM-L12-v2:
      - 118MB model, 384-dim embeddings
      - Supports 50+ languages including CN+EN
      - ~50ms per pair encode on CPU
    """

    MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self):
        self._model = None
        self._available = False  # lazy — loaded on first use

    def _init_model(self) -> bool:
        try:
            # 2026-08-16: 离线优先（原联网 HF 校验, 网络受限无 CPU 挂起）
            import os
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                self.MODEL_NAME, local_files_only=True)
            logger.info("SemanticCoref: model loaded (%s)", self.MODEL_NAME)
            return True
        except ImportError:
            logger.info("SemanticCoref: sentence-transformers not installed")
            return False
        except Exception as e:
            logger.warning("SemanticCoref: model init failed (%s)", e)
            return False

    def score_pair(self, mention_a: str, mention_b: str,
                   context: str = "") -> float:
        """Score coreference likelihood between two mentions.

        Returns 0-1 cosine similarity. Higher = more likely same entity.
        """
        if not self._available:
            self._available = self._init_model()
        if not self._available:
            return 0.5  # neutral when model unavailable

        # Encode mentions with context for disambiguation
        emb_a = self._encode(f"{context} [SEP] {mention_a}")
        emb_b = self._encode(f"{context} [SEP] {mention_b}")
        return float(self._cosine(emb_a, emb_b))

    def score_batch(self, pairs: List[Tuple[str, str]],
                    context: str = "") -> List[float]:
        """Batch score multiple mention pairs."""
        if not self._available:
            return [0.5] * len(pairs)

        texts_a = [f"{context} [SEP] {a}" for a, _ in pairs]
        texts_b = [f"{context} [SEP] {b}" for _, b in pairs]

        embs_a = self._model.encode(texts_a, show_progress_bar=False)
        embs_b = self._model.encode(texts_b, show_progress_bar=False)

        return [float(self._cosine(embs_a[i], embs_b[i]))
                for i in range(len(pairs))]

    def _encode(self, text: str) -> np.ndarray:
        return self._model.encode([text], show_progress_bar=False)[0]

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        dot = np.dot(a, b)
        norm = np.linalg.norm(a) * np.linalg.norm(b)
        return max(0.0, min(1.0, dot / norm)) if norm > 0 else 0.5

    def is_available(self) -> bool:
        return self._available
