"""Scheduler policies."""
from abc import ABC, abstractmethod
from typing import List, Optional
from .models import Task, Worker, WorkerPool


class SchedulerPolicy(ABC):
    @abstractmethod
    def select_task(self, queue: List[Task]) -> Optional[Task]: ...
    @abstractmethod
    def assign_worker(self, task: Task, pool: WorkerPool) -> Optional[Worker]: ...
    def should_delay(self, task: Task) -> bool: return False
    def should_merge(self, a: Task, b: Task) -> bool: return False


class PriorityFIFOPolicy(SchedulerPolicy):
    def select_task(self, queue):
        return max(queue, key=lambda t: (t.priority, -t.created_at)) if queue else None

    def assign_worker(self, task, pool): return pool.next_idle()


class PathAwarePolicy(SchedulerPolicy):
    """Path-aware scheduling policy that respects path state machines.

    Tasks are selected from queues whose paths are in IDLE or BACKLOGGED state.
    Running paths are skipped to prevent resource contention.
    """

    def __init__(self, path_states: dict = None):
        """Initialize with optional path state mapping.

        Args:
            path_states: Mapping of path_name -> PathStateMachine.
        """
        self._path_states = path_states or {}

    def set_path_states(self, path_states: dict) -> None:
        """Update the path state mapping (called by scheduler on each tick)."""
        self._path_states = path_states

    def _get_path_name(self, task: Task) -> str:
        """Infer path name from task_id prefix."""
        tid = task.task_id
        if tid.startswith("obs_"): return "async"
        elif tid.startswith("hyp_"): return "slow"
        elif tid.startswith("kn_"): return "slow"
        elif tid.startswith("sk_"): return "deep"
        elif tid.startswith("maintenance"): return "slow"
        return "async"

    def select_task(self, queue: List[Task]) -> Optional[Task]:
        """Select the highest-priority task from paths that can run."""
        eligible = []
        for task in queue:
            path_name = self._get_path_name(task)
            psm = self._path_states.get(path_name)
            if psm is None or psm.can_run():
                eligible.append(task)
        return max(eligible, key=lambda t: (t.priority, -t.created_at)) if eligible else None

    def assign_worker(self, task: Task, pool: WorkerPool) -> Optional[Worker]:
        return pool.next_idle()

    def should_delay(self, task: Task) -> bool:
        """Delay tasks whose path is currently RUNNING."""
        path_name = self._get_path_name(task)
        psm = self._path_states.get(path_name)
        return psm is not None and psm.is_running()
