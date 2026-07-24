"""Verify auto-persistence hooks in ArtifactRegistry and KnowledgeGraph."""
import tempfile, os, pytest
from core.agent.persistence.unified_graph_store import UnifiedGraphStore
from core.agent.engineering.persistence import EngineeringChainPersistence
from core.agent.engineering import ArtifactRegistry, KnowledgeGraph, ArtifactType

@pytest.fixture
def pers():
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = db.name; db.close()
    s = UnifiedGraphStore(db_path=path)
    p = EngineeringChainPersistence(s)
    yield p
    s.close()
    os.unlink(path)

class TestAutoPersist:
    def test_artifact_auto_saved(self, pers):
        reg = ArtifactRegistry(persistence=pers)
        reg.register("AutoTest", atype=ArtifactType.PROVIDER)
        loaded = pers.load_artifacts()
        assert len(loaded) == 1
        assert loaded[0].name == "AutoTest"

    def test_knowledge_auto_saved(self, pers):
        kg = KnowledgeGraph(persistence=pers)
        kg.add("Custom Rule", __import__("core.agent.v3_2.engineering_chain.models", fromlist=["KnowledgeType"]).KnowledgeType.CONSTRAINT)
        rows = pers._store.load_nodes_by_session("default", domain="E")
        assert any(r["node_type"] == "constraint" for r in rows)
