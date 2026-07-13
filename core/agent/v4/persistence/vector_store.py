"""VectorStore: abstract interface + SQLite-backed numpy cosine similarity."""
from __future__ import annotations
import json, sqlite3, time, logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class VectorStore(ABC):
    """Abstract interface for vector storage and similarity search.

    Implementations:
        SQLiteVectorStore  — SQLite + numpy cosine (default, zero external deps)
        MilvusVectorStore  — Milvus (reserved interface, for >100K vectors)
    """

    @abstractmethod
    def put(self, node_id: str, vector: np.ndarray, metadata: dict = None) -> None:
        """Store a vector with associated node ID."""

    @abstractmethod
    def get(self, node_id: str) -> Optional[np.ndarray]:
        """Retrieve a vector by node ID."""

    @abstractmethod
    def search(self, query_vector: np.ndarray, top_k: int = 10) -> List[Tuple[str, float]]:
        """Search for most similar vectors. Returns (node_id, score) pairs."""

    @abstractmethod
    def delete(self, node_id: str) -> None:
        """Remove a vector."""

    @property
    @abstractmethod
    def count(self) -> int:
        """Number of stored vectors."""


class SQLiteVectorStore(VectorStore):
    """SQLite-backed vector store with numpy cosine similarity.

    Good for <100K vectors. Zero external service dependencies.
    For larger scale, switch to MilvusVectorStore.

    Usage:
        store = SQLiteVectorStore("data/vectors.db")
        store.open()
        store.put("node1", np.array([0.1, 0.2, ...]))
        results = store.search(np.array([0.1, 0.3, ...]), top_k=5)
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

    def __init__(self, db_path: str = None):
        self._db_path = db_path or ":memory:"
        self._conn: Optional[sqlite3.Connection] = None
        self._count = 0

    def open(self) -> None:
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(self.SCHEMA)
        self._conn.commit()
        row = self._conn.execute("SELECT COUNT(*) FROM vectors").fetchone()
        self._count = row[0] if row else 0
        logger.info("SQLiteVectorStore opened at %s (%d vectors)", self._db_path, self._count)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def put(self, node_id: str, vector: np.ndarray, metadata: dict = None) -> None:
        now = time.time()
        vec_json = json.dumps(vector.tolist())
        meta_json = json.dumps(metadata, ensure_ascii=False) if metadata else None

        # Check if node exists before insert
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
        if not existed:
            self._count += 1

    def get(self, node_id: str) -> Optional[np.ndarray]:
        row = self._conn.execute(
            "SELECT vector_json FROM vectors WHERE node_id=?", (node_id,)
        ).fetchone()
        if row is None:
            return None
        return np.array(json.loads(row[0]))

    def search(self, query_vector: np.ndarray, top_k: int = 10) -> List[Tuple[str, float]]:
        """Search via numpy cosine similarity.

        For <100K vectors, this is fast enough (<10ms).
        For larger scale, switch to MilvusVectorStore.
        """
        if not isinstance(query_vector, np.ndarray):
            query_vector = np.array(query_vector)

        # Normalize query
        q_norm = np.linalg.norm(query_vector)
        if q_norm > 0:
            query_vector = query_vector / q_norm

        rows = self._conn.execute(
            "SELECT node_id, vector_json FROM vectors"
        ).fetchall()

        results = []
        for node_id, vec_json in rows:
            vec = np.array(json.loads(vec_json))
            v_norm = np.linalg.norm(vec)
            if v_norm == 0:
                continue
            vec = vec / v_norm
            sim = float(np.dot(query_vector, vec))
            results.append((node_id, sim))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def delete(self, node_id: str) -> None:
        existed = self.get(node_id) is not None
        with self._conn:
            self._conn.execute("DELETE FROM vectors WHERE node_id=?", (node_id,))
        if existed:
            self._count = max(0, self._count - 1)

    @property
    def count(self) -> int:
        return self._count

    @property
    def is_open(self) -> bool:
        return self._conn is not None


class MilvusVectorStore(VectorStore):
    """Milvus-backed vector store (reserved interface).

    For >100K vectors. Requires external Milvus server.
    Not yet implemented — stub returns empty results.
    """

    def __init__(self, host: str = "localhost", port: int = 19530, collection: str = "dialogmesh"):
        self._host = host
        self._port = port
        self._collection = collection
        self._connected = False

    def connect(self) -> bool:
        """Connect to Milvus server. Stub returns False."""
        return False

    def put(self, node_id: str, vector: np.ndarray, metadata: dict = None) -> None:
        pass  # Stub

    def get(self, node_id: str) -> Optional[np.ndarray]:
        return None  # Stub

    def search(self, query_vector: np.ndarray, top_k: int = 10) -> List[Tuple[str, float]]:
        return []  # Stub

    def delete(self, node_id: str) -> None:
        pass  # Stub

    @property
    def count(self) -> int:
        return 0
