"""Tests for EngineeringChain persistence."""
import tempfile, os, pytest
from core.agent.persistence.unified_graph_store import UnifiedGraphStore
from core.agent.engineering import (
    ArtifactType, Artifact, KnowledgeType, KnowledgeNode, Source,
    ArtifactRegistry, KnowledgeGraph,
)
from core.agent.engineering.persistence import EngineeringChainPersistence

@pytest.fixture
def store():
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = db.name; db.close()
    s = UnifiedGraphStore(db_path=path)
    yield s
    s.close()
    os.unlink(path)

class TestUnifiedGraphStore:
    def test_save_and_load_node(self, store):
        store.save_node("n1", "artifact", "E", {"name": "Test"})
        node = store.load_node("n1")
        assert node is not None
        assert node["node_type"] == "artifact"
        assert node["domain"] == "E"

    def test_touch_increments_activation(self, store):
        store.save_node("n2", "test", "T", {})
        store.touch("n2")
        store.touch("n2")
        node = store.load_node("n2")
        assert node["activation_count"] == 2

    def test_tier_management(self, store):
        store.save_node("n3", "test", "T", {})
        store.update_tier("n3", "W")
        node = store.load_node("n3")
        assert node["tier"] == "W"

class TestEngineeringPersistence:
    def test_save_load_artifact(self, store):
        pers = EngineeringChainPersistence(store)
        art = Artifact(id="a1", name="TestProvider", atype=ArtifactType.PROVIDER)
        pers.save_artifact(art)
        loaded = pers.load_artifacts()
        assert len(loaded) == 1
        assert loaded[0].name == "TestProvider"

    def test_save_load_knowledge(self, store):
        pers = EngineeringChainPersistence(store)
        node = KnowledgeNode(id="kn1", ktype=KnowledgeType.CONSTRAINT,
                             name="Test Constraint", source=Source.CORE)
        pers.save_knowledge(node)
        # just verify no crash - load_knowledge not implemented yet
        node2 = store.load_node("kn1")
        assert node2 is not None
