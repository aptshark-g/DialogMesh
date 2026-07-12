"""Cognitive Scheduler models: Task, Worker, WorkerPool."""
from __future__ import annotations
import time, threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


class Task(ABC):
    def __init__(self, task_id: str = "", priority: int = 0,
                 max_retries: int = 3, timeout_ms: int = 30000):
        self.task_id = task_id or f"task_{id(self)}"
        self.priority = priority
        self.status = "pending"
        self.max_retries = max_retries
        self.timeout_ms = timeout_ms
        self.created_at = time.time()
        self.completed_at: Optional[float] = None

    @abstractmethod
    def execute(self) -> Any: ...

    def on_complete(self, result: Any) -> None: self.status = "done"; self.completed_at = time.time()
    def on_failure(self, error: Exception) -> None: self.status = "failed"
    def on_cancel(self) -> None: self.status = "cancelled"


class CallableTask(Task):
    def __init__(self, fn: Callable, priority: int = 0, name: str = ""):
        super().__init__(task_id=name or f"callable_{id(fn)}", priority=priority)
        self._fn = fn
    def execute(self): return self._fn()


@dataclass
class WorkerStats:
    success: int = 0; failures: int = 0


class Worker:
    def __init__(self, worker_id: str):
        self.worker_id = worker_id; self.status = "idle"
        self.current_task: Optional[Task] = None
        self.stats = WorkerStats()

    def run(self, task: Task) -> Any:
        self.status = "running"; self.current_task = task
        try:
            result = task.execute()
            task.on_complete(result); self.stats.success += 1
            return result
        except Exception as e:
            task.on_failure(e); self.stats.failures += 1
            if task.max_retries > 0: task.max_retries -= 1; task.status = "pending"
            raise
        finally: self.status = "idle"; self.current_task = None


class WorkerPool:
    def __init__(self, size: int = 4):
        self._workers = [Worker(f"w{i}") for i in range(size)]
        self._idle = list(self._workers); self._lock = threading.Lock()

    def next_idle(self) -> Optional[Worker]:
        with self._lock:
            return self._idle.pop(0) if self._idle else None

    def release(self, worker: Worker):
        with self._lock: self._idle.append(worker)

    def idle_count(self) -> int:
        with self._lock: return len(self._idle)

    def stats(self) -> dict:
        return {"total": len(self._workers), "idle": self.idle_count(),
                "success": sum(w.stats.success for w in self._workers),
                "failures": sum(w.stats.failures for w in self._workers)}
