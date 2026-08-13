# -*- coding: utf-8 -*-
"""符号注入测试 — 执行迹 → Mermaid 状态图 + 上下文压缩（2026-08-10）。"""
from __future__ import annotations

from core.agent.llm.symbol_injector import (
    trace_to_mermaid,
    build_symbol_summary,
    compress_old_tool_rounds,
)


def _trace():
    return [
        {"round": 1, "tool": "write_file", "ok": True, "latency_ms": 12,
         "error": ""},
        {"round": 2, "tool": "run_shell", "ok": False, "latency_ms": 300,
         "error": "command not found: python3"},
        {"round": 3, "tool": "run_shell", "ok": True, "latency_ms": 88,
         "error": ""},
    ]


def test_trace_to_mermaid_generates_graph():
    graph = trace_to_mermaid(_trace())
    assert "mermaid" in graph
    assert "graph LR" in graph
    assert "write_file" in graph
    assert "n1" in graph and "n3" in graph
    assert "--> n2" in graph  # 边推进
    assert "ERR: command not found" in graph


def test_build_symbol_summary_includes_stats():
    s = build_symbol_summary(_trace())
    assert "已完成步骤: 3" in s
    assert "ok=2" in s and "err=1" in s
    assert "write_file×1" in s
    assert "## 执行状态图" in s


def test_compress_keeps_recent_and_symbolizes_old():
    msgs = [
        {"role": "system", "content": "goal"},
        {"role": "user", "content": "do it"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "t1"}]},
        {"role": "tool", "tool_call_id": "t1", "content": "r1"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "t2"}]},
        {"role": "tool", "tool_call_id": "t2", "content": "r2"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "t3"}]},
        {"role": "tool", "tool_call_id": "t3", "content": "r3"},
    ]
    out = compress_old_tool_rounds(msgs, _trace(), keep_last=2)
    # 保留: system/user + 最近 2 轮原文(assistant+tool x2) + 符号摘要
    assert out[0]["role"] == "system"
    assert out[1]["role"] == "user"
    symbol_msgs = [m for m in out if m.get("_symbol_summary")]
    assert len(symbol_msgs) == 1
    assert "mermaid" in symbol_msgs[0]["content"]
    # 旧轮次原文被压缩: 只留 2 轮 (t2,t3) 的 tool 消息
    tool_msgs = [m for m in out if m.get("role") == "tool"]
    assert len(tool_msgs) == 2
    assert "r1" not in [m["content"] for m in tool_msgs]
    assert "r2" in [m["content"] for m in tool_msgs]
    assert "r3" in [m["content"] for m in tool_msgs]


def test_compress_noop_on_short_trace():
    msgs = [{"role": "user", "content": "hi"}]
    out = compress_old_tool_rounds(msgs, [], keep_last=2)
    assert out == msgs


def test_symbol_summary_empty_for_no_trace():
    assert build_symbol_summary([]) == ""
    assert trace_to_mermaid([]) == ""
