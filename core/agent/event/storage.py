"""Phase 3: StorageLayer — unified Hot/Warm/Cold storage abstraction.

HotStore:  in-memory dict with TTL + LRU eviction (session state, current context)
WarmStore: SQLite with WAL mode (behavior edges, association chain, event log)  
ColdStore: JSON files + ChromaDB vectors (discourse summaries, semantic objects, history)

Replaces scattered `open("data/xxx.json")` calls with a single unified interface.
"""
import json, os, time, threading, sqlite3
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from collections import OrderedDict

logger = __import__('logging').getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  HotStore — memory, TTL expiration, LRU eviction
# ═══════════════════════════════════════════════════════════

@dataclass
class HotEntry:
    value: Any
    expire_at: float = 0.0  # 0 = never expire
    access_count: int = 0


class HotStore:
    """In-memory key-value store with TTL + LRU eviction.
    For: session state, current context, active blueprints.
    """

    def __init__(self, max_size: int = 1000, default_ttl_sec: int = 300):
        self._data: OrderedDict[str, HotEntry] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl_sec
        self._lock = threading.Lock()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return default
            if entry.expire_at > 0 and time.time() > entry.expire_at:
                del self._data[key]
                return default
            entry.access_count += 1
            self._data.move_to_end(key)  # LRU: move to end
            return entry.value

    def set(self, key: str, value: Any, ttl_sec: int = None) -> None:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
            ttl = ttl_sec if ttl_sec is not None else self._default_ttl
            self._data[key] = HotEntry(
                value=value,
                expire_at=time.time() + ttl if ttl > 0 else 0,
            )
            self._evict_if_needed()

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    def keys(self, pattern: str = None) -> List[str]:
        with self._lock:
            keys = list(self._data.keys())
            if pattern:
                keys = [k for k in keys if pattern in k]
            return keys

    def stats(self) -> dict:
        with self._lock:
            return {"size": len(self._data), "max": self._max_size}

    def _evict_if_needed(self):
        while len(self._data) > self._max_size:
            # Evict oldest (LRU front)
            self._data.popitem(last=False)


# ═══════════════════════════════════════════════════════════
#  WarmStore — SQLite with WAL mode
# ═══════════════════════════════════════════════════════════

class WarmStore:
    """SQLite-based store with WAL mode for concurrent reads.
    For: behavior edges, association chain, event log, meta decisions.
    """

    def __init__(self, db_path: str = None):
        from pathlib import Path
        if db_path is None:
            root = Path(__file__).resolve().parent.parent.parent.parent
            data_dir = root / "data"
            db_path = str(data_dir / "warm_store.db")
        self._is_memory = db_path == ":memory:"
        if not self._is_memory:
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def _init_db(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                payload TEXT,
                session_id TEXT,
                created_at REAL DEFAULT (strftime('%s','now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS behavior (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                from_concept TEXT,
                to_concept TEXT,
                session_id TEXT,
                metadata TEXT,
                created_at REAL DEFAULT (strftime('%s','now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS associations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                rel_type TEXT DEFAULT 'related',
                confidence REAL DEFAULT 0.5,
                session_id TEXT,
                created_at REAL DEFAULT (strftime('%s','now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta_decisions (
                id TEXT PRIMARY KEY,
                decision_type TEXT,
                verdict TEXT,
                reasoning TEXT,
                session_id TEXT,
                created_at REAL DEFAULT (strftime('%s','now'))
            )
        """)
        conn.commit()

    def insert_event(self, kind: str, payload: dict, session_id: str = "default") -> str:
        import uuid
        eid = str(uuid.uuid4())[:12]
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO events (id, kind, payload, session_id) VALUES (?, ?, ?, ?)",
            (eid, kind, json.dumps(payload, ensure_ascii=False), session_id),
        )
        conn.commit()
        return eid

    def query_events(self, kind: str = None, session_id: str = None, limit: int = 50) -> List[dict]:
        conn = self._get_conn()
        conditions = []
        params = []
        if kind:
            conditions.append("kind = ?")
            params.append(kind)
        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        rows = conn.execute(
            f"SELECT id, kind, payload, session_id, created_at FROM events {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        return [{"id": r[0], "kind": r[1], "payload": json.loads(r[2]), "session_id": r[3], "ts": r[4]} for r in rows]

    def insert_behavior(self, action: str, from_conc: str = "", to_conc: str = "",
                        session_id: str = "default", metadata: dict = None) -> int:
        conn = self._get_conn()
        c = conn.execute(
            "INSERT INTO behavior (action, from_concept, to_concept, session_id, metadata) VALUES (?, ?, ?, ?, ?)",
            (action, from_conc, to_conc, session_id, json.dumps(metadata or {})),
        )
        conn.commit()
        return c.lastrowid

    def insert_association(self, source: str, target: str, rel_type: str = "related",
                           confidence: float = 0.5, session_id: str = "default") -> int:
        conn = self._get_conn()
        c = conn.execute(
            "INSERT INTO associations (source, target, rel_type, confidence, session_id) VALUES (?, ?, ?, ?, ?)",
            (source, target, rel_type, confidence, session_id),
        )
        conn.commit()
        return c.lastrowid

    def insert_meta(self, decision_id: str, decision_type: str, verdict: str,
                    reasoning: str = "", session_id: str = "default") -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO meta_decisions (id, decision_type, verdict, reasoning, session_id) VALUES (?, ?, ?, ?, ?)",
            (decision_id, decision_type, verdict, reasoning, session_id),
        )
        conn.commit()

    def stats(self) -> dict:
        conn = self._get_conn()
        tables = ["events", "behavior", "associations", "meta_decisions"]
        result = {}
        for t in tables:
            count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            result[t] = count
        return {"tables": result, "db_path": self._db_path}

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


# ═══════════════════════════════════════════════════════════
#  ColdStore — JSON files
# ═══════════════════════════════════════════════════════════

class ColdStore:
    """File-based persistence for long-term storage.
    For: discourse summaries, semantic objects, profile history.
    """

    def __init__(self, data_dir: str = None):
        from pathlib import Path
        if data_dir is None:
            data_dir = str(Path(__file__).parent.parent.parent.parent / "data")
        self._dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

    def save(self, filename: str, data: Any) -> str:
        path = os.path.join(self._dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        return path

    def load(self, filename: str, default: Any = None) -> Any:
        path = os.path.join(self._dir, filename)
        if not os.path.exists(path):
            return default
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def delete(self, filename: str) -> bool:
        path = os.path.join(self._dir, filename)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    def list(self, pattern: str = "*.json") -> List[str]:
        import glob
        return [os.path.basename(p) for p in glob.glob(os.path.join(self._dir, pattern))]

    def stats(self) -> dict:
        files = self.list()
        total = sum(os.path.getsize(os.path.join(self._dir, f)) for f in files)
        return {"files": len(files), "total_bytes": total, "dir": self._dir}


# ═══════════════════════════════════════════════════════════
#  StorageLayer — unified interface
# ═══════════════════════════════════════════════════════════

class StorageLayer:
    """Unified storage interface — Hot/Warm/Cold with single API.

    Usage:
        store = StorageLayer()
        store.hot.set("session_ctx", {...}, ttl_sec=300)
        store.warm.insert_event("pcr_computed", {"zone": "MIXED"})
        store.cold.save("discourse_state.json", block_tree)
        stats = store.stats()
    """

    def __init__(self, data_dir: str = None, db_path: str = None):
        self.hot = HotStore()
        self.warm = WarmStore(db_path)
        self.cold = ColdStore(data_dir)

    def stats(self) -> dict:
        return {
            "hot": self.hot.stats(),
            "warm": self.warm.stats(),
            "cold": self.cold.stats(),
        }

    def save_state(self, name: str, data: Any, tier: str = "cold") -> str:
        """Persist engine state to appropriate tier."""
        if tier == "hot":
            self.hot.set(name, data)
            return "hot:" + name
        elif tier == "warm":
            self.warm.insert_event(name, data)
            return "warm:event"
        else:
            return self.cold.save(name, data)

    def load_state(self, name: str, tier: str = "cold") -> Any:
        if tier == "hot":
            return self.hot.get(name)
        elif tier == "warm":
            return self.warm.query_events(name)
        else:
            return self.cold.load(name)

    def close(self):
        self.warm.close()
