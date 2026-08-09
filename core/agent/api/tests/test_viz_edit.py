"""M2 白盒编辑后端测试 — B5-3 (edit/revert/journal/mode 全链路).

覆盖:
  * 三档模式开关 (smart/whitebox/fullwhite) — M2-P2
  * 5 端点真数据编辑 (graph/tree/objects/relations/ir) — M2-P3
  * journal 记录 + 白盒检查 — A17/A19
  * revert 恢复端点 (读 journal before → 应用回滚) — M2-P1
"""
import asyncio
import os
import tempfile

import pytest
from fastapi import HTTPException

from core.agent.runtime.engine import CognitiveRuntimeEngine
from core.agent.api import api_viz_edit as viz
from core.agent.compiler.semantic_object import SemanticObject
from core.agent.compiler.relation_substrate import RelationSubstrate, RelationEdge
from core.agent.v4.cognitive.correction_journal import CorrectionJournal


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def engine():
    eng = CognitiveRuntimeEngine()
    # 隔离测试: journal 写到临时目录, 不污染 data/profile/corrections.jsonl
    tmpdir = tempfile.mkdtemp(prefix="viz_edit_test_")
    eng._correction_journal = CorrectionJournal(
        path=os.path.join(tmpdir, "corrections.jsonl"))
    viz.init(eng)
    return eng


@pytest.fixture(scope="module")
def seeded(engine):
    """真实数据种子: world objects + relation substrate + discourse tree."""
    engine._world_objects = {
        "A": SemanticObject(identity="A", name="A"),
        "B": SemanticObject(identity="B", name="B"),
        "C": SemanticObject(identity="C", name="C"),
    }
    rs = RelationSubstrate()
    rs.add(RelationEdge(
        identity="e1", source="A", target="B",
        predicate="depends_on", inverse="depended_by",
        relation_kind="structural", semantic_strength="association",
        confidence=0.6,
    ))
    engine._relation_substrate = rs
    # 重新初始化白盒 → interaction graph 从 substrate 构建
    engine._init_whitebox()
    engine._discourse_tree.feed(
        "用户提出关于架构设计的深层次问题，希望讨论模块划分和职责边界。", "s1")
    return engine


# ── M2-P2 三档模式开关 ────────────────────────────────────────────────

class TestMode:
    def test_default_smart(self, engine):
        r = run(viz.get_mode())
        assert r["mode"] == "smart"
        assert {m["key"] for m in r["modes"]} == {"smart", "whitebox", "fullwhite"}

    def test_switch_whitebox(self, engine):
        r = run(viz.set_mode(viz.ModeRequest(mode="whitebox")))
        assert r["mode"] == "whitebox"
        assert run(viz.get_mode())["mode"] == "whitebox"

    def test_switch_fullwhite(self, engine):
        run(viz.set_mode(viz.ModeRequest(mode="fullwhite")))
        assert run(viz.get_mode())["mode"] == "fullwhite"

    def test_invalid_mode_422(self, engine):
        with pytest.raises(HTTPException) as exc:
            run(viz.set_mode(viz.ModeRequest(mode="bogus")))
        assert exc.value.status_code == 422

    def test_mode_journaled(self, engine):
        journal = engine._correction_journal
        assert journal.last_entry("mode") is not None
        assert journal.last_entry("mode").reason == "user_mode"


# ── M2-P3 5 端点真数据编辑 ────────────────────────────────────────────

class TestEditGraph:
    def test_update_weight(self, seeded):
        r = run(viz.edit_graph(viz.GraphEditRequest(
            action="update_weight", source="A", target="B", weight=0.9)))
        assert r["edited"] == "edge"
        assert r["weight"] == 0.9
        ig = seeded._interaction_graph
        edges = ig._adjacency.get("A", [])
        assert any(e.target == "B" and e.influence_weight == 0.9 for e in edges)
        assert seeded._correction_journal.last_entry("graph.edge.A→B") is not None

    def test_set_node(self, seeded):
        r = run(viz.edit_graph(viz.GraphEditRequest(
            action="set_node", node_id="A",
            node_state={"confidence": 0.9, "attention": 0.7})))
        assert r["edited"] == "node"
        assert seeded._interaction_graph.get_node_state("A")["confidence"] == 0.9

    def test_remove_edge(self, seeded):
        run(viz.edit_graph(viz.GraphEditRequest(
            action="update_weight", source="C", target="B", weight=0.8)))
        r = run(viz.edit_graph(viz.GraphEditRequest(
            action="remove_edge", source="C", target="B")))
        assert r["edited"] == "edge_removed"
        edges = seeded._interaction_graph._adjacency.get("C", [])
        assert not any(e.target == "B" for e in edges)


class TestEditTree:
    def test_reclassify_temperature(self, seeded):
        tree = seeded._discourse_tree._trees.get("s1")
        bid = next(iter(tree.blocks))
        r = run(viz.edit_tree(viz.TreeEditRequest(
            action="reclassify", block_id=bid, temperature="cold")))
        assert r["edited"] == "temperature"
        assert tree.blocks[bid].temperature == "cold"
        assert seeded._correction_journal.last_entry(
            f"tree.{bid}.temperature") is not None

    def test_rename_topic(self, seeded):
        tree = seeded._discourse_tree._trees.get("s1")
        bid = next(iter(tree.blocks))
        r = run(viz.edit_tree(viz.TreeEditRequest(
            action="rename", block_id=bid, topic="架构讨论")))
        assert r["edited"] == "topic"
        assert tree.blocks[bid].topic == "架构讨论"

    def test_invalid_temperature_422(self, seeded):
        tree = seeded._discourse_tree._trees.get("s1")
        bid = next(iter(tree.blocks))
        with pytest.raises(HTTPException) as exc:
            run(viz.edit_tree(viz.TreeEditRequest(
                action="reclassify", block_id=bid, temperature="scorching")))
        assert exc.value.status_code == 422


class TestEditObjects:
    def test_relate(self, seeded):
        r = run(viz.edit_objects(viz.ObjectEditRequest(
            action="relate", source="A", target="C", relation_type="depends_on")))
        assert r["edited"] == "relation_added"
        obj = seeded._world_objects["A"]
        assert any(x["target"] == "C" and x["type"] == "depends_on"
                   for x in obj.relations)

    def test_unrelate(self, seeded):
        r = run(viz.edit_objects(viz.ObjectEditRequest(
            action="unrelate", source="A", target="C")))
        assert r["edited"] == "relation_removed"
        obj = seeded._world_objects["A"]
        assert not any(x["target"] == "C" for x in obj.relations)

    def test_rename(self, seeded):
        r = run(viz.edit_objects(viz.ObjectEditRequest(
            action="rename", source="B", new_name="Engine")))
        assert r["edited"] == "renamed"
        assert seeded._world_objects["B"].name == "Engine"

    def test_set_lifespan(self, seeded):
        r = run(viz.edit_objects(viz.ObjectEditRequest(
            action="set_lifespan", source="B", lifespan="MIND")))
        assert r["edited"] == "lifespan"
        from core.agent.state.state_object import Lifespan
        assert seeded._world_objects["B"].lifespan == Lifespan.MIND


class TestEditRelations:
    def test_update_strength(self, seeded):
        r = run(viz.edit_relations(viz.RelationEditRequest(
            action="update", source="A", target="B", strength=0.95)))
        assert r["edited"] == "relation"
        edges = seeded._relation_substrate.query(source="A", target="B")
        assert abs(edges[0].confidence - 0.95) < 1e-6

    def test_add(self, seeded):
        r = run(viz.edit_relations(viz.RelationEditRequest(
            action="add", source="C", target="B", kind="contains",
            strength=0.7)))
        assert r["edited"] == "added"
        assert seeded._relation_substrate.query(source="C", target="B")

    def test_remove(self, seeded):
        r = run(viz.edit_relations(viz.RelationEditRequest(
            action="remove", source="C", target="B")))
        assert r["edited"] == "removed"
        assert not seeded._relation_substrate.query(source="C", target="B")


class TestEditIR:
    def test_add_entry(self, seeded):
        r = run(viz.edit_ir(viz.IREditRequest(
            domain="E", entry_type="architecture", content="模块划分讨论")))
        assert r["edited"] == "ir_entry_upserted"
        lc = seeded._last_context
        assert any(e.domain == "E" and e.type == "architecture"
                   and e.content == "模块划分讨论" for e in lc.entries)
        entry = seeded._correction_journal.last_entry("ir.E.architecture")
        assert entry is not None and entry.before == "none"

    def test_upsert_edits_existing(self, seeded):
        run(viz.edit_ir(viz.IREditRequest(
            domain="E", entry_type="architecture", content="职责边界再讨论")))
        lc = seeded._last_context
        matches = [e for e in lc.entries
                   if e.domain == "E" and e.type == "architecture"]
        assert len(matches) == 1
        assert matches[0].content == "职责边界再讨论"


# ── M2-P1 revert 恢复端点 ─────────────────────────────────────────────

class TestRevert:
    def test_revert_ir(self, seeded):
        run(viz.edit_ir(viz.IREditRequest(
            domain="C", entry_type="profile", content="用户偏好深度技术")))
        before_count = len(seeded._last_context.entries)
        r = run(viz.revert_edit(viz.RevertRequest(dimension="ir.C.profile")))
        assert r["reverted"] == "ir"
        assert len(seeded._last_context.entries) == before_count - 1
        # revert 本身 journaled (A17)
        last = seeded._correction_journal.last_entry("ir.C.profile")
        assert last.reason == "user_revert"

    def test_revert_graph_edge(self, seeded):
        run(viz.edit_graph(viz.GraphEditRequest(
            action="update_weight", source="X", target="Y", weight=0.3)))
        r = run(viz.revert_edit(viz.RevertRequest(dimension="graph.edge.X→Y")))
        assert r["reverted"] == "graph.edge"
        edges = seeded._interaction_graph._adjacency.get("X", [])
        restored = next(e for e in edges if e.target == "Y")
        assert restored.influence_weight == 0.5  # 默认值 (无旧边)

    def test_revert_tree_temperature(self, seeded):
        tree = seeded._discourse_tree._trees.get("s1")
        bid = next(iter(tree.blocks))
        # 自包含: 先设已知基线, 再改, 回滚到基线
        run(viz.edit_tree(viz.TreeEditRequest(
            action="reclassify", block_id=bid, temperature="paused")))
        run(viz.edit_tree(viz.TreeEditRequest(
            action="reclassify", block_id=bid, temperature="frozen")))
        r = run(viz.revert_edit(viz.RevertRequest(
            dimension=f"tree.{bid}.temperature")))
        assert r["reverted"] == "tree.temperature"
        assert tree.blocks[bid].temperature == "paused"  # 基线

    def test_revert_relation_added(self, seeded):
        run(viz.edit_relations(viz.RelationEditRequest(
            action="add", source="B", target="C", strength=0.5)))
        r = run(viz.revert_edit(viz.RevertRequest(dimension="relation.B→C")))
        assert r["reverted"] == "relation_removed"
        assert not seeded._relation_substrate.query(source="B", target="C")

    def test_revert_last_without_dimension(self, seeded):
        r = run(viz.revert_edit(viz.RevertRequest()))
        assert "reverted" in r

    def test_revert_missing_dimension_404(self, engine):
        with pytest.raises(HTTPException) as exc:
            run(viz.revert_edit(viz.RevertRequest(dimension="nope.nothing")))
        assert exc.value.status_code == 404


# ── A19 白盒检查: journal ─────────────────────────────────────────────

class TestJournal:
    def test_inspection(self, seeded):
        r = run(viz.get_journal(limit=100))
        assert r["stats"]["total_corrections"] > 0
        assert r["entries"]
        assert "dimension" in r["entries"][-1]

    def test_filter_by_dimension(self, seeded):
        r = run(viz.get_journal(dimension="ir.", limit=50))
        assert all(e["dimension"].startswith("ir.") for e in r["entries"])


# ── HTTP 层冒烟 (v6_app 挂载验证, FE-1/G4) ────────────────────────────

class TestHTTPMount:
    def test_mode_endpoint_http(self, engine):
        try:
            from fastapi.testclient import TestClient
            import core.agent.api.v6_app as v6
        except Exception:
            pytest.skip("v6_app unavailable in this environment")
        client = TestClient(v6.app)
        r = client.get("/v6/edit/mode")
        assert r.status_code == 200
        assert r.json()["mode"] in ("smart", "whitebox", "fullwhite")
        r2 = client.put("/v6/edit/mode", json={"mode": "whitebox"})
        assert r2.status_code == 200
        assert r2.json()["mode"] == "whitebox"
