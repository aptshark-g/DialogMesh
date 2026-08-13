# -*- coding: utf-8 -*-
"""Symbolic context injection — 执行迹 → 紧凑符号图注入（2026-08-10）。

参考: TencentDB Agent Memory 的 MMD 符号注入（token -61% 实证）。
定位: 注入侧结构化——tool_loop 上下文放"提炼后的状态摘要"而非逐轮原文。
互补: 检索侧结构化（文本→SPO/块→混合锚点）已有, 本模块补注入侧。

设计（EXECUTION_LAYER_ARCHITECTURE + RECALL_CROSSLINGUAL_DECISION §三）:
  1. 提炼层: trace(steps) → Mermaid 状态图（高密度, 节点带 node_id=round）
  2. 注入层: tool_loop 上下文保留符号图 + 最近 N 轮原文, 早期原文 offload
  3. 可追溯: node_id(round) → trace 完整步骤可查（TaskResult.trace 全量返回）

默认关闭（symbol_interval=0 不改变既有行为）; 开启后每 N 轮压缩一次。
"""
from __future__ import annotations

from typing import Dict, List, Optional


def trace_to_mermaid(trace: List[Dict], max_nodes: int = 40) -> str:
    """执行迹 → Mermaid 状态图（紧凑符号注入）。

    每步: n<round>["tool: <name><br/>ok|err: <摘要>"]  + 边推进。
    node_id = round 序号（可追溯: 与 TaskResult.trace 对齐）。
    """
    if not trace:
        return ""
    steps = trace[-max_nodes:]
    lines = ["```mermaid", "graph LR"]
    prev = None
    for i, s in enumerate(steps):
        r = s.get("round", i + 1)
        tool = str(s.get("tool", "?"))[:40]
        ok = s.get("ok")
        status = "ok" if ok else ("err" if ok is False else "?")
        err = str(s.get("error", ""))[:80]
        label = f"n{r}[\"{tool} ({status})\""
        if err:
            label = f"n{r}[\"{tool} ERR: {err}\""
        label += "]"
        lines.append(f"    {label}")
        if prev is not None:
            lines.append(f"    n{prev} --> n{r}")
        prev = r
    lines.append("```")
    return "\n".join(lines)


def build_symbol_summary(trace: List[Dict], max_nodes: int = 40) -> str:
    """符号摘要 = Mermaid 图 + 统计行（注入 tool_loop 上下文的完整文本）。"""
    graph = trace_to_mermaid(trace, max_nodes)
    if not graph:
        return ""
    total = len(trace)
    ok_n = sum(1 for s in trace if s.get("ok"))
    err_n = sum(1 for s in trace if s.get("ok") is False)
    tools = {}
    for s in trace:
        t = str(s.get("tool", "?"))
        tools[t] = tools.get(t, 0) + 1
    top = ", ".join(f"{t}×{c}" for t, c in
                    sorted(tools.items(), key=lambda x: -x[1])[:5])
    return (
        "## 执行状态图（符号摘要, 详情按 round 查 trace）\n\n"
        f"- 已完成步骤: {total}（ok={ok_n}, err={err_n}）\n"
        f"- 工具使用: {top}\n\n"
        f"{graph}\n"
    )


def compress_old_tool_rounds(
    msgs: List[Dict],
    trace: List[Dict],
    keep_last: int = 2,
    max_nodes: int = 40,
) -> List[Dict]:
    """压缩早期 tool 轮次: 旧 (assistant+tool) 对 → 一条符号摘要消息。

    保留最近 keep_last 轮原文（LLM 需要近期细节）; 早期原文从上下文移除
    （信息不丢: TaskResult.trace 全量返回, node_id 可追溯）。
    返回新消息列表。默认符号注入关闭时由 tool_loop 决定是否调用。
    """
    if not trace:
        return msgs
    symbol = build_symbol_summary(trace[:-keep_last] if keep_last else trace,
                                  max_nodes)
    if not symbol:
        return msgs
    # 找出所有 tool 轮（assistant tool_calls + 对应 tool 消息）的索引
    tool_msg_idx = [
        i for i, m in enumerate(msgs)
        if m.get("role") == "tool" or m.get("tool_calls")
    ]
    # 保留最后 keep_last*2 条（最近轮次原文）
    drop = tool_msg_idx[:-keep_last * 2] if keep_last > 0 else tool_msg_idx
    if not drop:
        return msgs
    out = [m for i, m in enumerate(msgs) if i not in set(drop)]
    # 在最后一条 tool 消息位置附近插入符号摘要（作为 system 注入）
    insert_at = min(max(drop), len(out))
    out.insert(insert_at, {"role": "system",
                           "content": symbol,
                           "_symbol_summary": True})
    return out
