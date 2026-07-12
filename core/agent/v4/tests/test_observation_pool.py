"""Tests for ObservationPool."""
import pytest
from core.agent.v4.observation_compiler.pool import ObservationPool
from core.agent.v4.observation_compiler.models import ObservationBundle


class TestObservationPool:
    def test_put_and_get(self):
        pool = ObservationPool()
        bundle = ObservationBundle(bundle_id="b1", event_id="e1")
        pool.put(bundle)
        assert pool.get("b1") is bundle

    def test_get_nonexistent(self):
        pool = ObservationPool()
        assert pool.get("nonexistent") is None

    def test_get_by_event(self):
        pool = ObservationPool()
        b1 = ObservationBundle(bundle_id="b1", event_id="e1")
        b2 = ObservationBundle(bundle_id="b2", event_id="e1")
        pool.put(b1)
        pool.put(b2)
        results = pool.get_by_event("e1")
        assert len(results) == 2

    def test_evict_old_consumed(self):
        pool = ObservationPool(max_age_sec=0)
        b = ObservationBundle(bundle_id="b1", event_id="e1")
        pool.put(b)
        pool.mark_consumed("b1")
        removed = pool.evict_old(max_age_sec=-1)  # evict immediately
        assert pool.get("b1") is None

    def test_stats(self):
        pool = ObservationPool()
        pool.put(ObservationBundle(bundle_id="b1", event_id="e1"))
        s = pool.stats()
        assert s["total_bundles"] == 1
