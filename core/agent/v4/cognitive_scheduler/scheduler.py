"""CognitiveScheduler: unified scheduling loop."""
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from .models import Task, Worker, WorkerPool, WorkerStats
from .policy import SchedulerPolicy, PriorityFIFOPolicy


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


class CognitiveScheduler:
    def __init__(self, policy: SchedulerPolicy = None,
                 pool: WorkerPool = None, monitor: SchedulerMonitor = None,
                 registry=None):
        self.policy = policy or PriorityFIFOPolicy()
        self.pool = pool or WorkerPool(size=4)
        self.monitor = monitor or SchedulerMonitor()
        self.queue: List[Task] = []
        self._running = False
        self._registry = registry

    def submit(self, task: Task): self.queue.append(task)

    def tick(self) -> List[Any]:
        results = []
        task = self.policy.select_task(self.queue)
        if not task: return results
        worker = self.policy.assign_worker(task, self.pool)
        if not worker: return results
        self.queue.remove(task)
        try: results.append(worker.run(task))
        except Exception: pass
        finally: self.pool.release(worker)
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

    def stop(self): self._running = False

    def stats(self) -> dict:
        return {"queue_size": len(self.queue), "workers": self.pool.stats(),
                "monitor_snapshots": self.monitor.snapshot_count(),
                "suggestions": self.monitor.suggest()}
