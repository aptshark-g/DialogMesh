# -*- coding: utf-8 -*-
"""ExecutionMonitor 测试 — Hot 信号 / Warm 裁决 / Cold 复盘（v2 执行层）。"""
import time

from core.agent.meta.execution_monitor import ExecutionMonitor
from core.agent.blueprint.decision_event import DecisionEventBus


def _step(tool="run_python", ok=True, latency=5.0, error=""):
    return {"round": 1, "tool": tool, "ok": ok,
            "latency_ms": latency, "error": error}


def test_hot_signals_accumulate():
    m = ExecutionMonitor()
    m.on_step(_step("run_python"))
    m.on_step(_step("run_shell", ok=False, error="boom"))
    sig = m.signals()
    assert sig["steps"] == 2
    assert sig["failures"] == 1
    assert sig["failure_rate"] == 0.5
    assert sig["failed_tools"] == {"run_shell": 1}
    assert sig["last_error"] == "boom"


def test_evaluate_continue_on_ok():
    m = ExecutionMonitor()
    m.on_step(_step())
    v = m.evaluate()
    assert v.action == "continue"


def test_evaluate_failure_rate_replan():
    m = ExecutionMonitor()
    m.on_step(_step(ok=False, error="e1"))
    m.on_step(_step(ok=False, error="e2"))
    v = m.evaluate()
    assert v.action == "replan"
    assert "失败率" in v.reason


def test_evaluate_consecutive_failures_replan():
    m = ExecutionMonitor(thresholds={"failure_rate": 0.9})
    m.on_step(_step())
    m.on_step(_step(ok=False, error="e1"))
    m.on_step(_step(ok=False, error="e2"))
    v = m.evaluate()
    assert v.action == "replan"
    assert "连续失败" in v.reason


def test_evaluate_budget_timeout_replan():
    m = ExecutionMonitor()
    m.on_step(_step())
    m._t0 = time.time() - 200  # 模拟已运行 200s
    v = m.evaluate(budget_time_s=100)
    assert v.action == "replan"
    assert "预算超时" in v.reason


def test_evaluate_ask_user_when_rounds_exhausted():
    m = ExecutionMonitor()
    for _ in range(4):
        m.on_step(_step())
    v = m.evaluate(max_rounds=4, content="")
    assert v.action == "ask_user"


def test_review_writes_event_for_non_continue():
    bus = DecisionEventBus()
    m = ExecutionMonitor(decision_bus=bus)
    ev = m.review({"verdict": "replan", "reason": "超时",
                   "advice": "换方案"}, node_id="n1")
    assert ev is not None
    assert ev["kind"] == "meta_advice"
    assert ev["dimension"] == "execution.node.n1"


def test_review_skips_continue():
    bus = DecisionEventBus()
    m = ExecutionMonitor(decision_bus=bus)
    assert m.review({"verdict": "continue"}, node_id="n1") is None
    assert bus.all() == []
