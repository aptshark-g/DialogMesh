"""Path-aware scheduler policies.

Replaces PriorityFIFOPolicy with path-aware scheduling.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from .models import Task, Worker, WorkerPool
from .path_models import PathTask, PathWorkerPool


class SchedulerPolicy(ABC):
    @abstractmethod
    def select_task(self, queue: List[Task]) -> Optional[Task]: ...
    @abstractmethod
    def assign_worker(self, task: Task, pool: WorkerPool) -> Optional[Worker]: ...
    def should_delay(self, task: Task) -> bool: return False
    def should_merge(self, a: Task, b: Task) -> bool: return False


class PriorityFIFOPolicy(SchedulerPolicy):
    """Original FIFO policy (kept for backward compatibility)."""
    def select_task(self, queue):
        return max(queue, key=lambda t: (t.priority, -t.created_at)) if queue else None

    def assign_worker(self, task, pool): return pool.next_idle()


class PathAwarePolicy(SchedulerPolicy):
    """Path-aware scheduling policy.

    Prioritizes:
      1. Async Path tasks (latency-sensitive)
      2. Non-backlogged paths
      3. Older tasks within same path
    """

    PATH_PRIORITY = {
        "async": 0,   # Highest
        "slow": 1,
        "deep": 2,    # Lowest
    }

    def __init__(self, path_states: Dict[str, str] = None):
        self._path_states = path_states or {}

    def select_task(self, queue: List[Task]) -> Optional[Task]:
        if not queue:
            return None

        # Filter out tasks from backlogged paths
        eligible = [
            t for t in queue
            if self._path_states.get(getattr(t, 'path_name', ''), 'idle') != 'backlogged'
        ]
        if not eligible:
            # All backlogged — pick oldest
            eligible = queue

        # Sort by: path priority, then task priority, then age
        def sort_key(t):
            path = getattr(t, 'path_name', '')
            path_prio = self.PATH_PRIORITY.get(path, 99)
            return (path_prio, t.priority, -t.created_at)

        eligible.sort(key=sort_key)
        return eligible[0]

    def assign_worker(self, task: Task, pool: WorkerPool) -> Optional[Worker]:
        if isinstance(pool, PathWorkerPool):
            path = getattr(task, 'path_name', '')
            return pool.assign(path)
        return pool.next_idle()
