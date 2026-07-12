"""UnifiedGraphStore v4: SQLite-backed universal graph persistence.

Stores all v4 cognitive data: ObservationBundle, HypothesisNode,
KnowledgeNode, Skill, StructuralWorldGraph.

Thread-safe with tiered storage (hot/warm/cold/archive).
"""
from __future__ import annotations
import json, sqlite3, threading, time, logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class NodeRecord:
    """A universal node record."""
    node_id: str
    node_type: str
    tier: str = "warm"
    data: Any = None
    created_at: float = 0.0
    updated_at: float = 0.0
    access_count: int = 0


@dataclass
class EdgeRecord:
    """A universal edge record."""
    edge_id: str
    edge_type: str
    source_id: str
    target_id: str
    weight: float = 1.0
    data: Any = None
    created_at: float = 0.0


@dataclass
class SnapshotRecord:
    """Metadata for a snapshot."""
    snapshot_id: str
    created_at: float
    node_count: int = 0
    edge_count: int = 0
    metadata: dict = field(default_factory=dict)


class UnifiedGraphStore:
    """SQLite-backed universal graph store for v4 cognitive data.

    Tier model:
        hot    — in-memory cache (managed by caller)
        warm   — SQLite (default, fast access)
        cold   — JSON file on disk (low-frequency)
        archive — compressed file (historical, read-only)
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS nodes (
        node_id TEXT PRIMARY KEY,
        node_type TEXT NOT NULL,
        tier TEXT DEFAULT 'warm',
        data_json TEXT,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        access_count INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS edges (
        edge_id TEXT PRIMARY KEY,
        edge_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        target_id TEXT NOT NULL,
        weight REAL DEFAULT 1.0,
        data_json TEXT,
        created_at REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS snapshots (
        snapshot_id TEXT PRIMARY KEY,
        created_at REAL NOT NULL,
        node_count INTEGER DEFAULT 0,
        edge_count INTEGER DEFAULT 0,
        metadata TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
    CREATE INDEX IF NOT EXISTS idx_nodes_tier ON nodes(tier);
    CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
    CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
    CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type);
    """

    def __init__(self, db_path: str = None):
        """Initialize the store.

        Args:
            db_path: Path to SQLite database file. Defaults to :memory: for testing.
        """
        self._db_path = db_path or ":memory:"
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._stats = {"puts": 0, "gets": 0, "errors": 0}

    def open(self) -> None:
        """Open the database connection and initialize schema."""
        with self._lock:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(self.SCHEMA)
            self._conn.commit()
            logger.info("UnifiedGraphStore opened at %s", self._db_path)

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
                logger.info("UnifiedGraphStore closed")

    # ---- Node operations ----

    def put_node(self, node_id: str, node_type: str, data: Any,
                 tier: str = "warm") -> bool:
        """Insert or update a node."""
        now = time.time()
        data_json = json.dumps(data, default=str, ensure_ascii=False)
        try:
            with self._lock:
                self._conn.execute(
                    """INSERT OR REPLACE INTO nodes
                       (node_id, node_type, tier, data_json, created_at, updated_at, access_count)
                       VALUES (?, ?, ?, ?,
                         COALESCE((SELECT created_at FROM nodes WHERE node_id=?), ?),
                         ?, 0)""",
                    (node_id, node_type, tier, data_json, node_id, now, now),
                )
                self._conn.commit()
                self._stats["puts"] += 1
                return True
        except Exception as e:
            logger.error("put_node failed: %s", e)
            self._stats["errors"] += 1
            return False

    def get_node(self, node_id: str) -> Optional[NodeRecord]:
        """Retrieve a node by ID."""
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT node_id, node_type, tier, data_json, created_at, updated_at, access_count "
                    "FROM nodes WHERE node_id=?",
                    (node_id,),
                ).fetchone()
                if row is None:
                    return None
                # Increment access count
                self._conn.execute(
                    "UPDATE nodes SET access_count = access_count + 1 WHERE node_id=?",
                    (node_id,),
                )
                self._conn.commit()
                self._stats["gets"] += 1
                return NodeRecord(
                    node_id=row[0],
                    node_type=row[1],
                    tier=row[2],
                    data=json.loads(row[3]) if row[3] else None,
                    created_at=row[4],
                    updated_at=row[5],
                    access_count=row[6] + 1,
                )
        except Exception as e:
            logger.error("get_node failed: %s", e)
            self._stats["errors"] += 1
            return None

    def delete_node(self, node_id: str) -> bool:
        """Delete a node and its edges."""
        try:
            with self._lock:
                self._conn.execute("DELETE FROM nodes WHERE node_id=?", (node_id,))
                self._conn.execute(
                    "DELETE FROM edges WHERE source_id=? OR target_id=?",
                    (node_id, node_id),
                )
                self._conn.commit()
                return True
        except Exception as e:
            logger.error("delete_node failed: %s", e)
            return False

    def query_nodes(self, node_type: str = None, tier: str = None,
                    limit: int = 100) -> List[NodeRecord]:
        """Query nodes by type and/or tier."""
        try:
            with self._lock:
                conditions = []
                params = []
                if node_type:
                    conditions.append("node_type=?")
                    params.append(node_type)
                if tier:
                    conditions.append("tier=?")
                    params.append(tier)

                where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
                rows = self._conn.execute(
                    f"SELECT node_id, node_type, tier, data_json, created_at, updated_at, access_count "
                    f"FROM nodes {where} ORDER BY updated_at DESC LIMIT ?",
                    tuple(params + [limit]),
                ).fetchall()

                return [
                    NodeRecord(
                        node_id=row[0], node_type=row[1], tier=row[2],
                        data=json.loads(row[3]) if row[3] else None,
                        created_at=row[4], updated_at=row[5], access_count=row[6],
                    )
                    for row in rows
                ]
        except Exception as e:
            logger.error("query_nodes failed: %s", e)
            return []

    # ---- Edge operations ----

    def put_edge(self, edge_id: str, edge_type: str, source_id: str,
                 target_id: str, weight: float = 1.0, data: Any = None) -> bool:
        """Insert or update an edge."""
        now = time.time()
        data_json = json.dumps(data, default=str, ensure_ascii=False) if data else None
        try:
            with self._lock:
                self._conn.execute(
                    """INSERT OR REPLACE INTO edges
                       (edge_id, edge_type, source_id, target_id, weight, data_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (edge_id, edge_type, source_id, target_id, weight, data_json, now),
                )
                self._conn.commit()
                self._stats["puts"] += 1
                return True
        except Exception as e:
            logger.error("put_edge failed: %s", e)
            return False

    def get_edges(self, source_id: str = None, target_id: str = None,
                  edge_type: str = None, limit: int = 200) -> List[EdgeRecord]:
        """Query edges by source, target, and/or type."""
        try:
            with self._lock:
                conditions = []
                params = []
                if source_id:
                    conditions.append("source_id=?")
                    params.append(source_id)
                if target_id:
                    conditions.append("target_id=?")
                    params.append(target_id)
                if edge_type:
                    conditions.append("edge_type=?")
                    params.append(edge_type)

                where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
                rows = self._conn.execute(
                    f"SELECT edge_id, edge_type, source_id, target_id, weight, data_json, created_at "
                    f"FROM edges {where} ORDER BY created_at DESC LIMIT ?",
                    tuple(params + [limit]),
                ).fetchall()

                return [
                    EdgeRecord(
                        edge_id=row[0], edge_type=row[1], source_id=row[2],
                        target_id=row[3], weight=row[4],
                        data=json.loads(row[5]) if row[5] else None,
                        created_at=row[6],
                    )
                    for row in rows
                ]
        except Exception as e:
            logger.error("get_edges failed: %s", e)
            return []

    # ---- Snapshot operations ----

    def create_snapshot(self, metadata: dict = None) -> SnapshotRecord:
        """Create a snapshot of current state."""
        now = time.time()
        base_id = int(now * 1000000)
        try:
            with self._lock:
                node_count = self._conn.execute(
                    "SELECT COUNT(*) FROM nodes"
                ).fetchone()[0]
                edge_count = self._conn.execute(
                    "SELECT COUNT(*) FROM edges"
                ).fetchone()[0]
                # Retry with counter on ID collision
                for retry in range(100):
                    snapshot_id = f"snap_{base_id + retry}"
                    try:
                        self._conn.execute(
                            "INSERT INTO snapshots (snapshot_id, created_at, node_count, edge_count, metadata) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (snapshot_id, now, node_count, edge_count,
                             json.dumps(metadata or {}, ensure_ascii=False)),
                        )
                        self._conn.commit()
                        break
                    except sqlite3.IntegrityError:
                        continue
                else:
                    raise RuntimeError("Failed to create snapshot after 100 retries")
                return SnapshotRecord(
                    snapshot_id=snapshot_id,
                    created_at=now,
                    node_count=node_count,
                    edge_count=edge_count,
                    metadata=metadata or {},
                )
        except Exception as e:
            logger.error("create_snapshot failed: %s", e)
            raise

    def get_snapshots(self, limit: int = 10) -> List[SnapshotRecord]:
        """Get recent snapshots."""
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT snapshot_id, created_at, node_count, edge_count, metadata "
                    "FROM snapshots ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [
                    SnapshotRecord(
                        snapshot_id=row[0], created_at=row[1],
                        node_count=row[2], edge_count=row[3],
                        metadata=json.loads(row[4]) if row[4] else {},
                    )
                    for row in rows
                ]
        except Exception as e:
            logger.error("get_snapshots failed: %s", e)
            return []

    # ---- Tier migration ----

    def run_maintenance(self) -> Dict[str, int]:
        """Run tier migration maintenance.

        Returns:
            Dict with migration counts per tier.
        """
        result = {"hot_to_warm": 0, "warm_to_cold": 0, "cold_to_archive": 0}
        try:
            with self._lock:
                now = time.time()
                # Promote frequently accessed nodes to warm
                self._conn.execute(
                    "UPDATE nodes SET tier='warm' WHERE tier='cold' AND access_count > 100"
                )
                result["cold_to_warm"] = self._conn.total_changes

                # Demote old cold nodes to archive (>90 days no access)
                self._conn.execute(
                    "UPDATE nodes SET tier='archive' "
                    "WHERE tier='cold' AND updated_at < ? AND access_count < 5",
                    (now - 90 * 86400,),
                )
                result["cold_to_archive"] = self._conn.total_changes

                self._conn.commit()
                return result
        except Exception as e:
            logger.error("run_maintenance failed: %s", e)
            return result

    # ---- Stats ----

    @property
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            if self._conn is None:
                return {"puts": 0, "gets": 0, "errors": 0, "node_count": 0, "edge_count": 0}
            node_count = self._conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            edge_count = self._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            return {
                **self._stats,
                "node_count": node_count,
                "edge_count": edge_count,
            }

    @property
    def is_open(self) -> bool:
        return self._conn is not None
