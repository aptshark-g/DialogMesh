"""HybridIndex: semantic + keyword dual-path retrieval with merge ranking.

Design (DESIGN_UNIFIED_PERSISTENCE.md §8.3):
    Path A (semantic): embedding cosine → top-K
    Path B (keyword):  BM25/exact match → top-K
    Merge: dedup → weighted rerank (semantic 0.7 + keyword 0.3) → top-K

Usage:
    index = HybridIndex(
        vector_store=tiered_store,
        keyword_index=keyword_index,  # e.g., SQLite FTS or simple inverted index
        semantic_weight=0.7,
        keyword_weight=0.3,
    )
    results = index.search("gateway cache", top_k=10)
"""
from __future__ import annotations
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Set

import numpy as np

from core.agent.v4.persistence.vector_store import VectorStore

logger = logging.getLogger(__name__)


class KeywordIndex:
    """Simple inverted index for keyword matching.

    Not a full BM25 — just term frequency scoring.
    For production, replace with SQLite FTS5 or whoosh.
    """

    def __init__(self):
        self._index: Dict[str, Set[str]] = {}  # term -> {doc_id}
        self._docs: Dict[str, str] = {}         # doc_id -> text

    def add(self, doc_id: str, text: str) -> None:
        """Add a document to the index."""
        self._docs[doc_id] = text.lower()
        terms = set(self._tokenize(text))
        for term in terms:
            self._index.setdefault(term, set()).add(doc_id)

    def remove(self, doc_id: str) -> None:
        """Remove a document from the index."""
        if doc_id not in self._docs:
            return
        text = self._docs.pop(doc_id)
        for term in self._tokenize(text):
            if term in self._index:
                self._index[term].discard(doc_id)

    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """Search by keyword matching. Returns (doc_id, score) pairs."""
        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        # Score by term frequency
        scores: Dict[str, float] = {}
        for term in query_terms:
            for doc_id in self._index.get(term, set()):
                scores[doc_id] = scores.get(doc_id, 0.0) + 1.0

        # Normalize by query length, then sort by score desc, then doc_id for stability
        results = [
            (doc_id, score / len(query_terms))
            for doc_id, score in scores.items()
        ]
        results.sort(key=lambda x: (-x[1], x[0]))
        return results[:top_k]

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Simple whitespace tokenization + lowercasing."""
        return text.lower().split()

    def __contains__(self, doc_id: str) -> bool:
        return doc_id in self._docs

    @property
    def doc_count(self) -> int:
        return len(self._docs)


class HybridIndex:
    """Hybrid retrieval: semantic + keyword with weighted merge.

    Args:
        vector_store: VectorStore for semantic search (required)
        keyword_index: KeywordIndex for keyword search (optional)
        embedder: Callable[[str], np.ndarray] — encodes query string to vector
        semantic_weight: Weight for semantic scores in merge (default 0.7)
        keyword_weight: Weight for keyword scores in merge (default 0.3)
        top_k_semantic: Number of semantic results to fetch (default 20)
        top_k_keyword: Number of keyword results to fetch (default 20)
    """

    def __init__(
        self,
        vector_store: VectorStore,
        embedder: Callable[[str], np.ndarray],
        keyword_index: Optional[KeywordIndex] = None,
        semantic_weight: float = 0.7,
        keyword_weight: float = 0.3,
        top_k_semantic: int = 20,
        top_k_keyword: int = 20,
    ):
        self._vector_store = vector_store
        self._embedder = embedder
        self._keyword_index = keyword_index or KeywordIndex()
        self._semantic_weight = semantic_weight
        self._keyword_weight = keyword_weight
        self._top_k_semantic = top_k_semantic
        self._top_k_keyword = top_k_keyword

    # ------------------------------------------------------------------ #
    # Core API
    # ------------------------------------------------------------------ #

    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """Hybrid search: semantic + keyword, merged and reranked.

        Returns:
            List of (doc_id, combined_score) sorted by score descending.
        """
        semantic_results = self._search_semantic(query)
        keyword_results = self._search_keyword(query)
        merged = self._merge(semantic_results, keyword_results)
        return merged[:top_k]

    def search_with_sources(
        self, query: str, top_k: int = 10
    ) -> List[Tuple[str, float, Dict[str, float]]]:
        """Hybrid search with per-source scores.

        Returns:
            List of (doc_id, combined_score, {source: score}) tuples.
        """
        semantic_results = self._search_semantic(query)
        keyword_results = self._search_keyword(query)
        merged = self._merge_with_sources(semantic_results, keyword_results)
        return merged[:top_k]

    # ------------------------------------------------------------------ #
    # Index management
    # ------------------------------------------------------------------ #

    def index_document(
        self, doc_id: str, text: str, vector: Optional[np.ndarray] = None
    ) -> None:
        """Index a document in both semantic and keyword indexes."""
        # Keyword index
        self._keyword_index.add(doc_id, text)

        # Vector store (if vector provided, else embed on the fly)
        if vector is not None:
            self._vector_store.put(doc_id, vector, metadata={"text": text})
        else:
            try:
                vec = self._embedder(text)
                self._vector_store.put(doc_id, vec, metadata={"text": text})
            except Exception as e:
                logger.warning("Failed to embed document %s: %s", doc_id, e)

    def remove_document(self, doc_id: str) -> None:
        """Remove a document from both indexes."""
        self._keyword_index.remove(doc_id)
        self._vector_store.delete(doc_id)

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _search_semantic(self, query: str) -> Dict[str, float]:
        """Semantic search path. Returns {doc_id: score}."""
        try:
            query_vec = self._embedder(query)
            if isinstance(query_vec, list):
                query_vec = np.array(query_vec)
            results = self._vector_store.search(query_vec, self._top_k_semantic)
            return {doc_id: float(score) for doc_id, score in results}
        except Exception as e:
            logger.warning("Semantic search failed: %s", e)
            return {}

    def _search_keyword(self, query: str) -> Dict[str, float]:
        """Keyword search path. Returns {doc_id: score}."""
        if self._keyword_index is None:
            return {}
        try:
            results = self._keyword_index.search(query, self._top_k_keyword)
            return {doc_id: float(score) for doc_id, score in results}
        except Exception as e:
            logger.warning("Keyword search failed: %s", e)
            return {}

    def _merge(
        self,
        semantic: Dict[str, float],
        keyword: Dict[str, float],
    ) -> List[Tuple[str, float]]:
        """Merge two result sets with weighted scores."""
        all_ids = set(semantic.keys()) | set(keyword.keys())
        merged = []
        for doc_id in all_ids:
            s_score = semantic.get(doc_id, 0.0)
            k_score = keyword.get(doc_id, 0.0)
            combined = (
                self._semantic_weight * s_score +
                self._keyword_weight * k_score
            )
            merged.append((doc_id, combined))
        merged.sort(key=lambda x: x[1], reverse=True)
        return merged

    def _merge_with_sources(
        self,
        semantic: Dict[str, float],
        keyword: Dict[str, float],
    ) -> List[Tuple[str, float, Dict[str, float]]]:
        """Merge with per-source score breakdown."""
        all_ids = set(semantic.keys()) | set(keyword.keys())
        merged = []
        for doc_id in all_ids:
            s_score = semantic.get(doc_id, 0.0)
            k_score = keyword.get(doc_id, 0.0)
            combined = (
                self._semantic_weight * s_score +
                self._keyword_weight * k_score
            )
            sources = {}
            if doc_id in semantic:
                sources["semantic"] = s_score
            if doc_id in keyword:
                sources["keyword"] = k_score
            merged.append((doc_id, combined, sources))
        merged.sort(key=lambda x: x[1], reverse=True)
        return merged

    # ------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------ #

    @property
    def vector_count(self) -> int:
        return self._vector_store.count

    @property
    def keyword_count(self) -> int:
        return self._keyword_index.doc_count
