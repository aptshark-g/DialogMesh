#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""执行树消费端量化评测（2026-08-14, 只量化有可量化价值的维度）。

维度（用户拍板: 不能唯数字论, 量化真实可量化项）:
  1. 偏差检测精度 — 带标注合成树集 → 每信号 precision/recall/F1
     （检测器准不准, 这是此前缺失的 goldset 等价物）
  2. 回流有效性 — doom_loop 阈值触发 → MetaFeedback 收到低分审计
     （闭环是否真生效, 不是只看事件数）
  3. 性能缩放 — tree_patterns 在 10/100/500/1000 节点树的耗时
     （结构是否近线性, 不堆无关数字）
  4. 确定性 — 同一树集双跑检测结果一致（防随机抖动）

用法: .venv\\Scripts\\python.exe scripts/exec_consume_eval.py
输出: docs/test/EXEC_CONSUMPTION_EVAL_20260814.md
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core.agent.execution.tree_consumers import (
    AuditFeedbackLoop, MetaTreeConsumer)
from core.agent.execution.tree_manager import (
    ExecutionTree, NodeStatus)


def _build_tree(seed: str, label: str, variant: int = 0) -> ExecutionTree:
    """按标注造执行树（确定性; variant 只扰动步数, 不改信号）。"""
    tree = ExecutionTree()
    if label == "doom_loop":
        n = 3 + (variant % 2)  # 3-4 次同输入
        _task(tree, steps=[
            {"tool": "run_shell", "input": '{"command": "ping x"}'},
            {"tool": "run_shell", "input": '{"command": "ping x"}'},
            {"tool": "run_shell", "input": '{"command": "ping x"}'},
            *[{"tool": "run_shell", "input": '{"command": "ping x"}'}
              for _ in range(n - 3)],
            {"tool": "write_file", "input": '{"path": "a.py"}'},
        ], status=NodeStatus.COMPLETED)
    elif label == "stuck_active":
        t = tree.create_task({"steps": ["卡死"], "strategy": "TOOL_LOOP"})
        t.created_at = time.time() - 3600
    elif label == "failing_tool":
        errs = 2 + (variant % 2)  # 2-3 次失败
        _task(tree, steps=[
            {"tool": "grep", "outcome": "error", "input": "a"},
            *[{"tool": "grep", "outcome": "error", "input": f"b{i}"}
              for i in range(errs - 1)],
            {"tool": "write_file", "outcome": "success", "input": "c"},
        ], status=NodeStatus.COMPLETED)
    elif label == "text_only":
        t = tree.create_task({"steps": ["纯文本"], "strategy": "TOOL_LOOP"})
        tree.complete_node(t.node_id, {"status": "ok", "tools": []})
    elif label == "consecutive_failures":
        _task(tree, steps=[
            {"tool": "run_python", "outcome": "error", "input": "a"},
            {"tool": "run_python", "outcome": "error", "input": "b"},
            {"tool": "run_shell", "outcome": "error", "input": "c"},
        ], status=NodeStatus.COMPLETED)
    else:  # clean
        _task(tree, steps=[
            {"tool": "write_file", "outcome": "success", "input": "a"},
            {"tool": "run_python", "outcome": "success", "input": "b"},
        ], status=NodeStatus.COMPLETED)
    return tree


def _task(tree, steps=None, status=None):
    t = tree.create_task({"steps": ["目标"], "strategy": "TOOL_LOOP"})
    if status:
        t.status = status
    for i, step in enumerate(steps or []):
        n = tree.spawn_sub_agent(
            t.node_id, task=f"{step['tool']}: 第{i}步",
            context_size=0, pointers=[f"trace:{i}"])
        n.content["outcome"] = step.get("outcome", "success")
        n.content["input"] = step.get("input", "")
    if status == NodeStatus.COMPLETED:
        tree.complete_node(t.node_id, {"status": "ok", "tools": [
            s["tool"] for s in (steps or [])]})
    return t


def _detect(tree: ExecutionTree) -> set:
    """检测器对一棵树的信号集合（signal 名）。"""
    c = MetaTreeConsumer(min_interval=0)
    r = c.consume(tree, force=True)
    return {e["signal"] for e in r.get("events", [])}


def main():
    from collections import defaultdict

    labels = ["doom_loop", "stuck_active", "failing_tool",
              "text_only", "consecutive_failures", "clean"]
    # 多标签期望（多信号树: failing_tool 树也含连续失败, 是真实检测
    # 不是误报 — 单标签计数会把真阳算成假阳, 因此用期望集）
    LABEL_SIGNALS = {
        "doom_loop": {"doom_loop"},
        "stuck_active": {"stuck_active"},
        "failing_tool": {"failing_tool", "consecutive_failures"},
        "text_only": {"text_only"},
        "consecutive_failures": {"consecutive_failures", "failing_tool"},
        "clean": set(),
    }
    # 每标注 6 棵: 5 正例（步数扰动）+ 1 干净对照（测 FP）
    cases = []
    for label in labels:
        expected = LABEL_SIGNALS[label]
        for i in range(5):
            cases.append((f"{label}_{i}", expected, label, i))
        cases.append((f"{label}_clean", set(), "clean", None))

    # 1) 检测精度（双跑取一致性验证）
    tp = defaultdict(int)
    fp = defaultdict(int)
    fn = defaultdict(int)
    det1 = {}
    det2 = {}
    t0 = time.time()
    for cid, expected, label, variant in cases:
        tree = _build_tree(cid, label, variant or 0)
        d1 = _detect(tree)
        d2 = _detect(tree)
        det1[cid] = d1
        det2[cid] = d2
        assert d1 == d2, f"确定性破坏: {cid} {d1} != {d2}"
        for signal in ("doom_loop", "stuck_active", "failing_tool",
                       "text_only", "consecutive_failures"):
            want = signal in expected
            if signal in d1 and want:
                tp[signal] += 1
            elif signal in d1 and not want:
                fp[signal] += 1
            elif signal not in d1 and want:
                fn[signal] += 1
    detect_ms = (time.time() - t0) * 1000 / len(cases)

    # 2) 回流有效性
    consumed = []

    class _FakeMF:
        def consume(self, audit):
            consumed.append(audit)

    loop = AuditFeedbackLoop(meta_feedback=_FakeMF())
    loop.consume_event({"kind": "exec_tree_audit", "signal": "doom_loop",
                        "ts": time.time(), "payload": {"tool": "x"}})
    r2 = loop.consume_event({"kind": "exec_tree_audit", "signal": "doom_loop",
                             "ts": time.time(), "payload": {"tool": "x"}})
    reflux_ok = (len(r2.get("actions", [])) == 1
                 and len(consumed) == 1
                 and consumed[0].dag_quality_score == 0.2)

    # 3) 性能缩放（每档一棵树, 确定性构造）
    perf = {}
    for size in (10, 100, 500, 1000):
        tree = ExecutionTree()
        t = tree.create_task({"steps": ["大任务"], "strategy": "TOOL_LOOP"})
        for i in range(size):
            n = tree.spawn_sub_agent(
                t.node_id, task=f"write_file: 第{i}步",
                context_size=0, pointers=[f"trace:{i}"])
            n.content["outcome"] = "success"
            n.content["input"] = '{"path": "f.py"}'
        tree.complete_node(t.node_id, {"status": "ok"})
        t0 = time.time()
        for _ in range(3):
            tree.tree_patterns()
        perf[size] = round((time.time() - t0) * 1000 / 3, 2)

    out = ["# 执行树消费端量化评测（2026-08-14）", "",
           "- 范围: 偏差检测精度 / 回流有效性 / 性能缩放 / 确定性",
           f"- 树集: 36 棵带标注合成树（6 标注 × [5 正例 + 1 干净对照]）",
           "- 解读: 检测器是确定性规则, 合成树按规则构造 → 1.00 分是",
           "  **回归保护**（改坏检测/树结构会破数）; 真实世界精度需",
           "  真实执行迹标注集（待办）; 性能缩放与回流有效性是",
           "  真实可量化项。", ""]
    out += ["## 1. 偏差检测（precision/recall/F1, 每信号）", "",
            "| 信号 | TP | FP | FN | precision | recall | F1 |",
            "|---|---|---|---|---|---|---|"]
    for signal in ("doom_loop", "stuck_active", "failing_tool",
                   "text_only", "consecutive_failures"):
        p = tp[signal] / (tp[signal] + fp[signal]) if (tp[signal] + fp[signal]) else 0
        r = tp[signal] / (tp[signal] + fn[signal]) if (tp[signal] + fn[signal]) else 0
        f1 = 2 * p * r / (p + r) if (p + r) else 0
        out.append(f"| {signal} | {tp[signal]} | {fp[signal]} | {fn[signal]} "
                   f"| {p:.2f} | {r:.2f} | {f1:.2f} |")
    out += ["", "## 2. 回流有效性（闭环是否真生效）", "",
            f"- 2 次 doom_loop 事件 → AuditFeedbackLoop 触发回流: "
            f"{'OK' if reflux_ok else 'FAIL'}",
            f"- MetaFeedback 收到低分审计(0.2): "
            f"{'OK' if reflux_ok else 'FAIL'}", "",
            "## 3. 性能缩放（tree_patterns 平均耗时, 3 次取均）", "",
            "| 节点数 | ms |", "|---|---|"]
    for size, ms in perf.items():
        out.append(f"| {size} | {ms} |")
    out += ["", "## 4. 确定性", "",
            f"- 36 棵双跑信号一致: OK（断言通过）",
            f"- 检测平均耗时: {detect_ms:.1f} ms/树", ""]
    path = "docs/test/EXEC_CONSUMPTION_EVAL_20260814.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("\n".join(out))


if __name__ == "__main__":
    main()
