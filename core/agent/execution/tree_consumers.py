# -*- coding: utf-8 -*-
"""执行树消费器（2026-08-14, 吸收 Grok/OpenCode/OpenClaw/OpenWorker）。

设计主线: EXECUTION_LAYER_ARCHITECTURE_20260809 元认知树图职责 —
  执行中/后 → 树图分析 → 偏差检测（本模块）→ 介入仍走既有裁决
  （ExecutionMonitor 在线 Warm / PlanGate 人工 / TaskRunner 重规划）。

吸收纪律（跨项目共识, 见 EXEC_TREE_CONSUMPTION_ABSORPTION）:
  1. 检测与介入分离（Grok/OpenCode/OpenClaw 三方印证）— 只发事件
  2. doom loop = 同工具+同输入连续 N 次, 不是失败次数（OpenCode O3）
  3. 消费频率门控 = 代码常量（Hermes H2）— 配置不能变高频写手
  4. 审计事件 schema 化（OpenWorker W1 / Grok / OpenCode）
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from core.agent.execution.tree_manager import AgentTreeNode

logger = logging.getLogger(__name__)


# 偏差信号集（对齐吸收: O3 doom loop / OpenClaw 循环恢复 / Grok 检测器）
VALID_SIGNALS = ("doom_loop", "stuck_active", "failing_tool",
                 "text_only", "consecutive_failures")


class MetaTreeConsumer:
    """元认知消费器 — 读执行树发现偏差（检测层, 不介入）。

    输出: decision_bus.log(kind="exec_tree_audit", ...) 事件
    （schema: signal/维度/原因/载荷）。介入权保持在外层:
    本模块绝不发 replan/abort 类建议（那会与 ExecutionMonitor
    在线裁决打架 — 两个裁决者=一个系统两个大脑）。
    """

    # 频率纪律（H2）: 代码常量, 独立于任何配置 — 消费不能变高频写手。
    # 任务完成时 force=True 可旁路（终端状态立即审计, Grok force_persist 同语义）。
    MIN_INTERVAL_SECONDS = 60.0
    STUCK_ACTIVE_SECONDS = 300.0
    DOOM_LOOP_COUNT = 3

    def __init__(self, bus: Any = None, min_interval: Optional[float] = None):
        self._bus = bus
        self._min_interval = (min_interval
                              if min_interval is not None
                              else self.MIN_INTERVAL_SECONDS)
        self._last_consume = 0.0
        self._audit_count = 0

    def consume(self, tree: Any, session_id: str = "",
                force: bool = False) -> Dict[str, Any]:
        """读树 → 偏差事件。返回 {events, skipped?, patterns}。"""
        now = time.time()
        if not force and now - self._last_consume < self._min_interval:
            return {"skipped": True, "reason": "interval",
                    "events": [], "patterns": {}}
        self._last_consume = now
        if tree is None:
            return {"events": [], "patterns": {}}
        patterns = tree.tree_patterns()
        events: List[Dict[str, Any]] = []
        for dl in patterns.get("doom_loops", []):
            events.append(self._emit("doom_loop", session_id, {
                "tool": dl.get("tool"), "input": dl.get("input"),
                "count": dl.get("count"),
                "reason": f"同工具同输入连续 {dl.get('count')} 次（死循环）",
            }))
        if patterns.get("stuck_active"):
            events.append(self._emit("stuck_active", session_id, {
                "count": patterns["stuck_active"],
                "reason": f"{patterns['stuck_active']} 个任务卡 ACTIVE "
                          f"超 {self.STUCK_ACTIVE_SECONDS / 60:.0f} 分钟",
            }))
        for tool in patterns.get("failing_tools", []):
            events.append(self._emit("failing_tool", session_id, {
                "tool": tool, "reason": f"工具 {tool} 失败≥成功（抖动信号）",
            }))
        if patterns.get("text_only"):
            events.append(self._emit("text_only", session_id, {
                "count": patterns["text_only"],
                "reason": "完成但无任何工具步骤（纯文本回合）",
            }))
        for cf in patterns.get("consecutive_failures", []):
            if cf >= 2:
                events.append(self._emit("consecutive_failures", session_id, {
                    "count": cf, "reason": f"任务内连续失败 {cf} 步",
                }))
        return {"events": events, "patterns": patterns}

    def _emit(self, signal: str, session_id: str,
              payload: Dict[str, Any]) -> Dict[str, Any]:
        """审计事件（schema 化: signal/维度/原因/载荷）。"""
        event = {
            "kind": "exec_tree_audit",
            "signal": signal,
            "dimension": f"exec_tree.{signal}",
            "session_id": session_id,
            "reason": payload.get("reason", ""),
            "payload": {k: v for k, v in payload.items() if k != "reason"},
            "ts": time.time(),
        }
        self._audit_count += 1
        bus = self._bus
        if bus is not None and hasattr(bus, "log"):
            try:
                bus.log(
                    kind="exec_tree_audit",
                    dimension=event["dimension"],
                    before=None,
                    after={"signal": signal, "payload": event["payload"]},
                    reason=event["reason"],
                    actor="meta",
                    attribution="tool",
                )
            except Exception as e:
                logger.debug("exec_tree_audit log failed: %s", e)
        else:
            logger.info("exec_tree_audit[%s] %s: %s",
                        signal, session_id or "?", event["reason"])
        return event


class ExecutionPatternStore:
    """执行模式沉淀（行为链学模式的批处理形态, dream 门控）。

    设计边界（用户拍板: 主旋律自有设计 + A9 在线学习契约）:
      不污染 BehaviorBrain 的用户行为预测模型 — 工具序列/成败是
      "执行模式", 不是用户行为事件（learn_from_event 喂错会造
      假 reject 池, brain.py 已有同类警告）。沉淀结果供:
        - W7 深度偏好雏形（任务步骤数 → 深挖话题识别）
        - 预测学习加强的原料（待办, §五）
    """

    MIN_INTERVAL_SECONDS = 300.0   # 频率纪律（H2）: 5 分钟起步

    def __init__(self, path: Optional[str] = None,
                 min_interval: Optional[float] = None):
        self._path = path or self._default_path()
        self._min_interval = (min_interval
                              if min_interval is not None
                              else self.MIN_INTERVAL_SECONDS)
        self._last_consume = 0.0
        self._lock = threading.Lock()
        self._patterns: Dict[str, Any] = {
            "tool_sequences": [], "tool_stats": {}, "tasks": 0,
            "avg_steps": 0.0, "max_steps": 0, "sessions": set(),
        }
        self._load()

    @staticmethod
    def _default_path() -> str:
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))),
            "data", "execution_patterns.json")

    def _load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._patterns["tool_sequences"] = data.get("tool_sequences", [])
            self._patterns["tool_stats"] = data.get("tool_stats", {})
            self._patterns["tasks"] = int(data.get("tasks", 0))
            self._patterns["avg_steps"] = float(data.get("avg_steps", 0.0))
            self._patterns["max_steps"] = int(data.get("max_steps", 0))
            self._patterns["sessions"] = set(data.get("sessions", []))
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug("execution patterns load failed: %s", e)

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({
                    "tool_sequences": self._patterns["tool_sequences"][-200:],
                    "tool_stats": self._patterns["tool_stats"],
                    "tasks": self._patterns["tasks"],
                    "avg_steps": self._patterns["avg_steps"],
                    "max_steps": self._patterns["max_steps"],
                    "sessions": sorted(self._patterns["sessions"])[-100:],
                }, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self._path)
        except Exception as e:
            logger.debug("execution patterns save failed: %s", e)

    def consume(self, tree: Any, session_id: str = "",
                force: bool = False) -> Dict[str, Any]:
        """dream 门控: 距上次 >= min_interval（或 force）才消费。"""
        now = time.time()
        if not force and now - self._last_consume < self._min_interval:
            return {"skipped": True, "reason": "interval"}
        self._last_consume = now
        if tree is None:
            return {"skipped": True, "reason": "no_tree"}
        p = tree.tree_patterns()
        with self._lock:
            self._patterns["tasks"] += p["tasks"]
            self._patterns["sessions"].add(session_id or "_")
            for seq in p.get("tool_sequences", []):
                self._patterns["tool_sequences"].append(seq)
                for tool in seq:
                    st = self._patterns["tool_stats"].setdefault(
                        tool, {"uses": 0, "errors": 0})
                    st["uses"] += 1
            for tool, bucket in p.get("tool_outcomes", {}).items():
                st = self._patterns["tool_stats"].setdefault(
                    tool, {"uses": 0, "errors": 0})
                st["errors"] += bucket.get("error", 0)
            n = max(1, self._patterns["tasks"])
            self._patterns["avg_steps"] = round(
                (self._patterns["avg_steps"] * (n - 1)
                 + p["avg_steps_per_task"]) / n, 2)
            self._patterns["max_steps"] = max(
                self._patterns["max_steps"], p["max_steps_per_task"])
            self._save()
        return {"skipped": False, "patterns": dict(self._patterns)}

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            out = dict(self._patterns)
            out["sessions"] = sorted(out["sessions"])
            return out


# 执行摘要模板（2026-08-14, 阶段 4, 吸收 O5 简化 + W3 只改出站视图）。
# 三策略（用户拍板: 多选比单一好 — 机械提取受纸面字面限制, LLM 补语义;
# 对应 P2 算法与 LLM 分工）:
#   mechanical — 确定性模板, 零成本零延迟（默认）
#   llm       — LLM 按模板生成（Goal/Discoveries/Accomplished/Files）
#   hybrid    — 机械骨架 + LLM 语义补全（Discoveries/Next steps）
SUMMARY_STRATEGIES = ("mechanical", "llm", "hybrid")
SUMMARY_TEMPLATE = (
    "## Goal\n{goal}\n\n## Steps\n{steps}\n\n"
    "## Outcomes\n{outcomes}\n\n## Files\n{files}\n\n"
    "## Verdict\n{verdict}"
)


def _extract_files(steps: List[AgentTreeNode]) -> List[str]:
    """从步骤输入机械提取文件/路径（OpenWorker _resource 同思路）。
    受纸面限制: 只认 path/file/目标 键; LLM 策略可补语义。"""
    out: List[str] = []
    for s in steps:
        inp = (s.content.get("input") or "") or ""
        try:
            args = json.loads(inp) if inp.startswith("{") else {}
        except Exception:
            args = {}
        for key in ("path", "file", "target"):
            val = args.get(key)
            if isinstance(val, str) and val and val not in out:
                out.append(val)
    return out[:8]


def render_execution_summary(
    tree: Any,
    task_id: str,
    strategy: str = "mechanical",
    llm_callback: Optional[Any] = None,
) -> Dict[str, Any]:
    """执行摘要（纯函数, 只读树 — 只改出站视图, 不动持久化）。

    mechanical: 确定性模板; llm: LLM 模板生成; hybrid: 机械骨架 +
    LLM 语义补全（Discoveries/Next steps）。失败降级 mechanical。
    """
    if tree is None:
        return {"ok": False, "error": "no tree", "summary": ""}
    task = tree.get_node(task_id) if hasattr(tree, "get_node") else None
    if task is None:
        tasks = tree.get_tasks()
        task = tasks[0] if tasks else None
    if task is None:
        return {"ok": False, "error": "no task", "summary": ""}
    steps = tree.get_subagents(task.node_id)
    result = (task.content.get("result") or {}) if isinstance(
        task.content.get("result"), dict) else {}
    status = str(result.get("status") or task.status.value)
    tools = [tree._tool_name_of(s) for s in steps]
    outcomes = {}
    for s in steps:
        o = tree._outcome_of(s)
        outcomes[o] = outcomes.get(o, 0) + 1
    files = _extract_files(steps)
    goal = (task.content.get("steps") or ["(未记录)"])
    goal_text = str(goal[0] if goal else "(未记录)")[:200]
    base = SUMMARY_TEMPLATE.format(
        goal=goal_text,
        steps=" → ".join(tools) if tools else "（无工具步骤）",
        outcomes=", ".join(f"{k}={v}" for k, v in outcomes.items())
        if outcomes else "（无）",
        files=", ".join(files) if files else "（未识别）",
        verdict=f"{status} (rounds={result.get('rounds', '?')}, "
                f"replans={result.get('replans', 0)})",
    )
    if strategy == "mechanical":
        return {"ok": True, "strategy": "mechanical", "summary": base}
    if llm_callback is None:
        return {"ok": True, "strategy": "mechanical",
                "summary": base, "note": "llm 策略无回调, 降级 mechanical"}
    prompt = (
        "把执行记录压缩为续接摘要（保留目标/发现/完成/文件）:\n"
        f"{base}\n\n只输出摘要文本:"
    )
    try:
        if callable(llm_callback):
            text = str(llm_callback(prompt) or "").strip()
        elif hasattr(llm_callback, "generate"):
            from core.agent.llm_providers.base import GenerateRequest
            result = llm_callback.generate(GenerateRequest(
                prompt=prompt, max_tokens=400, temperature=0.0,
                metadata={"thinking": {"type": "disabled"}}))
            text = str(getattr(result, "text", "") or "").strip()
        else:
            text = ""
    except Exception as e:
        logger.debug("execution summary llm failed: %s", e)
        text = ""
    if not text:
        return {"ok": True, "strategy": "mechanical", "summary": base,
                "note": "llm 空返回, 降级 mechanical"}
    if strategy == "llm":
        return {"ok": True, "strategy": "llm", "summary": text}
    # hybrid: 机械骨架 + LLM 语义补全
    return {"ok": True, "strategy": "hybrid",
            "summary": f"{base}\n\n## Discoveries / Next\n{text[:800]}"}


class AuditFeedbackLoop:
    """审计事件 → 回流闭环（2026-08-14, 阶段 5 补: 检测→介入→回流）。

    设计边界（用户拍板: 检测与介入分离）:
      本循环只做**学习层回流**（ExecutionAudit → MetaFeedback 策略权重,
      A6 修正回流）— 不直接改执行流（那仍是 ExecutionMonitor 在线
      裁决 / PlanGate 人工的事）。回流动作发 decision_bus 事件可回看。

    触发（窗口聚合, 防单次误报）:
      doom_loop >= 2   — 同输入死循环反复出现 → 策略降级信号
      failing_tool >= 2 — 多个失败工具（非单次抖动）→ 权重下调
    """

    DOOM_LOOP_TRIGGER = 2
    FAILING_TOOL_TRIGGER = 2
    WINDOW_SECONDS = 3600.0

    def __init__(self, meta_feedback: Any = None,
                 decision_bus: Any = None):
        self._meta_feedback = meta_feedback
        self._bus = decision_bus
        self._window: List[Dict[str, Any]] = []
        self._triggered = 0

    def consume_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """接收一条 exec_tree_audit 事件; 窗口聚合, 达阈值回流。"""
        if not isinstance(event, dict) or event.get("kind") != "exec_tree_audit":
            return {"ok": False, "reason": "not_audit"}
        now = time.time()
        self._window = [e for e in self._window
                        if now - float(e.get("ts", 0) or 0) <= self.WINDOW_SECONDS]
        self._window.append(event)
        doom = sum(1 for e in self._window
                   if e.get("signal") == "doom_loop")
        failing_tools = {
            (e.get("payload") or {}).get("tool")
            for e in self._window if e.get("signal") == "failing_tool"}
        actions: List[Dict[str, Any]] = []
        if doom >= self.DOOM_LOOP_TRIGGER:
            actions.append(self._feedback(
                "doom_loop", doom,
                f"窗口内 {doom} 次同输入死循环 → 执行策略降级信号"))
        if len(failing_tools) >= self.FAILING_TOOL_TRIGGER:
            tools = sorted(t for t in failing_tools if t)
            actions.append(self._feedback(
                "failing_tool", len(tools),
                f"窗口内 {len(tools)} 个失败工具 {tools} → 工具权重下调信号"))
        if actions:
            self._triggered += 1
            self._window = []   # 触发后清窗, 防重复回流
        return {"ok": True, "window": len(self._window),
                "actions": actions}

    def _feedback(self, signal: str, count: int,
                  reason: str) -> Dict[str, Any]:
        """回流: ExecutionAudit(低分+异常) → MetaFeedback; 事件留痕。"""
        action = {"signal": signal, "count": count, "reason": reason,
                  "ts": time.time()}
        if self._meta_feedback is not None and hasattr(
                self._meta_feedback, "consume"):
            try:
                from core.agent.blueprint.models import ExecutionAudit
                self._meta_feedback.consume(ExecutionAudit(
                    request_id=f"exec_tree_audit:{signal}",
                    blueprint_id="execution_tree",
                    strategy="EXECUTION",
                    dag_quality_score=0.2,
                    anomalies=[reason],
                ))
                action["reflux"] = "meta_feedback"
            except Exception as e:
                logger.debug("audit reflux failed: %s", e)
                action["reflux"] = "failed"
        if self._bus is not None and hasattr(self._bus, "log"):
            try:
                self._bus.log(
                    kind="strategy_switch",
                    dimension=f"exec_audit_reflux.{signal}",
                    before={"window_signal": signal},
                    after={"count": count, "reflux": action.get("reflux")},
                    reason=reason,
                    actor="meta",
                    attribution="tool",
                )
            except Exception as e:
                logger.debug("audit reflux event failed: %s", e)
        return action

    def summary(self) -> Dict[str, Any]:
        return {"triggered": self._triggered,
                "window_size": len(self._window)}
