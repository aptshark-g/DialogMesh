"""GAP-O4 接线测试 — world/importance 归位（backbone 断线修复）。"""

from __future__ import annotations

from core.agent.world.schema import (
    ReferenceUnit, StructuralEdge, StructuralWorldGraph,
)
from core.agent.world.compiler import StructuralContextCompiler
from core.agent.world.importance import compute_backbone_scores


def _star_graph() -> StructuralWorldGraph:
    """星形图: a 为中心, 连接 b/c/d — betweenness 中心最高。"""
    g = StructuralWorldGraph(graph_id="g1", world="code")
    for uid, name in [("a", "A"), ("b", "B"), ("c", "C"), ("d", "D")]:
        g.units[uid] = ReferenceUnit(unit_id=uid, unit_type="class",
                                     name=name, world="code")
    g.edges = [
        StructuralEdge("e1", "calls", "a", "b"),
        StructuralEdge("e2", "calls", "a", "c"),
        StructuralEdge("e3", "calls", "a", "d"),
        StructuralEdge("e4", "references", "b", "c"),
    ]
    return g


def test_ensure_backbone_fills_graph():
    """compiler._ensure_backbone 填充 graph.backbone + units.backbone_score。"""
    g = _star_graph()
    assert not g.backbone  # 断线前: 从未填充
    compiler = StructuralContextCompiler()
    compiler._ensure_backbone(g)
    assert g.backbone
    # 星形中心 betweenness 最高 → backbone 最高
    assert g.backbone["a"] > g.backbone["b"]
    assert g.units["a"].backbone_score > 0.0


def test_compile_subgraph_triggers_backbone():
    """compile_subgraph 入口懒填充（空 intent 走 fallback seeds）。"""
    g = _star_graph()
    compiler = StructuralContextCompiler(fallback_seed_count=2)
    result = compiler.compile_subgraph(g, intent="", max_nodes=4)
    assert g.backbone  # 编译后已填充
    assert result.backbone_units
    assert result.backbone_units[0] == "a"  # 中心节点优先


def test_compute_backbone_scores_fusion():
    """四维融合: 结构 0.3 + 运行时 0.3 + 提交 0.2 + 检索 0.2。"""
    g = _star_graph()
    structural = {"a": 1.0, "b": 0.5, "c": 0.5}
    runtime = {"a": 0.5}
    scores = compute_backbone_scores(g, structural, runtime_centrality=runtime)
    # a: 0.3*1.0 + 0.3*0.5 + 0 = 0.45
    assert abs(scores["a"] - 0.45) < 1e-6
    # b: 0.3*0.5 = 0.15
    assert abs(scores["b"] - 0.15) < 1e-6
    # 未提供维度的节点 → 不在结果中（调用方 get 缺省 0）
    assert scores.get("d", 0.0) == 0.0
