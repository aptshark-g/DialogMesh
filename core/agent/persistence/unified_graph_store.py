"""UnifiedGraphStore: generic graph persistence for all domain models.

G10-P3 (2026-08-04): 完成半实现 — 补齐 CLI/快照消费方所需的 API：
  open/is_open/stats / query_nodes / run_maintenance /
  SnapshotRecord + create_snapshot/get_snapshots/delete_snapshot。
"""
from __future__ import annotations
import json, logging, sqlite3, threading, time, os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DDL = """CREATE TABLE IF NOT EXISTS unified_nodes (
    node_id TEXT PRIMARY KEY, node_type TEXT NOT NULL,
    domain TEXT NOT NULL, session_id TEXT, data TEXT NOT NULL,
    summary TEXT DEFAULT '', l2_summary TEXT DEFAULT '',
    activation_count INTEGER DEFAULT 0, importance REAL DEFAULT 0.0,
    tier TEXT DEFAULT 'H', source_events TEXT DEFAULT '[]',
    generated_questions TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS unified_edges (
    edge_id INTEGER PRIMARY KEY AUTOINCREMENT, edge_type TEXT NOT NULL,
    domain TEXT NOT NULL, session_id TEXT, source_id TEXT NOT NULL,
    target_id TEXT NOT NULL, data TEXT NOT NULL, weight REAL DEFAULT 1.0,
    activation_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_un_nodes_domain ON unified_nodes(domain);
CREATE INDEX IF NOT EXISTS idx_un_nodes_type ON unified_nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_un_nodes_tier ON unified_nodes(tier);
CREATE INDEX IF NOT EXISTS idx_un_nodes_session ON unified_nodes(session_id);
CREATE INDEX IF NOT EXISTS idx_un_edges_domain ON unified_edges(domain);
CREATE INDEX IF NOT EXISTS idx_un_edges_src ON unified_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_un_nodes_hot ON unified_nodes(activation_count) WHERE activation_count > 10;"""

SNAPSHOT_DDL = """CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    node_count INTEGER DEFAULT 0,
    edge_count INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"""


@dataclass
class SnapshotRecord:
    """Snapshot metadata record (CLI/SnapshotManager contract)."""
    snapshot_id: str
    created_at: str = ""
    node_count: int = 0
    edge_count: int = 0
    metadata: dict = None


class UnifiedGraphStore:

    def __init__(self, db_path: str = "~/.memorygraph/unified_graph.db"):
        self._db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._hot_threshold = 10
        self._ensure_tables()

    # ── Lifecycle (G10-P3: CLI/SnapshotManager 契约) ────────────────────

    def open(self) -> None:
        """Idempotent open — ensure tables (CLI contract)."""
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        self._ensure_tables()

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    @property
    def stats(self) -> dict:
        """Node/edge counts + tier distribution (CLI contract)."""
        try:
            with self._lock:
                node_row = self._conn.execute(
                    "SELECT COUNT(*) as cnt FROM unified_nodes").fetchone()
                edge_row = self._conn.execute(
                    "SELECT COUNT(*) as cnt FROM unified_edges").fetchone()
            # 注意: 不能持锁调用 get_tier_counts()（非重入锁 → 死锁）
            tiers = self.get_tier_counts()
            return {
                "node_count": node_row["cnt"] if node_row else 0,
                "edge_count": edge_row["cnt"] if edge_row else 0,
                "tiers": tiers,
                "db_path": self._db_path,
            }
        except Exception as e:
            return {"error": str(e)}

    def _ensure_tables(self):
        with self._lock:
            self._conn.executescript(DDL)
            self._conn.executescript(SNAPSHOT_DDL)
            self._conn.commit()

    def set_hot_threshold(self, threshold: int):
        self._hot_threshold = max(1, threshold)
        with self._lock:
            self._conn.execute("DROP INDEX IF EXISTS idx_un_nodes_hot")
            self._conn.execute(f"CREATE INDEX idx_un_nodes_hot ON unified_nodes(activation_count) WHERE activation_count > {self._hot_threshold}")
            self._conn.commit()

    def save_node(self, node_id: str, node_type: str, domain: str,
                  data: dict, session_id: str = None, summary: str = "",
                  l2_summary: str = "", importance: float = 0.0,
                  source_events: list = None, generated_questions: list = None,
                  tier: str = "H") -> bool:
        with self._lock:
            self._conn.execute(
                """INSERT INTO unified_nodes (node_id,node_type,domain,session_id,data,summary,l2_summary,importance,source_events,generated_questions,tier,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(node_id) DO UPDATE SET data=excluded.data,summary=excluded.summary,l2_summary=excluded.l2_summary,importance=excluded.importance,tier=excluded.tier,updated_at=CURRENT_TIMESTAMP""",
                (node_id, node_type, domain, session_id,
                 json.dumps(data, ensure_ascii=False), summary, l2_summary,
                 importance,
                 json.dumps(source_events or [], ensure_ascii=False),
                 json.dumps(generated_questions or [], ensure_ascii=False),
                 tier))
            self._conn.commit()
        return True

    def load_node(self, node_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM unified_nodes WHERE node_id=?", (node_id,)).fetchone()
        if row is None: return None
        return self._row_to_dict(row)

    def load_nodes_by_session(self, session_id: str, domain: str = None, limit: int = 1000) -> List[dict]:
        with self._lock:
            if domain:
                rows = self._conn.execute("SELECT * FROM unified_nodes WHERE session_id=? AND domain=? ORDER BY updated_at DESC LIMIT ?", (session_id, domain, limit)).fetchall()
            else:
                rows = self._conn.execute("SELECT * FROM unified_nodes WHERE session_id=? ORDER BY updated_at DESC LIMIT ?", (session_id, limit)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def touch(self, node_id: str):
        with self._lock:
            self._conn.execute("UPDATE unified_nodes SET activation_count=activation_count+1, updated_at=CURRENT_TIMESTAMP WHERE node_id=?", (node_id,))
            self._conn.commit()

    def get_tier_counts(self) -> Dict[str, int]:
        with self._lock:
            rows = self._conn.execute("SELECT tier, COUNT(*) as cnt FROM unified_nodes GROUP BY tier").fetchall()
        return {r["tier"]: r["cnt"] for r in rows}

    def query_nodes(self, tier: str = None, node_type: str = None,
                    domain: str = None, limit: int = 100) -> List[dict]:
        """Filtered node query (CLI maintenance contract)."""
        conditions, params = [], []
        if tier:
            conditions.append("tier = ?")
            params.append(tier)
        if node_type:
            conditions.append("node_type = ?")
            params.append(node_type)
        if domain:
            conditions.append("domain = ?")
            params.append(domain)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM unified_nodes {where} ORDER BY updated_at DESC LIMIT ?",
                params + [limit]).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def run_maintenance(self) -> Dict[str, int]:
        """GC: hot overflow → warm, warm stale → cold, cold stale → archive.

        Returns per-tier migration counts (CLI maintenance contract).
        """
        result: Dict[str, int] = {"H->W": 0, "W->C": 0, "C->A": 0}
        try:
            from core.agent.persistence.graph_tier_manager import (
                GraphTierManager, HOT_MAX_NODES, WARM_TO_COLD_ACTIVATION,
                HOT_TO_WARM_INACTIVE_ROUNDS,
            )
            mgr = GraphTierManager(self)
            counts = self.get_tier_counts()
            if counts.get("H", 0) > HOT_MAX_NODES:
                excess = counts.get("H", 0) - HOT_MAX_NODES
                self.demote_stale_nodes("H", "W",
                                        max_activation=HOT_TO_WARM_INACTIVE_ROUNDS,
                                        limit=excess)
                result["H->W"] = excess
            counts = self.get_tier_counts()
            if counts.get("W", 0) > 100:
                n = counts.get("W", 0) // 2
                self.demote_stale_nodes("W", "C",
                                        max_activation=WARM_TO_COLD_ACTIVATION,
                                        limit=n)
                result["W->C"] = n
            mgr._strip_cold_data()
            counts = self.get_tier_counts()
            if counts.get("C", 0) > 50:
                n = counts.get("C", 0) // 4
                self.demote_stale_nodes("C", "A", max_activation=0, limit=n)
                result["C->A"] = n
            return result
        except Exception as e:
            logger.warning("run_maintenance failed: %s", e)
            return result

    # ── Snapshots (G10-P3: SnapshotManager 契约) ────────────────────────

    def create_snapshot(self, metadata: dict = None) -> SnapshotRecord:
        """Snapshot current node/edge counts into the snapshots table."""
        with self._lock:
            node_row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM unified_nodes").fetchone()
            edge_row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM unified_edges").fetchone()
            node_count = node_row["cnt"] if node_row else 0
            edge_count = edge_row["cnt"] if edge_row else 0
            snapshot_id = f"snap_{int(time.time())}_{node_count}"
            self._conn.execute(
                "INSERT INTO snapshots (snapshot_id, node_count, edge_count, metadata) VALUES (?,?,?,?)",
                (snapshot_id, node_count, edge_count,
                 json.dumps(metadata or {}, ensure_ascii=False)))
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM snapshots WHERE snapshot_id=?", (snapshot_id,)
            ).fetchone()
        return self._snapshot_from_row(row)

    def get_snapshots(self, limit: int = 10) -> List[SnapshotRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM snapshots ORDER BY created_at DESC LIMIT ?",
                (limit,)).fetchall()
        return [self._snapshot_from_row(r) for r in rows]

    def delete_snapshot(self, snapshot_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM snapshots WHERE snapshot_id=?", (snapshot_id,))
            self._conn.commit()
        return cur.rowcount > 0

    @staticmethod
    def _snapshot_from_row(row) -> SnapshotRecord:
        if row is None:
            return SnapshotRecord(snapshot_id="")
        try:
            meta = json.loads(row["metadata"] or "{}")
        except Exception:
            meta = {}
        return SnapshotRecord(
            snapshot_id=row["snapshot_id"],
            created_at=str(row["created_at"]),
            node_count=row["node_count"],
            edge_count=row["edge_count"],
            metadata=meta,
        )


    def update_tier(self, node_id: str, tier: str):
        with self._lock:
            self._conn.execute(
                "UPDATE unified_nodes SET tier=?,updated_at=CURRENT_TIMESTAMP WHERE node_id=?", (tier, node_id))
            self._conn.commit()

    def promote_cold_nodes(self, node_ids: List[str]):
        with self._lock:
            self._conn.executemany(
                "UPDATE unified_nodes SET tier='W',activation_count=activation_count+1,updated_at=CURRENT_TIMESTAMP WHERE node_id=? AND tier IN('C','A')",
                [(nid,) for nid in node_ids])
            self._conn.commit()

    def demote_stale_nodes(self, tier_from: str, tier_to: str, max_activation: int = 0, limit: int = 100):
        with self._lock:
            self._conn.execute(
                "UPDATE unified_nodes SET tier=? WHERE node_id IN (SELECT node_id FROM unified_nodes WHERE tier=? AND activation_count<=? ORDER BY updated_at ASC LIMIT ?)",
                (tier_to, tier_from, max_activation, limit))
            self._conn.commit()

    def save_edge(self, edge_type: str, domain: str, source_id: str, target_id: str, data: dict, session_id: str = None, weight: float = 1.0):
        with self._lock:
            self._conn.execute(
                "INSERT INTO unified_edges(edge_type,domain,session_id,source_id,target_id,data,weight) VALUES(?,?,?,?,?,?,?)",
                (edge_type, domain, session_id, source_id, target_id, json.dumps(data, ensure_ascii=False), weight))
            self._conn.commit()

    def load_edges(self, node_id: str, domain: str = None) -> List[dict]:
        with self._lock:
            if domain:
                rows = self._conn.execute(
                    "SELECT * FROM unified_edges WHERE domain=? AND (source_id=? OR target_id=?) ORDER BY created_at DESC",
                    (domain, node_id, node_id)).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM unified_edges WHERE source_id=? OR target_id=? ORDER BY created_at DESC",
                    (node_id, node_id)).fetchall()
        return [dict(r) for r in rows]

    def hot_node_ids(self) -> List[str]:
        with self._lock:
            rows = self._conn.execute(
                f"SELECT node_id FROM unified_nodes WHERE activation_count > {self._hot_threshold}").fetchall()
        return [r["node_id"] for r in rows]

    def delete_domain(self, domain: str) -> int:
        """按域清理节点与边（2026-08-11: 图重建/增量更新/域迁移用）。

        返回删除的边数（节点数可从 stats 对账）。边先删（外键语义,
        unified_edges 无 FK 约束, 顺序仅为语义清晰）。
        """
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM unified_edges WHERE domain=?", (domain,))
            edge_del = cur.rowcount
            cur = self._conn.execute(
                "DELETE FROM unified_nodes WHERE domain=?", (domain,))
            node_del = cur.rowcount
            self._conn.commit()
        logger = __import__("logging").getLogger(__name__)
        logger.info("delete_domain(%s): %d nodes, %d edges", domain, node_del, edge_del)
        return edge_del

    def _row_to_dict(self, row) -> dict:
        d = dict(row)
        d["data"] = json.loads(d["data"])
        d["source_events"] = json.loads(d.get("source_events", "[]"))
        d["generated_questions"] = json.loads(d.get("generated_questions", "[]"))
        return d

    def close(self):
        self._conn.close()
