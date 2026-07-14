"""Cognitive Scheduler models: Task, Worker, WorkerPool, PathStateMachine."""
from __future__ import annotations
import time, threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional


class PathState(Enum):
    """Finite state machine states for a cognitive path."""
    IDLE = auto()
    RUNNING = auto()
    BACKLOGGED = auto()


class PathStateMachine:
    """Manages the lifecycle state of a single cognitive path.

    Valid transitions:
        IDLE -> RUNNING   (path starts execution)
        RUNNING -> IDLE   (path completes successfully, queue empty)
        RUNNING -> BACKLOGGED (queue depth exceeds threshold while running)
        BACKLOGGED -> IDLE (queue drained below threshold)
        BACKLOGGED -> RUNNING (path resumes execution from backlog)
    """

    _VALID_TRANSITIONS: Dict[PathState, set] = {
        PathState.IDLE: {PathState.RUNNING},
        PathState.RUNNING: {PathState.IDLE, PathState.BACKLOGGED},
        PathState.BACKLOGGED: {PathState.IDLE, PathState.RUNNING},
    }

    def __init__(
        self,
        path_name: str,
        backlog_threshold: int = 10,
        initial_state: PathState = PathState.IDLE,
    ):
        self.path_name = path_name
        self.backlog_threshold = backlog_threshold
        self._state = initial_state
        self._lock = threading.Lock()
        self._state_changed_at = time.time()
        self._history: List[tuple] = []

    @property
    def state(self) -> PathState:
        """Current state of the path."""
        with self._lock:
            return self._state

    def transition(self, new_state: PathState) -> bool:
        """Attempt to transition to *new_state*.

        Returns:
            True if the transition was valid and applied, False otherwise.
        """
        with self._lock:
            if new_state not in self._VALID_TRANSITIONS.get(self._state, set()):
                return False
            old_state = self._state
            self._state = new_state
            self._state_changed_at = time.time()
            self._history.append((old_state, new_state, time.time()))
            return True

    def on_queue_depth(self, depth: int) -> PathState:
        """Update state based on current queue depth.

        Returns:
            The (possibly updated) current state.
        """
        with self._lock:
            if self._state == PathState.RUNNING and depth > self.backlog_threshold:
                self._state = PathState.BACKLOGGED
                self._state_changed_at = time.time()
                self._history.append((PathState.RUNNING, PathState.BACKLOGGED, time.time()))
            elif self._state == PathState.BACKLOGGED and depth <= self.backlog_threshold:
                self._state = PathState.IDLE
                self._state_changed_at = time.time()
                self._history.append((PathState.BACKLOGGED, PathState.IDLE, time.time()))
            return self._state

    def time_in_state(self) -> float:
        """Seconds spent in the current state."""
        with self._lock:
            return time.time() - self._state_changed_at

    def can_run(self) -> bool:
        """Return True if the path is eligible to start execution."""
        with self._lock:
            return self._state in (PathState.IDLE, PathState.BACKLOGGED)

    def is_running(self) -> bool:
        """Return True if the path is currently executing."""
        with self._lock:
            return self._state == PathState.RUNNING

    def history(self) -> List[tuple]:
        """Return a copy of the state transition history."""
        with self._lock:
            return list(self._history)

    def __repr__(self) -> str:
        return f"<PathStateMachine {self.path_name} state={self._state.name}>"


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
