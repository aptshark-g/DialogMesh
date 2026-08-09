"""二阶抽象生产接线测试 — 启发注入 llm_reply / 变化触发（失败节流/用户纠正）。"""

from __future__ import annotations

from core.agent.blueprint.executor import BlueprintExecutor
from core.agent.blueprint.heuristic_inventory import HeuristicInventory
from core.agent.blueprint.learning_bridge import LearningBridge, ExecutionTrace
from core.agent.blueprint.heuristic_distiller import HeuristicDistiller
from core.agent.blueprint.models import BlueprintNode
import core.agent.blueprint.executor as executor_mod


class _ToolExec(BlueprintExecutor):
    def _handle_pcr(self, node, outputs, text):
        return {"route": {"zone": "MIXED"}, "status": "ok"}


def _seed_traces(lb: LearningBridge, n: int = 3):
    for _ in range(n):
        lb.trace_store.add(ExecutionTrace(
            tool_sequence=["search", "read"], success=True, intent="research"))


def test_llm_reply_injects_heuristics(tmp_path, monkeypatch):
    """llm_reply 构建时注入 [决策依据] 块（与 engineering 约束并列）。"""
    inv = HeuristicInventory(str(tmp_path / "h.json"))
    captured: dict = {}

    def fake_call_switch(messages, **kwargs):
        captured["messages"] = messages
        return "（测试回复）"

    monkeypatch.setattr(executor_mod, "call_switch", fake_call_switch)
    ex = _ToolExec(heuristic_inventory=inv)
    node = BlueprintNode("llm_1", "llm_reply", params={"reply_mode": "llm"})
    out = ex._handle_llm_reply(
        node, {"pcr_0": {"route": {"zone": "MIXED"}}}, "低概率事件怎么处理")
    assert out["status"] == "ok"
    user_msg = captured["messages"][-1]["content"]
    assert "[决策依据]" in user_msg
    assert "差异即信息" in user_msg
    assert "用户:" in user_msg


def test_no_inventory_no_injection(tmp_path, monkeypatch):
    """无库存时不注入（不破坏现有 llm_reply）。"""
    captured: dict = {}

    def fake_call_switch(messages, **kwargs):
        captured["messages"] = messages
        return "（回复）"

    monkeypatch.setattr(executor_mod, "call_switch", fake_call_switch)
    ex = _ToolExec()  # 无 heuristic_inventory
    node = BlueprintNode("llm_1", "llm_reply", params={"reply_mode": "llm"})
    ex._handle_llm_reply(node, {}, "你好")
    user_msg = captured["messages"][-1]["content"]
    assert "[决策依据]" not in user_msg


def test_tool_failure_throttled_trigger(tmp_path):
    """工具失败累计 2 次 + 间隔满足 → 触发蒸馏（rule 模式）。"""
    inv = HeuristicInventory(str(tmp_path / "h.json"))
    lb = LearningBridge()
    lb._trigger_min_interval = 0.0
    d = HeuristicDistiller(llm_provider=None, inventory=inv, trace_store=lb.trace_store)
    lb.attach_distiller(d)
    _seed_traces(lb)

    r1 = lb.on_tool_failure("file_read", "not found")  # count=1 → throttle
    assert r1["triggered"] is False
    assert r1["reason"] == "failure_throttle"
    r2 = lb.on_tool_failure("file_read", "not found")  # count=2 → trigger
    assert r2["triggered"] is True
    assert r2.get("mode") == "rule"


def test_tool_failure_interval_throttle(tmp_path, monkeypatch):
    """间隔未到（默认 60s）→ 即使计数够也不触发。"""
    inv = HeuristicInventory(str(tmp_path / "h.json"))
    lb = LearningBridge()  # 默认 interval 60s
    d = HeuristicDistiller(llm_provider=None, inventory=inv, trace_store=lb.trace_store)
    lb.attach_distiller(d)
    _seed_traces(lb)
    # 手动把上次触发时间设为最近, 模拟刚触发过
    lb._last_trigger_ts = 0.0  # 确保第一次可触发
    r1 = lb.on_tool_failure("a", "e")
    r2 = lb.on_tool_failure("a", "e")
    assert r1["triggered"] is False
    assert r2["triggered"] is True  # 触发后 last_trigger_ts 更新
    # 立刻再失败 → 间隔节流
    r3 = lb.on_tool_failure("a", "e")
    r4 = lb.on_tool_failure("a", "e")
    assert r4["triggered"] is False
    assert r4["reason"] == "interval_throttle"


def test_user_correction_triggers(tmp_path):
    """用户纠正 → 变化触发（共性找底, rule 模式）。"""
    inv = HeuristicInventory(str(tmp_path / "h.json"))
    lb = LearningBridge()
    d = HeuristicDistiller(llm_provider=None, inventory=inv, trace_store=lb.trace_store)
    lb.attach_distiller(d)
    _seed_traces(lb)
    r = lb.on_user_correction("behavior")
    assert r["triggered"] is True
    assert r.get("mode") == "rule"
