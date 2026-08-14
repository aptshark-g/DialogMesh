# -*- coding: utf-8 -*-
"""StateMachine v2 执行层接线 — agentic 工具节点走 TaskRunner。"""
import pytest

from core.agent.event.statemachine import DeciderStateMachine
from core.agent.event.statemachine import PipelinePhase
from core.agent.blueprint.models import BlueprintDAG, BlueprintNode, BlueprintEdge
from core.agent.blueprint.decision_event import DecisionEventBus


def test_dag_agentic_tool_node_runs_task_runner(monkeypatch):
    import core.agent.llm.task_runner as tr_module
    captured = {}

    def fake_loop(msgs, model="", max_rounds=6, allowed_tools=None,
                  system_inject=None, on_step=None, timeout_s=0.0,
                  **kwargs):
        captured["inject"] = system_inject
        captured["tools"] = allowed_tools
        if on_step:
            on_step({"round": 1, "tool": "run_python", "ok": True,
                     "latency_ms": 5})
        return {"content": "任务完成", "tool_calls": [],
                "rounds": 1, "trace": [], "error": ""}

    monkeypatch.setattr(tr_module, "_default_llm_loop", fake_loop)
    sm = DeciderStateMachine()
    bus = DecisionEventBus()
    dag = BlueprintDAG(
        nodes=[BlueprintNode("tool_0", "tool", priority=0, params={
            "agentic": True, "goal": "写 hello.py",
            "allowed_tools": ["write_file", "run_python"]})],
        edges=[])
    r = sm.run_dag(dag, context={"decision_bus": bus, "session_id": "s1",
                                 "request_id": "r1"})
    out = r["results"]["tool_0"]
    assert out["status"] == "ok"
    assert out["task_result"]["content"] == "任务完成"
    assert "写 hello.py" in captured["inject"]
    assert captured["tools"] == ["write_file", "run_python"]


def test_static_tool_node_unchanged(monkeypatch):
    """非 agentic 工具节点仍走静态 ToolRegistry 执行（不回归）。"""
    sm = DeciderStateMachine()
    dag = BlueprintDAG(
        nodes=[BlueprintNode("tool_0", "tool", priority=0, params={
            "tool": "echo", "args": {"message": "hi"}})],
        edges=[])
    r = sm.run_dag(dag, context={})
    out = r["results"]["tool_0"]
    assert out["status"] == "ok"
    assert out.get("tool") == "echo"


def test_dag_recall_anchor_topology(monkeypatch):
    """v2.1 图拓扑: subgraph 锚点节点 → agentic tool 节点 data_key 消费。

    锚点是图中的节点（白盒可见）, 不是字符串拼尾部。
    """
    import core.agent.llm.task_runner as tr_module
    import core.agent.recall.recall_service as rs_mod
    from core.agent.recall.recall_service import RecallResult, RecallHit
    captured = {}

    def fake_loop(msgs, model="", max_rounds=6, allowed_tools=None,
                  system_inject=None, on_step=None, timeout_s=0.0,
                  **kwargs):
        captured["inject"] = system_inject
        if on_step:
            on_step({"round": 1, "tool": "file_read", "ok": True,
                     "latency_ms": 5})
        return {"content": "按锚点读取完成", "tool_calls": [],
                "rounds": 1, "trace": [], "error": ""}

    monkeypatch.setattr(tr_module, "_default_llm_loop", fake_loop)

    class FakeRecall:
        # 2026-08-13: 生产契约已扩展（W1 intent + W3 expand_graph）—
        # 桩签名与 RecallService.recall 对齐, 否则新参数 TypeError。
        def recall(self, query, top_k=5, sid=None, intent=None,
                   use_hyde=True, expand_graph=None):
            return RecallResult(query=query, hits=[RecallHit(
                id="a1", text="候选锚点片段 AES 密钥", source="bm25",
                score=0.8, confidence=0.9)])

    monkeypatch.setattr(rs_mod, "RecallService", lambda **kw: FakeRecall())

    sm = DeciderStateMachine()
    bus = DecisionEventBus()
    dag = BlueprintDAG(
        nodes=[
            BlueprintNode("sub_0", "subgraph", priority=0,
                          params={"recall_anchor": True}),
            BlueprintNode("tool_1", "tool", priority=0, params={
                "agentic": True, "goal": "按锚点查阅文件"}),
        ],
        edges=[BlueprintEdge("sub_0", "tool_1", "anchors")],
    )
    r = sm.run_dag(dag, context={
        "text": "查 AES 密钥文档", "session_id": "s1",
        "decision_bus": bus, "request_id": "r1"})
    sub_out = r["results"]["sub_0"]
    assert sub_out["status"] == "ok"
    assert "候选锚点片段" in sub_out["anchors"]
    tool_out = r["results"]["tool_1"]
    assert tool_out["status"] == "ok"
    # 锚点来自上游图节点（不是节点内自召回）
    assert "候选锚点" in captured["inject"]
    assert "bm25" in captured["inject"]


def test_tool_node_params_flow_to_handler(monkeypatch):
    """蓝图薄点修复（2026-08-13）: 模板工具节点 params 直传 handler —
    recall_pipeline 的 top_k/parallel 此前因缺 args 键从不进工具。"""
    import core.agent.tools.registry as treg
    captured = {}

    def fake_execute(name, **kwargs):
        captured["name"] = name
        captured["kwargs"] = kwargs
        return treg.ToolResult(name, True, data={"ok": True})

    monkeypatch.setattr(treg.ToolRegistry, "execute", fake_execute)
    sm = DeciderStateMachine()
    bus = DecisionEventBus()
    dag = BlueprintDAG(
        nodes=[BlueprintNode(
            "tool_0", "tool", priority=0,
            params={"tool": "recall_decompose",
                    "top_k": 7, "parallel": True})],
        edges=[])
    r = sm.run_dag(dag, context={"text": "查 AES 密钥",
                                 "session_id": "s1",
                                 "decision_bus": bus})
    assert r["results"]["tool_0"]["status"] == "ok"
    assert captured["name"] == "recall_decompose"
    assert captured["kwargs"]["top_k"] == 7
    assert captured["kwargs"]["parallel"] is True
    assert captured["kwargs"]["query"] == "查 AES 密钥"


def test_multi_segments_injected_into_recall_tool(monkeypatch):
    """多意图 segments 注入（2026-08-13）: intent 节点输出
    segments → recall_decompose.sub_queries（意图副路径实质化）。"""
    import core.agent.tools.registry as treg
    captured = {}

    def fake_execute(name, **kwargs):
        captured["kwargs"] = kwargs
        return treg.ToolResult(name, True, data={"ok": True})

    monkeypatch.setattr(treg.ToolRegistry, "execute", fake_execute)
    sm = DeciderStateMachine()
    sm.register_handler(
        PipelinePhase.INTENT,
        lambda ctx: {"category": "multi", "is_multi": True,
                     "segments": ["先定位延迟", "然后修复"]})
    bus = DecisionEventBus()
    dag = BlueprintDAG(
        nodes=[
            BlueprintNode("intent_1", "intent", priority=0),
            BlueprintNode("tool_2", "tool", priority=1,
                          params={"tool": "recall_decompose",
                                  "top_k": 5}),
        ],
        edges=[BlueprintEdge("intent_1", "tool_2", "intent_context")],
    )
    r = sm.run_dag(dag, context={"text": "先定位延迟然后修复",
                                 "session_id": "s1",
                                 "decision_bus": bus})
    assert r["results"]["tool_2"]["status"] == "ok"
    assert captured["kwargs"]["sub_queries"] == ["先定位延迟", "然后修复"]
