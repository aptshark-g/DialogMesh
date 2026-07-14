"""MilvusVectorStore: production Milvus client with lazy connection.

Design:
    - Lazy connect: only connects when first operation is called
    - Graceful fallback: if connection fails, all operations return empty/no-op
    - TieredVectorStore decides WHEN to use Milvus (threshold-based)
    - This class only handles HOW to talk to Milvus

Dependencies:
    pymilvus (optional — only imported when Milvus is actually used)

Usage:
    store = MilvusVectorStore(host="localhost", port=19530, dimension=384)
    if store.connect():  # lazy connect
        store.put("node1", vector, metadata={"text": "..."})
        results = store.search(query_vector, top_k=5)
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from core.agent.v4.persistence.vector_store import VectorStore

logger = logging.getLogger(__name__)


class MilvusVectorStore(VectorStore):
    """Milvus-backed vector store with lazy connection and graceful degradation.

    Connection strategy:
        1. First call to put/get/search triggers lazy connect
        2. If connect fails, all subsequent operations are no-op (return empty)
        3. connect() can be called explicitly to check availability
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        collection: str = "dialogmesh",
        dimension: int = 384,
        metric_type: str = "COSINE",
    ):
        self._host = host
        self._port = port
        self._collection = collection
        self._dimension = dimension
        self._metric_type = metric_type
        self._connected = False
        self._client = None  # pymilvus.MilvusClient instance
        self._count_cache = 0

    # ------------------------------------------------------------------ #
    # Connection management
    # ------------------------------------------------------------------ #

    def connect(self) -> bool:
        """Lazy connect to Milvus server. Returns True if connected."""
        if self._connected:
            return True

        try:
            from pymilvus import MilvusClient, DataType

            self._client = MilvusClient(
                uri=f"http://{self._host}:{self._port}"
            )

            # Check if collection exists, create if not
            if not self._client.has_collection(self._collection):
                self._create_collection()

            self._connected = True
            self._count_cache = self._client.num_entities(self._collection)
            logger.info(
                "Milvus connected: %s:%d/%s (%d vectors)",
                self._host, self._port, self._collection, self._count_cache,
            )
            return True

        except ImportError:
            logger.warning(
                "pymilvus not installed. Milvus store disabled. "
                "Install with: pip install pymilvus"
            )
            return False

        except Exception as e:
            logger.warning(
                "Milvus connection failed (%s:%d): %s. "
                "Falling back to SQLite.",
                self._host, self._port, e,
            )
            self._connected = False
            self._client = None
            return False

    def disconnect(self) -> None:
        """Close connection to Milvus."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self._connected = False
        self._client = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------ #
    # VectorStore API
    # ------------------------------------------------------------------ #

    def put(self, node_id: str, vector: np.ndarray, metadata: dict = None) -> None:
        """Store a vector. If not connected, silently drops."""
        if not self._ensure_connected():
            return

        try:
            vec_list = vector.tolist() if isinstance(vector, np.ndarray) else list(vector)
            meta = metadata or {}
            meta["node_id"] = node_id

            self._client.insert(
                collection_name=self._collection,
                data=[{"vector": vec_list, **meta}],
            )
            self._count_cache += 1
        except Exception as e:
            logger.warning("Milvus put failed for %s: %s", node_id, e)

    def get(self, node_id: str) -> Optional[np.ndarray]:
        """Retrieve a vector by node_id. Returns None if not found or not connected."""
        if not self._ensure_connected():
            return None

        try:
            results = self._client.query(
                collection_name=self._collection,
                filter=f'node_id == "{node_id}"',
                output_fields=["vector"],
            )
            if results:
                vec = results[0].get("vector")
                if vec:
                    return np.array(vec)
            return None
        except Exception as e:
            logger.warning("Milvus get failed for %s: %s", node_id, e)
            return None

    def search(
        self, query_vector: np.ndarray, top_k: int = 10
    ) -> List[Tuple[str, float]]:
        """Search for most similar vectors. Returns (node_id, score) pairs."""
        if not self._ensure_connected():
            return []

        try:
            vec_list = (
                query_vector.tolist()
                if isinstance(query_vector, np.ndarray)
                else list(query_vector)
            )

            results = self._client.search(
                collection_name=self._collection,
                data=[vec_list],
                limit=top_k,
                output_fields=["node_id"],
            )

            # Parse results: [[(id, distance, ...), ...]]
            parsed = []
            for hits in results:
                for hit in hits:
                    # hit format varies by pymilvus version
                    if hasattr(hit, "entity"):
                        entity = hit.entity
                        node_id = entity.get("node_id", "")
                        score = hit.distance if hasattr(hit, "distance") else 0.0
                    elif isinstance(hit, dict):
                        node_id = hit.get("entity", {}).get("node_id", "")
                        score = hit.get("distance", 0.0)
                    else:
                        continue
                    parsed.append((node_id, float(score)))
            return parsed

        except Exception as e:
            logger.warning("Milvus search failed: %s", e)
            return []

    def delete(self, node_id: str) -> None:
        """Remove a vector by node_id."""
        if not self._ensure_connected():
            return

        try:
            self._client.delete(
                collection_name=self._collection,
                filter=f'node_id == "{node_id}"',
            )
            self._count_cache = max(0, self._count_cache - 1)
        except Exception as e:
            logger.warning("Milvus delete failed for %s: %s", node_id, e)

    @property
    def count(self) -> int:
        if not self._ensure_connected():
            return 0
        try:
            self._count_cache = self._client.num_entities(self._collection)
        except Exception:
            pass
        return self._count_cache

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def _ensure_connected(self) -> bool:
        """Ensure lazy connection is established."""
        if self._connected:
            return True
        return self.connect()

    def _create_collection(self) -> None:
        """Create collection with schema."""
        from pymilvus import DataType

        schema = self._client.create_schema(
            auto_id=True,
            enable_dynamic_field=True,
        )
        schema.add_field("id", DataType.INT64, is_primary=True)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=self._dimension)
        schema.add_field("node_id", DataType.VARCHAR, max_length=256)

        self._client.create_collection(
            collection_name=self._collection,
            schema=schema,
        )

        # Create index
        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="IVF_FLAT",
            metric_type=self._metric_type,
            params={"nlist": 128},
        )
        self._client.create_index(
            collection_name=self._collection,
            index_params=index_params,
        )
        self._client.load_collection(self._collection)
        logger.info("Milvus collection created: %s", self._collection)
