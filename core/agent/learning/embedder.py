# -*- coding: utf-8 -*-
"""Embedder — LM Studio nomic-embed-text 768d vector embedding."""

from __future__ import annotations

import logging
import json
import urllib.request
import urllib.error
from typing import List, Optional

logger = logging.getLogger(__name__)

LM_STUDIO_URL = "http://localhost:1234/v1/embeddings"
MODEL_NAME = "nomic-embed-text"


class Embedder:
    """Text → 768d vector via LM Studio nomic-embed-text."""

    def __init__(self, base_url: str = LM_STUDIO_URL, model: str = MODEL_NAME):
        self.base_url = base_url
        self.model = model
        self._available = None

    @property
    def available(self) -> bool:
        if self._available is None:
            try:
                req = urllib.request.Request(
                    self.base_url,
                    data=json.dumps({"input": "test", "model": self.model}).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read())
                self._available = "data" in data and len(data["data"]) > 0
                logger.info("Embedder: %s available=%s", self.model, self._available)
            except Exception:
                self._available = False
                logger.warning("Embedder: %s unavailable", self.model)
        return self._available

    def embed(self, text: str) -> Optional[List[float]]:
        """Get embedding vector for text. Returns None on failure."""
        if not text or not self.available:
            return None
        try:
            body = {"input": text[:2000], "model": self.model}
            req = urllib.request.Request(
                self.base_url,
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            vec = data["data"][0]["embedding"]
            return vec
        except Exception as e:
            logger.warning("Embed failed: %s", e)
            return None

    def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Embed multiple texts in sequence. Returns list with None for failures."""
        results = []
        for text in texts:
            results.append(self.embed(text))
        n_success = sum(1 for r in results if r is not None)
        logger.debug("Embed batch: %d/%d succeeded", n_success, len(texts))
        return results
