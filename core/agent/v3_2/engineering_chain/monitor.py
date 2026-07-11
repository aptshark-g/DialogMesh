"""Engineering chain pipeline monitor."""
from __future__ import annotations
import time
from collections import defaultdict
from typing import Any, Dict, List


class EngineeringMonitor:

    def __init__(self, session_id: str = ""):
        self._session_id = session_id
        self._stages: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._turn_count = 0
        self._start_time = time.time()

    def record(self, stage: str, event: str, data: Dict[str, Any], duration_ms: float = 0.0):
        self._turn_count += 1
        self._stages[stage].append({"turn": self._turn_count, "event": event,
                                     "data": data, "duration_ms": duration_ms})

    def summary(self) -> Dict[str, Any]:
        return {"session_id": self._session_id, "total_turns": self._turn_count,
                "elapsed_sec": time.time() - self._start_time,
                "stages": {k: len(v) for k, v in self._stages.items()}}
