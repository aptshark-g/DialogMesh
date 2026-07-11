"""UnifiedGraphStore: generic graph persistence for all domain models."""
from __future__ import annotations
import json, logging, sqlite3, threading, time, os
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


class UnifiedGraphStore:

    def __init__(self, db_path: str = "~/.memorygraph/unified_graph.db"):
        self._db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._hot_threshold = 10
        self._ensure_tables()

    def _ensure_tables(self):
        with self._lock: self._conn.executescript(DDL); self._conn.commit()

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

    def _row_to_dict(self, row) -> dict:
        d = dict(row)
        d["data"] = json.loads(d["data"])
        d["source_events"] = json.loads(d.get("source_events", "[]"))
        d["generated_questions"] = json.loads(d.get("generated_questions", "[]"))
        return d

    def close(self):
        self._conn.close()
