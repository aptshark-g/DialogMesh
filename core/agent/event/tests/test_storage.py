"""Tests for Phase 3 StorageLayer."""
import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from core.agent.event.storage import HotStore, WarmStore, ColdStore, StorageLayer


class TestHotStore:
    def test_set_get(self):
        h = HotStore(max_size=10)
        h.set("a", 42)
        assert h.get("a") == 42

    def test_ttl_expires(self):
        h = HotStore(max_size=10, default_ttl_sec=0)
        h.set("b", "data", ttl_sec=1)
        import time; time.sleep(1.5)  # past TTL
        assert h.get("b", "MISSING") == "MISSING"

    def test_ttl_not_expired(self):
        h = HotStore(max_size=10, default_ttl_sec=999)
        h.set("b", "data")
        assert h.get("b") == "data"

    def test_lru_eviction(self):
        h = HotStore(max_size=3)
        for i in range(5):
            h.set(f"key{i}", i)
        assert h.get("key0", "evicted") == "evicted"
        assert h.get("key4") == 4

    def test_delete(self):
        h = HotStore()
        h.set("x", 1)
        assert h.delete("x")
        assert not h.delete("x")

    def test_keys_pattern(self):
        h = HotStore()
        h.set("session_1", {})
        h.set("session_2", {})
        h.set("other", {})
        assert len(h.keys("session")) == 2

    def test_stats(self):
        h = HotStore()
        h.set("a", 1)
        s = h.stats()
        assert s["size"] == 1


class TestWarmStore:
    def setup_method(self):
        self.db = WarmStore(db_path=":memory:")

    def test_insert_query_events(self):
        self.db.insert_event("pcr", {"zone": "MIXED"}, "s1")
        events = self.db.query_events(kind="pcr")
        assert len(events) == 1
        assert events[0]["payload"]["zone"] == "MIXED"

    def test_insert_behavior(self):
        rid = self.db.insert_behavior("navigate", "A", "B")
        assert rid > 0

    def test_insert_association(self):
        rid = self.db.insert_association("concept1", "concept2", "related", 0.8)
        assert rid > 0

    def test_insert_meta(self):
        self.db.insert_meta("dec1", "profile_update", "accepted")
        stats = self.db.stats()
        assert stats["tables"]["meta_decisions"] == 1

    def test_stats(self):
        self.db.insert_event("test", {}, "s1")
        s = self.db.stats()
        assert s["tables"]["events"] == 1

    def test_multiple_sessions(self):
        self.db.insert_event("msg", {}, "s1")
        self.db.insert_event("msg", {}, "s2")
        assert len(self.db.query_events(session_id="s1")) == 1
        assert len(self.db.query_events(session_id="s2")) == 1

    def teardown_method(self):
        self.db.close()


class TestColdStore:
    def setup_method(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.cold = ColdStore(self.tmp)

    def test_save_load(self):
        self.cold.save("test.json", {"key": "value"})
        data = self.cold.load("test.json")
        assert data["key"] == "value"

    def test_load_missing(self):
        assert self.cold.load("nonexistent.json", "fallback") == "fallback"

    def test_delete(self):
        self.cold.save("del.json", {})
        assert self.cold.delete("del.json")
        assert not self.cold.exists("del.json") if hasattr(self.cold, 'exists') else True

    def test_list(self):
        self.cold.save("a.json", {})
        self.cold.save("b.json", {})
        files = self.cold.list()
        assert len(files) >= 2

    def test_stats(self):
        self.cold.save("s.json", {"x": "y"})
        s = self.cold.stats()
        assert s["files"] >= 1
        assert s["total_bytes"] > 0


class TestStorageLayer:
    def test_create(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            s = StorageLayer(data_dir=d, db_path=":memory:")
            stats = s.stats()
            assert "hot" in stats
            assert "warm" in stats
            assert "cold" in stats
            s.close()

    def test_save_load_tiers(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            s = StorageLayer(data_dir=d, db_path=":memory:")
            s.save_state("profile.json", {"dims": {"O": 0.5}}, tier="cold")
            data = s.load_state("profile.json", tier="cold")
            assert data["dims"]["O"] == 0.5
            s.close()

    def test_hot_tier(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            s = StorageLayer(data_dir=d, db_path=":memory:")
            s.save_state("ctx", {"session": "s1"}, tier="hot")
            assert s.load_state("ctx", tier="hot")["session"] == "s1"
            s.close()
