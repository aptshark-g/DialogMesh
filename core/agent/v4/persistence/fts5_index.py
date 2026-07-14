"""FTS5Index: SQLite FTS5 full-text search for keyword retrieval.

Replaces linear keyword matching with O(log n) inverted index search.
Built on SQLite FTS5 (no external dependencies).

Usage:
    fts = FTS5Index(":memory:")
    fts.open()
    fts.index_document("k1", "Gateway needs monitoring", metadata={"domain": "engineering"})
    fts.index_document("k2", "RateLimiter is middleware", metadata={"domain": "engineering"})
    results = fts.search("gateway monitoring", top_k=10)
    # -> [("k1", 2.5), ("k2", 0.8), ...]
"""
from __future__ import annotations
import json, sqlite3, time, logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class FTS5Index:
    """SQLite FTS5 full-text search index.

    Complexity: O(log n) via FTS5 inverted index
    Storage: SQLite (FTS5 virtual table)
    """

    def __init__(self, db_path: str = None):
        self._db_path = db_path or ":memory:"
        self._conn: Optional[sqlite3.Connection] = None
        self._count = 0

    def open(self) -> None:
        """Open database and create FTS5 virtual table."""
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")

        # FTS5 virtual table for full-text search
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_docs USING fts5(
                doc_id,
                content,
                metadata,
                tokenize='porter unicode61'
            )
        """)

        # Auxiliary table for metadata lookup
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS doc_metadata (
                doc_id TEXT PRIMARY KEY,
                metadata_json TEXT,
                indexed_at REAL
            )
        """)

        self._conn.commit()

        # Count
        row = self._conn.execute("SELECT COUNT(*) FROM fts_docs").fetchone()
        self._count = row[0] if row else 0
        logger.info("FTS5Index opened: %d documents", self._count)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def index_document(self, doc_id: str, content: str,
                       metadata: dict = None) -> None:
        """Index a document for keyword search.

        Args:
            doc_id: Unique document identifier
            content: Text content to index
            metadata: Optional metadata dict
        """
        meta_json = json.dumps(metadata, ensure_ascii=False) if metadata else "{}"

        # Delete existing
        self._conn.execute("DELETE FROM fts_docs WHERE doc_id=?", (doc_id,))
        self._conn.execute("DELETE FROM doc_metadata WHERE doc_id=?", (doc_id,))

        # Insert into FTS5
        self._conn.execute(
            "INSERT INTO fts_docs (doc_id, content, metadata) VALUES (?, ?, ?)",
            (doc_id, content, meta_json),
        )

        # Insert metadata
        self._conn.execute(
            "INSERT INTO doc_metadata (doc_id, metadata_json, indexed_at) VALUES (?, ?, ?)",
            (doc_id, meta_json, time.time()),
        )

        self._conn.commit()
        self._count += 1

    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """Search documents by keyword query.

        Uses FTS5 BM25 ranking for relevance scoring.

        Returns: list of (doc_id, bm25_score) sorted by score desc.
        """
        if not query.strip():
            return []

        # FTS5 query syntax: use AND for multi-word
        # Escape quotes to prevent syntax errors
        safe_query = query.replace('"', '""')

        try:
            rows = self._conn.execute(
                """SELECT doc_id, bm25(fts_docs) as score
                   FROM fts_docs
                   WHERE fts_docs MATCH ?
                   ORDER BY score DESC
                   LIMIT ?""",
                (safe_query, top_k),
            ).fetchall()
        except sqlite3.OperationalError:
            # FTS5 syntax error — fallback to simple OR query
            words = safe_query.split()
            or_query = " OR ".join(words)
            rows = self._conn.execute(
                """SELECT doc_id, bm25(fts_docs) as score
                   FROM fts_docs
                   WHERE fts_docs MATCH ?
                   ORDER BY score DESC
                   LIMIT ?""",
                (or_query, top_k),
            ).fetchall()

        return [(doc_id, float(score)) for doc_id, score in rows]

    def search_with_metadata(self, query: str, top_k: int = 10) -> List[Tuple[str, float, dict]]:
        """Search with metadata included.

        Returns: list of (doc_id, bm25_score, metadata_dict)
        """
        results = self.search(query, top_k)
        enriched = []
        for doc_id, score in results:
            row = self._conn.execute(
                "SELECT metadata_json FROM doc_metadata WHERE doc_id=?",
                (doc_id,),
            ).fetchone()
            meta = json.loads(row[0]) if row and row[0] else {}
            enriched.append((doc_id, score, meta))
        return enriched

    def delete(self, doc_id: str) -> None:
        """Remove a document from the index."""
        self._conn.execute("DELETE FROM fts_docs WHERE doc_id=?", (doc_id,))
        self._conn.execute("DELETE FROM doc_metadata WHERE doc_id=?", (doc_id,))
        self._conn.commit()
        self._count = max(0, self._count - 1)

    def get(self, doc_id: str) -> Optional[Tuple[str, dict]]:
        """Get document content and metadata by ID."""
        row = self._conn.execute(
            "SELECT content, metadata FROM fts_docs WHERE doc_id=?", (doc_id,)
        ).fetchone()
        if row is None:
            return None
        content, meta_json = row
        metadata = json.loads(meta_json) if meta_json else {}
        return (content, metadata)

    @property
    def count(self) -> int:
        return self._count

    def stats(self) -> Dict[str, Any]:
        """Index statistics."""
        vocab = self._conn.execute(
            "SELECT COUNT(*) FROM fts_docs_vocab"
        ).fetchone()[0] if self._table_exists("fts_docs_vocab") else 0
        return {
            "documents": self._count,
            "vocabulary": vocab,
        }

    def _table_exists(self, name: str) -> bool:
        row = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        return row is not None

    def optimize(self) -> None:
        """Optimize FTS5 index (merge segments)."""
        self._conn.execute("INSERT INTO fts_docs(fts_docs) VALUES('optimize')")
        self._conn.commit()
