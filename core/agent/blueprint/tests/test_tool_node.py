# -*- coding: utf-8 -*-
"""G1 tool 节点测试（FLOW_SELF_GROWTH）.

覆盖:
  - tool 节点调 ToolRegistry.execute（真实工具执行）
  - 工具失败 → status=error（可触发 RECOVERY）
  - learn 阶段 discover 找到工具（替代硬编码引用表）
  - converge prompt 注入工具列表
"""
from __future__ import annotations

from core.agent.blueprint.models import (
    BlueprintDAG, BlueprintNode, BlueprintEdge,
)
from core.agent.blueprint.executor import BlueprintExecutor
from core.agent.blueprint.llm_dag_builder import LLMDAGBuilder, LearningResult, Hypothesis


class _ToolExec(BlueprintExecutor):
    """测试替身: 只覆盖 pcr（tool/llm_reply 走真实实现）. """

    def _handle_pcr(self, node, outputs, text):
        return {"route": {"zone": "MIXED"}, "status": "ok"}


def test_tool_node_executes_real_tool():
    """tool 节点调用 ToolRegistry.execute（file_read 真执行）."""
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    tmp.write("hello tool")
    tmp.close()
    dag = BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("tool_1", "tool", priority=1,
                          params={"tool": "file_read", "args": {"path": tmp.name}}),
            BlueprintNode("llm_reply_2", "llm_reply", priority=2),
        ],
        edges=[
            BlueprintEdge("pcr_0", "tool_1", "route", required=False),
            BlueprintEdge("tool_1", "llm_reply_2", "tool_result"),
        ],
        strategy="TEMPLATE",
    )
    ex = _ToolExec()
    r = ex.execute(dag, user_text="读文件")
    out = r["chain_outputs"]["tool_1"]
    assert out["status"] == "ok"
    assert out["tool"] == "file_read"
    assert "hello tool" in str(out["tool_result"])
    assert "hello tool" in out["summary"]
    os.unlink(tmp.name)


def test_tool_node_missing_tool_param():
    """缺 tool 参数 → error."""
    dag = BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("tool_1", "tool", priority=1, params={}),
            BlueprintNode("llm_reply_2", "llm_reply", priority=2),
        ],
        strategy="TEMPLATE",
    )
    ex = _ToolExec()
    r = ex.execute(dag, user_text="t")
    assert r["chain_outputs"]["tool_1"]["status"] == "error"
    assert "missing 'tool' param" in r["chain_outputs"]["tool_1"]["error"]


def test_learn_discovers_tools():
    """learn 阶段 discover 找到工具（查论文 → arxiv_search）."""
    import core.agent.tools.builtin  # noqa: F401 — 注册内置工具
    from core.agent.tools.registry import ToolRegistry
    b = LLMDAGBuilder()
    result = LearningResult()
    # 直接调用 discover 路径（learn 内逻辑）
    tools = [
        {"name": t.name, "description": t.description, "category": t.category}
        for t in ToolRegistry.discover("查一下最近的论文", limit=5)
    ]
    names = [t["name"] for t in tools]
    # conftest 的 assertrepr 对 list-in 崩溃, 用 join 断言
    assert "arxiv_search" in " ".join(names)


def test_converge_prompt_contains_tools():
    """converge prompt 注入工具列表 + tool 节点说明."""
    b = LLMDAGBuilder()
    learning = LearningResult(
        tools=[{"name": "arxiv_search", "description": "Search papers",
                "category": "search"}],
    )
    # 通过 _call_llm mock 捕获 prompt
    captured = {}
    orig = b._call_llm
    b._call_llm = lambda sys, user, **kw: (captured.update(prompt=user) or
                                           '[{"confidence":0.9,"rationale":"r"}]')
    try:
        dag = b.converge("查论文", "代码分析",
                         [Hypothesis(nodes=[{"chain": "tool", "reason": "r"}],
                                     confidence=0.5, rationale="r")],
                         learning)
        assert "arxiv_search" in captured["prompt"]
        assert "tool 节点" in captured["prompt"]
    finally:
        b._call_llm = orig


def test_tool_validation_blocks_missing_args():
    """T2: 缺必填参数 → 校验拦截（不盲执行）."""
    dag = BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            # file_read 的 schema 要求 path（必填）
            BlueprintNode("tool_1", "tool", priority=1,
                          params={"tool": "file_read", "args": {}}),
            BlueprintNode("llm_reply_2", "llm_reply", priority=2),
        ],
        strategy="TEMPLATE",
    )
    ex = _ToolExec()
    r = ex.execute(dag, user_text="读文件")
    out = r["chain_outputs"]["tool_1"]
    assert out["status"] == "error"
    assert "missing required args" in out["error"]
    assert "path" in out["error"]


def test_tool_result_flows_to_llm_reply():
    """T3: 工具结果进 llm_reply 上下文（非空 context_block）."""
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    tmp.write("TOOL_RESULT_MARKER_123")
    tmp.close()
    dag = BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("tool_1", "tool", priority=1,
                          params={"tool": "file_read", "args": {"path": tmp.name}}),
            BlueprintNode("llm_reply_2", "llm_reply", priority=2, params={"reply_mode": "template"}),
        ],
        edges=[
            BlueprintEdge("pcr_0", "tool_1", "route", required=False),
            BlueprintEdge("tool_1", "llm_reply_2", "tool_result"),
        ],
        strategy="TEMPLATE",
    )
    ex = _ToolExec()
    r = ex.execute(dag, user_text="读文件")
    # template 模式: reply = context_block（应含工具结果）
    assert "TOOL_RESULT_MARKER_123" in r["llm_reply"]
    os.unlink(tmp.name)
