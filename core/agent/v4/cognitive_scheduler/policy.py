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
