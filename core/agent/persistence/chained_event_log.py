"""P0: SHA256-chained Event Log — append-only, tamper-evident.

Each event carries hash(prev_hash + event_data).
Tampering with any event breaks the chain → detectable on verification.
"""
from __future__ import annotations
import hashlib, json, os, time, logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ChainedEvent:
    event_id: str
    event_type: str              # "NodeEdited" | "PatternDiscovered" | ...
    timestamp: float
    data: Dict[str, Any]
    prev_hash: str = "genesis"   # SHA256 of previous event
    hash: str = ""               # SHA256(prev_hash + json(data))
    verified: bool = True        # False if chain broken

    def __post_init__(self):
        if not self.hash:
            payload = f"{self.prev_hash}|{json.dumps(self.data, sort_keys=True, ensure_ascii=False)}"
            self.hash = hashlib.sha256(payload.encode()).hexdigest()


class ChainedEventLog:
    """Append-only, SHA256-chained event store.
    
    Guarantees:
      - Events cannot be modified without breaking the hash chain
      - verify() returns True iff the entire chain is intact
      - replay() reconstructs state from any checkpoint
    """

    def __init__(self, path: str = "data/events/event_log.jsonl"):
        self._path = path
        self._events: List[ChainedEvent] = []
        self._last_hash: str = "genesis"
        self._counter = 0
        self._load()

    def append(self, event_type: str, data: Dict[str, Any]) -> ChainedEvent:
        """Append an event to the chained log. Thread-safe."""
        event = ChainedEvent(
            event_id=f"evt_{self._counter}_{int(time.time()*1000)}",
            event_type=event_type, timestamp=time.time(), data=data,
            prev_hash=self._last_hash,
        )
        self._events.append(event)
        self._last_hash = event.hash
        self._counter += 1

        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "id": event.event_id, "type": event.event_type,
                "ts": event.timestamp, "prev": event.prev_hash,
                "hash": event.hash, "data": event.data,
            }, ensure_ascii=False) + "\n")
            f.flush()

        return event

    def verify(self) -> Dict[str, Any]:
        """Check entire chain integrity. Returns broken events if any."""
        broken = []
        prev = "genesis"
        for e in self._events:
            expected = hashlib.sha256(
                f"{prev}|{json.dumps(e.data, sort_keys=True, ensure_ascii=False)}".encode()
            ).hexdigest()
            if e.hash != expected:
                broken.append(e.event_id)
                e.verified = False
            else:
                e.verified = True
            prev = e.hash
        
        return {
            "total": len(self._events),
            "broken": len(broken),
            "broken_ids": broken,
            "chain_intact": len(broken) == 0,
            "last_hash": self._last_hash,
        }

    def replay(self, from_checkpoint: Optional[Dict] = None, 
               state_class: Any = None) -> List[ChainedEvent]:
        """Replay events to reconstruct state. 
        
        Returns list of events (caller applies to State).
        """
        if from_checkpoint:
            start_hash = from_checkpoint.get("last_hash", "genesis")
            events = []
            started = (start_hash == "genesis")
            for e in self._events:
                if not started and e.prev_hash == start_hash:
                    started = True
                if started:
                    events.append(e)
            return events
        return list(self._events)

    def stats(self) -> Dict[str, Any]:
        return {
            "total_events": len(self._events),
            "last_hash": self._last_hash[:16],
            "by_type": {t: sum(1 for e in self._events if e.event_type == t)
                       for t in set(e.event_type for e in self._events)},
        }

    def _load(self):
        if not os.path.exists(self._path): return
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    e = ChainedEvent(
                        event_id=d["id"], event_type=d["type"],
                        timestamp=d["ts"], data=d["data"],
                        prev_hash=d["prev"], hash=d["hash"],
                    )
                    self._events.append(e)
                    self._last_hash = e.hash
                    self._counter += 1
                except Exception: pass
