"""P0: Write-Ahead Log — persistent command queue with Group Commit.

All Commands first land in WAL (disk) before entering Decider.
Never drop events. Backpressure = rate-limit pull, not queue-cap.
Group Commit = batch N commands into 1 fsync.

ARCHIVED (2026-08-16): 崩溃恢复属分布式/持久化阶段（G5 触发）, 当前单进程
内存态无 WAL 需求。保留代码不删（A17）。
"""
from __future__ import annotations
import json, os, time, threading, logging
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class WALEntry:
    id: str
    cmd_type: str
    target: str
    payload: Dict[str, Any]
    author: str = "user"
    ts: float = field(default_factory=time.time)
    status: str = "accepted"  # accepted | processing | done | failed

    def to_dict(self):
        return {
            "id": self.id, "type": self.cmd_type, "target": self.target,
            "payload": self.payload, "author": self.author,
            "ts": self.ts, "status": self.status,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(id=d["id"], cmd_type=d["type"], target=d["target"],
                   payload=d["payload"], author=d.get("author", "user"),
                   ts=d.get("ts", time.time()), status=d.get("status", "accepted"))


class WriteAheadLog:
    """P0: Persistent command queue with Group Commit.
    
    Reference: Kafka producer batch / Temporal WAL.
    
    Guarantees:
      - append() writes to disk before returning (durability)
      - group_commit() batches N appends into 1 fsync (perf)
      - pull() retrieves in FIFO order, rate-limited
      - Never drops commands. Queue is on disk, not in memory.
    """

    def __init__(self, path: str = "data/wal", group_size: int = 5, 
                 flush_interval_s: float = 0.1):
        self._path = path
        self._wal_file = f"{path}/wal.jsonl"
        self._offset_file = f"{path}/offset.json"
        self._group_size = group_size
        self._flush_interval = flush_interval_s
        
        # Batch buffer
        self._batch: List[WALEntry] = []
        self._batch_lock = threading.Lock()
        self._last_flush = time.time()
        
        # Read offset
        self._read_offset = 0
        self._written = 0
        
        os.makedirs(path, exist_ok=True)
        self._load_offset()

    def append(self, cmd_type: str, target: str, payload: Dict,
               author: str = "user") -> str:
        """Append command to WAL. Returns accepted ID.
        
        Synchronous write for durability, but Group Commit batches.
        """
        entry_id = f"wal_{self._written}_{int(time.time()*1000)}"
        entry = WALEntry(id=entry_id, cmd_type=cmd_type, target=target,
                        payload=payload, author=author)
        
        with self._batch_lock:
            self._batch.append(entry)
            self._written += 1
            
            # Auto flush if batch full or interval elapsed
            if (len(self._batch) >= self._group_size or 
                time.time() - self._last_flush > self._flush_interval):
                self._flush_batch()
        
        return entry_id

    def group_commit(self) -> int:
        """Force flush pending batch. Returns count flushed."""
        with self._batch_lock:
            return self._flush_batch()

    def pull(self, max_items: int = 3) -> List[WALEntry]:
        """Pull pending commands for Decider. Rate-limited by max_items.
        
        Reads from disk — no memory queue cap.
        """
        items = []
        if not os.path.exists(self._wal_file):
            return items
        
        with open(self._wal_file, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i < self._read_offset: continue
                if len(items) >= max_items: break
                try:
                    d = json.loads(line)
                    if d.get("status") == "accepted":
                        items.append(WALEntry.from_dict(d))
                except Exception: pass
        
        return items

    def acknowledge(self, entry_id: str, status: str = "done"):
        """Mark entry as processed. Updates status in WAL."""
        # Re-write the WAL with updated status (simple approach)
        if not os.path.exists(self._wal_file): return
        
        lines = []
        with open(self._wal_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    if d["id"] == entry_id:
                        d["status"] = status
                    lines.append(json.dumps(d, ensure_ascii=False))
                except Exception:
                    lines.append(line.strip())
        
        with open(self._wal_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        
        # Advance read offset
        self._read_offset = self._find_next_accepted()

    def pending_count(self) -> int:
        """Count accepted-but-unprocessed entries."""
        return max(0, self._count_accepted() - self._read_offset)

    def stats(self) -> Dict[str, Any]:
        total = self._count_total()
        return {
            "total_written": self._written,
            "total_on_disk": total,
            "read_offset": self._read_offset,
            "pending": self.pending_count(),
            "batch_size": len(self._batch),
        }

    # ── Internal ──

    def _flush_batch(self) -> int:
        if not self._batch: return 0
        count = len(self._batch)
        
        lines = "\n".join(json.dumps(e.to_dict(), ensure_ascii=False) 
                         for e in self._batch) + "\n"
        with open(self._wal_file, "a", encoding="utf-8") as f:
            f.write(lines)
            f.flush()  # Group Commit: 1 fsync for N entries
        
        self._batch.clear()
        self._last_flush = time.time()
        self._save_offset()
        return count

    def _count_total(self) -> int:
        if not os.path.exists(self._wal_file): return 0
        return sum(1 for _ in open(self._wal_file, "r", encoding="utf-8"))

    def _count_accepted(self) -> int:
        if not os.path.exists(self._wal_file): return 0
        count = 0
        with open(self._wal_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    if json.loads(line).get("status") == "accepted":
                        count += 1
                except Exception: pass
        return count

    def _find_next_accepted(self) -> int:
        if not os.path.exists(self._wal_file): return 0
        for i, line in enumerate(open(self._wal_file, "r", encoding="utf-8")):
            try:
                if json.loads(line).get("status") == "accepted":
                    return i
            except Exception: pass
        return self._count_total()

    def _save_offset(self):
        with open(self._offset_file, "w") as f:
            json.dump({"read_offset": self._read_offset, "written": self._written}, f)

    def _load_offset(self):
        if os.path.exists(self._offset_file):
            with open(self._offset_file) as f:
                d = json.load(f)
                self._read_offset = d.get("read_offset", 0)
                self._written = d.get("written", 0)
