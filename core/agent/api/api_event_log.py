"""EventLog: append-only, idempotent SQLite event store.

Queue-agnostic interface. Today: SQLite. Tomorrow: Kafka (same put/ack/replay API).
"""
from __future__ import annotations
import json, sqlite3, time, logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


class EventLog:
    """Append-only event log backed by SQLite.

    Guarantees:
        - Idempotent writes (INSERT OR IGNORE on event_id)
        - Crash recovery via replay_unconsumed()
        - Old event cleanup (retention_sec)
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS event_log (
        event_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        payload TEXT,
        trace_id TEXT,
        created_at REAL NOT NULL,
        consumed INTEGER DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_event_consumed ON event_log(consumed, created_at);
    CREATE INDEX IF NOT EXISTS idx_event_trace ON event_log(trace_id);
    """

    def __init__(self, db_path: str = "data/event_log.db", retention_hours: int = 24):
        self._db_path = db_path
        self._retention_sec = retention_hours * 3600
        self._conn: Optional[sqlite3.Connection] = None

    def open(self):
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(self.SCHEMA)
        self._conn.commit()
        logger.info("EventLog opened at %s", self._db_path)

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def put_event(self, event_id: str, kind: str, payload: dict,
                  trace_id: str = "") -> bool:
        """Write event. Idempotent: same event_id -> no duplicate."""
        now = time.time()
        payload_json = json.dumps(payload, ensure_ascii=False) if payload else None
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT OR IGNORE INTO event_log "
                    "(event_id, kind, payload, trace_id, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (event_id, kind, payload_json, trace_id, now),
                )
            return True
        except Exception as e:
            logger.error("EventLog put failed: %s", e)
            return False

    def ack_event(self, event_id: str) -> bool:
        """Mark event as consumed."""
        if not self._conn:
            return False
        self._conn.execute(
            "UPDATE event_log SET consumed=1 WHERE event_id=?", (event_id,)
        )
        self._conn.commit()
        return True

    def record_event(self, *args, **kwargs):
        """Alias for put_event. Handles both EventIR objects and raw args."""
        if len(args) == 1 and hasattr(args[0], 'id') and hasattr(args[0], 'kind'):
            # EventIR object → unpack
            evt = args[0]
            payload = evt.payload if hasattr(evt, 'payload') else {}
            trace_id = kwargs.get('trace_id', getattr(evt, 'trace_id', '') if hasattr(evt, 'trace_id') else '')
            return self.put_event(event_id=evt.id, kind=evt.kind, payload=dict(payload), trace_id=trace_id)
        return self.put_event(*args, **kwargs)

    def replay_unconsumed(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return unconsumed events ordered by creation time."""
        rows = self._conn.execute(
            "SELECT event_id, kind, payload, trace_id, created_at "
            "FROM event_log WHERE consumed=0 "
            "ORDER BY created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()

        return [
            {
                "event_id": row[0],
                "kind": row[1],
                "payload": json.loads(row[2]) if row[2] else {},
                "trace_id": row[3],
                "created_at": row[4],
            }
            for row in rows
        ]

    def cleanup_old(self) -> int:
        """Delete events older than retention period."""
        cutoff = time.time() - self._retention_sec
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM event_log WHERE consumed=1 AND created_at < ?",
                (cutoff,),
            )
            self._conn.commit()
            deleted = cursor.rowcount
        if deleted:
            logger.info("EventLog cleaned up %d old events", deleted)
        return deleted

    @property
    def stats(self) -> Dict[str, int]:
        total = self._conn.execute("SELECT COUNT(*) FROM event_log").fetchone()[0]
        unconsumed = self._conn.execute(
            "SELECT COUNT(*) FROM event_log WHERE consumed=0"
        ).fetchone()[0]
        return {"total": total, "unconsumed": unconsumed}

    def tail(self, limit: int = 20) -> list:
        """Return last N events (CLI)."""
        if not self._conn:
            return []
        rows = self._conn.execute(
            "SELECT event_id, kind, payload, trace_id, created_at FROM event_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"id": r[0], "kind": r[1], "payload": json.loads(r[2]) if r[2] else {},
             "trace_id": r[3], "created_at": r[4]}
            for r in reversed(rows)
        ]

    def recent(self, limit: int = 20) -> list:
        """Alias for tail (CLI)."""
        return self.tail(limit)
