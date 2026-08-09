# -*- coding: utf-8 -*-
"""三层介入分级 — P1-2 (META_ARBITER_ASYNC_INTERVENTION §3.3).

变更类型 → 介入方式:
  低风险（策略微调/顺序调整）  → 异步日志, 事后可回看 (CHANGELOG)
  中风险（元认知建议切换）    → 异步 + 通知, approve/reject (PR review)
  高风险（写文件/不可逆/花钱） → 同步 PlanGate, 必须确认 (merge gate)

实现:
  RiskClassifier — 事件/节点 → 风险级
  InterventionRouter.route() — 统一写入决策事件（按风险定 status）:
    low    → status=applied（已生效, 留痕）
    medium → status=proposed（待 approve/reject, 不阻塞执行）
    high   → status=proposed + sync_required=True（走 PlanGate 同步确认）
  route().approve()/.reject() — 中风险介入回写（DecisionEventBus.intervene）
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from core.agent.blueprint.decision_event import DecisionEventBus
from core.agent.blueprint.protection import HIGH_RISK_CHAINS

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# 维度/原因关键词 → 升级为高风险（写/不可逆/花钱）
HIGH_RISK_KEYWORDS = (
    "write", "delete", "remove", "rm ", "overwrite", "spend", "pay",
    "写文件", "删除", "不可逆", "花", "钱",
)

# 只读类工具（前缀/包含匹配 → 低风险, 直接执行 + 留痕）
READ_TOOL_HINTS = (
    "search", "read", "get_", "list", "find", "query", "lookup",
    "fetch", "check", "inspect", "status", "show", "ping", "test",
)


class RiskClassifier:
    """事件/节点 → 风险级."""

    @staticmethod
    def classify_kind(kind: str, dimension: str = "", reason: str = "") -> RiskLevel:
        """按事件 kind + 维度/原因关键词分级."""
        if kind == "plan_gate":
            return RiskLevel.HIGH
        if kind == "user_correction":
            return RiskLevel.LOW  # 用户修正本身已是最权威, 直接留痕
        if kind in ("strategy_switch", "meta_advice"):
            # 元认知建议的策略切换 = 中风险（PR review 语义）
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW
        # 关键词升级: 写/删除/花钱类操作 → 高风险
        hay = f"{dimension} {reason}".lower()
        if any(k in hay for k in HIGH_RISK_KEYWORDS):
            return RiskLevel.HIGH
        return level

    @staticmethod
    def classify_node(node) -> RiskLevel:
        """蓝图节点 → 风险级（checkpoint/高风险链 → 同步 gate）."""
        if getattr(node, "checkpoint", False):
            return RiskLevel.HIGH
        if getattr(node, "chain", "") in HIGH_RISK_CHAINS:
            return RiskLevel.HIGH
        return RiskLevel.LOW

    @staticmethod
    def classify_tool(tool_name: str, args: Optional[dict] = None) -> RiskLevel:
        """工具调用 → 风险级（GAP-3 批次介入分级）。

        高危关键词（写/删/花钱类, 含工具名与参数）→ HIGH（批次 sync_required）;
        只读类工具 → LOW（直接执行 + 留痕）;
        其余 → MEDIUM（中风险批量场景, PR review 语义 proposed）。
        """
        try:
            hay = f"{tool_name} {json.dumps(args or {}, ensure_ascii=False)}".lower()
        except Exception:
            hay = tool_name.lower()
        if any(k in hay for k in HIGH_RISK_KEYWORDS):
            return RiskLevel.HIGH
        tl = tool_name.lower()
        if any(hint in tl for hint in READ_TOOL_HINTS):
            return RiskLevel.LOW
        return RiskLevel.MEDIUM


class InterventionRouter:
    """统一决策事件写入 + 介入回看/回写."""

    def __init__(self, decision_bus: Optional[DecisionEventBus] = None):
        self._bus = decision_bus
        self.classifier = RiskClassifier()

    def attach_bus(self, bus):
        if bus is not None:
            self._bus = bus

    def route(self, kind: str, dimension: str, before=None, after=None,
              reason: str = "", actor: str = "agent", turn: int = 0,
              request_id: str = "", trace_id: str = "",
              attribution: str = "none") -> Dict[str, Any]:
        """按风险分级写决策事件.

        返回 {"level", "status", "sync_required", "event"} —
        sync_required=True 时调用方必须走同步 PlanGate 确认。
        """
        level = self.classifier.classify_kind(kind, dimension, reason)
        status = "applied" if level == RiskLevel.LOW else "proposed"
        ev = {}
        if self._bus is not None:
            try:
                ev = self._bus.log(
                    kind=kind, dimension=dimension, before=before, after=after,
                    reason=reason, actor=actor, turn=turn, status=status,
                    request_id=request_id, trace_id=trace_id,
                    attribution=attribution,
                )
            except Exception as e:
                logger.debug("intervention route failed: %s", e)
        return {
            "level": level.value,
            "status": status,
            "sync_required": level == RiskLevel.HIGH,
            "event": ev,
        }

    def approve(self, dimension: str = "", kind: str = "strategy_switch",
                comment: str = "") -> Optional[Dict[str, Any]]:
        """中风险事件 approve（PR review 语义）→ status=applied."""
        if self._bus is None:
            return None
        return self._bus.intervene(
            status="applied", comment=comment, dimension=dimension, kind=kind)

    def reject(self, dimension: str = "", kind: str = "strategy_switch",
               comment: str = "") -> Optional[Dict[str, Any]]:
        """中风险事件 reject → status=rejected."""
        if self._bus is None:
            return None
        return self._bus.intervene(
            status="rejected", comment=comment, dimension=dimension, kind=kind)

    def route_batch(self, tools: List[Dict[str, Any]], dimension: str = "tool_batch",
                    reason: str = "", turn: int = 0, request_id: str = "") -> Dict[str, Any]:
        """GAP-3: 工具批次级介入（OpenClaw beforeToolBatch 对齐）。

        一批工具调用合并为一个决策事件（批维度 approve/reject）:
          含高危（写/删/花钱）→ HIGH, sync_required=True（批次拦截待确认）
          含中危且无高危 → MEDIUM, proposed（不阻塞, PR review 语义）
          全只读 → LOW, applied（直接执行 + 留痕）
        """
        levels = [self.classifier.classify_tool(t.get("tool", ""), t.get("args", {}))
                  for t in tools]
        has_high = any(l == RiskLevel.HIGH for l in levels)
        has_medium = any(l == RiskLevel.MEDIUM for l in levels)
        if has_high:
            level, status, sync = RiskLevel.HIGH, "proposed", True
        elif has_medium:
            level, status, sync = RiskLevel.MEDIUM, "proposed", False
        else:
            level, status, sync = RiskLevel.LOW, "applied", False
        summary = [f"{t.get('tool', '?')}({len(t.get('args', {}) or {})} args)"
                   for t in tools]
        ev: Dict[str, Any] = {}
        if self._bus is not None:
            try:
                ev = self._bus.log(
                    kind="tool_batch", dimension=dimension,
                    before=None, after=summary,
                    reason=reason or f"batch of {len(tools)} tools",
                    actor="agent", turn=turn, status=status,
                    request_id=request_id, attribution="none",
                )
            except Exception as e:
                logger.debug("route_batch failed: %s", e)
        return {
            "level": level.value,
            "status": status,
            "sync_required": sync,
            "tools": summary,
            "event": ev,
        }
