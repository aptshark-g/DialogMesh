"""Async LLM Dispatch — non-blocking LLM calls via thread pool.

P0 Performance: prevent single LLM Activity from blocking the Tick cycle.
Thread pool submits tasks, engine collects results next Tick.
"""
from __future__ import annotations
import concurrent.futures, threading, time, logging
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PendingCall:
    id: str
    future: concurrent.futures.Future
    callback: Callable
    submitted_at: float = field(default_factory=time.time)
    timeout_s: float = 30


class AsyncDispatcher:
    """Thread-pool backed LLM call dispatcher.

    Usage:
      dispatcher = AsyncDispatcher(max_workers=3)
      dispatcher.submit(lambda: llm.generate(req), on_complete=handle_response)
      # ... next Tick ...
      dispatcher.collect()  # fire callbacks for completed calls
    """

    def __init__(self, max_workers: int = 3):
        self._pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="dm-llm"
        )
        self._pending: Dict[str, PendingCall] = {}
        self._counter = 0
        self._lock = threading.Lock()

    def submit(self, fn: Callable, callback: Callable = None,
               timeout_s: float = 30) -> Optional[str]:
        """Submit LLM call to thread pool. Returns immediately."""
        self._counter += 1
        call_id = f"async_{self._counter}_{int(time.time()*1000)}"
        
        future = self._pool.submit(fn)
        pending = PendingCall(id=call_id, future=future, callback=callback or (lambda r: None),
                             timeout_s=timeout_s)
        
        with self._lock:
            self._pending[call_id] = pending
        
        return call_id

    def collect(self, max_results: int = 5) -> int:
        """Collect completed calls. Fire callbacks. Returns count handled."""
        completed = []
        timed_out = []
        
        with self._lock:
            for call_id, pc in list(self._pending.items()):
                if pc.future.done():
                    completed.append(call_id)
                elif time.time() - pc.submitted_at > pc.timeout_s:
                    timed_out.append(call_id)
        
        count = 0
        for call_id in completed:
            pc = self._pending.pop(call_id, None)
            if not pc: continue
            try:
                result = pc.future.result(timeout=0.1)
                pc.callback(result)
                count += 1
            except Exception as e:
                logger.error("Async call %s failed: %s", call_id, e)
                pc.callback(None)
                count += 1

        for call_id in timed_out:
            self._pending.pop(call_id, None)
            logger.warning("Async call %s timed out", call_id)

        return count

    def pending(self) -> int:
        return len(self._pending)

    def shutdown(self):
        self._pool.shutdown(wait=False, cancel_futures=True)
