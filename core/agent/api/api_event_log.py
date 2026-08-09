"""EventLog: append-only, idempotent SQLite event store.

Queue-agnostic interface. Today: SQLite. Tomorrow: Kafka (same put/ack/replay API).
G2: per-subscriber watermark (event_consumer) + semantic_value anchors.
"""
from __future__ import annotations
import json, sqlite3, time, logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


class EventLog:
    """Append-only event log backed by SQLite.

    Guarantees:
        - Idempotent writes (INSERT OR IGNORE on event_id)
        - Crash recovery via replay_unconsumed() / replay_for_consumer()
        - Old event cleanup (retention_sec)
    G2 (G2-P1/P2):
        - event_consumer 表 = per-subscriber 水位线（last_seq 单调前进）
        - ack_event 保留为单消费者快捷路径（兼容）
        - semantic_value = 摘要锚点数（cross_ref + l2_summary 存在性，不 LLM 打分）
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS event_log (
        event_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        payload TEXT,
        trace_id TEXT,
        created_at REAL NOT NULL,
        consumed INTEGER DEFAULT 0,
        semantic_value INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS event_consumer (
        consumer_id TEXT PRIMARY KEY,
        last_seq INTEGER NOT NULL DEFAULT 0,
        updated_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_event_consumed ON event_log(consumed, created_at);
    CREATE INDEX IF NOT EXISTS idx_event_trace ON event_log(trace_id);
    """

    # G2-P2: 锚点载体 key（cross_ref 完整性 + l2_summary 存在性）
    ANCHOR_KEYS = ("cross_ref", "cross_refs", "references", "anchors", "refs")

    def __init__(self, db_path: str = "data/event_log.db", retention_hours: int = 24):
        self._db_path = db_path
        self._retention_sec = retention_hours * 3600
        self._conn: Optional[sqlite3.Connection] = None

    def open(self):
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(self.SCHEMA)
        self._migrate()
        self._conn.commit()
        logger.info("EventLog opened at %s", self._db_path)

    def _migrate(self):
        """G2-P2: 老库补 semantic_value 列（ALTER TABLE ADD COLUMN）。"""
        try:
            cols = [r[1] for r in self._conn.execute("PRAGMA table_info(event_log)").fetchall()]
            if "semantic_value" not in cols:
                self._conn.execute("ALTER TABLE event_log ADD COLUMN semantic_value INTEGER DEFAULT 0")
                logger.info("EventLog migrated: added semantic_value column")
        except Exception as e:
            logger.warning("EventLog migrate skipped: %s", e)

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def put_event(self, event_id: str, kind: str, payload: dict,
                  trace_id: str = "") -> bool:
        """Write event. Idempotent: same event_id -> no duplicate."""
        now = time.time()
        payload_json = json.dumps(payload, ensure_ascii=False) if payload else None
        semantic = self.compute_semantic_value(payload)
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT OR IGNORE INTO event_log "
                    "(event_id, kind, payload, trace_id, created_at, semantic_value) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (event_id, kind, payload_json, trace_id, now, semantic),
                )
            return True
        except Exception as e:
            logger.error("EventLog put failed: %s", e)
            return False

    @staticmethod
    def compute_semantic_value(payload: Optional[dict]) -> int:
        """G2-P2: 语义价值 = 摘要锚点数（不 LLM 打分）。

        锚点 = cross_ref/cross_refs/references/anchors/refs 条目数
             + l2_summary 存在性（+1）。
        锚点多 → 永不减枝原文；锚点少 → 允许摘要化/丢弃。
        """
        if not payload:
            return 0
        anchors = 0
        for key in EventLog.ANCHOR_KEYS:
            v = payload.get(key)
            if isinstance(v, (list, tuple, set)):
                anchors += len(v)
            elif isinstance(v, dict):
                anchors += len(v)
            elif v:
                anchors += 1
        if payload.get("l2_summary"):
            anchors += 1
        return anchors

    def ack_event(self, event_id: str) -> bool:
        """Mark event as consumed (legacy single-consumer shortcut)."""
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

    # ────────────────────────────────────────────── #
    # G2-P1: per-subscriber 水位线
    # ────────────────────────────────────────────── #

    def register_consumer(self, consumer_id: str) -> bool:
        """注册消费者（幂等）。last_seq 从 0 开始。"""
        if not self._conn:
            return False
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO event_consumer (consumer_id, last_seq, updated_at) "
                "VALUES (?, 0, ?)",
                (consumer_id, time.time()),
            )
        return True

    def unregister_consumer(self, consumer_id: str) -> bool:
        """注销消费者。"""
        if not self._conn:
            return False
        with self._conn:
            self._conn.execute(
                "DELETE FROM event_consumer WHERE consumer_id=?", (consumer_id,)
            )
        return True

    def consumer_watermark(self, consumer_id: str) -> int:
        """返回消费者水位线（未注册返回 0）。"""
        if not self._conn:
            return 0
        row = self._conn.execute(
            "SELECT last_seq FROM event_consumer WHERE consumer_id=?", (consumer_id,)
        ).fetchone()
        return row[0] if row else 0

    def consumers(self) -> List[Dict[str, Any]]:
        """所有已注册消费者 + 水位线。"""
        if not self._conn:
            return []
        rows = self._conn.execute(
            "SELECT consumer_id, last_seq FROM event_consumer ORDER BY consumer_id"
        ).fetchall()
        return [{"consumer_id": r[0], "last_seq": r[1]} for r in rows]

    def event_seq(self, event_id: str) -> Optional[int]:
        """事件 rowid（单调递增，作为全局 seq）。"""
        if not self._conn:
            return None
        row = self._conn.execute(
            "SELECT rowid FROM event_log WHERE event_id=?", (event_id,)
        ).fetchone()
        return row[0] if row else None

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """按 event_id 直接查询（情景溯源 RECALL_SUBGRAPH_BRIDGE 用）。

        不依赖"未消费"水位线（replay_unconsumed 只扫 consumed=0 且
        ASC 排序会截断最新事件——溯源需直查）。
        """
        if not self._conn:
            return None
        row = self._conn.execute(
            "SELECT event_id, kind, payload, trace_id, created_at "
            "FROM event_log WHERE event_id=?",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "event_id": row[0],
            "kind": row[1],
            "payload": json.loads(row[2]) if row[2] else {},
            "trace_id": row[3],
            "created_at": row[4],
        }

    def ack_consumer(self, consumer_id: str, seq: int) -> bool:
        """per-subscriber 水位线前进（单调，只前进不回退）。"""
        if not self._conn:
            return False
        with self._conn:
            self._conn.execute(
                "UPDATE event_consumer SET last_seq = MAX(last_seq, ?), updated_at = ? "
                "WHERE consumer_id = ?",
                (seq, time.time(), consumer_id),
            )
        return True

    def replay_for_consumer(self, consumer_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """增量拉取：seq > 该消费者水位线的事件（含 event_id 用于 ack_consumer）。"""
        if not self._conn:
            return []
        wm = self.consumer_watermark(consumer_id)
        rows = self._conn.execute(
            "SELECT event_id, kind, payload, trace_id, created_at, rowid "
            "FROM event_log WHERE rowid > ? ORDER BY rowid ASC LIMIT ?",
            (wm, limit),
        ).fetchall()
        return [
            {
                "event_id": row[0],
                "kind": row[1],
                "payload": json.loads(row[2]) if row[2] else {},
                "trace_id": row[3],
                "created_at": row[4],
                "seq": row[5],
            }
            for row in rows
        ]

    def all_registered_consumed(self, seq: int) -> bool:
        """所有已注册消费者水位线 >= seq（空消费者集 = True 退化为 legacy 判据）。"""
        if not self._conn:
            return True
        consumers = self.consumers()
        if not consumers:
            return True
        return all(c["last_seq"] >= seq for c in consumers)

    def prunable_events(self, limit: int = 200, retention_sec: Optional[float] = None) -> List[Dict[str, Any]]:
        """G2-P3: 温减枝候选 = 全消费者已消费 + 超 retention（水位线判据优先，legacy 兜底）。"""
        if not self._conn:
            return []
        cutoff = time.time() - (retention_sec if retention_sec is not None else self._retention_sec)
        consumers = self.consumers()
        if consumers:
            min_wm = min(c["last_seq"] for c in consumers)
            rows = self._conn.execute(
                "SELECT event_id, kind, payload, trace_id, created_at, semantic_value, rowid "
                "FROM event_log WHERE rowid <= ? AND created_at < ? "
                "ORDER BY created_at ASC LIMIT ?",
                (min_wm, cutoff, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT event_id, kind, payload, trace_id, created_at, semantic_value, rowid "
                "FROM event_log WHERE consumed=1 AND created_at < ? "
                "ORDER BY created_at ASC LIMIT ?",
                (cutoff, limit),
            ).fetchall()
        return [
            {
                "event_id": r[0], "kind": r[1],
                "payload": json.loads(r[2]) if r[2] else {},
                "trace_id": r[3], "created_at": r[4],
                "semantic_value": r[5], "seq": r[6],
            }
            for r in rows
        ]

    def update_payload(self, event_id: str, payload: dict) -> bool:
        """减枝/摘要后回写 payload（保留 event_id/kind/trace/seq）。"""
        if not self._conn:
            return False
        payload_json = json.dumps(payload, ensure_ascii=False) if payload else None
        semantic = self.compute_semantic_value(payload)
        with self._conn:
            self._conn.execute(
                "UPDATE event_log SET payload=?, semantic_value=? WHERE event_id=?",
                (payload_json, semantic, event_id),
            )
        return True

    def cleanup_old(self) -> int:
        """Delete events older than retention period (legacy: only consumed=1)."""
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
        return {"total": total, "unconsumed": unconsumed,
                "consumers": len(self.consumers())}

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
