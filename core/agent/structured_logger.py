# -*- coding: utf-8 -*-
"""
core/agent/structured_logger.py
────────────────────────────────
Structured JSON logging (P2-2). Outputs JSON Lines — one JSON object per line.

Compatible with: ELK, Loki, Fluentd, CloudWatch Logs, etc.
"""

from __future__ import annotations

import sys
import time
import json
import threading
from typing import Dict, Any, Optional
from pathlib import Path


class StructuredLogger:
    """
    JSON Lines logger with standard fields.

    Fields:
        - timestamp: ISO 8601
        - level: DEBUG | INFO | WARNING | ERROR | CRITICAL
        - event: event type (e.g., "request", "llm_call", "security_block")
        - session_id: session identifier
        - turn_index: turn number
        - context: arbitrary context dict
        - metrics: metrics snapshot
        - message: human-readable message
    """

    LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

    def __init__(
        self,
        name: str = "memorygraph",
        sink=None,           # file path or file-like object; default stdout
        min_level: str = "INFO",
        include_metrics: bool = True,
    ):
        self.name = name
        self.min_level = self.LEVELS.get(min_level, 20)
        self.include_metrics = include_metrics
        self._lock = threading.Lock()
        if sink is None:
            self._file = sys.stdout
        elif isinstance(sink, (str, Path)):
            self._file = open(sink, "a", encoding="utf-8")
        else:
            self._file = sink

    def _write(self, record: Dict[str, Any]):
        with self._lock:
            self._file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            self._file.flush()

    def _log(
        self,
        level: str,
        event: str,
        message: str,
        session_id: Optional[str] = None,
        turn_index: Optional[int] = None,
        context: Optional[Dict] = None,
        metrics: Optional[Dict] = None,
    ):
        if self.LEVELS.get(level, 0) < self.min_level:
            return
        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()) + f".{int(time.time() * 1000) % 1000:03d}Z",
            "logger": self.name,
            "level": level,
            "event": event,
            "message": message,
        }
        if session_id is not None:
            record["session_id"] = session_id
        if turn_index is not None:
            record["turn_index"] = turn_index
        if context:
            record["context"] = context
        if metrics and self.include_metrics:
            record["metrics"] = metrics
        self._write(record)

    # ── Convenience methods ─────────────────────────────────────────────────

    def debug(self, event: str, message: str, **kwargs):
        self._log("DEBUG", event, message, **kwargs)

    def info(self, event: str, message: str, **kwargs):
        self._log("INFO", event, message, **kwargs)

    def warning(self, event: str, message: str, **kwargs):
        self._log("WARNING", event, message, **kwargs)

    def error(self, event: str, message: str, **kwargs):
        self._log("ERROR", event, message, **kwargs)

    def critical(self, event: str, message: str, **kwargs):
        self._log("CRITICAL", event, message, **kwargs)

    def close(self):
        if self._file is not sys.stdout:
            self._file.close()
