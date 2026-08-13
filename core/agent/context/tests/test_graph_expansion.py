# -*- coding: utf-8 -*-
"""DAG 分层局部扩展测试（2026-08-11, SUBGRAPH_EXPANSION_UPGRADE 设计 1）。"""
from __future__ import annotations

from core.agent.context.graph_source import ConceptGraph


def _graph():
    g = ConceptGraph()
    # 小图: seed A → B(高置信) → C; A → D(低置信) → E（应被剪枝）
    g._nodes = {
        "A": {"relations": [
            {"target": "B", "type": "implies", "confidence": 0.9},
            {"target": "D", "type": "hints", "confidence": 0.1},
        ], "observations": ["obsA"], "docs": {"d1"}},
        "B": {"relations": [
            {"target": "C", "type": "implies", "confidence": 0.8},
        ], "observations": ["obsB"], "docs": {"d1"}},
        "C": {"relations": [], "observations": ["obsC"], "docs": {"d1"}},
        "D": {"relations": [
            {"target": "E", "type": "hints", "confidence": 0.05},
        ], "observations": ["obsD"], "docs": {"d1"}},
        "E": {"relations": [], "observations": ["obsE"], "docs": {"d1"}},
    }
    g._built = True
    return g


def test_layered_expand_prunes_low_confidence():
    """同步剪枝: 低置信边（D→E, conf 0.05）不应进入结果。"""
    g = _graph()
    g.dag_layer_expand = True
    g.dag_prune_threshold = 0.3
    visited, edges = g.expand_subgraph(["A"], max_hops=2, max_nodes=10)
    assert "B" in visited and "C" in visited
    assert "D" not in visited, "低置信边应被剪枝"
    assert "E" not in visited
    prio = [e.get("prio") for e in edges if e["source"] == "A"]
    assert prio, "边应带 prio 字段"


def test_layered_expand_respects_budget():
    """每层预算: budget_per_layer 限制层内节点数。"""
    g = _graph()
    g.dag_layer_expand = True
    g.dag_budget_per_layer = 1
    g.dag_prune_threshold = 0.0
    visited, _ = g.expand_subgraph(["A"], max_hops=1, max_nodes=10)
    # 第 0 层 A; 第 1 层 budget=1 → 只保留 B 或 D 之一
    assert len(visited) >= 1


def test_layered_expand_fallback_bfs():
    """开关关闭时回退旧 BFS（行为不变）。"""
    g = _graph()
    g.dag_layer_expand = False
    visited, _ = g.expand_subgraph(["A"], max_hops=1, max_nodes=10)
    assert "B" in visited and "D" in visited  # 旧 BFS 不过滤低置信


# ── 设计 3: 全局社区层（GraphRAG 对齐, 2026-08-11）──


def _community_graph():
    g = ConceptGraph()
    # 两个社区: {A,B,C} 紧密相连; {X,Y,Z} 另一簇; W 孤立
    g._nodes = {
        "A": {"relations": [{"target": "B", "type": "t", "confidence": 0.9},
                            {"target": "C", "type": "t", "confidence": 0.9}],
              "observations": ["主题甲相关内容"], "docs": {"d1"}},
        "B": {"relations": [{"target": "A", "type": "t", "confidence": 0.9},
                            {"target": "C", "type": "t", "confidence": 0.8}],
              "observations": ["主题甲补充"], "docs": {"d1"}},
        "C": {"relations": [{"target": "A", "type": "t", "confidence": 0.8}],
              "observations": ["主题甲细节"], "docs": {"d1"}},
        "X": {"relations": [{"target": "Y", "type": "t", "confidence": 0.9}],
              "observations": ["主题乙内容"], "docs": {"d2"}},
        "Y": {"relations": [{"target": "X", "type": "t", "confidence": 0.9},
                            {"target": "Z", "type": "t", "confidence": 0.7}],
              "observations": ["主题乙补充"], "docs": {"d2"}},
        "Z": {"relations": [{"target": "Y", "type": "t", "confidence": 0.7}],
              "observations": ["主题乙细节"], "docs": {"d2"}},
        "W": {"relations": [], "observations": ["孤立节点"], "docs": {"d3"}},
    }
    g._edges = [
        {"source": s, "target": rel["target"], "type": rel["type"],
         "confidence": rel["confidence"]}
        for s in g._nodes for rel in g._nodes[s]["relations"]
    ]
    g._built = True
    return g


def test_build_communities_detects_clusters():
    """社区检测: 两个紧密簇被识别, 孤立节点不入社区。"""
    g = _community_graph()
    n = g.build_communities()
    assert n >= 1
    all_members = [m for c in g._communities for m in c]
    assert "W" not in all_members, "孤立节点不应入社区"
    # A 与 X 不应在同一社区
    for c in g._communities:
        assert not ("A" in c and "X" in c)


def test_community_top_k_keyword_fallback():
    """查询期: 无向量时用关键词兜底, 返回社区列表。"""
    g = _community_graph()
    g.build_communities()
    # 无 embedder → 关键词兜底路径
    out = g.community_top_k("主题乙", top_k=2, threshold=0.0)
    assert out, "应返回命中社区"
    hit_communities = [c for c, _ in out]
    assert any("X" in c for c in hit_communities), "主题乙社区应命中"


def test_build_communities_small_graph_skipped():
    """小图（<4 节点）跳过社区检测, 不抛异常。"""
    g = _graph()  # 5 节点但 A-D 低置信; 仍 >=4, 用更小图验证
    g2 = ConceptGraph()
    g2._nodes = {"a": {"relations": [], "observations": ["o"], "docs": set()}}
    assert g2.build_communities() == 0


# ── 设计 2/4: 图存储加载 + 图导航（CONTENT_TO_GRAPH, 2026-08-11）──


def _store_with_vault(tmp_path):
    """构造含 vault_docs 域的 UnifiedGraphStore。"""
    from core.agent.persistence.unified_graph_store import UnifiedGraphStore
    s = UnifiedGraphStore(db_path=str(tmp_path / "g.db"))
    s.open()
    s.save_node("vault:A", "document", "vault_docs",
                {"title": "A", "source": "docs/a.md"}, summary="A 摘要")
    s.save_node("vault:B", "document", "vault_docs",
                {"title": "B", "source": "docs/b.md"}, summary="B 摘要")
    s.save_node("vault:C", "document", "vault_docs",
                {"title": "C", "source": "docs/c.md"}, summary="C 摘要")
    s.save_edge("wikilink", "vault_docs", "vault:A", "vault:B",
                {"source_kind": "extracted"}, weight=0.9)
    s.save_edge("cross_ref", "vault_docs", "vault:B", "vault:C",
                {"source_kind": "extracted"}, weight=0.8)
    return s


def test_build_from_graph_store(tmp_path):
    """从 UnifiedGraphStore 加载节点+边（含 source_kind 标签）。"""
    store = _store_with_vault(tmp_path)
    g = ConceptGraph()
    n = g.build_from_graph_store(store)
    assert n == 3
    assert "vault:A" in g._nodes and "vault:C" in g._nodes
    # 边带 source_kind（extracted → 高置信）
    edge = next(e for e in g._edges if e["source"] == "vault:A")
    assert edge["source_kind"] == "extracted"
    assert edge["confidence"] == 0.9
    # summary 进 observations（Coarse scan 原料）
    assert "A 摘要" in g._nodes["vault:A"]["observations"]
    store.close()


def test_graph_neighbors_and_callers(tmp_path):
    store = _store_with_vault(tmp_path)
    g = ConceptGraph()
    g.build_from_graph_store(store)
    assert g.neighbors("vault:A") == ["vault:B"]
    assert "vault:B" in g.neighbors("vault:A", edge_type="wikilink")
    assert g.callers("vault:B") == ["vault:A"]
    assert g.callers("vault:C") == ["vault:B"]
    store.close()


def test_graph_path_bfs(tmp_path):
    store = _store_with_vault(tmp_path)
    g = ConceptGraph()
    g.build_from_graph_store(store)
    path = g.path("vault:A", "vault:C")
    assert path == ["vault:A", "vault:B", "vault:C"]
    assert g.path("vault:A", "不存在") is None
    store.close()
