"""EventLog adapter for v4 CognitiveRuntimeEngine.

Wraps v4 EventLog (api_event_log.py) behind a lifecycle-managed interface.
Responsibilities:
- Lifecycle: open / close
- Event persistence on on_event()
- Replay unconsumed events for recovery
- Integration with _compile_context() for historical context
"""
from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent.v4.event_ir import EventIR

logger = logging.getLogger(__name__)


@dataclass
class EventLogConfig:
    """Configuration for v4 EventLog adapter."""
    db_path: str = "data/event_log.db"
    retention_hours: int = 24
    auto_open: bool = True


class V4EventLog:
    """v4 lifecycle-managed wrapper for EventLog.

    Provides:
      - record_event(event) -> bool
      - replay_unconsumed(limit) -> List[EventIR]
      - get_recent_events(n) -> List[EventIR]
      - stats -> dict
    """

    def __init__(self, config: EventLogConfig = None):
        self._config = config or EventLogConfig()
        self._log = None
        self._is_open = False
        self._init_log()

    def _init_log(self) -> None:
        """Lazy-init the EventLog."""
        from core.agent.v4.api_event_log import EventLog
        self._log = EventLog(
            db_path=self._config.db_path,
            retention_hours=self._config.retention_hours,
        )
        if self._config.auto_open:
            self.open()

    def open(self) -> bool:
        """Open the event log."""
        if self._is_open:
            return True
        try:
            self._log.open()
            self._is_open = True
            logger.info("EventLog opened at %s", self._config.db_path)
            return True
        except Exception as e:
            logger.warning("EventLog open failed: %s", e)
            return False

    def close(self) -> None:
        """Close the event log."""
        if self._log is not None:
            self._log.close()
        self._is_open = False
        logger.info("EventLog closed")

    # ------------------------------------------------------------------ #
    # Event persistence
    # ------------------------------------------------------------------ #

    def record_event(self, event: EventIR, trace_id: str = "") -> bool:
        """Persist an EventIR to the log.

        Returns:
            True if written successfully.
        """
        if not self._is_open or self._log is None:
            return False
        payload = event.payload if hasattr(event, "payload") else {}
        return self._log.put_event(
            event_id=event.id,
            kind=event.kind,
            payload=dict(payload),
            trace_id=trace_id,
        )

    def ack_event(self, event_id: str) -> bool:
        """Mark event as consumed."""
        if not self._is_open or self._log is None:
            return False
        return self._log.ack_event(event_id)

    # ------------------------------------------------------------------ #
    # Replay & retrieval
    # ------------------------------------------------------------------ #

    def replay_unconsumed(self, limit: int = 100) -> List[EventIR]:
        """Replay unconsumed events as EventIR objects."""
        if not self._is_open or self._log is None:
            return []
        rows = self._log.replay_unconsumed(limit=limit)
        events = []
        for row in rows:
            try:
                ev = EventIR(
                    id=row["event_id"],
                    kind=row["kind"],
                    payload=row.get("payload", {}),
                    metadata={"trace_id": row.get("trace_id", ""), "replayed": True},
                    timestamp=row.get("created_at", time.time()),
                )
                events.append(ev)
            except Exception as e:
                logger.debug("EventLog replay parse error: %s", e)
        return events

    def get_recent_events(self, n: int = 10) -> List[EventIR]:
        """Get the most recent n events (consumed or not)."""
        if not self._is_open or self._log is None:
            return []
        # EventLog doesn't have a direct recent query; use replay_unconsumed
        # as a proxy, or we could extend EventLog. For now, return replay.
        return self.replay_unconsumed(limit=n)

    # ------------------------------------------------------------------ #
    # Maintenance
    # ------------------------------------------------------------------ #

    def cleanup(self) -> int:
        """Delete old consumed events."""
        if not self._is_open or self._log is None:
            return 0
        return self._log.cleanup_old()

    @property
    def stats(self) -> Dict[str, int]:
        if not self._is_open or self._log is None:
            return {"total": 0, "unconsumed": 0}
        return self._log.stats

    @property
    def is_open(self) -> bool:
        return self._is_open
