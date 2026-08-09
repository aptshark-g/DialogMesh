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
