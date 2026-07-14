"""PathAwareScheduler: Path-aware cognitive task scheduler.

Replaces simple FIFO with path-aware scheduling, worker reservation,
and backpressure handling.
"""
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .models import Task, Worker, WorkerPool
from .path_models import PathTask, PathWorkerPool
from .path_policy import PathAwarePolicy, SchedulerPolicy
from .path_trigger_policy import PathStateMachine, PathState


@dataclass
class QueueSnapshot:
    pending: int = 0; running: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)


class SchedulerMonitor:
    def __init__(self):
        self._snapshots: List[QueueSnapshot] = []

    def snapshot(self, queue_size: int, running: int,
                 by_type: Dict[str, int] = None) -> QueueSnapshot:
        snap = QueueSnapshot(pending=queue_size, running=running,
                             by_type=by_type or {})
        self._snapshots.append(snap)
        return snap

    def suggest(self) -> List[str]:
        suggestions = []
        if len(self._snapshots) >= 3:
            s = self._snapshots
            obs_growth = s[-1].by_type.get("observation", 0) - s[0].by_type.get("observation", 0)
            if obs_growth > 10: suggestions.append("Observation queue growing")
            hyp_growth = s[-1].by_type.get("hypothesis", 0) - s[0].by_type.get("hypothesis", 0)
            if hyp_growth > 5: suggestions.append("Hypothesis backlog")
        return suggestions

    def snapshot_count(self) -> int: return len(self._snapshots)


class PathAwareScheduler:
    """Path-aware scheduler with state machine integration.

    Args:
        policy: Scheduling policy (default: PathAwarePolicy)
        pool: Worker pool (default: PathWorkerPool with 4 workers)
        monitor: Scheduler monitor
        state_machine: PathStateMachine for path state tracking
    """

    def __init__(self, policy: SchedulerPolicy = None,
                 pool: PathWorkerPool = None, monitor: SchedulerMonitor = None,
                 state_machine: PathStateMachine = None):
        self.policy = policy or PathAwarePolicy()
        self.pool = pool or PathWorkerPool(size=4)
        self.monitor = monitor or SchedulerMonitor()
        self.state_machine = state_machine or PathStateMachine()
        self.queue: List[PathTask] = []
        self._running = False

    def submit(self, task: PathTask):
        """Submit a path-bound task."""
        self.queue.append(task)

    def tick(self) -> List[Any]:
        """Process one task from the queue."""
        results = []

        # Update policy with current path states
        if isinstance(self.policy, PathAwarePolicy):
            self.policy._path_states = {
                name: record.state.value
                for name, record in self.state_machine._paths.items()
            }

        task = self.policy.select_task(self.queue)
        if not task:
            return results

        worker = self.policy.assign_worker(task, self.pool)
        if not worker:
            return results

        self.queue.remove(task)

        # Mark path as running
        path_name = getattr(task, 'path_name', 'unknown')
        self.state_machine.mark_trigger(path_name)

        try:
            result = worker.run(task)
            results.append(result)
            self.state_machine.mark_success(path_name)
        except Exception:
            self.state_machine.mark_failure(path_name)
        finally:
            if isinstance(self.pool, PathWorkerPool):
                self.pool.release(worker, path_name)
            else:
                self.pool.release(worker)

        # Monitor snapshot
        by_type = {"observation": 0, "hypothesis": 0, "knowledge": 0, "skill": 0}
        for t in self.queue:
            tid = t.task_id
            if "obs" in tid: by_type["observation"] += 1
            elif "hyp" in tid: by_type["hypothesis"] += 1
            elif "kn" in tid: by_type["knowledge"] += 1
            elif "sk" in tid: by_type["skill"] += 1
        self.monitor.snapshot(len(self.queue), sum(1 for w in self.pool._workers if w.status == "running"), by_type)
        return results

    def run_loop(self, max_ticks: int = -1, interval_ms: int = 100):
        self._running = True; ticks = 0
        while self._running and (max_ticks < 0 or ticks < max_ticks):
            self.tick(); ticks += 1; time.sleep(interval_ms / 1000.0)

    def stop(self):
        self._running = False

    def stats(self) -> dict:
        return {
            "queue_size": len(self.queue),
            "workers": self.pool.stats(),
            "path_states": self.state_machine.stats(),
            "monitor_snapshots": self.monitor.snapshot_count(),
            "suggestions": self.monitor.suggest(),
        }
