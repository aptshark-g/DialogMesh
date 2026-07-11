"""Lightweight monitor for ContextCompiler pipeline observability."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict, List


class CompilerMonitor:
    """Records per-stage metrics for ContextCompiler pipeline."""

    def __init__(self, session_id: str = ""):
        self._session_id = session_id
        self._stages: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._turn_count = 0
        self._start_time = time.time()

    def record(self, stage: str, event: str, data: Dict[str, Any],
               duration_ms: float = 0.0):
        self._turn_count += 1
        entry = {
            "turn": self._turn_count,
            "event": event,
            "timestamp": time.time() - self._start_time,
            "data": data,
            "duration_ms": duration_ms,
        }
        self._stages[stage].append(entry)

    def summary(self) -> Dict[str, Any]:
        return {
            "session_id": self._session_id,
            "total_turns": self._turn_count,
            "elapsed_sec": time.time() - self._start_time,
            "stages": {k: len(v) for k, v in self._stages.items()},
        }

    def stage_log(self, stage: str, last_n: int = 5) -> List[Dict]:
        entries = self._stages.get(stage, [])
        return entries[-last_n:]

    def reset(self):
        self._stages.clear()
        self._turn_count = 0
        self._start_time = time.time()
