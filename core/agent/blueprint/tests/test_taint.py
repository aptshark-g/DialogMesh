"""GAP-5 回合污染跟踪测试（OpenClaw toolResultTaintsTurn 对齐）."""

from __future__ import annotations

import os
import tempfile

from core.agent.blueprint.models import BlueprintDAG, BlueprintNode, BlueprintEdge
from core.agent.blueprint.executor import BlueprintExecutor


class _ToolExec(BlueprintExecutor):
    def _handle_pcr(self, node, outputs, text):
        return {"route": {"zone": "MIXED"}, "status": "ok"}


def _dag_with_tool(params):
    return BlueprintDAG(
        nodes=[
            BlueprintNode("pcr_0", "pcr", priority=0),
            BlueprintNode("tool_1", "tool", priority=1, params=params),
            BlueprintNode("llm_reply_2", "llm_reply", priority=2),
        ],
        edges=[
            BlueprintEdge("pcr_0", "tool_1", "route", required=False),
            BlueprintEdge("tool_1", "llm_reply_2", "tool_result"),
        ],
        strategy="TEMPLATE",
    )


def test_execute_tainted_on_tool_failure():
    """工具失败（文件不存在）→ execute 返回 tainted=True。"""
    missing = os.path.join(tempfile.gettempdir(), "dm_no_such_file_xyz.txt")
    if os.path.exists(missing):
        os.unlink(missing)
    dag = _dag_with_tool({"tool": "file_read", "args": {"path": missing}})
    ex = _ToolExec()
    r = ex.execute(dag, user_text="读文件")
    assert r["tainted"] is True
    assert r["chain_outputs"]["tool_1"]["status"] == "error"


def test_execute_not_tainted_on_success():
    """工具成功 → tainted=False。"""
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    f.write("hello")
    f.close()
    try:
        dag = _dag_with_tool({"tool": "file_read", "args": {"path": f.name}})
        ex = _ToolExec()
        r = ex.execute(dag, user_text="读文件")
        assert r["tainted"] is False
    finally:
        os.unlink(f.name)


def test_summarize_untrusted_mark():
    """失败输出 → [不可信] 标注（污染传播到 llm_reply 上下文）。"""
    ex = _ToolExec()
    assert ex._summarize({"status": "error", "error": "boom"}).startswith("[不可信]")
    assert ex._summarize({"status": "ok", "response": "fine"}).startswith("[不可信]") is False


def test_tool_blocked_by_negative_kb():
    """负知识约束（TieredNegativeKB）: HARD_BLOCK 工具调用 → blocked。"""
    from core.agent.negative_kb.tiered import TieredNegativeKB, SEED_RULES

    class _Eng:
        def __init__(self):
            self._negative_kb = None

        def _ensure_negative_kb(self):
            if self._negative_kb is None:
                self._negative_kb = TieredNegativeKB()
                for rule in SEED_RULES:
                    self._negative_kb.register(rule)
            return self._negative_kb

    ex = _ToolExec(engine=_Eng())
    dag = _dag_with_tool({"tool": "file_read", "args": {"path": "rm -rf /tmp/x"}})
    r = ex.execute(dag, user_text="清理")
    out = r["chain_outputs"]["tool_1"]
    assert out["status"] == "blocked"
    assert out["reason"] == "negative_kb"


def test_tool_not_blocked_without_engine():
    """无 engine（无负知识库）→ 正常执行（不破坏现有）。"""
    import tempfile
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    f.write("hello")
    f.close()
    try:
        ex = _ToolExec()  # 无 engine
        dag = _dag_with_tool({"tool": "file_read", "args": {"path": f.name}})
        r = ex.execute(dag, user_text="读文件")
        assert r["chain_outputs"]["tool_1"]["status"] == "ok"
    finally:
        os.unlink(f.name)
