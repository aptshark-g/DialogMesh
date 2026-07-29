"""Tests for Phase 2 DeciderScheduler — priority execution + timeout/retry."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from core.agent.event.scheduler import (
    Priority, ScheduledTask, TaskResult, DeciderScheduler,
    SUBSCRIBER_PRIORITY, SUBSCRIBER_TIMEOUT, create_scheduled_task,
)


class TestPriority:
    def test_priority_order(self):
        assert Priority.P0_REALTIME < Priority.P1_INTERACTIVE
        assert Priority.P1_INTERACTIVE < Priority.P2_BATCH
        assert Priority.P2_BATCH < Priority.P3_IDLE

    def test_subscriber_priority_mapping(self):
        assert SUBSCRIBER_PRIORITY["discourse"] == Priority.P2_BATCH
        assert SUBSCRIBER_PRIORITY["meta"] == Priority.P1_INTERACTIVE
        assert SUBSCRIBER_PRIORITY["persistence"] == Priority.P3_IDLE

    def test_subscriber_timeout_mapping(self):
        assert SUBSCRIBER_TIMEOUT["meta"] == 50
        assert SUBSCRIBER_TIMEOUT["persistence"] == 3000


class TestScheduledTask:
    def test_create(self):
        def handler(): pass
        t = ScheduledTask("test", Priority.P1_INTERACTIVE, handler)
        assert t.name == "test"
        assert t.priority == Priority.P1_INTERACTIVE
        assert t.timeout_ms == 1000

    def test_factory(self):
        handled = []
        def my_handler(kind, payload):
            handled.append((kind, payload))

        t = create_scheduled_task("discourse", my_handler, "pcr", {"data": 1})
        assert t.name == "discourse"
        assert t.priority == Priority.P2_BATCH
        assert t.timeout_ms == 200
        assert t.max_retries == 1

        # Verify handler works
        t.handler(*t.args, **t.kwargs)
        assert len(handled) == 1
        assert handled[0] == ("pcr", {"data": 1})


class TestDeciderScheduler:
    def test_empty_run(self):
        s = DeciderScheduler()
        results = s.run_batch()
        assert results == []

    def test_sync_execution(self):
        s = DeciderScheduler()
        results_store = []

        def sync_handler(data):
            results_store.append(data)

        s.submit(ScheduledTask("a", Priority.P0_REALTIME, sync_handler, ("hello",)))
        s.submit(ScheduledTask("b", Priority.P1_INTERACTIVE, sync_handler, ("world",)))

        results = s.run_batch()
        assert len(results) == 2
        assert all(r.success for r in results)
        assert results_store == ["hello", "world"]

    def test_priority_ordering(self):
        s = DeciderScheduler()
        order = []

        def ordered(name):
            order.append(name)

        # P3 submitted first, P0 last — should execute P0 first
        s.submit(ScheduledTask("p3", Priority.P3_IDLE, ordered, ("p3",)))
        s.submit(ScheduledTask("p1", Priority.P1_INTERACTIVE, ordered, ("p1",)))
        s.submit(ScheduledTask("p0", Priority.P0_REALTIME, ordered, ("p0",)))

        results = s.run_batch()
        # P0 and P1 are synchronous; P3 is threaded so may complete after
        sync_ordered = [e for e in order if e in ("p0", "p1")]
        assert sync_ordered == ["p0", "p1"]

    def test_failure_tracking(self):
        s = DeciderScheduler()

        def fail():
            raise RuntimeError("boom")

        s.submit(ScheduledTask("fail", Priority.P0_REALTIME, fail))
        results = s.run_batch()
        assert len(results) == 1
        assert not results[0].success
        assert "boom" in results[0].error
        assert results[0].retries == 1

    def test_retry_success(self):
        s = DeciderScheduler()
        attempts = []

        def flaky():
            attempts.append(1)
            if len(attempts) < 2:
                raise RuntimeError("first fail")

        s.submit(ScheduledTask("flaky", Priority.P0_REALTIME, flaky, max_retries=3))
        results = s.run_batch()
        assert results[0].success
        assert results[0].retries == 1  # 0-indexed: failed first, succeeded second
        assert len(attempts) == 2

    def test_threaded_execution(self):
        s = DeciderScheduler()
        storage = []

        def bg_task(name):
            time.sleep(0.05)
            storage.append(name)

        s.submit(ScheduledTask("bg", Priority.P2_BATCH, bg_task, ("bg",)))
        s.run_batch()
        # Threaded tasks complete within join timeout
        assert "bg" in storage

    def test_stats(self):
        s = DeciderScheduler()
        s.submit(ScheduledTask("ok", Priority.P0_REALTIME, lambda: None))
        s.submit(ScheduledTask("fail", Priority.P0_REALTIME, lambda: (_ for _ in ()).throw(RuntimeError("x"))))
        s.run_batch()
        stats = s.stats()
        assert stats["total_executed"] == 2
        assert stats["success_rate"] == 0.5
        assert "P0_REALTIME" in stats["by_priority"]

    def test_queue_depth(self):
        s = DeciderScheduler()
        s.submit(ScheduledTask("a", Priority.P0_REALTIME, lambda: None))
        assert s.stats()["queue_depth"] == 1
        s.run_batch()
        assert s.stats()["queue_depth"] == 0

    def test_shutdown(self):
        s = DeciderScheduler()
        s.shutdown()
        assert not s._running
