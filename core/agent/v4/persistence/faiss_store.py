"""FaissVectorStore: HNSW-accelerated vector store with SQLite persistence.

Replaces SQLiteVectorStore's O(n) full scan with O(log n) HNSW approximate search.
SQLite remains the source of truth for vector storage; HNSW is the search accelerator.

Usage:
    store = FaissVectorStore("data/vectors.db", dim=384)
    store.open()
    store.put("node1", np.array([0.1, 0.2, ...]))
    results = store.search(query_vec, top_k=5)
    # -> [("node1", 0.87), ("k3", 0.72), ...]
"""
from __future__ import annotations
import json, sqlite3, time, logging
from typing import Any, Dict, List, Optional, Tuple

from core.agent.v4.persistence.vector_store import VectorStore
from core.agent.v4.persistence.hnsw_index import HNSWIndex

try:
    import numpy as np
    HAS_NUMPY = True
except Exception:
    HAS_NUMPY = False
    np = None

logger = logging.getLogger(__name__)


class FaissVectorStore(VectorStore):
    """HNSW-accelerated vector store.

    Architecture:
        SQLite: source of truth (all vectors stored as JSON)
        HNSWIndex: in-memory search accelerator (built on open, rebuilt on put)

    Search complexity: O(log n) via HNSW
    Storage: SQLite on disk (vectors as JSON)
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS vectors (
        node_id TEXT PRIMARY KEY,
        vector_json TEXT NOT NULL,
        model_name TEXT DEFAULT 'default',
        metadata TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_vectors_model ON vectors(model_name);
    """

    def __init__(self, db_path: str = None, dim: int = 384,
                 M: int = 16, ef_construction: int = 200, ef_search: int = 64):
        """Args:
            db_path: SQLite database path
            dim: Vector dimension
            M: HNSW neighbor count (16-32 typical)
            ef_construction: HNSW construction quality (higher = better, slower)
            ef_search: HNSW search quality (higher = better, slower)
        """
        self._db_path = db_path or ":memory:"
        self._dim = dim
        self._M = M
        self._ef_construction = ef_construction
        self._ef_search = ef_search
        self._conn: Optional[sqlite3.Connection] = None
        self._hnsw: Optional[HNSWIndex] = None
        self._count = 0

    def open(self) -> None:
        """Open SQLite and build HNSW index from stored vectors."""
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(self.SCHEMA)
        self._conn.commit()

        # Count existing vectors
        row = self._conn.execute("SELECT COUNT(*) FROM vectors").fetchone()
        self._count = row[0] if row else 0

        # Build HNSW index from existing vectors
        self._rebuild_hnsw()

        logger.info("FaissVectorStore opened: %d vectors, dim=%d", self._count, self._dim)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
        self._hnsw = None

    def _rebuild_hnsw(self) -> None:
        """Rebuild HNSW index from SQLite."""
        self._hnsw = HNSWIndex(
            dim=self._dim,
            M=self._M,
            ef_construction=self._ef_construction,
            ef_search=self._ef_search,
            metric="cosine",
        )

        rows = self._conn.execute(
            "SELECT node_id, vector_json FROM vectors"
        ).fetchall()

        for node_id, vec_json in rows:
            vec = self._json_to_vector(vec_json)
            self._hnsw.add(node_id, vec)

        self._hnsw.build()
        logger.info("HNSW index rebuilt: %d vectors", len(rows))

    def _json_to_vector(self, vec_json: str):
        """Convert JSON string to vector."""
        vec_list = json.loads(vec_json)
        return np.array(vec_list) if HAS_NUMPY else vec_list

    def _vector_to_json(self, vector) -> str:
        """Convert vector to JSON string."""
        if HAS_NUMPY and isinstance(vector, np.ndarray):
            return json.dumps(vector.tolist())
        return json.dumps(list(vector))

    # ---- VectorStore API ----

    def put(self, node_id: str, vector, metadata: dict = None) -> None:
        """Store vector in SQLite and update HNSW index."""
        now = time.time()
        vec_json = self._vector_to_json(vector)
        meta_json = json.dumps(metadata, ensure_ascii=False) if metadata else None

        # Check if exists
        existed = self.get(node_id) is not None

        with self._conn:
            self._conn.execute(
                """INSERT OR REPLACE INTO vectors
                   (node_id, vector_json, metadata, created_at, updated_at)
                   VALUES (?, ?, ?,
                     COALESCE((SELECT created_at FROM vectors WHERE node_id=?), ?),
                     ?)""",
                (node_id, vec_json, meta_json, node_id, now, now),
            )

        # Update HNSW
        if self._hnsw is None:
            self._rebuild_hnsw()
        else:
            # Normalize for cosine
            if HAS_NUMPY and isinstance(vector, np.ndarray):
                norm = np.linalg.norm(vector)
                if norm > 0:
                    vector = vector / norm
            self._hnsw.add(node_id, vector)
            self._hnsw.build()

        if not existed:
            self._count += 1

    def get(self, node_id: str) -> Optional[Any]:
        """Retrieve vector by node ID."""
        row = self._conn.execute(
            "SELECT vector_json FROM vectors WHERE node_id=?", (node_id,)
        ).fetchone()
        if row is None:
            return None
        return self._json_to_vector(row[0])

    def search(self, query_vector, top_k: int = 10) -> List[Tuple[str, float]]:
        """Search via HNSW O(log n) approximate nearest neighbor.

        Returns: list of (node_id, similarity_score) sorted by score desc.
        """
        if self._hnsw is None or self._count == 0:
            return []

        # Ensure numpy array
        if HAS_NUMPY and not isinstance(query_vector, np.ndarray):
            query_vector = np.array(query_vector)

        return self._hnsw.search(query_vector, top_k)

    def delete(self, node_id: str) -> None:
        """Remove vector from SQLite and HNSW."""
        existed = self.get(node_id) is not None
        with self._conn:
            self._conn.execute("DELETE FROM vectors WHERE node_id=?", (node_id,))
        if existed and self._hnsw:
            self._hnsw.delete(node_id)
            self._count -= 1

    @property
    def count(self) -> int:
        return self._count

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    def hnsw_stats(self) -> Dict[str, Any]:
        """Return HNSW index statistics."""
        if self._hnsw:
            return self._hnsw.stats()
        return {}
