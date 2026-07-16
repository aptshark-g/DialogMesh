"""EventLog package — EventIR-aware persistence layer for v4."""
from __future__ import annotations

from core.agent.v4.event_log.adapter import (
    EventLogAdapter,
    EventLogEntry,
    EventLogReplayAdapter,
    DEFAULT_DB_PATH,
    DEFAULT_RETENTION_HOURS,
)

__all__ = [
    "EventLogAdapter",
    "EventLogEntry",
    "EventLogReplayAdapter",
    "DEFAULT_DB_PATH",
    "DEFAULT_RETENTION_HOURS",
]
