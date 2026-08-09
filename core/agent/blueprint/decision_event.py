# -*- coding: utf-8 -*-
"""决策变更事件 — 元认知仲裁 × 异步介入的统一事件 schema.

设计定案: docs/only/blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md §3.2

决策变更 = 事件（写 EventLog, A17），同时进 CorrectionJournal（before/after/
reason 语义）。两类消费方:
  - 回看（git log 语义）: 用户/前端读事件流, 看"为什么变、谁变的、变成什么"
  - 介入（PR review 语义）: 建议/否决/约束 → 追加评论事件, 不打断执行

事件 kinds（对齐设计 §3.1）:
  strategy_switch  — 元认知裁决的策略切换（如 RECOVERY 执行期换子图）
  plan_gate        — PlanGate checkpoint 触发/批准/否决
  meta_advice      — 元认知建议（复盘 verdict/recommendation）
  user_correction  — 用户显式修正/约束
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# 合法事件 kinds
VALID_KINDS = {"strategy_switch", "plan_gate", "meta_advice", "user_correction"}
# T5 (BIDIRECTIONAL_ATTRIBUTION): 偏差归因类型
VALID_ATTRIBUTIONS = {"plan", "constraint", "data", "tool", "none"}


@dataclass
class DecisionEvent:
    """一次决策变更的完整记录。"""
    kind: str                       # strategy_switch | plan_gate | meta_advice | user_correction
    dimension: str                  # 变更对象（blueprint/plan/subgraph/strategy/...）
    attribution: str = "none"       # T5: 偏差归因（plan/constraint/data/tool）
    before: Any = None              # 变更前
    after: Any = None               # 变更后
    reason: str = ""                # 为什么变（元认知裁决依据）
    actor: str = "agent"            # agent | meta | user
    turn: int = 0
    ts: float = field(default_factory=time.time)
    comment: str = ""               # 用户介入时的评论/建议（PR review 语义）
    status: str = "applied"         # applied | proposed | rejected | reverted
    request_id: str = ""
    trace_id: str = ""

    def __post_init__(self):
        if self.kind not in VALID_KINDS:
            raise ValueError(
                f"Unknown decision kind '{self.kind}'. Valid: {sorted(VALID_KINDS)}"
            )
        if self.attribution not in VALID_ATTRIBUTIONS:
            raise ValueError(
                f"Unknown attribution '{self.attribution}'. "
                f"Valid: {sorted(VALID_ATTRIBUTIONS)}"
            )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # before/after 可序列化化（对象 → 摘要 str）
        for k in ("before", "after"):
            v = d.get(k)
            if v is not None and not isinstance(v, (str, int, float, bool, dict, list)):
                d[k] = str(v)[:500]
        return d


class DecisionEventBus:
    """决策变更事件总线 — EventLog 持久化 + CorrectionJournal 双写.

    - EventLog: 事件流（回看/审计, A17）
    - CorrectionJournal: before/after 修正语义（行为链学习源）
    """

    def __init__(self, event_log=None, journal=None):
        self._event_log = event_log
        self._journal = journal
        self._memory: List[Dict[str, Any]] = []
        self._max_memory = 500

    def attach(self, event_log=None, journal=None):
        if event_log is not None:
            self._event_log = event_log
        if journal is not None:
            self._journal = journal

    def record(self, event: DecisionEvent) -> Dict[str, Any]:
        """记录一次决策变更（双写 + 内存缓冲）。"""
        d = event.to_dict()
        # 1) 内存缓冲（快速回看, 不依赖 DB）
        self._memory.append(d)
        if len(self._memory) > self._max_memory:
            self._memory = self._memory[-self._max_memory:]
        # 2) EventLog 持久化（事件流, 回看/审计）
        if self._event_log is not None:
            try:
                event_id = f"decision_{int(event.ts * 1000)}_{event.kind}_{event.turn}"
                self._event_log.put_event(
                    event_id=event_id,
                    kind=f"decision.{event.kind}",
                    payload=d,
                    trace_id=event.trace_id,
                )
            except Exception as e:
                logger.debug("DecisionEvent EventLog write failed: %s", e)
        # 3) CorrectionJournal（before/after 修正语义）
        if self._journal is not None:
            try:
                self._journal.record(
                    dimension=f"decision.{event.dimension}",
                    before=event.before,
                    after=event.after,
                    reason=event.reason,
                    turn=event.turn,
                )
            except Exception as e:
                logger.debug("DecisionEvent journal write failed: %s", e)
        return d

    def log(self, kind: str, dimension: str, before=None, after=None,
            reason: str = "", actor: str = "agent", turn: int = 0,
            comment: str = "", status: str = "applied",
            request_id: str = "", trace_id: str = "",
            attribution: str = "none") -> Dict[str, Any]:
        """便捷单行记录。"""
        ev = DecisionEvent(
            kind=kind, dimension=dimension, before=before, after=after,
            reason=reason, actor=actor, turn=turn, comment=comment,
            status=status, request_id=request_id, trace_id=trace_id,
            attribution=attribution,
        )
        return self.record(ev)

    def recent(self, limit: int = 100, kind: str = "") -> List[Dict[str, Any]]:
        """最近事件（回看, git log 语义）。"""
        events = self._memory
        if kind:
            events = [e for e in events if e.get("kind") == kind]
        return list(reversed(events[-limit:]))

    def all(self) -> List[Dict[str, Any]]:
        return list(self._memory)

    def intervene(self, status: str, comment: str = "",
                  dimension: str = "", kind: str = "",
                  latest_only: bool = True) -> Optional[Dict[str, Any]]:
        """P1-2 中风险介入回写（PR review 语义）:

        在内存事件流中找最近一条匹配的事件, 更新 status + comment
        （approve→applied / reject→rejected）, 并追加一条 user_correction
        评论事件（回看可追溯谁介入、何时介入）。返回被更新的事件或 None。
        """
        if status not in ("applied", "rejected"):
            raise ValueError(f"intervene status must be applied|rejected, got {status}")
        for ev in reversed(self._memory):
            if dimension and ev.get("dimension") != dimension:
                continue
            if kind and ev.get("kind") != kind:
                continue
            if ev.get("status") != "proposed":
                continue
            ev["status"] = status
            ev["comment"] = comment or ev.get("comment", "")
            verdict = "批准" if status == "applied" else "否决"
            self.log(
                kind="user_correction",
                dimension=f"intervention.{ev.get('dimension', '?')}",
                before=ev.get("status"),
                after=status,
                reason=f"用户介入({verdict}): {comment or verdict}",
                actor="user",
                comment=comment,
            )
            return ev
        return None
