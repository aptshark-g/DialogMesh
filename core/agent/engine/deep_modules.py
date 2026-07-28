"""Deep engine modules — MemoryCompiler, FormatEngine, ContextAssembler, SubgraphCompiler.

These fill the remaining 12 CLI placeholder gaps. All are self-contained
with no external dependencies beyond stdlib. Engine integrates them via lazy attr.
"""
import json, os, time, threading, sqlite3, uuid
from typing import Any, Dict, List, Optional
from collections import OrderedDict


# ═══════════════════════════════════════════════════════════
# 1. EventLog SQLite — proper init + open/close
# ═══════════════════════════════════════════════════════════

class EventLogDB:
    """Persistent event log backed by SQLite. Thread-safe."""

    def __init__(self, db_path: str = "data/event_log.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()

    def open(self) -> bool:
        """Initialize DB and create schema. Safe to call multiple times."""
        with self._lock:
            if self._conn is not None:
                return True
            os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else ".", exist_ok=True)
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT DEFAULT '{}',
                    session_id TEXT DEFAULT '',
                    trace_id TEXT DEFAULT '',
                    ts REAL DEFAULT (julianday('now'))
                )
            """)
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id)")
            self._conn.commit()
            return True

    def close(self):
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    def put(self, event_id: str, kind: str, payload: Any = None,
            session_id: str = "", trace_id: str = "") -> bool:
        self.open()
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT OR IGNORE INTO events(event_id, kind, payload, session_id, trace_id) VALUES(?,?,?,?,?)",
                    (event_id, kind, json.dumps(payload or {}), session_id, trace_id)
                )
                self._conn.commit()
            return True
        except Exception:
            return False

    def search(self, keyword: str = "", kind: str = "", session_id: str = "",
               limit: int = 50) -> List[Dict]:
        self.open()
        try:
            parts = ["SELECT event_id, kind, payload, session_id, ts FROM events WHERE 1=1"]
            params = []
            if keyword:
                parts.append("AND payload LIKE ?"); params.append(f"%{keyword}%")
            if kind:
                parts.append("AND kind = ?"); params.append(kind)
            if session_id:
                parts.append("AND session_id = ?"); params.append(session_id)
            parts.append("ORDER BY ts DESC LIMIT ?"); params.append(limit)
            with self._lock:
                rows = self._conn.execute(" ".join(parts), params).fetchall()
            return [dict(zip(["event_id","kind","payload","session_id","ts"], r)) for r in rows]
        except Exception:
            return []

    def tail(self, limit: int = 20) -> List[Dict]:
        return self.search(limit=limit)

    def stats(self) -> Dict:
        self.open()
        try:
            with self._lock:
                total = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
                by_kind = {}
                for row in self._conn.execute("SELECT kind, COUNT(*) FROM events GROUP BY kind"):
                    by_kind[row[0]] = row[1]
            return {"total": total, "by_kind": by_kind}
        except Exception:
            return {"total": 0, "by_kind": {}}

    def clear(self):
        self.open()
        try:
            with self._lock:
                self._conn.execute("DELETE FROM events")
                self._conn.commit()
            return True
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════
# 2. MemoryCompiler — tier management (Hot/Warm/Cold)
# ═══════════════════════════════════════════════════════════

class MemoryCompiler:
    """Three-tier memory: Hot (~10 nodes, <5ms), Warm (~1000 nodes, <50ms), Cold (archive).

    CLI commands: memory tier-show, tier-hot, tier-warm, tier-cold,
                  tier-promote, tier-demote, compress, compress-cold,
                  compile, conflict-show, conflict-resolve, checkpoint, stats.
    """

    def __init__(self, data_dir: str = "data/memory"):
        self.data_dir = data_dir
        self._hot: OrderedDict = OrderedDict()    # id → {data, access_count, ts}
        self._warm: OrderedDict = OrderedDict()
        self._cold: List[Dict] = []
        self._conflicts: List[Dict] = []
        self._checkpoints: List[Dict] = []
        self._merge_count = 0
        self._lock = threading.Lock()
        os.makedirs(data_dir, exist_ok=True)
        self._load()

    def _load(self):
        p = os.path.join(self.data_dir, "memory.json")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
                self._hot = OrderedDict(d.get("hot", {}))
                self._warm = OrderedDict(d.get("warm", {}))
                self._cold = d.get("cold", [])
                self._conflicts = d.get("conflicts", [])
                self._checkpoints = d.get("checkpoints", [])
            except: pass

    def _save(self):
        with self._lock:
            with open(os.path.join(self.data_dir, "memory.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "hot": dict(self._hot), "warm": dict(self._warm),
                    "cold": self._cold, "conflicts": self._conflicts,
                    "checkpoints": self._checkpoints,
                }, f, indent=2, ensure_ascii=False, default=str)

    # ── tier operations ──

    def tier_show(self) -> Dict:
        return {"hot": len(self._hot), "warm": len(self._warm),
                "cold": len(self._cold), "merges": self._merge_count,
                "conflicts": len(self._conflicts)}

    def tier_hot(self) -> List:
        return list(self._hot.keys())[-20:]

    def tier_warm(self) -> List:
        return list(self._warm.keys())[-50:]

    def tier_cold(self) -> List:
        return [c.get("id", "?") for c in self._cold[-50:]]

    def promote(self, node_id: str) -> Dict:
        with self._lock:
            if node_id in self._warm:
                v = self._warm.pop(node_id)
                self._hot[node_id] = v
            elif node_id in {c.get("id") for c in self._cold}:
                for i, c in enumerate(self._cold):
                    if c.get("id") == node_id:
                        self._hot[node_id] = c
                        self._cold.pop(i)
                        break
            else:
                return {"status": "not_found", "id": node_id}
            self._save()
            return {"status": "promoted", "id": node_id}

    def demote(self, node_id: str) -> Dict:
        with self._lock:
            if node_id in self._hot:
                v = self._hot.pop(node_id)
                self._warm[node_id] = v
            elif node_id in self._warm:
                v = self._warm.pop(node_id)
                self._cold.append(v)
            else:
                return {"status": "not_found", "id": node_id}
            self._save()
            return {"status": "demoted", "id": node_id}

    def compress(self) -> Dict:
        """Compress hot→warm (keep last 10 in hot)."""
        n = 0
        while len(self._hot) > 10:
            k, v = self._hot.popitem(last=False)
            self._warm[k] = v
            n += 1
        self._merge_count += n
        self._save()
        return {"status": "compressed", "moved": n, "hot": len(self._hot)}

    def compress_cold(self) -> Dict:
        """Compress warm→cold (keep last 500 in warm)."""
        n = 0
        while len(self._warm) > 500:
            k, v = self._warm.popitem(last=False)
            self._cold.append({"id": k, **v} if isinstance(v, dict) else {"id": k, "data": str(v)})
            n += 1
        self._merge_count += n
        self._save()
        return {"status": "compressed_cold", "moved": n, "warm": len(self._warm), "cold": len(self._cold)}

    # ── merge + conflict ──

    def compile(self, events: List[Dict] = None) -> Dict:
        """Compile events into memory (simulated)."""
        if events:
            for ev in events[-10:]:
                nid = ev.get("event_id", str(uuid.uuid4())[:8])
                self._hot[nid] = {"data": ev, "ts": time.time(), "access_count": 0}
        self._merge_count += 1
        self._save()
        return {"status": "compiled", "merge": self._merge_count}

    def conflict_show(self) -> List:
        return self._conflicts

    def conflict_resolve(self, cid: str, decision: str) -> Dict:
        with self._lock:
            for c in self._conflicts:
                if c.get("id") == cid:
                    c["resolution"] = decision
                    c["resolved_at"] = time.time()
                    self._save()
                    return {"status": "resolved", "id": cid}
        return {"status": "not_found", "id": cid}

    # ── checkpoint ──

    def checkpoint_create(self, label: str = "") -> Dict:
        cp = {"id": str(uuid.uuid4())[:8], "label": label, "ts": time.time(),
              "hot": len(self._hot), "warm": len(self._warm), "cold": len(self._cold)}
        self._checkpoints.append(cp)
        self._save()
        return cp

    def checkpoint_list(self) -> List:
        return self._checkpoints[-20:]

    def checkpoint_rollback(self, cid: str) -> Dict:
        return {"status": "rollback_simulated", "id": cid}


# ═══════════════════════════════════════════════════════════
# 3. ContextAssembler — compile + export ContextIR
# ═══════════════════════════════════════════════════════════

class ContextAssembler:
    """Compiles structured context from session state for LLM prompts.

    Produces ContextIR with sections: topic, reasoning, constraints, history, profile.
    """

    FORMATS = ("xml", "markdown", "json", "compact")

    def __init__(self, current_format: str = "markdown"):
        self.fmt = current_format if current_format in self.FORMATS else "markdown"
        self._last_ir: Dict = {}
        self._history: List[Dict] = []

    def compile(self, session_id: str = "", messages: List = None, profile: Dict = None) -> Dict:
        """Compile ContextIR from session data."""
        ir = {
            "session_id": session_id,
            "format": self.fmt,
            "sections": {
                "topic": {"tokens": len(str(messages)) if messages else 0},
                "reasoning": {"chains": 0},
                "constraints": [],
                "history": len(messages or []),
                "profile": list(profile.keys()) if profile else [],
            },
            "total_tokens": len(str(messages)) + len(str(profile)) if messages else 0,
            "ts": time.time(),
        }
        self._last_ir = ir
        self._history.append({"ts": time.time(), "tokens": ir["total_tokens"]})
        return ir

    def export(self) -> Dict:
        """Export full ContextIR as JSON."""
        if self._last_ir:
            return self._last_ir
        return {"sections": {}, "format": self.fmt, "total_tokens": 0}

    def section(self, stype: str) -> Dict:
        return self._last_ir.get("sections", {}).get(stype, {})

    def set_format(self, fmt: str) -> Dict:
        if fmt in self.FORMATS:
            self.fmt = fmt
            return {"status": "set", "format": fmt}
        return {"status": "unknown_format", "format": fmt, "available": list(self.FORMATS)}

    def get_format(self) -> str:
        return self.fmt


# ═══════════════════════════════════════════════════════════
# 4. SubgraphCompiler — k-hop expansion from anchor
# ═══════════════════════════════════════════════════════════

class SubgraphCompiler:
    """Expands subgraph from PersistentGraph using k-hop BFS."""

    def __init__(self, max_hops: int = 2, token_budget: int = 4096):
        self.max_hops = max_hops
        self.token_budget = token_budget
        self.strategy = "greedy_ilp"  # or "summary_fallback"
        self._last_subgraph: Dict = {}
        self._weights: Dict[str, float] = {
            "depends": 1.0, "creates": 1.0, "updates": 0.8,
            "constrains": 0.9, "reason": 0.7, "corrects": 0.6, "extends": 0.5
        }

    def expand(self, anchor: str, nodes: List[str] = None, edges: List[Dict] = None) -> Dict:
        """k-hop BFS from anchor."""
        if not nodes:
            self._last_subgraph = {"nodes": [], "edges": [], "anchor": anchor, "hops": 0}
            return self._last_subgraph
        visited = {anchor: 0}
        frontier = [anchor]
        sub_nodes = [anchor]
        sub_edges = []
        for hop in range(self.max_hops):
            next_frontier = []
            for n in frontier:
                for e in (edges or []):
                    if e.get("from") == n and e["to"] not in visited:
                        visited[e["to"]] = hop + 1
                        next_frontier.append(e["to"])
                        sub_nodes.append(e["to"])
                        sub_edges.append(e)
                    elif e.get("to") == n and e["from"] not in visited:
                        visited[e["from"]] = hop + 1
                        next_frontier.append(e["from"])
                        sub_nodes.append(e["from"])
                        sub_edges.append(e)
            frontier = next_frontier
            if not frontier:
                break
        self._last_subgraph = {"nodes": sub_nodes, "edges": sub_edges,
                                "anchor": anchor, "hops": min(hop, self.max_hops),
                                "budget": self.token_budget}
        return self._last_subgraph

    def show(self) -> Dict:
        return self._last_subgraph or {"nodes": [], "edges": [], "anchor": "", "hops": 0}

    def set_hop(self, n: int):
        self.max_hops = max(1, min(n, 5))
        return {"status": "set", "max_hops": self.max_hops}

    def set_weight(self, edge_type: str, w: float):
        self._weights[edge_type] = w
        return {"status": "set", "type": edge_type, "weight": w}

    def set_budget(self, tokens: int):
        self.token_budget = max(256, tokens)
        return {"status": "set", "token_budget": self.token_budget}

    def set_strategy(self, strategy: str):
        if strategy in ("greedy_ilp", "summary_fallback"):
            self.strategy = strategy
            return {"status": "set", "strategy": strategy}
        return {"status": "unknown", "available": ["greedy_ilp", "summary_fallback"]}


# ═══════════════════════════════════════════════════════════
# 5. FormatEngine — serialize/deserialize subgraph to tokens
# ═══════════════════════════════════════════════════════════

class FormatEngine:
    """Serializes subgraph/context into token sequences for LLM prompt injection."""

    TEMPLATES = ("xml", "compact", "list", "prompt")

    def __init__(self, template: str = "compact"):
        self.template = template if template in self.TEMPLATES else "compact"

    def encode(self, data: Any = None, fmt: str = None) -> Dict:
        """Serialize data to token sequence."""
        fmt = fmt or self.template
        if data is None:
            data = {}
        if fmt == "xml":
            encoded = "<data>" + json.dumps(data) + "</data>"
        elif fmt == "compact":
            encoded = json.dumps(data, separators=(",", ":"))
        elif fmt == "list":
            encoded = "\n".join(f"- {k}: {v}" for k, v in (data.items() if isinstance(data, dict) else enumerate(data)))
        else:
            encoded = json.dumps(data, indent=2)
        tokens = len(encoded) // 4  # rough estimate
        return {"encoded": encoded[:500], "tokens": tokens, "format": fmt}

    def decode(self, encoded: str) -> Dict:
        try:
            data = json.loads(encoded)
        except Exception:
            data = {"raw": encoded[:200]}
        return {"data": data, "tokens": len(encoded) // 4}

    def template_show(self) -> Dict:
        return {"template": self.template, "available": list(self.TEMPLATES)}

    def template_set(self, name: str) -> Dict:
        if name in self.TEMPLATES:
            self.template = name
            return {"status": "set", "template": name}
        return {"status": "unknown", "available": list(self.TEMPLATES)}

    def tokens(self, text: str = "") -> Dict:
        return {"text": text[:100], "tokens": len(text) // 4, "by_section": {}}

    def test(self, text: str = "") -> Dict:
        return self.encode({"test": text[:200]})
