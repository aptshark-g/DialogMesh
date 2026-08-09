# -*- coding: utf-8 -*-
"""GAP-E1/E2 测试 — executor meta/behavior 占位真接线
（COMPLETENESS_GAP_INVENTORY §B）.

覆盖:
  - E2: _handle_behavior 真调 engine._run_behavior_brain（learn+背景预测）;
    无 engine → unavailable（不再"deferred"占位）; 有 brain → stats 返回
  - E1: _handle_meta 真调 engine._run_meta_consume + trace 记录;
    无 engine → unavailable（不再"async"占位）; trace 有 transition 记录
"""
from __future__ import annotations

from types import SimpleNamespace

from core.agent.blueprint.executor import BlueprintExecutor
from core.agent.blueprint.models import BlueprintNode


class _FakeBrain:
    def stats(self):
        return {"learn_count": 3}


class _FakeEngine:
    """最小 engine 替身: 真实 handler 依赖的接口."""

    def __init__(self, with_trace=True):
        self._behavior_brain = _FakeBrain()
        self._behavior_calls = 0
        self._meta_calls = 0
        self._trace = None
        if with_trace:
            from core.agent.state.execution_trace import ExecutionTraceV3
            self._trace_v3 = ExecutionTraceV3(session_id="t")

    def _run_behavior_brain(self, event):
        self._behavior_calls += 1
        self._last_event = event

    def _run_meta_consume(self):
        self._meta_calls += 1
        return {"adjust": False, "warnings": []}


def _node(chain):
    return BlueprintNode(f"{chain}_1", chain, priority=1)


def test_behavior_handler_calls_brain():
    eng = _FakeEngine()
    ex = BlueprintExecutor(engine=eng)
    out = ex._handle_behavior(_node("behavior"), {}, "用户说你好")
    assert out["status"] == "ok"
    assert eng._behavior_calls == 1
    assert eng._last_event.kind == "blueprint.behavior"
    assert eng._last_event.payload["text"] == "用户说你好"
    assert out["learned"] is True
    assert out["stats"]["learn_count"] == 3


def test_behavior_handler_no_engine_unavailable():
    ex = BlueprintExecutor()
    out = ex._handle_behavior(_node("behavior"), {}, "x")
    assert out["status"] == "unavailable"
    assert "未接线" in out["note"]


def test_behavior_handler_engine_without_brain():
    eng = SimpleNamespace(_behavior_brain=None,
                          _run_behavior_brain=lambda e: None)
    ex = BlueprintExecutor(engine=eng)
    out = ex._handle_behavior(_node("behavior"), {}, "x")
    assert out["status"] == "ok"
    assert out["learned"] is False


def test_meta_handler_calls_consume_and_records_trace():
    eng = _FakeEngine(with_trace=True)
    ex = BlueprintExecutor(engine=eng)
    outputs = {"quality": {"score": 0.9, "degraded": False}}
    out = ex._handle_meta(_node("meta"), outputs, "x")
    assert out["status"] == "ok"
    assert eng._meta_calls == 1
    assert out["advice"] == {"adjust": False, "warnings": []}
    # trace 记录了一条 transition（元认知原料）
    assert len(eng._trace_v3.transitions) >= 1


def test_meta_handler_no_engine_unavailable():
    ex = BlueprintExecutor()
    out = ex._handle_meta(_node("meta"), {}, "x")
    assert out["status"] == "unavailable"
    assert "未接线" in out["note"]


def test_meta_handler_engine_without_consume():
    eng = SimpleNamespace(_trace_v3=None)
    ex = BlueprintExecutor(engine=eng)
    out = ex._handle_meta(_node("meta"), {}, "x")
    # 无 _run_meta_consume → 走 hasattr 分支 → 空 advice, 不崩
    assert out["status"] == "ok"
    assert out["advice"] == {}


def test_dag_with_meta_and_behavior_nodes_executes():
    """含 meta/behavior 节点的 DAG 完整执行不崩（真 handler 生效）."""
    from core.agent.blueprint.models import (
        BlueprintDAG, BlueprintNode, BlueprintEdge,
    )
    eng = _FakeEngine(with_trace=True)

    class _Ex(BlueprintExecutor):
        def _handle_pcr(self, node, outputs, text):
            return {"route": {"zone": "MIXED"}, "status": "ok"}

    ex = _Ex(engine=eng)
    dag = BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("behavior_1", "behavior", priority=9),
            BlueprintNode("meta_2", "meta", priority=9),
            BlueprintNode("llm_reply_3", "llm_reply", priority=2,
                          params={"reply_mode": "template"}),
        ],
        edges=[
            BlueprintEdge("pcr_0", "llm_reply_3", "route", required=False),
        ],
        strategy="TEMPLATE",
    )
    r = ex.execute(dag, user_text="完整执行")
    assert r["chain_outputs"]["behavior_1"]["status"] == "ok"
    assert r["chain_outputs"]["meta_2"]["status"] == "ok"
    assert eng._behavior_calls == 1
    assert eng._meta_calls == 1

