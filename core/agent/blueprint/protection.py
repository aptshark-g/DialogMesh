# -*- coding: utf-8 -*-
"""LLM_DRIVEN 四保护 — G3 (FLOW_SELF_GROWTH §三 G3).

四保护（设计: FLOW_SELF_GROWTH_20260806.md §三 G3）:
  PlanGate      — 高风险节点暂停, 用户 approve/adjust/reject（checkpoint 字段）
  Budget        — 节点数 ≤ 7 + 执行期总节点执行上限（防 RECOVERY 死循环）
  LoopDetector  — 重访节点 3 次 → 强制 checkpoint（plan_gate 事件）
  QualityGate   — 执行后元认知评分 → 低分降级 HYBRID（strategy_switch 事件）

全部保护动作走 decision_bus 事件（META_ARBITER §3.2 可回看/可介入）,
无 bus 时安全降级（记录日志, 不阻塞执行）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.agent.blueprint.models import BlueprintDAG, BlueprintNode

logger = logging.getLogger(__name__)

# 默认预算（与 ConstraintChecker.MAX_NODES 对齐）
DEFAULT_MAX_NODES = 7
# 执行期总节点执行上限 = 节点数 × 倍数（RECOVERY 替换/重跑可放大）
DEFAULT_EXECUTION_MULTIPLIER = 4
# LoopDetector 阈值: 同一节点执行次数 ≥ 3 → 强制 checkpoint
DEFAULT_LOOP_THRESHOLD = 3
# QualityGate 低分阈值
DEFAULT_QUALITY_LOW = 0.4
# 高风险链（写/不可逆操作, 触发 PlanGate 同步确认）
HIGH_RISK_CHAINS = {"tool", "engineering", "metap"}


# ═══════════════════════════════════════════════════════════════
# PlanGate
# ═══════════════════════════════════════════════════════════════

class PlanGate:
    """PlanGate checkpoint — 高风险节点执行前暂停, 用户 approve/reject.

    接线语义:
      - node.checkpoint=True 或链属于 HIGH_RISK_CHAINS → 需要 gate
      - resolver(node, outputs) -> dict: {"status": "approved"|"rejected"|"adjusted",
        "comment": str, "adjust": Optional[list[BlueprintNode]]}
      - 无 resolver → 默认 approved（异步日志语义, 事件仍写 plan_gate）
      - 写 decision_bus plan_gate 事件（可回看/介入）
    """

    def __init__(self, decision_bus=None, resolver: Optional[Callable] = None,
                 high_risk_chains: Optional[List[str]] = None):
        self._bus = decision_bus
        # resolver(node, outputs) → {"status": ..., "comment": ..., "adjust": [...]}
        self._resolver = resolver
        self._high_risk = set(high_risk_chains or HIGH_RISK_CHAINS)

    def attach_bus(self, bus):
        if bus is not None:
            self._bus = bus

    def requires_gate(self, node: BlueprintNode) -> bool:
        """是否需要 PlanGate: checkpoint 字段或高风险链."""
        if node.checkpoint:
            return True
        return node.chain in self._high_risk

    def resolve(self, node: BlueprintNode, outputs: dict,
                request_id: str = "", turn: int = 0) -> Dict[str, Any]:
        """执行 gate 解析. 返回 {"status": "approved"|"rejected", "comment": ...,
        "adjust": list} — adjust 非空时替换该节点."""
        if self._resolver is not None:
            try:
                verdict = self._resolver(node, outputs) or {}
            except Exception as e:
                logger.warning("PlanGate resolver failed: %s → default approve", e)
                verdict = {}
        else:
            verdict = {"status": "approved"}

        status = verdict.get("status", "approved")
        comment = str(verdict.get("comment", ""))
        adjust = verdict.get("adjust") or []
        self._record(node, status, comment, adjust, request_id, turn)
        return {"status": status, "comment": comment, "adjust": adjust}

    def _record(self, node, status, comment, adjust, request_id, turn):
        bus = self._bus
        if bus is None:
            return
        try:
            bus.log(
                kind="plan_gate",
                dimension=f"plan.node.{node.node_id}",
                before=None,
                after=",".join(a.node_id for a in adjust) if adjust else None,
                reason=f"PlanGate checkpoint (chain={node.chain})",
                actor="user" if status != "approved" else "agent",
                status=status,
                comment=comment,
                request_id=request_id,
                turn=turn,
            )
        except Exception as e:
            logger.debug("plan_gate event failed: %s", e)


# ═══════════════════════════════════════════════════════════════
# Budget
# ═══════════════════════════════════════════════════════════════

class Budget:
    """执行期预算 — 节点数上限 + 总执行次数上限.

    节点数上限对齐 ConstraintChecker.MAX_NODES=7; 执行次数上限 =
    节点数 × multiplier（RECOVERY 替换会放大执行次数, 防死循环）.
    """

    def __init__(self, max_nodes: int = DEFAULT_MAX_NODES,
                 execution_multiplier: int = DEFAULT_EXECUTION_MULTIPLIER):
        self.max_nodes = max_nodes
        self.execution_multiplier = execution_multiplier

    def check_node_count(self, dag: BlueprintDAG) -> bool:
        """节点数是否超限."""
        return dag.node_count <= self.max_nodes

    def max_executions(self, dag: BlueprintDAG) -> int:
        """执行期总节点执行次数上限."""
        return max(dag.node_count, 1) * self.execution_multiplier


# ═══════════════════════════════════════════════════════════════
# LoopDetector
# ═══════════════════════════════════════════════════════════════

class LoopDetector:
    """重访检测 — 同一节点执行次数 ≥ 阈值 → 强制 checkpoint.

    计数在 executor 每节点执行时上报; 超阈值后 requires_checkpoint(node_id)
    返回 True → executor 走 PlanGate（plan_gate 事件, 用户可介入）.
    """

    def __init__(self, threshold: int = DEFAULT_LOOP_THRESHOLD):
        self.threshold = threshold
        self._visits: Dict[str, int] = {}
        self._flagged: set = set()

    def visit(self, node_id: str) -> int:
        """记录一次执行, 返回累计次数."""
        self._visits[node_id] = self._visits.get(node_id, 0) + 1
        if self._visits[node_id] >= self.threshold:
            self._flagged.add(node_id)
        return self._visits[node_id]

    def requires_checkpoint(self, node_id: str) -> bool:
        return node_id in self._flagged

    def visits(self, node_id: str) -> int:
        return self._visits.get(node_id, 0)

    def reset(self):
        self._visits.clear()
        self._flagged.clear()

    def summary(self) -> Dict[str, int]:
        return dict(self._visits)


# ═══════════════════════════════════════════════════════════════
# QualityGate
# ═══════════════════════════════════════════════════════════════

class QualityGate:
    """执行后质量门槛 — 低分 → 降级 HYBRID + strategy_switch 事件.

    评分信号（纯算法, 零 LLM）:
      - 节点失败/跳过/unavailable → 扣分
      - llm_reply 产出非空 → 加分
      - tool 节点失败 → 额外扣分
    低分（< low_threshold）→ 写 strategy_switch 事件（降级方向）
    与 MetaFeedback.check_degradations 正交: 本 gate 是执行期单次判定,
    MetaFeedback 是跨执行统计判定（连续 3 次低分）.
    """

    def __init__(self, decision_bus=None, low_threshold: float = DEFAULT_QUALITY_LOW):
        self._bus = decision_bus
        self.low_threshold = low_threshold

    def attach_bus(self, bus):
        if bus is not None:
            self._bus = bus

    @staticmethod
    def score(dag: BlueprintDAG, chain_outputs: dict,
              llm_reply: str = "") -> float:
        """0.0-1.0 质量评分（纯算法）."""
        total = max(dag.node_count, 1)
        if total == 0:
            return 0.0
        score = 0.0
        for n in dag.nodes:
            out = chain_outputs.get(n.node_id, {})
            status = out.get("status", "ok")
            if status == "ok":
                score += 1.0
            elif status in ("error", "skipped"):
                score += 0.0
            else:  # unavailable / deferred / async / enqueued
                score += 0.5
        base = score / total
        # llm_reply 产出奖励
        if llm_reply:
            base = min(1.0, base + 0.1)
        # tool 失败惩罚
        tool_fails = sum(
            1 for n in dag.nodes if n.chain == "tool"
            and chain_outputs.get(n.node_id, {}).get("status") == "error"
        )
        base = max(0.0, base - 0.15 * tool_fails)
        return round(base, 3)

    def evaluate(self, dag: BlueprintDAG, chain_outputs: dict,
                 llm_reply: str = "", strategy: str = "",
                 request_id: str = "", turn: int = 0) -> Dict[str, Any]:
        """评分 + 低分写降级事件. 返回 {"score", "degraded", "detail"}."""
        s = self.score(dag, chain_outputs, llm_reply)
        degraded = False
        detail = ""
        if s < self.low_threshold:
            degraded = True
            detail = (f"quality {s:.2f} < {self.low_threshold}, "
                      f"degrade {strategy or dag.strategy} → HYBRID")
            bus = self._bus
            if bus is not None:
                try:
                    bus.log(
                        kind="strategy_switch",
                        dimension="meta.quality",
                        before=strategy or dag.strategy,
                        after="HYBRID",
                        reason=detail,
                        actor="meta",
                        request_id=request_id,
                        turn=turn,
                        comment=f"quality_score={s:.2f}",
                    )
                except Exception as e:
                    logger.debug("quality gate event failed: %s", e)
        return {"score": s, "degraded": degraded, "detail": detail}

