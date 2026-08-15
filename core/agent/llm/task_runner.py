# -*- coding: utf-8 -*-
"""TaskRunner — 蓝图节点级执行壳（v2 执行层分层, 2026-08-09）。

架构: EXECUTION_LAYER_ARCHITECTURE_20260809.md
  tool_loop = 微观执行引擎（自由 ReAct, 无约束）
  TaskRunner = 壳①: 蓝图约束注入（节点目标/范围/工具白名单）
             + 壳②: 元认知监控（ExecutionMonitor Hot/Warm/Cold）
             + 壳③: 三层介入（InterventionRouter 低/中/高风险路由）
             + 壳④: 复盘回流（meta_advice 决策事件 + MetaFeedback）

重规划循环（MC 例: 5 分钟做 MC 游戏）:
  第 1 轮: 手搓任务规划 → 监视检出"预算超时/失败率" → replan 裁决
  → InterventionRouter 路由（低/中风险自动继续, 高风险停下等用户）
  → replanner 回调给出替代约束（如"下载 forge 改造"）→ 重跑
  第 2 轮: 新约束下执行 → 正常完成 → continue

每次 replan / ask_user / abort 都写决策事件（/v6/changelog 可回看可介入）。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.agent.llm.tool_loop import tool_loop as _default_llm_loop

logger = logging.getLogger(__name__)


@dataclass
class TaskConstraint:
    """蓝图节点约束 — 注入执行 LLM 的系统提示。"""
    goal: str                                  # 节点目标（必须）
    scope: str = ""                            # 允许范围描述
    steps: Optional[List[str]] = None          # 规划产物步骤（任务图节点,
                                               # 2026-08-15: 落执行树 +
                                               # 注入执行上下文）
    allowed_tools: Optional[List[str]] = None  # 工具白名单（None = 全部）
    max_rounds: int = 6                        # 轮次预算
    timeout_s: float = 120.0                   # 总执行截止（tool_loop 硬截止）
    budget_time_s: float = 0.0                 # 监视时间预算（0 = 用 timeout_s）
    max_replans: int = 1                       # 自动重规划次数上限
    symbol_interval: int = 0                   # 符号注入: 每 N 轮压缩早期
                                               # tool 原文为状态图（0 = 关）
    symbol_keep_last: int = 2                  # 保留最近几轮 tool 原文


@dataclass
class TaskResult:
    """一次节点执行的完整结果（前端执行迹 + 决策事件回看）。"""
    status: str = "error"              # ok | replan | ask_user | aborted | timeout | error
    verdict: str = "continue"          # continue | replan | ask_user | abort
    content: str = ""
    reason: str = ""
    advice: str = ""
    tool_calls: List[Dict] = field(default_factory=list)
    trace: List[Dict] = field(default_factory=list)
    rounds: int = 0
    replans: int = 0
    latency_ms: float = 0.0
    node_id: str = ""
    events: List[Dict] = field(default_factory=list)  # 决策事件（回看）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status, "verdict": self.verdict,
            "content": self.content[:2000], "reason": self.reason,
            "advice": self.advice, "tool_calls": self.tool_calls[-20:],
            "rounds": self.rounds, "replans": self.replans,
            "latency_ms": round(self.latency_ms, 1), "node_id": self.node_id,
            "events": self.events[-10:],
        }


def _resolve_decision_bus() -> Optional[Any]:
    """惰性解析引擎的决策事件总线（changelog 同源, 回看可见）。"""
    try:
        from core.agent.cli.engine import get_engine
        eng = get_engine()
        if eng is not None:
            return getattr(eng, "_decision_bus", None)
    except Exception:
        pass
    return None


class TaskRunner:
    """蓝图节点级执行壳 — 约束注入 → tool_loop → 监控 → 重规划 → 复盘。"""

    def __init__(self, decision_bus: Any = None, monitor: Any = None,
                 intervention: Any = None, replanner: Optional[Callable] = None,
                 meta_feedback: Any = None, llm_loop: Optional[Callable] = None,
                 model: str = "", trace_store: Any = None,
                 execution_tree: Any = None):
        # 默认内存空总线（不触发 get_engine, 单元测试零启动成本）。
        # 生产接线（v3_session_api / statemachine）显式传 engine 总线,
        # 或调用 attach_engine_bus() 让事件进 /v6/changelog。
        if decision_bus is None:
            from core.agent.blueprint.decision_event import DecisionEventBus
            decision_bus = DecisionEventBus()
        self._bus = decision_bus
        from core.agent.meta.execution_monitor import ExecutionMonitor
        self._monitor = monitor or ExecutionMonitor(decision_bus=self._bus)
        from core.agent.blueprint.intervention import InterventionRouter
        self._intervention = intervention or InterventionRouter(decision_bus=self._bus)
        self._replanner = replanner          # callable(goal, verdict) → TaskConstraint | None
        self._meta_feedback = meta_feedback  # 复盘回流（A6）: consume(ExecutionAudit)
        self._llm_loop = llm_loop or _default_llm_loop
        self._model = model
        self._trace_store = trace_store
        # 执行轨迹落树（2026-08-13, P0 接线）: 淘宝 PES"全链路可回放" —
        # 每步执行同步写 ExecutionTree（create_task/spawn_sub_agent/
        # complete_node）, 行为链读树学模式, 元认知读树发现偏差。
        self._execution_tree = execution_tree

    def attach_engine_bus(self) -> bool:
        """绑定引擎的决策事件总线（changelog 同源, 回看可见）。"""
        bus = _resolve_decision_bus()
        if bus is None:
            return False
        self._bus = bus
        self._monitor.attach_bus(bus)
        self._intervention.attach_bus(bus)
        return True

    # ── 约束注入 ──────────────────────────────────────────────

    @staticmethod
    def build_inject(constraint: TaskConstraint) -> str:
        """把蓝图节点约束编译成 system 注入文本（层1 → 层2 投影）。"""
        parts = [f"## 当前任务节点目标\n{constraint.goal}"]
        # 2026-08-15（规划→执行步骤级接线）: 用户确认的任务图节点作为
        # 步骤地图注入 — 执行层不再只有原始 goal, 而是沿规划产物走。
        if constraint.steps:
            parts.append(
                "## 任务步骤地图（规划产物, 沿此推进, 可在范围内细化）\n"
                + "\n".join(
                    f"{i + 1}. {s}" for i, s in enumerate(constraint.steps)))
        # 2026-08-15（A2 地图式递归图落地）: 探索前先注入项目粗结构 —
        # 规划/探索任务模型曾逐格 dir_list 盲探（23 次死循环）; 粗视图
        # 一次给收敛判据, dir_list 变成定向缩放。
        try:
            from core.agent.tools.os_tools import _project_map
            pm = _project_map()
            if pm.success and pm.data.get("tree"):
                parts.append(
                    "## 项目结构概览（粗颗粒度, 先看全景再定向深入）\n"
                    + pm.data["tree"])
        except Exception:
            pass
        if constraint.scope:
            parts.append(f"## 允许范围\n{constraint.scope}")
        if constraint.allowed_tools:
            parts.append(
                "## 允许使用的工具\n" + ", ".join(constraint.allowed_tools))
        parts.append(
            "## 执行纪律\n"
            "- 只在当前节点目标范围内调用工具, 不越界\n"
            "- 完成节点目标后直接给出最终答复（不要再调用工具）")
        return "\n\n".join(parts)

    # ── 主执行 ────────────────────────────────────────────────

    def run(self, goal: str, context: Optional[Dict[str, Any]] = None,
            constraint: Optional[TaskConstraint] = None, node_id: str = "",
            session_id: str = "", request_id: str = "", turn: int = 0,
            messages: Optional[List[Dict]] = None,
            anchors: Optional[str] = None) -> TaskResult:
        """执行一个蓝图节点。返回 TaskResult（含监控裁决 + 决策事件）。"""
        t0 = time.time()
        constraint = constraint or TaskConstraint(goal=goal)
        if not constraint.goal:
            constraint.goal = goal
        msgs = [dict(m) for m in (messages or [])]
        if not any(m.get("role") == "system" for m in msgs):
            msgs.insert(0, {"role": "system",
                            "content": "你是 DialogMesh 执行层 agent。"})
        inject = self.build_inject(constraint)
        # v2.1 召回→执行层桥（RECALL_EXECUTION_BRIDGE_DESIGN）:
        # 粗召回锚点作为候选注入, LLM 用文件工具精确查阅真实内容。
        if anchors:
            inject = inject + "\n\n" + anchors
        budget_time = (constraint.budget_time_s or constraint.timeout_s
                       or 0.0)
        result = TaskResult(node_id=node_id)

        # 执行轨迹落树（P0）: 任务节点 create_task → 每步 spawn_sub_agent
        # → 收尾 complete_node（可回放/审计/归因）。
        tree = self._execution_tree
        tree_node_id = None
        _tree_steps: list = []
        if tree is not None:
            try:
                tree_node_id = tree.create_task(
                    {"steps": (constraint.steps
                               if constraint.steps else [constraint.goal]),
                     "strategy": "TOOL_LOOP"}).node_id
            except Exception as e:
                logger.debug("execution tree create_task failed: %s", e)
                tree_node_id = None

        def _step_hook(step):
            try:
                self._monitor.on_step(step)
            except Exception:
                pass
            if tree is not None and tree_node_id:
                try:
                    _tree_steps.append(step)
                    node = tree.spawn_sub_agent(
                        tree_node_id,
                        task="%s: %s" % (
                            step.get("name") or step.get("tool", "?"),
                            str(step.get("summary") or
                                step.get("args") or "")[:120]),
                        context_size=0,
                        pointers=["trace:%s" % step.get("round", 0)])
                    # 阶段 0（吸收 A2/O3）: 结果词汇化写节点 —
                    # 每步 outcome + 输入摘要, 执行树消费端可查
                    # "同工具+同输入连续 N 次"死循环与成败统计。
                    node.content["outcome"] = (
                        "error" if not step.get("ok") else "success")
                    node.content["input"] = (
                        str(step.get("input") or "")[:200])
                except Exception:
                    pass

        cur = constraint
        for attempt in range(1 + max(0, constraint.max_replans)):
            self._monitor.reset()
            try:
                raw = self._llm_loop(
                    msgs, model=self._model, max_rounds=cur.max_rounds,
                    allowed_tools=cur.allowed_tools, system_inject=inject,
                    on_step=_step_hook, timeout_s=cur.timeout_s,
                    symbol_interval=cur.symbol_interval,
                    symbol_keep_last=cur.symbol_keep_last)
            except Exception as _le:
                # 2026-08-13: 异常转 error 结果（不冒泡）— 保证落树收尾
                # （complete_node）与复盘回流必然执行, 树节点不卡 ACTIVE。
                logger.debug("llm_loop failed: %s", _le)
                result.status = "error"
                result.verdict = "abort"
                result.reason = str(_le)[:200]
                break
            content = str(raw.get("content", "") or "")
            error = str(raw.get("error", "") or "")
            result.tool_calls = raw.get("tool_calls") or []
            result.trace = raw.get("trace") or []
            result.rounds = int(raw.get("rounds", 0))

            verdict = self._monitor.evaluate(
                max_rounds=cur.max_rounds, content=content,
                budget_time_s=budget_time)
            if error and "timeout" in error:
                verdict.action = "replan"
                verdict.reason = verdict.reason or "tool_loop 超时"

            if verdict.action == "continue":
                result.status = "ok"
                result.verdict = "continue"
                result.content = content
                break

            # 非 continue: 三层介入路由（低=applied 留痕 / 中=proposed
            # 不阻塞 / 高=sync_required 停下等用户确认）
            routed = self._intervention.route(
                kind="meta_advice",
                dimension=f"execution.node.{node_id or '?'}",
                before=cur.goal,
                after=verdict.advice or verdict.reason,
                reason=verdict.reason, actor="meta",
                turn=turn, request_id=request_id,
                attribution="plan" if verdict.action == "replan" else "tool",
            )
            result.events.append(routed)

            if verdict.action == "abort" or routed.get("sync_required"):
                result.status = "aborted"
                result.verdict = "abort"
                result.reason = verdict.reason + "（高风险, 等待用户确认）"
                result.advice = verdict.advice
                break

            if attempt >= max(0, constraint.max_replans):
                result.status = verdict.action  # replan | ask_user
                result.verdict = verdict.action
                result.reason = verdict.reason
                result.advice = verdict.advice
                result.content = content
                break

            # 还有重规划额度 → replanner 给替代约束
            new_constraint = None
            if self._replanner is not None:
                try:
                    new_constraint = self._replanner(cur.goal, verdict)
                except Exception as e:
                    logger.debug("replanner failed: %s", e)
            if new_constraint is None or not getattr(new_constraint, "goal", ""):
                result.status = "ask_user"
                result.verdict = "ask_user"
                result.reason = verdict.reason + "（无可自动替换方案）"
                result.advice = verdict.advice
                break
            cur = new_constraint
            result.replans += 1
            inject = self.build_inject(cur)
            if anchors:
                inject = inject + "\n\n" + anchors
            logger.info("TaskRunner replan #%d: %s → %s (reason: %s)",
                        result.replans, goal, cur.goal, verdict.reason)
        else:
            result.status = "error"
            result.verdict = "abort"
            result.reason = "重规划次数耗尽"

        result.latency_ms = (time.time() - t0) * 1000
        # Cold 复盘: 非 continue 写 meta_advice 事件（可回看）
        self._monitor.review(
            {"verdict": result.verdict, "reason": result.reason,
             "advice": result.advice},
            node_id=node_id, session_id=session_id,
            request_id=request_id, turn=turn)
        # 复盘回流（A6）: 可选 MetaFeedback 消费（执行质量 → 策略权重）
        self._writeback(result, node_id, request_id)
        # 执行轨迹落树收尾: 完整/失败/中止都落 result 摘要
        if tree is not None and tree_node_id:
            try:
                tree.complete_node(tree_node_id, {
                    "status": result.status,
                    "verdict": result.verdict,
                    "reason": (result.reason or "")[:200],
                    "rounds": result.rounds,
                    "replans": result.replans,
                    "tools": [str(s.get("tool", "?"))
                              for s in _tree_steps[:20]],
                    "latency_ms": result.latency_ms,
                })
            except Exception as e:
                logger.debug("execution tree complete failed: %s", e)
        return result

    def _writeback(self, result: TaskResult, node_id: str,
                   request_id: str = ""):
        """执行成败 → ExecutionAudit → MetaFeedback（A6 修正回流）。"""
        # 生产轨迹（情景再现的"写的代码"支线）: 工具序列写入 trace_store
        if self._trace_store is not None:
            try:
                from core.agent.blueprint.learning_bridge import ExecutionTrace
                seq = [str(tc.get("name", "?"))
                       for tc in (result.tool_calls or [])]
                if seq:
                    self._trace_store.add(ExecutionTrace(
                        request_id=request_id or "task_runner",
                        intent=node_id or "task_node",
                        tool_sequence=seq,
                        strategy="EXECUTION",
                        success=result.status == "ok",
                        source_dag_id=request_id or "",
                    ))
            except Exception as e:
                logger.debug("trace_store write failed: %s", e)
        if self._meta_feedback is None:
            return
        try:
            from core.agent.blueprint.models import ExecutionAudit
            score = 1.0 if result.status == "ok" else 0.2
            anomalies = []
            if result.verdict != "continue":
                anomalies.append(result.reason or result.verdict)
            self._meta_feedback.consume(ExecutionAudit(
                request_id=request_id or "task_runner",
                blueprint_id=node_id or "task_node",
                strategy="EXECUTION",
                dag_quality_score=score,
                anomalies=anomalies,
            ))
        except Exception as e:
            logger.debug("task runner writeback failed: %s", e)
