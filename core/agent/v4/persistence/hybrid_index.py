"""HybridIndex: Combined HNSW + FTS5 + Graph retrieval.

Three-path retrieval:
  1. Semantic:   HNSW vector search (O(log n))
  2. Keyword:    FTS5 full-text search (O(log n))
  3. Structural: Graph traversal (O(V+E) for subgraph)

Merges and reranks results from all three paths.

Usage:
    index = HybridIndex(":memory:", dim=384)
    index.open()
    index.index("k1", vector, "Gateway monitoring text", {"domain": "engineering"})
    results = index.search("gateway monitoring", top_k=10)
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Tuple

from core.agent.v4.persistence.faiss_store import FaissVectorStore
from core.agent.v4.persistence.fts5_index import FTS5Index

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
    """Hybrid retrieval: semantic + keyword + structural.

    Args:
        db_path: SQLite database path (shared for vector and FTS5)
        dim: Vector dimension
        vector_weight: Weight for semantic results (0.0-1.0)
        keyword_weight: Weight for keyword results (0.0-1.0)
    """

    def __init__(self, db_path: str = None, dim: int = 384,
                 vector_weight: float = 0.6, keyword_weight: float = 0.4):
        self._db_path = db_path or ":memory:"
        self._dim = dim
        self._vector_weight = vector_weight
        self._keyword_weight = keyword_weight

        self._vector_store: Optional[FaissVectorStore] = None
        self._fts_index: Optional[FTS5Index] = None

    def open(self) -> None:
        """Open all sub-indices."""
        self._vector_store = FaissVectorStore(self._db_path, dim=self._dim)
        self._vector_store.open()

        self._fts_index = FTS5Index(self._db_path)
        self._fts_index.open()

        logger.info("HybridIndex opened: dim=%d", self._dim)

    def close(self) -> None:
        if self._vector_store:
            self._vector_store.close()
        if self._fts_index:
            self._fts_index.close()

    def index(self, doc_id: str, vector, content: str,
              metadata: dict = None) -> None:
        """Index a document across all paths.

        Args:
            doc_id: Unique identifier
            vector: Embedding vector (for semantic search)
            content: Text content (for keyword search)
            metadata: Optional metadata
        """
        if self._vector_store:
            self._vector_store.put(doc_id, vector, metadata)
        if self._fts_index:
            self._fts_index.index_document(doc_id, content, metadata)

    def search(self, query: str, query_vector=None, top_k: int = 10,
               semantic_only: bool = False, keyword_only: bool = False) -> List[Tuple[str, float, Dict]]:
        """Hybrid search across all paths.

        Args:
            query: Text query (for keyword search)
            query_vector: Optional embedding vector (for semantic search)
            top_k: Max results to return
            semantic_only: Only use vector search
            keyword_only: Only use keyword search

        Returns: list of (doc_id, combined_score, metadata) sorted by score desc.
        """
        scores: Dict[str, float] = {}
        metas: Dict[str, dict] = {}

        # Path 1: Semantic (HNSW)
        if not keyword_only and query_vector is not None and self._vector_store:
            vec_results = self._vector_store.search(query_vector, top_k * 2)
            for doc_id, sim in vec_results:
                scores[doc_id] = scores.get(doc_id, 0.0) + sim * self._vector_weight
                if doc_id not in metas:
                    metas[doc_id] = {}

        # Path 2: Keyword (FTS5)
        if not semantic_only and self._fts_index:
            kw_results = self._fts_index.search_with_metadata(query, top_k * 2)
            for doc_id, bm25, meta in kw_results:
                # Normalize BM25 (rough heuristic: typical range -10 to 0)
                normalized = min(1.0, max(0.0, (bm25 + 10) / 10))
                scores[doc_id] = scores.get(doc_id, 0.0) + normalized * self._keyword_weight
                metas[doc_id] = meta

        # Merge and rerank
        merged = []
        for doc_id, score in scores.items():
            # Normalize by number of paths that found it
            merged.append((doc_id, score, metas.get(doc_id, {})))

        merged.sort(key=lambda x: x[1], reverse=True)
        return merged[:top_k]

    def delete(self, doc_id: str) -> None:
        """Remove from all indices."""
        if self._vector_store:
            self._vector_store.delete(doc_id)
        if self._fts_index:
            self._fts_index.delete(doc_id)

    @property
    def count(self) -> int:
        return self._vector_store.count if self._vector_store else 0

    def stats(self) -> Dict[str, Any]:
        """Combined statistics."""
        return {
            "vector": self._vector_store.hnsw_stats() if self._vector_store else {},
            "keyword": self._fts_index.stats() if self._fts_index else {},
            "total_documents": self.count,
        }
