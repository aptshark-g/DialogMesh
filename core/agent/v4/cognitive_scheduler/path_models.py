"""Path-aware scheduler models: PathTask, PathWorkerPool.

Extends base models with path-aware scheduling capabilities.
"""
from __future__ import annotations
import time, threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .models import Task, Worker, WorkerPool


class PathTask(Task):
    """A task bound to a specific cognitive path.

    Args:
        path_name: "async" | "slow" | "deep"
        fn: Callable to execute
        priority: Lower number = higher priority
        name: Task identifier
    """

    def __init__(self, path_name: str, fn: Callable, priority: int = 0,
                 name: str = "", timeout_ms: int = 30000):
        super().__init__(task_id=name or f"{path_name}_{id(fn)}",
                         priority=priority, timeout_ms=timeout_ms)
        self.path_name = path_name
        self._fn = fn

    def execute(self):
        return self._fn()


class PathWorkerPool(WorkerPool):
    """Worker pool with per-path worker reservation.

    Ensures Slow Path tasks don't starve Async Path tasks
    by reserving workers per path.
    """

    def __init__(self, size: int = 4, path_reservation: Dict[str, int] = None):
        super().__init__(size=size)
        # Default: reserve 1 worker for slow, 1 for deep, rest for async
        self._path_reservation = path_reservation or {
            "slow": 1,
            "deep": 1,
        }
        self._path_usage: Dict[str, int] = {}
        self._path_lock = threading.Lock()

    def can_assign(self, path_name: str) -> bool:
        """Check if a path can claim a worker."""
        with self._path_lock:
            reserved = self._path_reservation.get(path_name, 0)
            used = self._path_usage.get(path_name, 0)
            # If below reservation, always allow
            if used < reserved:
                return True
            # Otherwise, check if idle workers available
            return self.idle_count() > 0

    def assign(self, path_name: str) -> Optional[Worker]:
        """Assign a worker for a specific path."""
        if not self.can_assign(path_name):
            return None
        worker = self.next_idle()
        if worker:
            with self._path_lock:
                self._path_usage[path_name] = self._path_usage.get(path_name, 0) + 1
        return worker

    def release(self, worker: Worker, path_name: str = ""):
        """Release worker back to pool."""
        super().release(worker)
        if path_name:
            with self._path_lock:
                self._path_usage[path_name] = max(0, self._path_usage.get(path_name, 0) - 1)

    def path_usage(self) -> Dict[str, int]:
        with self._path_lock:
            return dict(self._path_usage)
