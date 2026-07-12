"""Tests for CognitiveScheduler."""
import pytest, time
from core.agent.v4.cognitive_scheduler.models import Task, CallableTask, Worker, WorkerPool
from core.agent.v4.cognitive_scheduler.policy import PriorityFIFOPolicy
from core.agent.v4.cognitive_scheduler.scheduler import CognitiveScheduler, SchedulerMonitor


class TestWorkerPool:
    def test_next_idle(self):
        pool = WorkerPool(size=2)
        w = pool.next_idle()
        assert w is not None; assert w.status == "idle"
        pool.release(w)

    def test_stats(self):
        pool = WorkerPool(size=2)
        s = pool.stats()
        assert s["total"] == 2; assert s["idle"] == 2


class TestCognitiveScheduler:
    def test_submit_and_tick(self):
        s = CognitiveScheduler(pool=WorkerPool(size=2))
        results = []
        s.submit(CallableTask(lambda: results.append(1), priority=3))
        s.submit(CallableTask(lambda: results.append(2), priority=5))
        s.tick(); s.tick()
        assert len(results) >= 1

    def test_priority_order(self):
        s = CognitiveScheduler(pool=WorkerPool(size=1))
        order = []
        s.submit(CallableTask(lambda: order.append("low"), priority=1))
        s.submit(CallableTask(lambda: order.append("high"), priority=9))
        s.tick()
        assert order[0] == "high"

    def test_stats(self):
        s = CognitiveScheduler(pool=WorkerPool(size=2))
        s.submit(CallableTask(lambda: None, priority=5))
        s.tick()
        st = s.stats()
        assert st["queue_size"] == 0
        assert "workers" in st


class TestSchedulerMonitor:
    def test_snapshot(self):
        m = SchedulerMonitor()
        m.snapshot(5, 2, {"obs": 3, "hyp": 2})
        assert m.snapshot_count() == 1

    def test_suggestions(self):
        m = SchedulerMonitor()
        m.snapshot(5, 2, {"observation": 1})
        m.snapshot(5, 2, {"observation": 5})
        m.snapshot(5, 2, {"observation": 20})
        assert len(m.suggest()) >= 1
