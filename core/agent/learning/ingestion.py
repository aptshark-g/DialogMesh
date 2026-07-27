# -*- coding: utf-8 -*-
"""IngestionPipeline — search → fetch → embed → store in HybridIndex."""

from __future__ import annotations

import logging
import time
from typing import List, Dict, Optional

from core.agent.learning.source_registry import SourceRegistry
from core.agent.learning.content_fetcher import ContentFetcher
from core.agent.learning.embedder import Embedder
from core.agent.learning.credibility import CredibilityEvaluator

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Full learning ingestion pipeline.

    search → dedup → fetch top-N → embed → store in HybridIndex.
    """

    def __init__(self):
        self.registry = SourceRegistry.get()
        self.fetcher = ContentFetcher()
        self.embedder = Embedder()
        self.evaluator = CredibilityEvaluator()
        self._ingested_count = 0

    def run(self, query: str, max_results: int = 3,
            fetch_full: bool = True) -> List[Dict]:
        """Execute full ingestion pipeline.

        Args:
            query: search query
            max_results: number of results to fetch full text for
            fetch_full: if True, download + chunk + embed

        Returns:
            List of ingested items: {title, url, credibility, chunks, doc_id}
        """
        t0 = time.time()
        ingested = []

        # 1. Multi-source parallel search
        hits = self.registry.search_all(query, max_per_source=3, max_total=max_results * 3)
        if not hits:
            logger.info("Ingestion: no results for '%s'", query[:50])
            return []

        # 2. Score credibility for all hits (no full text yet)
        for h in hits:
            h["credibility"] = self.evaluator.evaluate(h)

        # Sort by credibility
        hits.sort(key=lambda h: h["credibility"], reverse=True)

        # 3. Fetch + embed top-N
        top_hits = hits[:max_results]
        for h in top_hits:
            if not fetch_full:
                ingested.append(h)
                continue

            url = h.get("url", "")
            if not url:
                continue

            ct, raw = self.fetcher.fetch(url)
            if not raw:
                h["content"] = ""
                h["chunks"] = []
                ingested.append(h)
                continue

            text = self.fetcher.extract_text(ct, raw)
            h["content"] = text[:2000]

            # Chunk + embed
            chunks = self.fetcher.chunk(text)
            h["chunks"] = chunks[:10]  # max 10 chunks

            # Embed only first chunk for storage (balance cost vs utility)
            if chunks:
                emb = self.embedder.embed(chunks[0])
                h["embedding"] = emb

            # Store in persistence
            try:
                doc_id = self._store_in_index(h, emb)
                h["doc_id"] = doc_id
            except Exception as e:
                logger.warning("Storage failed for %s: %s", url[:80], e)

            ingested.append(h)
            self._ingested_count += 1

        elapsed = (time.time() - t0) * 1000
        logger.info("Ingestion: %d/%d results, %d stored (%.0fms)",
                     len(ingested), len(hits), self._ingested_count, elapsed)
        return ingested

    def _store_in_index(self, hit: dict, embedding: Optional[List[float]]) -> Optional[str]:
        """Store hit in ChromaDB for external content.

        ChromaDB = external learning content (queryable, clusterable).
        HybridIndex = internal data (sessions, events, relations).
        """
        doc_id = str(abs(hash(hit.get("url", ""))) % (10 ** 9))

        # External content → ChromaDB
        try:
            from core.agent.learning.chroma_store import ChromaStore
            store = ChromaStore()
            if store.available:
                meta = {
                    "source_url": hit.get("url", ""),
                    "domain": self.evaluator._extract_domain(hit.get("url", "")),
                    "timestamp": hit.get("timestamp", time.time()),
                    "content_type": hit.get("source", "webpage"),
                    "title": hit.get("title", ""),
                    "credibility": hit.get("credibility", 0.5),
                }
                store.add(
                    doc_id=doc_id,
                    text=hit.get("content", hit.get("snippet", "")),
                    embedding=embedding or [0.0] * 768,
                    metadata=meta,
                )
                logger.debug("Stored in ChromaDB: %s", doc_id)
                return doc_id
        except ImportError:
            logger.debug("chromadb not installed")
        except Exception as e:
            logger.warning("ChromaDB store failed: %s", e)

        # Fallback: HybridIndex
        try:
            from core.agent.persistence.hybrid_index import HybridIndex
            idx = HybridIndex(db_path="data/learning_index.db")
            idx.index(
                doc_id=doc_id,
                vector=embedding or [0.0] * 768,
                content=hit.get("content", hit.get("snippet", "")),
                metadata={
                    "source_url": hit.get("url", ""),
                    "domain": self.evaluator._extract_domain(hit.get("url", "")),
                    "timestamp": hit.get("timestamp", time.time()),
                    "content_type": hit.get("source", "webpage"),
                    "title": hit.get("title", ""),
                    "credibility": hit.get("credibility", 0.5),
                },
            )
            return doc_id
        except ImportError:
            logger.debug("No persistence backend — skipping storage")
            return None

    @property
    def stats(self) -> dict:
        return {
            "ingested_total": self._ingested_count,
            "sources": self.registry.list_sources(),
        }
