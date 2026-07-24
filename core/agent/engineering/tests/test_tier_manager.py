"""Tests for GraphTierManager auto-migration."""
import tempfile, os, pytest
from core.agent.persistence.unified_graph_store import UnifiedGraphStore
from core.agent.persistence.graph_tier_manager import GraphTierManager

@pytest.fixture
def tier_system():
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = db.name; db.close()
    s = UnifiedGraphStore(db_path=path)
    tm = GraphTierManager(s)
    yield s, tm
    s.close()
    os.unlink(path)

class TestTierMigration:
    def test_cold_promoted_on_access(self, tier_system):
        s, tm = tier_system
        s.save_node("n1", "test", "T", {}, tier="C")
        for _ in range(3):
            tm.on_access("n1")
        n = s.load_node("n1")
        assert n["tier"] == "W"

    def test_warm_promoted_on_heavy_access(self, tier_system):
        s, tm = tier_system
        s.save_node("n2", "test", "T", {}, tier="W")
        for _ in range(10):
            tm.on_access("n2")
        n = s.load_node("n2")
        assert n["tier"] == "H"

    def test_cold_data_stripped_after_gc(self, tier_system):
        s, tm = tier_system
        s.save_node("nc", "test", "T", {"big": "data" * 100}, tier="C")
        tm._strip_cold_data()
        n = s.load_node("nc")
        assert n["data"] == {}

    def test_gc_demotes_hot_overflow(self, tier_system):
        s, tm = tier_system
        for i in range(1100):
            s.save_node(f"n{i}", "test", "T", {}, tier="H")
        tm.run_gc()
        counts = s.get_tier_counts()
        assert counts.get("H", 0) < 1100, f"GC should move hot nodes, got {counts}"
