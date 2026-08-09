# -*- coding: utf-8 -*-
"""T4 ReAct 子循环测试（BIDIRECTIONAL_ATTRIBUTION）.

覆盖:
  - 首次失败 → LLM 决策改参数重试 → 成功
  - 每步写 decision_bus 事件（可回看）
  - 超 max_steps 终止 → error（外层 RECOVERY 接管）
  - 无 LLM 时保守 done（不盲重试）
"""
from __future__ import annotations

from core.agent.blueprint.models import (
    BlueprintDAG, BlueprintNode, BlueprintEdge,
)
from core.agent.blueprint.executor import BlueprintExecutor
from core.agent.blueprint.decision_event import DecisionEventBus


class _RetryToolExec(BlueprintExecutor):
    """测试替身: echo 工具前 N 次失败, 之后成功. """

    def __init__(self, bus, fail_times=1, **kw):
        super().__init__(decision_bus=bus, **kw)
        self.fail_times = fail_times
        self.calls = 0

    def _handle_pcr(self, node, outputs, text):
        return {"route": {"zone": "MIXED"}, "status": "ok"}

    def _handle_llm_reply(self, node, outputs, text):
        return {"response": "final", "status": "ok"}

    def _llm_decide_tool(self, tool_name, args, result, text, step, failed=False):
        # 模拟 LLM: 失败 → 改参数重试; 成功且结果空 → done
        if failed:
            return {"done": False, "tool": tool_name,
                    "args": {"message": "retry-ok"}}
        return {"done": True}

    def _record_tool_step(self, node, tool_name, args, result, step):
        super()._record_tool_step(node, tool_name, args, result, step)
        self.calls += 1
        # 让 echo 工具可配置失败: 通过 args 传递
        if args.get("message") == "fail":
            result.success = False
            result.error = "simulated failure"


def _dag(message="hello"):
    return BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("tool_1", "tool", priority=1,
                          params={"tool": "echo",
                                  "args": {"message": message},
                                  "max_steps": 3}),
            BlueprintNode("llm_reply_2", "llm_reply", priority=2),
        ],
        edges=[
            BlueprintEdge("pcr_0", "tool_1", "route", required=False),
            BlueprintEdge("tool_1", "llm_reply_2", "tool_result"),
        ],
        strategy="TEMPLATE",
    )


def test_react_retry_on_failure():
    """首次失败 → LLM 改参数重试 → 成功（react_steps >= 2）."""
    bus = DecisionEventBus()
    ex = _RetryToolExec(bus=bus)

    # 首次执行时让 echo 失败（text=fail → _record_tool_step 置失败）
    dag = _dag(message="fail")
    r = ex.execute(dag, user_text="t")
    out = r["chain_outputs"]["tool_1"]
    assert out["status"] == "ok"
    assert out["react_steps"] >= 2, f"应重试, got {out.get('react_steps')}"
    # 每步事件可回看
    events = bus.recent()
    assert len(events) >= 2
    assert any("step1" in e["dimension"] for e in events)
    assert any("step2" in e["dimension"] for e in events)


def test_react_max_steps_terminates():
    """持续失败 → 超 max_steps 终止 → error."""
    bus = DecisionEventBus()

    class _AlwaysFail(_RetryToolExec):
        def _llm_decide_tool(self, *a, **kw):
            # 一直要求重试（text=fail 永远失败）
            return {"done": False, "tool": "echo", "args": {"message": "fail"}}

    ex = _AlwaysFail(bus=bus)
    r = ex.execute(_dag(message="fail"), user_text="t")
    out = r["chain_outputs"]["tool_1"]
    assert out["status"] == "error"
    assert "failed after 3 steps" in out["error"]


def test_react_success_no_retry():
    """首次成功且结果足够 → 不重试（react_steps == 1）."""
    bus = DecisionEventBus()
    ex = _RetryToolExec(bus=bus)
    r = ex.execute(_dag(message="hello"), user_text="t")
    out = r["chain_outputs"]["tool_1"]
    assert out["status"] == "ok"
    assert out["react_steps"] == 1


def test_react_no_llm_conservative():
    """无 LLM（call_switch 失败）→ 保守 done, 不盲重试."""
    import core.agent.blueprint.executor as exmod
    bus = DecisionEventBus()

    # 用基类真实 _llm_decide_tool（会调 call_switch）
    class _BaseToolExec(BlueprintExecutor):
        def _handle_pcr(self, node, outputs, text):
            return {"route": {"zone": "MIXED"}, "status": "ok"}
        def _handle_llm_reply(self, node, outputs, text):
            return {"response": "final", "status": "ok"}

    ex = _BaseToolExec(decision_bus=bus)
    # monkeypatch call_switch 返回空（无 LLM）
    orig = exmod.call_switch
    exmod.call_switch = lambda *a, **kw: ""
    try:
        # file_read 不存在路径 → 真失败 → 无 LLM → 保守 error（不盲重试）
        dag = BlueprintDAG(
            nodes=[
                BlueprintNode("pcr_0", "pcr", priority=0),
                BlueprintNode("tool_1", "tool", priority=1,
                              params={"tool": "file_read",
                                      "args": {"path": "/nonexistent/xyz.txt"},
                                      "max_steps": 3}),
                BlueprintNode("llm_reply_2", "llm_reply", priority=2),
            ],
            strategy="TEMPLATE",
        )
        r = ex.execute(dag, user_text="t")
        out = r["chain_outputs"]["tool_1"]
        # 无 LLM → 失败后 _llm_decide_tool 返回 done → break → error
        assert out["status"] == "error"
    finally:
        exmod.call_switch = orig
