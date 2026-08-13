# -*- coding: utf-8 -*-
"""SubgraphCompiler.compile_from_anchors 测试（recall→subgraph 桥, 2026-08-09）。"""
import pytest

from core.agent.v4.cognitive.subgraph_compiler import SubgraphCompiler
from core.agent.recall.recall_service import RecallHit


def _hit(hid="h1", text="AES 密钥安全存储", path=None):
    return RecallHit(id=hid, text=text, source="bm25",
                     score=0.8, confidence=0.9,
                     path=path or ["docs/only/recall/DESIGN.md", "§五"])


def test_compile_from_anchors_no_engine_safe():
    """无引擎时安全: 只返回锚点条目, 事件/图扩展降级为空。"""
    sc = SubgraphCompiler(engine=None)
    ctx = sc.compile_from_anchors([_hit()])
    assert ctx.perspective == "dialogue"
    assert ctx.compile_strategy == "anchors"
    assert len(ctx.entries) == 1
    assert ctx.entries[0].domain == "R"
    assert "AES 密钥" in ctx.entries[0].content


def test_anchor_path_becomes_cross_ref():
    """锚点 path → cross_refs（执行层精确查阅的路径索引）。"""
    sc = SubgraphCompiler(engine=None)
    ctx = sc.compile_from_anchors([_hit()])
    refs = ctx.entries[0].cross_refs
    assert refs and refs[0]["target_domain"] == "file"
    assert "DESIGN.md" in refs[0]["note"]


def test_compile_from_anchors_event_id_no_crash():
    """带 event_id 无引擎不崩（事件溯源容错返回 []）。"""
    sc = SubgraphCompiler(engine=None)
    ctx = sc.compile_from_anchors([_hit()], event_id="evt_1")
    assert len(ctx.entries) >= 1


def test_empty_anchors_returns_empty_ctx():
    sc = SubgraphCompiler(engine=None)
    ctx = sc.compile_from_anchors([])
    assert ctx.entries == []


class _FakeTrace:
    def __init__(self, request_id, seq, strategy="TEMPLATE"):
        self.request_id = request_id
        self.tool_sequence = seq
        self.strategy = strategy


class _FakeStore:
    def __init__(self, traces):
        self._traces = traces

    def get_all(self):
        return self._traces


class _FakeEngine:
    def __init__(self, store):
        self._learning_bridge = type("LB", (), {"trace_store": store})()


def test_expand_from_trace_finds_code_sequence():
    """生产轨迹溯源: 同 request_id 的工具序列（写的代码/操作）进子图。"""
    store = _FakeStore([
        _FakeTrace("req_1", ["write_file", "run_shell"], "EXECUTION"),
        _FakeTrace("req_2", ["grep"], "TEMPLATE"),
    ])
    sc = SubgraphCompiler(engine=_FakeEngine(store))
    ctx = sc.compile_from_anchors([_hit()], event_id="req_1")
    t_entries = [e for e in ctx.entries if e.domain == "T"]
    assert len(t_entries) == 1
    assert "write_file" in t_entries[0].content
    assert "run_shell" in t_entries[0].content


def test_expand_from_trace_no_match_returns_empty():
    store = _FakeStore([_FakeTrace("other", ["grep"])])
    sc = SubgraphCompiler(engine=_FakeEngine(store))
    assert sc._expand_from_trace("missing_req") == []


def test_graph_entry_doc_bridge(tmp_path):
    """设计 5: 图节点 metadata.doc → DomainEntry cross_refs（file 桥）。"""
    from core.agent.context.graph_source import ConceptGraph

    class _GraphEngine:
        def __init__(self, graph):
            self._graph = graph

    g = ConceptGraph()
    g._nodes = {
        "vault:X": {
            "relations": [],
            "observations": ["X 的观测"],
            "docs": {"docs/only/recall/DESIGN.md"},
        },
    }
    g._built = True
    sc = SubgraphCompiler(engine=_GraphEngine(g))
    entries = sc.expand_from_graph("X", max_nodes=8)
    assert entries, "图检索应命中"
    refs = entries[0].cross_refs
    assert refs and refs[0]["target_domain"] == "file"
    assert "DESIGN.md" in refs[0]["note"]


# ── 设计 4: 异步图扩展 + 增量拼接（2026-08-11）──


def test_merge_incremental_dedup_and_budget():
    """增量拼接: 去重 + 预算超限按 confidence 裁剪。"""
    from core.agent.v4.cognitive.subgraph_compiler import DomainEntry, SubgraphContext
    sc = SubgraphCompiler(engine=None)
    e1 = DomainEntry("G", "图条目一", 0.9, "concept_graph", 100)
    e2 = DomainEntry("G", "图条目二", 0.8, "concept_graph", 100)
    ctx = SubgraphContext("dialogue", [e1], 100, 150, {"G": 1.0},
                          "anchors", "query")
    # 新条目含重复 + 超预算
    dup = DomainEntry("G", "图条目一", 0.9, "concept_graph", 100)
    big = DomainEntry("G", "低置信长内容", 0.1, "concept_graph", 200)
    sc.merge_incremental(ctx, [dup, big])
    # 重复被去重（仍只有 2 个不重复条目）; 低置信超预算被裁剪
    contents = [e.content for e in ctx.entries]
    assert contents.count("图条目一") == 1
    assert "低置信长内容" not in contents


def test_merge_incremental_empty_safe():
    sc = SubgraphCompiler(engine=None)
    from core.agent.v4.cognitive.subgraph_compiler import SubgraphContext
    ctx = SubgraphContext("dialogue", [], 0, 2000, {}, "anchors", "query")
    out = sc.merge_incremental(ctx, [])
    assert out is ctx
    assert len(ctx.entries) == 0


def test_async_graph_expand_no_engine_returns_none():
    """无引擎时异步图扩展直接返回 None（不启动线程）。"""
    sc = SubgraphCompiler(engine=None)
    assert sc.async_graph_expand("query") is None
