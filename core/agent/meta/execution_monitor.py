# -*- coding: utf-8 -*-
"""ExecutionMonitor — 执行层元认知监控（Hot / Warm / Cold 三层）。

设计: EXECUTION_LAYER_ARCHITECTURE_20260809.md §一/§四 + META_ARBITER §四。

  Hot   每步轻量信号（耗时/失败/工具名/预算使用）— 零 LLM, 纯算法
  Warm  执行中/后单次评估 → MonitorVerdict 裁决
        （continue / replan / ask_user / abort）
  Cold  执行结束复盘 → 决策变更事件写 EventLog（用户可见回看）

裁决信号（对齐 META_ARBITER §2.2 三信号, 确定性实现）:
  ① 时间偏差: 预算超时 → replan（MC 例: 手搓超时 → 换 forge）
  ② 质量偏差: 失败率超阈值 / 同一工具连续失败 → replan
  ③ 轮次耗尽无结果 → ask_user（不阻塞, PR review 语义）

Hot 信号零 LLM 成本; Warm 裁决为纯算法（v1 不引入 LLM 评估, 阈值
参数化可调）。冷复盘写入的 meta_advice 事件供前端 changelog 回看。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 默认阈值（可经 thresholds 参数覆盖）
DEFAULT_THRESHOLDS = {
    "failure_rate": 0.5,     # 失败率 ≥ 50% → replan
    "repeat_failures": 2,    # 同一工具连续失败 ≥ 2 → replan
    "ask_user_rounds": 4,    # 达轮次上限且无结果 → ask_user
}

VALID_ACTIONS = ("continue", "replan", "ask_user", "abort")


@dataclass
class MonitorVerdict:
    """一次 Warm 评估的裁决结果。"""
    action: str                    # continue | replan | ask_user | abort
    reason: str = ""               # 触发原因（用户可见）
    advice: str = ""               # 建议（replan 时给替代方向/约束）
    signals: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


class ExecutionMonitor:
    """执行监视器 — 每次 TaskRunner 运行前 reset(), 运行中喂 on_step。"""

    def __init__(self, decision_bus: Any = None,
                 thresholds: Optional[Dict[str, float]] = None):
        self._bus = decision_bus
        self._thresholds = dict(DEFAULT_THRESHOLDS)
        if thresholds:
            self._thresholds.update(thresholds)
        self.reset()

    def attach_bus(self, bus):
        if bus is not None:
            self._bus = bus

    # ── Hot: 每步信号 ──────────────────────────────────────────

    def reset(self):
        self._steps = 0
        self._failures = 0
        self._failed_tools: Dict[str, int] = {}
        self._tool_calls: List[str] = []
        self._elapsed_ms = 0.0
        self._last_error = ""
        self._last_tool = ""
        self._consecutive_failures = 0
        self._t0 = time.time()

    def on_step(self, step: Dict[str, Any]):
        """Hot 钩子 — 每步工具执行后调用（tool_loop on_step）。"""
        self._steps += 1
        tool = str(step.get("tool", ""))
        self._tool_calls.append(tool)
        try:
            self._elapsed_ms += float(step.get("latency_ms", 0.0) or 0.0)
        except (TypeError, ValueError):
            pass
        ok = bool(step.get("ok"))
        if not ok:
            self._failures += 1
            self._failed_tools[tool] = self._failed_tools.get(tool, 0) + 1
            if tool == self._last_tool:
                self._consecutive_failures += 1
            else:
                self._consecutive_failures = 1
            self._last_error = str(step.get("error", ""))[:200]
        else:
            self._consecutive_failures = 0
        self._last_tool = tool

    def signals(self) -> Dict[str, Any]:
        """Hot 信号汇总（零 LLM）。"""
        n = max(self._steps, 1)
        return {
            "steps": self._steps,
            "failures": self._failures,
            "failure_rate": round(self._failures / n, 3),
            "failed_tools": dict(self._failed_tools),
            "tool_calls": list(self._tool_calls),
            "elapsed_ms": round(self._elapsed_ms, 1),
            "wall_ms": round((time.time() - self._t0) * 1000, 1),
            "consecutive_failures": self._consecutive_failures,
            "last_error": self._last_error,
        }

    # ── Warm: 单次评估（确定性裁决）───────────────────────────

    def evaluate(self, max_rounds: int = 0, content: str = "",
                 budget_time_s: float = 0.0) -> MonitorVerdict:
        """执行中/后评估 → 裁决。

        参数:
          max_rounds    蓝图节点给的轮次预算（0 = 不限）
          content       LLM 已产出的最终内容（空 = 尚无结论）
          budget_time_s 时间预算秒（0 = 不限）
        """
        sig = self.signals()
        fail_rate = sig["failure_rate"]
        steps = sig["steps"]

        # ① 时间偏差（预算超时）→ replan
        if budget_time_s and budget_time_s > 0:
            budget_ms = budget_time_s * 1000
            if sig["wall_ms"] >= budget_ms:
                return MonitorVerdict(
                    action="replan",
                    reason=f"预算超时（{sig['wall_ms']:.0f}ms ≥ {budget_ms:.0f}ms）",
                    advice="切换更高效路径或改用已有方案（如下载开源成品改造）",
                    signals=sig,
                )
        # ② 质量偏差: 失败率
        if steps >= 2 and fail_rate >= self._thresholds["failure_rate"]:
            return MonitorVerdict(
                action="replan",
                reason=f"失败率 {fail_rate:.0%} 超阈值",
                advice=f"最近失败: {sig['last_error'][:100] or '未知'}",
                signals=sig,
            )
        # ② 质量偏差: 同一工具连续失败
        if sig["consecutive_failures"] >= self._thresholds["repeat_failures"]:
            return MonitorVerdict(
                action="replan",
                reason=(f"工具 {sig['tool_calls'][-1] if sig['tool_calls'] else '?'} "
                        f"连续失败 {sig['consecutive_failures']} 次"),
                advice=f"错误: {sig['last_error'][:120] or '未知'}",
                signals=sig,
            )
        # ③ 轮次耗尽无结果 → ask_user
        if max_rounds and steps >= max_rounds and not content:
            return MonitorVerdict(
                action="ask_user",
                reason=f"已达 {max_rounds} 轮工具调用仍无最终答复",
                advice="是否继续深入？可调整约束/工具范围或改方案",
                signals=sig,
            )
        return MonitorVerdict(action="continue", reason="", signals=sig)

    # ── Cold: 复盘 → 决策事件（用户可见回看）──────────────────

    def review(self, result: Dict[str, Any], node_id: str = "",
               session_id: str = "", request_id: str = "",
               turn: int = 0) -> Optional[Dict[str, Any]]:
        """执行结束复盘: 非 continue 的裁决写 meta_advice 事件。

        返回写入的事件 dict（无 bus 或正常完成时返回 None）。
        """
        action = str(result.get("verdict", "continue"))
        if action == "continue":
            return None
        if self._bus is None:
            return None
        try:
            return self._bus.log(
                kind="meta_advice",
                dimension=f"execution.node.{node_id or '?'}",
                before=None,
                after={"verdict": action,
                       "reason": result.get("reason", ""),
                       "advice": result.get("advice", "")},
                reason=f"执行监控裁决: {result.get('reason', action)}",
                actor="meta",
                turn=turn,
                request_id=request_id,
            )
        except Exception as e:
            logger.debug("execution monitor review event failed: %s", e)
            return None
