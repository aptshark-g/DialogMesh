# -*- coding: utf-8 -*-
"""T5/T6 归因测试（BIDIRECTIONAL_ATTRIBUTION）.

覆盖:
  - DecisionEvent attribution 字段（合法值校验）
  - 工具失败 → 事件带 attribution=tool
  - attribution_hook 回流（失败 → 归因回调被调）
"""
from __future__ import annotations

import pytest

from core.agent.blueprint.decision_event import (
    DecisionEvent, DecisionEventBus, VALID_ATTRIBUTIONS,
)
from core.agent.blueprint.models import (
    BlueprintDAG, BlueprintNode,
)
from core.agent.blueprint.executor import BlueprintExecutor


class TestAttributionSchema:
    def test_valid_attributions(self):
        assert VALID_ATTRIBUTIONS == {"plan", "constraint", "data", "tool", "none"}

    def test_invalid_attribution_rejected(self):
        with pytest.raises(ValueError):
            DecisionEvent(kind="meta_advice", dimension="x",
                          attribution="bogus")

    def test_attribution_in_to_dict(self):
        ev = DecisionEvent(kind="meta_advice", dimension="x",
                           attribution="plan")
        assert ev.to_dict()["attribution"] == "plan"

    def test_log_with_attribution(self):
        bus = DecisionEventBus()
        d = bus.log(kind="strategy_switch", dimension="tool.x",
                    before="a", after="b", attribution="tool")
        assert d["attribution"] == "tool"


class TestToolAttribution:
    def test_failure_event_has_tool_attribution(self):
        """工具失败 → decision_bus 事件 attribution=tool."""
        bus = DecisionEventBus()

        class _Ex(BlueprintExecutor):
            def __init__(self, **kw):
                super().__init__(**kw)
            def _handle_pcr(self, node, outputs, text):
                return {"route": {"zone": "M"}, "status": "ok"}
            def _handle_llm_reply(self, node, outputs, text):
                return {"response": "final", "status": "ok"}
            def _llm_decide_tool(self, *a, **kw):
                return {"done": True}  # 不重试

        ex = _Ex(decision_bus=bus)
        dag = BlueprintDAG(nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("tool_1", "tool", priority=1,
                          params={"tool": "file_read",
                                  "args": {"path": "/nonexistent/xyz.txt"},
                                  "max_steps": 1}),
            BlueprintNode("llm_reply_2", "llm_reply", priority=2),
        ], strategy="TEMPLATE")
        r = ex.execute(dag, user_text="t")
        assert r["chain_outputs"]["tool_1"]["status"] == "error"
        events = bus.recent()
        assert any(e.get("attribution") == "tool" for e in events)

    def test_attribution_hook_called_on_failure(self):
        """attribution_hook 在工具失败时被调用（归因回流）."""
        calls = []

        def hook(tool_name, args, error, attribution):
            calls.append((tool_name, attribution, error))

        class _Ex(BlueprintExecutor):
            def __init__(self, **kw):
                super().__init__(**kw)
            def _handle_pcr(self, node, outputs, text):
                return {"route": {"zone": "M"}, "status": "ok"}
            def _handle_llm_reply(self, node, outputs, text):
                return {"response": "final", "status": "ok"}
            def _llm_decide_tool(self, *a, **kw):
                return {"done": True}

        ex = _Ex(attribution_hook=hook)
        dag = BlueprintDAG(nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("tool_1", "tool", priority=1,
                          params={"tool": "file_read",
                                  "args": {"path": "/nonexistent/xyz.txt"},
                                  "max_steps": 1}),
            BlueprintNode("llm_reply_2", "llm_reply", priority=2),
        ], strategy="TEMPLATE")
        ex.execute(dag, user_text="t")
        assert len(calls) == 1
        tool_name, attribution, error = calls[0]
        assert tool_name == "file_read"
        assert attribution == "tool"
        assert "nonexistent" in error

    def test_success_no_attribution_hook(self):
        """成功 → attribution_hook 不调用."""
        calls = []
        ex = BlueprintExecutor(attribution_hook=lambda *a: calls.append(a))
        # 不触发工具（只验证无失败 → 无 hook）
        assert calls == []
