"""GAP-3 工具批次级介入（OpenClaw beforeToolBatch 对齐）测试."""

from __future__ import annotations

import os
import tempfile

from core.agent.blueprint.executor import BlueprintExecutor
from core.agent.blueprint.intervention import (
    InterventionRouter, RiskClassifier, RiskLevel,
)
from core.agent.blueprint.models import BlueprintNode


class _ToolExec(BlueprintExecutor):
    """测试替身: 直接调 _handle_tool_batch（不需要完整 DAG）。"""


def _batch_node():
    return BlueprintNode("tool_batch_1", "tool", params={})


def _tmp_file(content: str = "hello") -> str:
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


# ── RiskClassifier.classify_tool ─────────────────────────────

def test_classify_tool_levels():
    assert RiskClassifier.classify_tool("file_write", {"path": "/tmp/x"}) == RiskLevel.HIGH
    assert RiskClassifier.classify_tool("file_delete", {}) == RiskLevel.HIGH
    assert RiskClassifier.classify_tool("file_read", {"path": "/tmp/x"}) == RiskLevel.LOW
    assert RiskClassifier.classify_tool("web_search", {"q": "x"}) == RiskLevel.LOW
    # 参数含高危关键词 → 升级
    assert RiskClassifier.classify_tool("call", {"cmd": "rm -rf /"}) == RiskLevel.HIGH
    assert RiskClassifier.classify_tool("call", {"cmd": "ls"}) == RiskLevel.MEDIUM


# ── InterventionRouter.route_batch 汇总 ──────────────────────

def test_route_batch_all_readonly_applied():
    r = InterventionRouter().route_batch(
        tools=[{"tool": "file_read", "args": {"path": "/a"}},
               {"tool": "web_search", "args": {"q": "x"}}],
    )
    assert r["level"] == "low"
    assert r["status"] == "applied"
    assert r["sync_required"] is False


def test_route_batch_medium_proposed():
    r = InterventionRouter().route_batch(
        tools=[{"tool": "call", "args": {"cmd": "ls"}}],
    )
    assert r["level"] == "medium"
    assert r["status"] == "proposed"
    assert r["sync_required"] is False


def test_route_batch_high_sync_required():
    r = InterventionRouter().route_batch(
        tools=[{"tool": "file_read", "args": {"path": "/a"}},
               {"tool": "file_write", "args": {"path": "/b", "content": "x"}}],
    )
    assert r["level"] == "high"
    assert r["status"] == "proposed"
    assert r["sync_required"] is True
    assert len(r["tools"]) == 2


# ── executor._handle_tool_batch ──────────────────────────────

def test_batch_readonly_tools_executes():
    # 2026-08-13 强化: 内容用独特字符串（不可能出现在临时路径/用户名里）,
    # 旧断言 "a"/"b" 会因路径含字母碰巧通过 — 浅测试实锤。
    p1, p2 = _tmp_file("alpha-content"), _tmp_file("beta-content")
    try:
        ex = _ToolExec()
        node = _batch_node()
        r = ex._handle_tool_batch(node, [
            {"tool": "file_read", "args": {"path": p1}},
            {"tool": "file_read", "args": {"path": p2}},
        ], "读两个文件")
        assert r["status"] == "ok"
        assert "alpha-content" in str(r["tool_results"])
        assert "beta-content" in str(r["tool_results"])
        # 同名工具不互相覆盖: 第二个 file_read 结果独立保留（2026-08-13）
        keys = list(r["tool_results"].keys())
        assert len(keys) == 2, f"两个 file_read 应有两个结果键: {keys}"
        assert "file_read" in keys and "file_read#2" in keys
    finally:
        os.unlink(p1)
        os.unlink(p2)


def test_batch_with_write_tool_blocked():
    p = _tmp_file("x")
    try:
        ex = _ToolExec()
        node = _batch_node()
        r = ex._handle_tool_batch(node, [
            {"tool": "file_read", "args": {"path": p}},
            {"tool": "file_write", "args": {"path": p, "content": "overwrite"}},
        ], "读后改")
        assert r["status"] == "blocked"
        assert r["reason"] == "tool_batch_approval_required"
        assert "file_write" in r["tools"]
    finally:
        os.unlink(p)


def test_batch_missing_tool_field():
    ex = _ToolExec()
    r = ex._handle_tool_batch(_batch_node(), [{"args": {}}], "t")
    assert r["status"] == "error"
    assert "missing 'tool'" in r["error"]


def test_batch_empty():
    ex = _ToolExec()
    r = ex._handle_tool_batch(_batch_node(), [], "t")
    assert r["status"] == "error"
    assert "empty" in r["error"]
