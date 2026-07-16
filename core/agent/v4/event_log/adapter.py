"""EventLog adapter for v4 — wraps api_event_log with EventIR integration.

Provides:
  - EventLogAdapter: persists EventIR → SQLite via EventLog
  - EventLogReplayAdapter: replays unconsumed events back into the engine
  - engine integration: CognitiveRuntimeEngine.start() auto-opens EventLog

Upstream:   EventBus.publish() → EventLogAdapter.put_event()
Downstream: replay_unconsumed() → EventIR → on_event()
"""
from __future__ import annotations
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.agent.v4.event_ir import EventIR
from core.agent.v4.api_event_log import EventLog

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "data/event_log.db"
DEFAULT_RETENTION_HOURS = 24


@dataclass
class EventLogEntry:
    """Normalized entry returned by replay; mirrors EventIR fields."""
    event_id: str
    kind: str
    payload: dict = field(default_factory=dict)
    refs: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    timestamp: float = 0.0
    trace_id: str = ""

    def to_event_ir(self) -> EventIR:
        """Convert back to EventIR for re-injection into engine."""
        return EventIR(
            id=self.event_id,
            kind=self.kind,
            payload=dict(self.payload),
            refs=dict(self.refs),
            metadata=dict(self.metadata),
            timestamp=self.timestamp,
        )

    @classmethod
    def from_event_ir(cls, event: EventIR, trace_id: str = "") -> "EventLogEntry":
        return cls(
            event_id=event.id,
            kind=event.kind,
            payload=event.payload if hasattr(event, "payload") else {},
            refs=event.refs if hasattr(event, "refs") else {},
            metadata=event.metadata if hasattr(event, "metadata") else {},
            timestamp=event.timestamp if hasattr(event, "timestamp") else time.time(),
            trace_id=trace_id,
        )


class EventLogAdapter:
    """Wraps api_event_log.EventLog with EventIR serialization.

    Lifecycle:
        adapter = EventLogAdapter()
        adapter.open()          # creates DB + WAL mode
        adapter.put_event(event_ir, trace_id="session_001")
        adapter.ack_event(event_id)
        entries = adapter.replay_unconsumed(limit=100)
        adapter.close()
    """

    def __init__(self, db_path: str = None, retention_hours: int = DEFAULT_RETENTION_HOURS):
        self._db_path = db_path or os.environ.get("DIALOGMESH_EVENTLOG_PATH", DEFAULT_DB_PATH)
        self._retention_hours = retention_hours
        self._event_log: Optional[EventLog] = None
        self._open = False

    # ---- Lifecycle ----

    def open(self) -> None:
        """Open the underlying SQLite EventLog."""
        if self._open:
            return
        self._event_log = EventLog(
            db_path=self._db_path,
            retention_hours=self._retention_hours,
        )
        self._event_log.open()
        self._open = True
        logger.info("EventLogAdapter opened at %s", self._db_path)

    def close(self) -> None:
        """Close the underlying EventLog."""
        if self._event_log is not None:
            self._event_log.close()
            self._event_log = None
        self._open = False
        logger.info("EventLogAdapter closed")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # ---- Write ----

    def put_event(self, event: EventIR, trace_id: str = "") -> bool:
        """Persist an EventIR. Returns False on failure."""
        if not self._open or self._event_log is None:
            logger.warning("EventLog not open, dropping event %s", getattr(event, "id", "?"))
            return False

        payload = event.payload if hasattr(event, "payload") else {}
        # Merge refs + metadata into payload for round-trip fidelity
        enriched_payload = dict(payload)
        enriched_payload["_refs"] = event.refs if hasattr(event, "refs") else {}
        enriched_payload["_metadata"] = event.metadata if hasattr(event, "metadata") else {}
        enriched_payload["_timestamp"] = event.timestamp if hasattr(event, "timestamp") else time.time()

        return self._event_log.put_event(
            event_id=event.id,
            kind=event.kind,
            payload=enriched_payload,
            trace_id=trace_id,
        )

    # ---- Ack ----

    def ack_event(self, event_id: str) -> bool:
        """Mark event as consumed."""
        if not self._open or self._event_log is None:
            return False
        return self._event_log.ack_event(event_id)

    # ---- Read / Replay ----

    def replay_unconsumed(self, limit: int = 100) -> List[EventLogEntry]:
        """Return unconsumed events as EventLogEntry, ordered by creation time."""
        if not self._open or self._event_log is None:
            return []

        rows = self._event_log.replay_unconsumed(limit=limit)
        entries: List[EventLogEntry] = []
        for row in rows:
            payload = row.get("payload", {})
            # Extract round-trip fields if present
            refs = payload.pop("_refs", {}) if isinstance(payload, dict) else {}
            metadata = payload.pop("_metadata", {}) if isinstance(payload, dict) else {}
            timestamp = payload.pop("_timestamp", row.get("created_at", 0.0)) if isinstance(payload, dict) else row.get("created_at", 0.0)

            entries.append(EventLogEntry(
                event_id=row["event_id"],
                kind=row["kind"],
                payload=payload,
                refs=refs,
                metadata=metadata,
                timestamp=timestamp,
                trace_id=row.get("trace_id", ""),
            ))
        return entries

    # ---- Maintenance ----

    def cleanup_old(self) -> int:
        """Delete consumed events older than retention period."""
        if not self._open or self._event_log is None:
            return 0
        return self._event_log.cleanup_old()

    @property
    def stats(self) -> Dict[str, int]:
        if not self._open or self._event_log is None:
            return {"total": 0, "unconsumed": 0}
        return self._event_log.stats

    @property
    def is_open(self) -> bool:
        return self._open


class EventLogReplayAdapter:
    """Replays unconsumed EventLog entries back into the engine.

    Usage:
        replay = EventLogReplayAdapter(event_log_adapter, engine)
        replay.replay_all()   # acks each event after successful on_event()
    """

    def __init__(self, event_log: EventLogAdapter, on_event_fn: Callable[[EventIR], Optional[str]]):
        self._event_log = event_log
        self._on_event = on_event_fn
        self._replayed_count = 0
        self._failed_count = 0

    def replay_all(self, limit: int = 100, auto_ack: bool = True) -> Dict[str, int]:
        """Replay unconsumed events through the engine.

        Args:
            limit: Max events to replay.
            auto_ack: If True, ack event after successful on_event().

        Returns:
            {"replayed": int, "failed": int, "remaining": int}
        """
        entries = self._event_log.replay_unconsumed(limit=limit)
        replayed = 0
        failed = 0

        for entry in entries:
            event = entry.to_event_ir()
            try:
                self._on_event(event)
                replayed += 1
                if auto_ack:
                    self._event_log.ack_event(entry.event_id)
            except Exception as e:
                logger.warning("Replay failed for %s: %s", entry.event_id, e)
                failed += 1

        self._replayed_count += replayed
        self._failed_count += failed
        remaining = self._event_log.stats.get("unconsumed", 0)

        logger.info(
            "Replay complete: %d replayed, %d failed, %d remaining",
            replayed, failed, remaining,
        )
        return {"replayed": replayed, "failed": failed, "remaining": remaining}

    @property
    def replayed_count(self) -> int:
        return self._replayed_count

    @property
    def failed_count(self) -> int:
        return self._failed_count
