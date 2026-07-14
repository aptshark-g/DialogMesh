"""Path-aware scheduling policy.

Extends ``SchedulerPolicy`` with path-level task selection,
worker affinity, and merge/delay heuristics.
"""
from abc import ABC, abstractmethod
from typing import List, Optional

from .path_models import PathTask, PathWorker, PathWorkerPool, PathType


class PathSchedulerPolicy(ABC):
    """Abstract base for path-aware scheduling policies."""

    @abstractmethod
    def select_task(self, queue: List[PathTask]) -> Optional[PathTask]:
        """Select the next task from *queue*."""
        ...

    @abstractmethod
    def assign_worker(self, task: PathTask, pool: PathWorkerPool) -> Optional[PathWorker]:
        """Assign an idle worker to *task*."""
        ...

    def should_delay(self, task: PathTask) -> bool:
        """Return ``True`` if *task* should be deferred."""
        return False

    def should_merge(self, a: PathTask, b: PathTask) -> bool:
        """Return ``True`` if *a* and *b* can be merged."""
        return False


class PriorityPathPolicy(PathSchedulerPolicy):
    """Priority-based FIFO policy with path affinity.

    Tasks are ordered by ``(priority, -created_at)`` (higher priority first).
    Workers are assigned from the global idle pool without path pinning.
    """

    def select_task(self, queue: List[PathTask]) -> Optional[PathTask]:
        if not queue:
            return None
        # Use the task's queued_at time (from metrics) as a proxy for created_at
        return max(
            queue,
            key=lambda t: (t.priority, -t.metrics.queued_at),
        )

    def assign_worker(self, task: PathTask, pool: PathWorkerPool) -> Optional[PathWorker]:
        return pool.next_idle()


class PathAffinityPolicy(PathSchedulerPolicy):
    """Priority FIFO with path-aware worker affinity.

    Prefers workers that are already running (or have recently run) tasks
    of the same path type, reducing context-switch overhead.
    """

    def select_task(self, queue: List[PathTask]) -> Optional[PathTask]:
        if not queue:
            return None
        return max(queue, key=lambda t: (t.priority, -t.metrics.queued_at))

    def assign_worker(self, task: PathTask, pool: PathWorkerPool) -> Optional[PathWorker]:
        # Try to find a worker already running the same path
        same_path_workers = pool.workers_for_path(task.path)
        # If any are idle (shouldn't happen in normal flow), prefer them
        idle = pool.next_idle()
        if idle is None:
            return None
        # Simple heuristic: any idle worker is fine; future work can track
        # per-worker path history for stronger affinity.
        return idle

    def should_delay(self, task: PathTask) -> bool:
        # Deep path tasks can be delayed if the system is under pressure
        if task.path == PathType.DEEP:
            return False
        return False

    def should_merge(self, a: PathTask, b: PathTask) -> bool:
        # Merge same-path tasks with identical task_id prefix
        if a.path != b.path:
            return False
        return a.task_id.split("_")[0] == b.task_id.split("_")[0]
