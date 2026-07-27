"""Tests for EventIR and EventBus concurrency."""
import time, threading, pytest
from core.agent.events.event_ir import EventIR, EventBus, DialogAdapter


class TestEventIR:
    def test_creation(self):
        e = EventIR(id="e1", kind="dialog.message", payload={"text": "hello"})
        assert e.kind == "dialog.message"
        assert e.payload["text"] == "hello"

    def test_timestamp_auto(self):
        e = EventIR(id="e2", kind="test", payload={})
        assert e.timestamp > 0


class TestDialogAdapter:
    def test_adapt_basic(self):
        a = DialogAdapter()
        e = a.adapt("hello world", session_id="s1", turn_number=1)
        assert e.kind == "dialog.message"
        assert e.payload["text"] == "hello world"
        assert e.refs["turn_number"] == 1


class TestEventBus:
    def test_publish_and_consume(self):
        bus = EventBus(capacity=100)
        for i in range(10):
            bus.publish(EventIR(id=f"e{i}", kind="test", payload={}))
        batch = bus.consume_batch(max_events=5)
        assert len(batch) == 5
        batch2 = bus.consume_batch(max_events=10)
        assert len(batch2) == 5

    def test_overflow_drops_oldest(self):
        bus = EventBus(capacity=10)
        for i in range(15):
            bus.publish(EventIR(id=f"e{i}", kind="test", payload={}))
        h = bus.health()
        assert h["stats"]["dropped"] >= 4
        assert h["pending"] <= 10

    def test_concurrent_publish(self):
        bus = EventBus(capacity=500)
        def writer(start, count):
            for i in range(start, start + count):
                bus.publish(EventIR(id=f"e{i}", kind="test", payload={}))
        threads = []
        for t in range(4):
            th = threading.Thread(target=writer, args=(t * 100, 100))
            threads.append(th)
        for th in threads: th.start()
        for th in threads: th.join()
        h = bus.health()
        assert h["stats"]["published"] == 400

    def test_subscriber_callback(self):
        bus = EventBus(capacity=100)
        received = []
        def collector(batch):
            received.extend(batch)
        bus.subscribe(collector)
        for i in range(5):
            bus.publish(EventIR(id=f"e{i}", kind="test", payload={}))
        t = bus.start_consumer(batch_size=10, poll_interval=0.05)
        time.sleep(0.3)
        bus.shutdown()
        t.join(timeout=1)
        assert len(received) >= 5

    def test_health_shows_stats(self):
        bus = EventBus(capacity=50)
        bus.publish(EventIR(id="h1", kind="test", payload={}))
        h = bus.health()
        assert "pending" in h
        assert "capacity" in h
        assert "stats" in h
        assert h["stats"]["published"] >= 1
