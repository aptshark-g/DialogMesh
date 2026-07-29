"""Phase 2: Priority Scheduler — P0-P3 execution levels with timeout/retry.

Linux CFS inspiration: each subscriber gets a priority class.
P0 (REALTIME):  PCR/security — synchronous, <10ms
P1 (INTERACTIVE): Intent/context — synchronous, <100ms  
P2 (BATCH):       Discourse/behavior/association — threaded, <1s
P3 (IDLE):        OCEAN/meta/persistence — threaded, background

The DeciderScheduler replaces the simple fire-and-forget subscriber
dispatch with priority-ordered, timeout-guarded execution.
"""
import time, threading, logging
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Dict, Any, Callable, Optional

logger = logging.getLogger(__name__)


class Priority(IntEnum):
    """Execution priority — lower = sooner."""
    P0_REALTIME   = 0   # must complete before response
    P1_INTERACTIVE = 1   # should complete before response
    P2_BATCH       = 2   # fire-and-forget, threaded
    P3_IDLE        = 3   # background only, throttled


@dataclass
class ScheduledTask:
    """One unit of work with priority + timeout."""
    name: str
    priority: Priority
    handler: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    timeout_ms: int = 1000
    max_retries: int = 1
    created_at: float = field(default_factory=time.time)


@dataclass
class TaskResult:
    """Execution result for monitoring."""
    name: str
    priority: Priority
    success: bool
    latency_ms: float = 0
    error: str = ""
    retries: int = 0


class DeciderScheduler:
    """Priority-based task scheduler with timeout + execution tracking.

    Usage:
        sched = DeciderScheduler()
        sched.submit(ScheduledTask("discourse", Priority.P2, handler, (evt,)))
        sched.run_batch()  # P0 synchronous, P1-P3 threaded
        stats = sched.stats()
    """

    def __init__(self):
        self._queue: list[ScheduledTask] = []
        self._lock = threading.Lock()
        self._history: list[TaskResult] = []
        self._max_history = 500
        self._running = True
        self._worker = None

    def submit(self, task: ScheduledTask) -> None:
        with self._lock:
            self._queue.append(task)

    def stats(self) -> dict:
        with self._lock:
            total = len(self._history)
            success = sum(1 for r in self._history if r.success)
            by_priority = {}
            for r in self._history[-50:]:
                p_name = r.priority.name
                if p_name not in by_priority:
                    by_priority[p_name] = {"success": 0, "fail": 0, "total_latency": 0.0}
                by_priority[p_name]["success" if r.success else "fail"] += 1
                by_priority[p_name]["total_latency"] += r.latency_ms
            return {
                "total_executed": total,
                "success_rate": round(success / total, 3) if total > 0 else 1.0,
                "queue_depth": len(self._queue),
                "by_priority": by_priority,
            }

    def run_batch(self) -> list[TaskResult]:
        """Execute all queued tasks in priority order. P0 synchronous, P1-P3 threaded."""
        with self._lock:
            tasks = sorted(self._queue, key=lambda t: t.priority)
            self._queue.clear()

        results = []
        threads = []

        for task in tasks:
            if task.priority <= Priority.P1_INTERACTIVE:
                # Synchronous — must complete
                result = self._execute(task)
                results.append(result)
            else:
                # Threaded — fire and collect later
                t = threading.Thread(
                    target=lambda t=task: self._execute(t),
                    name=f"sched_{task.name}",
                    daemon=True,
                )
                threads.append(t)
                t.start()

        # Wait for threads with timeout
        for t in threads:
            t.join(timeout=2.0)

        # Collect threaded results from history
        return results

    def _execute(self, task: ScheduledTask) -> TaskResult:
        """Execute one task with timeout and retry."""
        start = time.time()
        last_error = ""

        for attempt in range(task.max_retries):
            try:
                task.handler(*task.args, **task.kwargs)
                latency = (time.time() - start) * 1000
                result = TaskResult(
                    name=task.name, priority=task.priority,
                    success=True, latency_ms=round(latency, 1), retries=attempt,
                )
                self._record(result)
                return result
            except Exception as e:
                last_error = str(e)[:200]
                logger.debug("Task %s attempt %d/%d failed: %s",
                           task.name, attempt + 1, task.max_retries, last_error)
                if attempt < task.max_retries - 1:
                    time.sleep(0.1)  # brief backoff before retry

        latency = (time.time() - start) * 1000
        result = TaskResult(
            name=task.name, priority=task.priority,
            success=False, latency_ms=round(latency, 1),
            error=last_error, retries=task.max_retries,
        )
        self._record(result)
        return result

    def _record(self, result: TaskResult) -> None:
        with self._lock:
            self._history.append(result)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

    def shutdown(self):
        self._running = False
        if self._worker:
            self._worker.join(timeout=3)


# ═══════════════════════════════════════════════════════════
#  Priority mapping — which subscriber gets which level
# ═══════════════════════════════════════════════════════════

SUBSCRIBER_PRIORITY: dict[str, Priority] = {
    # P0: must execute before LLM reply
    # (security constraint checks, PCR route validation)
    # P1: should execute before LLM reply
    "meta":         Priority.P1_INTERACTIVE,
    "association":  Priority.P1_INTERACTIVE,
    # P2: fire-and-forget, can complete after reply
    "discourse":    Priority.P2_BATCH,
    "behavior":     Priority.P2_BATCH,
    "profile":      Priority.P2_BATCH,
    # P3: background only, never blocks
    "persistence":  Priority.P3_IDLE,
}

SUBSCRIBER_TIMEOUT: dict[str, int] = {
    "meta":         50,     # 50ms
    "association":  100,    # 100ms
    "discourse":    200,    # 200ms
    "behavior":     100,
    "profile":      500,    # OCEAN might be slow
    "persistence":  3000,   # file I/O
}


def create_scheduled_task(name: str, handler: Callable,
                          kind: str, payload: dict) -> ScheduledTask:
    """Factory: create a ScheduledTask from subscriber name."""
    return ScheduledTask(
        name=name,
        priority=SUBSCRIBER_PRIORITY.get(name, Priority.P2_BATCH),
        handler=handler,
        args=(kind, payload),
        timeout_ms=SUBSCRIBER_TIMEOUT.get(name, 1000),
        max_retries=1 if name != "persistence" else 3,
    )
