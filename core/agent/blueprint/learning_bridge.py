# -*- coding: utf-8 -*-
"""学习桥 — GAP-D2 + GAP-D1（COMPLETENESS_GAP_INVENTORY §A）.

打通"执行层 → 学习闭环"的原料管道:

  GAP-D2: learn_blueprint 生产零注入
    生产主路径（v3_session_api → StateMachine.run_dag）跑完后从不调
    learn_blueprint → LEARNED_TEMPLATES 只在测试里沉淀。
    本桥在 run_dag 之后注入 learn_from_execution()。

  GAP-D1: 蒸馏原料管道断
    DistillationEngine.scan() 全库零数据流。本桥把执行轨迹
    （tool 序列 / 意图 / DAG / 成败）收集进 ExecutionTraceStore,
    周期性喂给 DistillationEngine.scan(behavior_store=...),
    候选经 A24 可逆推验证（coverage 60-80%）后进 SkillRegistry。

设计对齐:
  - A24 逆向动力（聚类凝练→规则化→反向推导验证 coverage 60-80%;
    100%=过拟合, 0%=没学到）— PARADIGM.md A24
  - G2 模板进化（learn_blueprint 已实现, 补接线）
  - FLOW_SELF_GROWTH 业务流三来源（种子/生成/沉淀）
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent.blueprint.skill_registry import SkillRegistry, LEARNED_TEMPLATES

logger = logging.getLogger(__name__)

# A24 可逆推验证 coverage 区间（PARADIGM.md: 60-80% 合格）
COVERAGE_MIN = 0.60
COVERAGE_MAX = 0.80
# 蒸馏触发阈值: 同类 tool 序列出现次数
DISTILL_MIN_SEQUENCES = 3
# 轨迹存储上限（防无限增长）
TRACE_MAX = 200


@dataclass
class ExecutionTrace:
    """一次执行的成功轨迹（蒸馏原料）."""
    request_id: str = ""
    intent: str = ""
    tool_sequence: List[str] = field(default_factory=list)
    node_count: int = 0
    strategy: str = ""
    success: bool = False
    ts: float = field(default_factory=time.time)
    source_dag_id: str = ""

    def to_sequence_record(self) -> Dict[str, Any]:
        """DistillationEngine._find_behavior_patterns 消费的格式."""
        return {"actions": list(self.tool_sequence), "intent": self.intent}


class ExecutionTraceStore:
    """执行轨迹环形存储 — 蒸馏引擎的 behavior_store 数据源."""

    def __init__(self, max_size: int = TRACE_MAX):
        self._traces: deque = deque(maxlen=max_size)

    def add(self, trace: ExecutionTrace):
        if trace.tool_sequence and trace.success:
            self._traces.append(trace)

    def get_sequences(self) -> List[Dict[str, Any]]:
        """DistillationEngine 要求的接口（actions 序列列表）."""
        return [t.to_sequence_record() for t in self._traces]

    def get_all(self) -> List[ExecutionTrace]:
        return list(self._traces)

    def __len__(self):
        return len(self._traces)


class LearningBridge:
    """执行层 → 学习闭环的统一入口.

    生产接线（v3_session_api Phase 3.5 run_dag 之后）:
        bridge = engine 持有的单例
        bridge.learn_from_execution(
            dag=dag, intent=intent, request_id=msg_id,
            success=..., llm_reply=...)
    """

    def __init__(self, registry: Optional[SkillRegistry] = None,
                 trace_store: Optional[ExecutionTraceStore] = None,
                 decision_bus=None):
        self.registry = registry or SkillRegistry()
        self.trace_store = trace_store or ExecutionTraceStore()
        self._decision_bus = decision_bus
        self._distill_engine = None
        self._distill_runs = 0
        self._last_distill_ts = 0.0
        self._distill_interval = 300.0  # 5 分钟一次批量蒸馏
        # 二阶抽象提炼管道（变化驱动触发, GAP-D6 / blog chapter3）
        self._distiller = None
        self._last_trigger_ts = 0.0
        self._failure_count = 0
        self._trigger_min_interval = 60.0  # 变化触发最小间隔（防 LLM 蒸馏过频）
        self._trigger_min_failures = 2     # 至少累计 2 次失败才触发

    def attach_bus(self, bus):
        if bus is not None:
            self._decision_bus = bus

    # ── 二阶抽象: 变化驱动触发 ─────────────────────────────

    def attach_distiller(self, distiller):
        """挂载 HeuristicDistiller（二阶抽象提炼管道）。"""
        self._distiller = distiller

    def trigger_distill(self, reason: str = "", variant: str = "commonalize") -> dict:
        """变化触发: 失败/用户纠正/公理冲突/活性/缺公理感 → 提炼。

        定时蒸馏（distill_once）仅兜底; 主触发是事件驱动（设计定案 §3.2）。
        """
        if self._distiller is None:
            return {"triggered": False, "reason": "no_distiller"}
        try:
            return self._distiller.try_distill(
                reason=reason,
                samples=self.trace_store.get_all(),
                variant=variant,
            )
        except Exception as e:
            logger.debug("trigger_distill failed: %s", e)
            return {"triggered": False, "error": str(e)[:120]}

    def on_tool_failure(self, tool_name: str = "", error: str = "") -> dict:
        """工具失败 → 变化触发（决策失败信号 → 反向掩盖发散: 缺什么导致失败）。

        节流: 累计失败 ≥2 次 且 距上次触发 ≥60s 才真正调用蒸馏
        （LLM 蒸馏有成本, 单次失败不立即触发）。
        """
        self._failure_count += 1
        now = time.time()
        if self._failure_count < self._trigger_min_failures:
            return {"triggered": False, "reason": "failure_throttle",
                    "count": self._failure_count}
        if (now - self._last_trigger_ts) < self._trigger_min_interval:
            return {"triggered": False, "reason": "interval_throttle"}
        self._failure_count = 0
        self._last_trigger_ts = now
        return self.trigger_distill(
            reason=f"tool_failure:{tool_name}:{str(error)[:80]}",
            variant="reverse_mask",
        )

    def on_user_correction(self, dimension: str = "") -> dict:
        """用户纠正 → 变化触发（行为链 user_correction → 共性找底）。"""
        return self.trigger_distill(
            reason=f"user_correction:{dimension}",
            variant="commonalize",
        )

    def check_heuristic_health(self, threshold: float = 0.5) -> dict:
        """启发活性监测: coverage 跌破阈值 → 停用 + 决策事件记录。

        周期/变化触发时调用; 停用的启发可由下一次蒸馏重新长出
        （A24: 启发过时不是删除, 是活性标记 + 再触发）。
        """
        inv = getattr(self._distiller, "_inventory", None) if self._distiller else None
        if inv is None:
            return {"checked": False, "reason": "no_distiller"}
        try:
            stale = inv.deactivate_stale(threshold)
            if stale and self._decision_bus is not None:
                try:
                    self._decision_bus.log(
                        kind="heuristic_health", dimension="inventory",
                        before=None, after={"deactivated": stale},
                        reason=f"coverage below {threshold}",
                        actor="system", status="applied",
                    )
                except Exception as e:
                    logger.debug("heuristic health event failed: %s", e)
            return {"checked": True, "deactivated": stale,
                    "stats": inv.stats()}
        except Exception as e:
            logger.debug("heuristic health check failed: %s", e)
            return {"checked": False, "error": str(e)[:120]}

    # ── GAP-D2: 生产 learn 入口 ──

    def learn_from_execution(self, dag, intent: str, request_id: str = "",
                             success: bool = True) -> bool:
        """run_dag 之后调用:
        ① learn_blueprint 沉淀（含 tool 节点才沉淀, 已有逻辑）
        ② 成功轨迹入 trace_store（蒸馏原料）
        ③ 周期触发批量蒸馏 → A24 验证 → 候选入 SkillRegistry
        """
        learned = False
        try:
            # ① G2 模板沉淀（GAP-D2 修复点）
            learned = self.registry.learn_blueprint(
                intent, dag, source_dag_id=request_id)
        except Exception as e:
            logger.debug("learn_blueprint failed: %s", e)

        # ② 轨迹收集（仅成功 + 含工具）
        if success and dag is not None:
            try:
                tools = [
                    n.params.get("tool", "")
                    for n in getattr(dag, "nodes", [])
                    if n.chain == "tool" and n.params.get("tool")
                ]
                if tools:
                    self.trace_store.add(ExecutionTrace(
                        request_id=request_id,
                        intent=intent,
                        tool_sequence=tools,
                        node_count=len(getattr(dag, "nodes", [])),
                        strategy=getattr(dag, "strategy", ""),
                        success=True,
                        source_dag_id=request_id,
                    ))
            except Exception as e:
                logger.debug("trace collect failed: %s", e)

        # ③ 周期蒸馏
        now = time.time()
        if (now - self._last_distill_ts) >= self._distill_interval:
            self.distill_once()
            self._last_distill_ts = now
        return learned

    # ── GAP-D1: 蒸馏原料管道 ──

    def _get_distill_engine(self):
        if self._distill_engine is None:
            from core.agent.planner.distillation_engine import DistillationEngine
            self._distill_engine = DistillationEngine()
        return self._distill_engine

    def distill_once(self) -> Dict[str, Any]:
        """批量蒸馏: trace_store → scan(behavior_store) → A24 验证 →
        达标候选沉淀为 LEARNED_TEMPLATES. 返回统计."""
        if len(self.trace_store) < DISTILL_MIN_SEQUENCES:
            return {"scanned": 0, "candidates": 0, "verified": 0}
        try:
            engine = self._get_distill_engine()
            candidates = engine.scan(behavior_store=self.trace_store)
            self._distill_runs += 1
            verified = 0
            for cand in candidates:
                if self._a24_verify(cand, self.trace_store.get_all()):
                    self._promote_candidate(cand)
                    verified += 1
            logger.info(
                "Distill: run=%d candidates=%d verified=%d",
                self._distill_runs, len(candidates), verified,
            )
            return {"scanned": len(self.trace_store),
                    "candidates": len(candidates), "verified": verified}
        except Exception as e:
            logger.debug("distill_once failed: %s", e)
            return {"scanned": 0, "candidates": 0, "verified": 0, "error": str(e)}

    @staticmethod
    def _a24_verify(candidate, traces: List[ExecutionTrace]) -> bool:
        """A24 可逆推验证: 候选蓝图的 action 序列能否反推回历史样本.

        coverage = 历史成功轨迹中包含该模式的比例.
        合格区间 60-80%（100%=过拟合, 0%=没学到）.
        """
        actions = [
            a.action for a in getattr(candidate.blueprint, "action_graph", [])
        ]
        if not actions:
            return False
        pattern = tuple(actions)
        matched = 0
        total = len(traces)
        for t in traces:
            seq = tuple(t.tool_sequence)
            if pattern and all(a in seq for a in pattern):
                matched += 1
        if total == 0:
            return False
        coverage = matched / total
        return COVERAGE_MIN <= coverage <= COVERAGE_MAX

    def _promote_candidate(self, candidate) -> bool:
        """达标候选 → 沉淀为 LEARNED_TEMPLATES（按意图）. """
        goal = getattr(candidate.blueprint, "goal", "") or ""
        # 从 goal 提取意图提示词（DistillationEngine 的 goal 含 pattern 描述）
        intent = goal[:40] if goal else "learned_pattern"
        nodes = []
        for a in getattr(candidate.blueprint, "action_graph", []):
            try:
                from core.agent.blueprint.models import BlueprintNode
                nodes.append(BlueprintNode(
                    node_id=f"tool_{len(nodes)}",
                    chain="tool",
                    params={"tool": a.action},
                ))
            except Exception:
                continue
        if not nodes:
            return False
        try:
            from core.agent.blueprint.models import BlueprintDAG, BlueprintEdge
            from core.agent.blueprint.models import BlueprintNode as BN
            dag = BlueprintDAG(
                nodes=[
                    BN("pcr_0", "pcr", priority=0),
                    BN("intent_1", "intent", priority=0),
                    *nodes,
                    BN("llm_reply_x", "llm_reply", priority=2,
                       params={"reply_mode": "llm"}),
                ],
                edges=[
                    BlueprintEdge("pcr_0", "intent_1", "route", required=False),
                    BlueprintEdge("intent_1", nodes[0].node_id, "intent_context"),
                ],
                strategy="TEMPLATE",
                design_rationale=(
                    f"DISTILLED (from: execution_traces, support="
                    f"{candidate.belief.support}, coverage="
                    f"{candidate.belief.coverage:.2f})"
                ),
            )
            return self.registry.learn_blueprint(intent, dag)
        except Exception as e:
            logger.debug("promote_candidate failed: %s", e)
            return False

    def summary(self) -> Dict[str, Any]:
        return {
            "traces": len(self.trace_store),
            "distill_runs": self._distill_runs,
            "learned_templates": len(LEARNED_TEMPLATES),
            "last_distill_ts": self._last_distill_ts,
        }
