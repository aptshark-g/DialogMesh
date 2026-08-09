# -*- coding: utf-8 -*-
"""P1-5 MCP 工具接入 ToolRegistry 测试（FLOW_SELF_GROWTH §5.5 OpenClaw 对齐）.

覆盖:
  - register_mcp_tools 注册进 core ToolRegistry（discover 可见/可执行）
  - MCPToolAdapter handler 同步桥接 async call_tool
  - availability: 未连接（env 缺失）→ 不可见/不可执行
  - executor tool 节点可执行 MCP 工具
  - P1-5 多工具并行（tool 节点 parallel 组并发执行）
"""
from __future__ import annotations

import os

from core.agent.tools.registry import ToolRegistry


class _FakeAdapter:
    """假 MCP client adapter — 同步返回, 记录调用."""

    def __init__(self):
        self.calls = []
        self._client = _FakeClient(self.calls)


class _FakeClient:
    def __init__(self, calls):
        self.calls = calls

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        return {"echo": args}


def test_register_mcp_tools():
    from core.agent.mcp.tool_bridge import register_mcp_tools
    adapter = _FakeAdapter()
    n = register_mcp_tools(adapter, "demo", [
        {"name": "fetch_web", "description": "fetch a web page",
         "input_schema": {"url": "string"}},
        {"name": "search", "description": "search",
         "input_schema": {"q": "string"}},
    ])
    assert n == 2
    # discover 可见
    names = [t.name for t in ToolRegistry.discover("fetch_web", limit=5)]
    assert "mcp_demo_fetch_web" in " ".join(names)
    # 可执行（handler 桥接）
    result = ToolRegistry.execute("mcp_demo_fetch_web", url="http://x")
    assert result.success is True
    assert adapter.calls == [("fetch_web", {"url": "http://x"})]
    ToolRegistry.unregister("mcp_demo_fetch_web")
    ToolRegistry.unregister("mcp_demo_search")


def test_mcp_tool_unavailable_when_disconnected():
    from core.agent.mcp.tool_bridge import register_mcp_tools
    adapter = _FakeAdapter()
    register_mcp_tools(adapter, "offline", [
        {"name": "gh_search", "description": "github search",
         "input_schema": {"q": "string"}},
    ])
    # 断开（env 移除）→ 不可见
    os.environ.pop("OFFLINE_CONNECTED", None)
    ok, reason = ToolRegistry.is_available("mcp_offline_gh_search")
    assert ok is False
    assert "OFFLINE_CONNECTED" in reason
    names = [t.name for t in ToolRegistry.discover("gh_search", limit=5)]
    assert "mcp_offline_gh_search" not in " ".join(names)
    # 恢复连接 → 可用
    os.environ["OFFLINE_CONNECTED"] = "1"
    ok, reason = ToolRegistry.is_available("mcp_offline_gh_search")
    assert ok is True
    os.environ.pop("OFFLINE_CONNECTED", None)
    ToolRegistry.unregister("mcp_offline_gh_search")


def test_sync_discover_from_adapter_cache():
    from core.agent.mcp.tool_bridge import sync_discover_and_register

    class _Meta:
        def __init__(self, name, desc):
            self.name = name
            self.description = desc
            self.input_schema = {"q": "string"}

    class _CacheAdapter:
        _tools = {"notes_create": _Meta("notes_create", "create note")}

        def __init__(self):
            self._client = _FakeClient([])

    n = sync_discover_and_register(_CacheAdapter(), "notes")
    assert n == 1
    result = ToolRegistry.execute("mcp_notes_notes_create", q="hi")
    assert result.success is True
    ToolRegistry.unregister("mcp_notes_notes_create")


def test_executor_runs_mcp_tool_node():
    from core.agent.mcp.tool_bridge import register_mcp_tools
    from core.agent.blueprint.models import BlueprintDAG, BlueprintNode, BlueprintEdge
    from core.agent.blueprint.executor import BlueprintExecutor

    adapter = _FakeAdapter()
    register_mcp_tools(adapter, "demo2", [
        {"name": "summarize", "description": "summarize",
         "input_schema": {"text": "string"}},
    ])

    class _Exec(BlueprintExecutor):
        def _handle_pcr(self, node, outputs, text):
            return {"route": {"zone": "MIXED"}, "status": "ok"}

    dag = BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("tool_1", "tool", priority=1,
                          params={"tool": "mcp_demo2_summarize",
                                  "args": {"text": "hello"}}),
            BlueprintNode("llm_reply_2", "llm_reply", priority=2,
                          params={"reply_mode": "template"}),
        ],
        edges=[
            BlueprintEdge("pcr_0", "tool_1", "route", required=False),
            BlueprintEdge("tool_1", "llm_reply_2", "tool_result"),
        ],
        strategy="TEMPLATE",
    )
    ex = _Exec()
    r = ex.execute(dag, user_text="summarize")
    out = r["chain_outputs"]["tool_1"]
    assert out["status"] == "ok"
    assert adapter.calls[0][0] == "summarize"
    assert adapter.calls[0][1] == {"text": "hello"}
    ToolRegistry.unregister("mcp_demo2_summarize")


# ═══════════════════════════════════════════════════════════════
# P1-5 多工具并行
# ═══════════════════════════════════════════════════════════════

def test_parallel_tools_execute():
    from core.agent.blueprint.models import (
        BlueprintDAG, BlueprintNode, BlueprintEdge,
    )
    from core.agent.blueprint.executor import BlueprintExecutor

    class _Exec(BlueprintExecutor):
        def _handle_pcr(self, node, outputs, text):
            return {"route": {"zone": "MIXED"}, "status": "ok"}

    dag = BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("tool_1", "tool", priority=1,
                          params={"parallel": [
                              {"tool": "echo", "args": {"message": "a"}},
                              {"tool": "time", "args": {}},
                          ]}),
            BlueprintNode("llm_reply_2", "llm_reply", priority=2,
                          params={"reply_mode": "template"}),
        ],
        edges=[
            BlueprintEdge("pcr_0", "tool_1", "route", required=False),
            BlueprintEdge("tool_1", "llm_reply_2", "tool_result"),
        ],
        strategy="TEMPLATE",
    )
    ex = _Exec()
    r = ex.execute(dag, user_text="parallel")
    out = r["chain_outputs"]["tool_1"]
    assert out["status"] == "ok"
    assert "echo" in out["tool_results"]
    assert "time" in out["tool_results"]
    assert "a" in out["tool_results"]["echo"]["message"]
    assert out["errors"] == {}


def test_parallel_partial_failure():
    from core.agent.blueprint.models import (
        BlueprintDAG, BlueprintNode, BlueprintEdge,
    )
    from core.agent.blueprint.executor import BlueprintExecutor

    class _Exec(BlueprintExecutor):
        def _handle_pcr(self, node, outputs, text):
            return {"route": {"zone": "MIXED"}, "status": "ok"}

    dag = BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("tool_1", "tool", priority=1,
                          params={"parallel": [
                              {"tool": "echo", "args": {"message": "ok"}},
                              {"tool": "no_such_tool_xyz", "args": {}},
                          ]}),
            BlueprintNode("llm_reply_2", "llm_reply", priority=2,
                          params={"reply_mode": "template"}),
        ],
        strategy="TEMPLATE",
    )
    ex = _Exec()
    r = ex.execute(dag, user_text="p")
    out = r["chain_outputs"]["tool_1"]
    assert out["status"] == "partial"
    assert "echo" in out["tool_results"]
    assert "no_such_tool_xyz" in out["errors"]


def test_parallel_validation_blocks_missing_args():
    from core.agent.blueprint.models import (
        BlueprintDAG, BlueprintNode, BlueprintEdge,
    )
    from core.agent.blueprint.executor import BlueprintExecutor

    class _Exec(BlueprintExecutor):
        def _handle_pcr(self, node, outputs, text):
            return {"route": {"zone": "MIXED"}, "status": "ok"}

    dag = BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("tool_1", "tool", priority=1,
                          params={"parallel": [
                              {"tool": "file_read", "args": {}},
                          ]}),
        ],
        strategy="TEMPLATE",
    )
    ex = _Exec()
    r = ex.execute(dag, user_text="p")
    out = r["chain_outputs"]["tool_1"]
    assert out["status"] == "error"
    assert "missing required args" in out["errors"]["file_read"]
