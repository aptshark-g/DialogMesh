"""Path-aware scheduler models: PathTask, PathWorker, PathWorkerPool.

Extends the base cognitive scheduler with path-aware state tracking,
typed metrics, and configuration-driven parameterization.
"""
from __future__ import annotations
import time
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class PathTaskStatus(str, Enum):
    """Lifecycle states for a PathTask."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PathState(str, Enum):
    """Finite state machine states for a processing path."""

    IDLE = "idle"
    RUNNING = "running"
    BACKLOGGED = "backlogged"


class PathType(str, Enum):
    """Canonical path identifiers in the v4 runtime."""

    ASYNC = "async"
    SLOW = "slow"
    DEEP = "deep"
    FAST = "fast"


@dataclass
class PathTaskMetrics:
    """Per-task execution metrics."""

    queued_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    retries: int = 0
    latency_ms: float = 0.0

    @property
    def wait_ms(self) -> float:
        """Time spent waiting in queue (ms)."""
        if self.started_at is None:
            return (time.time() - self.queued_at) * 1000.0
        return (self.started_at - self.queued_at) * 1000.0

    @property
    def exec_ms(self) -> float:
        """Execution time (ms)."""
        if self.started_at is None or self.completed_at is None:
            return 0.0
        return (self.completed_at - self.started_at) * 1000.0


@dataclass
class PathWorkerStats:
    """Aggregated worker statistics."""

    success: int = 0
    failures: int = 0
    cancelled: int = 0
    total_exec_ms: float = 0.0

    @property
    def total_tasks(self) -> int:
        return self.success + self.failures + self.cancelled

    @property
    def success_rate(self) -> float:
        total = self.total_tasks
        return self.success / total if total > 0 else 0.0


class PathTask(ABC):
    """Path-aware task with typed metadata and metrics tracking.

    Backward-compatible with the base ``Task`` interface while adding
    path-type awareness, metrics, and richer status tracking.
    """

    def __init__(
        self,
        task_id: str = "",
        path: PathType = PathType.ASYNC,
        priority: int = 0,
        max_retries: int = 3,
        timeout_ms: int = 30000,
    ):
        self.task_id = task_id or f"task_{id(self)}"
        self.path = path
        self.priority = priority
        self.max_retries = max_retries
        self.timeout_ms = timeout_ms
        self.status = PathTaskStatus.PENDING
        self.metrics = PathTaskMetrics()
        self.result: Any = None
        self.error: Optional[Exception] = None

    @abstractmethod
    def execute(self) -> Any:
        """Execute the task payload. Must be implemented by subclasses."""
        ...

    def on_complete(self, result: Any) -> None:
        """Hook called on successful execution."""
        self.status = PathTaskStatus.DONE
        self.result = result
        self.metrics.completed_at = time.time()

    def on_failure(self, error: Exception) -> None:
        """Hook called on execution failure."""
        self.status = PathTaskStatus.FAILED
        self.error = error
        self.metrics.completed_at = time.time()

    def on_cancel(self) -> None:
        """Hook called when the task is cancelled."""
        self.status = PathTaskStatus.CANCELLED
        self.metrics.completed_at = time.time()

    def mark_started(self) -> None:
        """Mark the task as started and record timing."""
        self.status = PathTaskStatus.RUNNING
        self.metrics.started_at = time.time()

    def mark_pending(self) -> None:
        """Reset task to pending (used for retries)."""
        self.status = PathTaskStatus.PENDING
        self.metrics.retries += 1


class CallablePathTask(PathTask):
    """Convenience task wrapping a callable."""

    def __init__(
        self,
        fn: Callable[[], Any],
        path: PathType = PathType.ASYNC,
        priority: int = 0,
        name: str = "",
    ):
        super().__init__(
            task_id=name or f"callable_{id(fn)}",
            path=path,
            priority=priority,
        )
        self._fn = fn

    def execute(self) -> Any:
        return self._fn()


class PathWorker:
    """Worker capable of executing PathTask instances with metrics tracking."""

    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self.status: str = "idle"
        self.current_task: Optional[PathTask] = None
        self.stats = PathWorkerStats()

    def run(self, task: PathTask) -> Any:
        """Execute *task*, updating status and stats along the way.

        Args:
            task: The ``PathTask`` to execute.

        Returns:
            The result of ``task.execute()``.

        Raises:
            Exception: Re-raised from ``task.execute()`` after updating stats.
        """
        self.status = "running"
        self.current_task = task
        task.mark_started()

        start = time.time()
        try:
            result = task.execute()
            task.on_complete(result)
            self.stats.success += 1
            return result
        except Exception as exc:
            task.on_failure(exc)
            self.stats.failures += 1
            if task.max_retries > 0:
                task.max_retries -= 1
                task.mark_pending()
            raise
        finally:
            elapsed = (time.time() - start) * 1000.0
            self.stats.total_exec_ms += elapsed
            task.metrics.latency_ms = elapsed
            self.status = "idle"
            self.current_task = None


class PathWorkerPool:
    """Thread-safe pool of ``PathWorker`` instances.

    Replaces the simple ``WorkerPool`` with path-aware worker allocation
    and per-path idle tracking.
    """

    def __init__(self, size: int = 4):
        self._workers = [PathWorker(f"w{i}") for i in range(size)]
        self._idle = list(self._workers)
        self._lock = threading.Lock()

    def next_idle(self) -> Optional[PathWorker]:
        """Acquire an idle worker, if any."""
        with self._lock:
            return self._idle.pop(0) if self._idle else None

    def release(self, worker: PathWorker) -> None:
        """Return a worker to the idle pool."""
        with self._lock:
            if worker not in self._idle:
                self._idle.append(worker)

    def idle_count(self) -> int:
        """Number of currently idle workers."""
        with self._lock:
            return len(self._idle)

    def stats(self) -> Dict[str, Any]:
        """Aggregate pool statistics."""
        return {
            "total": len(self._workers),
            "idle": self.idle_count(),
            "success": sum(w.stats.success for w in self._workers),
            "failures": sum(w.stats.failures for w in self._workers),
            "cancelled": sum(w.stats.cancelled for w in self._workers),
            "total_exec_ms": sum(w.stats.total_exec_ms for w in self._workers),
        }

    def workers_for_path(self, path: PathType) -> List[PathWorker]:
        """Return workers currently assigned to *path* (by running task)."""
        return [
            w
            for w in self._workers
            if w.current_task is not None and w.current_task.path == path
        ]
