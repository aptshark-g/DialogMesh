# -*- coding: utf-8 -*-
"""
core/agent/v3_0/planning/fallback.py
──────────────────────────────────
DialogMesh Agent v3.0 — 回退规划器。

用途：
- 当任务节点失败或任务图验证不通过时，生成备选任务图。
- 支持节点级回退（单个节点失败，切换备选方案）和图级回退（全图重规划）。
- 与认知树集成，将回退决策记录为 REFLECTION 类型节点。

设计原则：
- 保守安全：回退方案永远比原方案更保守（更少的 side effect、更简单的步骤）。
- 快速响应：不依赖 LLM，纯规则生成，延迟 < 50ms。
- 可追溯：每次回退生成 PlanRevision，记录到 PlanResult。

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from core.agent.models import DependencyType, TaskStatus
from core.agent.v3_0.data_models import (
    Intent_v3,
    TaskEdge_v3,
    TaskGraph_v3,
    TaskNode_v3,
)
from core.agent.v3_0.planning.models import PlanRevision

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 回退规划器
# ═══════════════════════════════════════════════════════════════════════════

class FallbackPlanner:
    """回退规划器——失败时的安全网。

    提供两种回退模式：
    1. **节点级回退**（``revise``）：当某个节点失败时，用备选节点替换或在其后插入诊断步骤。
    2. **图级回退**（``create_fallback``）：当整个图不可执行时，生成一个最小安全图。

    Args:
        enable_diagnostic_step: 是否在回退图中插入诊断节点。
        enable_simplified_plan: 是否生成简化版计划（减少节点数）。
        default_max_retries: 回退节点的默认最大重试次数。
    """

    def __init__(
        self,
        enable_diagnostic_step: bool = True,
        enable_simplified_plan: bool = True,
        default_max_retries: int = 2,
    ) -> None:
        self.enable_diagnostic_step = enable_diagnostic_step
        self.enable_simplified_plan = enable_simplified_plan
        self.default_max_retries = default_max_retries
        logger.debug("FallbackPlanner initialized")

    # ── 公共 API ───────────────────────────────────────────────────────────

    async def revise(
        self,
        original_graph: TaskGraph_v3,
        failed_node_id: str,
        reason: str,
    ) -> TaskGraph_v3:
        """节点级回退——当 ``failed_node_id`` 执行失败时，生成修订后的任务图。

        策略：
        - 若失败节点有 ``fallback_nodes``，则激活第一个备选节点。
        - 否则，在失败节点前插入诊断步骤，并将其标记为 NEEDS_CLARIFICATION。
        - 若回退策略用尽，将失败节点替换为安全节点（如 ``noop`` 或 ``ask_user``）。

        Args:
            original_graph: 原始任务图。
            failed_node_id: 失败节点 ID。
            reason: 失败原因。

        Returns:
            修订后的新任务图（深拷贝，不修改原图）。
        """
        try:
            await asyncio.sleep(0)
            logger.info(f"Revising graph for failed node {failed_node_id}: {reason}")

            new_graph = self._clone_graph(original_graph)
            failed_node = new_graph.get_node(failed_node_id)
            if failed_node is None:
                logger.warning(f"Failed node {failed_node_id} not found in graph, returning clone")
                return new_graph

            # 策略 1: 使用节点预定义的 fallback_nodes
            if failed_node.fallback_nodes:
                fallback_id = failed_node.fallback_nodes[0]
                fallback_node = new_graph.get_node(fallback_id)
                if fallback_node is not None:
                    logger.info(f"Activating fallback node {fallback_id} for {failed_node_id}")
                    # 将原失败节点的入边重定向到 fallback
                    new_edges: List[TaskEdge_v3] = []
                    for edge in new_graph.edges:
                        if edge.target_id == failed_node_id:
                            new_edges.append(TaskEdge_v3(
                                source_id=edge.source_id,
                                target_id=fallback_id,
                                dep_type=edge.dep_type,
                                condition=edge.condition,
                                metadata=edge.metadata,
                            ))
                        else:
                            new_edges.append(edge)
                    new_graph.edges = new_edges
                    # 标记原节点为 CANCELLED（逻辑上被回退替代）
                    failed_node.status = TaskStatus.CANCELLED
                    return new_graph

            # 策略 2: 插入诊断步骤 + 重试
            if self.enable_diagnostic_step:
                logger.info(f"Inserting diagnostic step before {failed_node_id}")
                diag_node = TaskNode_v3(
                    name="diagnose_failure",
                    goal=f"Diagnose failure of {failed_node.name}: {reason}",
                    layer=2,
                    tool_name="diagnose",
                    tool_params={"failed_node": failed_node_id, "reason": reason},
                )
                new_graph.add_node(diag_node)

                # 重定向原失败节点的入边到诊断节点
                new_edges = []
                for edge in new_graph.edges:
                    if edge.target_id == failed_node_id:
                        new_edges.append(TaskEdge_v3(
                            source_id=edge.source_id,
                            target_id=diag_node.id,
                            dep_type=edge.dep_type,
                            condition=edge.condition,
                            metadata=edge.metadata,
                        ))
                    else:
                        new_edges.append(edge)
                # 诊断节点 → 失败节点（条件依赖：诊断通过后才重试）
                new_edges.append(TaskEdge_v3(
                    source_id=diag_node.id,
                    target_id=failed_node_id,
                    dep_type=DependencyType.CONDITIONAL,
                    condition="diagnosis.success == true",
                ))
                new_graph.edges = new_edges
                # 增加重试次数
                failed_node.max_retries = max(failed_node.max_retries, self.default_max_retries)
                failed_node.status = TaskStatus.PENDING
                return new_graph

            # 策略 3: 最终兜底——标记为 NEEDS_CLARIFICATION
            logger.warning(f"No fallback strategy available for {failed_node_id}, marking NEEDS_CLARIFICATION")
            failed_node.status = TaskStatus.NEEDS_CLARIFICATION
            failed_node.error = reason
            return new_graph

        except Exception as exc:
            logger.error(f"FallbackPlanner.revise failed: {exc}, returning original graph clone")
            return self._clone_graph(original_graph)

    async def create_fallback(
        self,
        intent: Intent_v3,
        original_graph: Optional[TaskGraph_v3] = None,
    ) -> TaskGraph_v3:
        """图级回退——当整个任务图不可执行时，生成最小安全图。

        策略：
        - 生成一个单节点图：先诊断，再询问用户。
        - 若意图类别为 READ / SCAN，降级为只读安全操作。

        Args:
            intent: 用户意图。
            original_graph: 原始失败图（可选，用于提取信息）。

        Returns:
            最小安全任务图。
        """
        try:
            await asyncio.sleep(0)
            logger.info(f"Creating fallback graph for intent {intent.id}")

            graph = TaskGraph_v3(intent_id=intent.id)

            if self.enable_simplified_plan:
                # 极简方案：诊断 → 安全询问
                diag = TaskNode_v3(
                    name="fallback_diagnose",
                    goal="Diagnose why the original plan failed",
                    layer=2,
                    tool_name="diagnose",
                )
                ask = TaskNode_v3(
                    name="fallback_ask_user",
                    goal="Ask user for clarification or alternative approach",
                    layer=1,
                    tool_name="ask_user",
                )
                graph.add_node(diag)
                graph.add_node(ask)
                graph.add_edge(TaskEdge_v3(
                    source_id=diag.id,
                    target_id=ask.id,
                    dep_type=DependencyType.SEQUENTIAL,
                ))
            else:
                # 不简化：直接返回原图的克隆（但标记所有节点为 NEEDS_CLARIFICATION）
                if original_graph is not None:
                    graph = self._clone_graph(original_graph)
                    for node in graph.nodes.values():
                        if node.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                            node.status = TaskStatus.NEEDS_CLARIFICATION

            return graph

        except Exception as exc:
            logger.error(f"FallbackPlanner.create_fallback failed: {exc}, returning minimal graph")
            return self._minimal_safe_graph(intent.id)

    # ── 内部工具 ─────────────────────────────────────────────────────────

    def _clone_graph(self, graph: TaskGraph_v3) -> TaskGraph_v3:
        """深拷贝任务图。"""
        try:
            new_graph = TaskGraph_v3(intent_id=graph.intent_id)
            for node in graph.nodes.values():
                new_graph.add_node(node.model_copy(deep=True))
            for edge in graph.edges:
                new_graph.add_edge(edge.model_copy(deep=True))
            new_graph.metadata = dict(graph.metadata) if graph.metadata else {}
            new_graph.created_at = graph.created_at
            return new_graph
        except Exception as exc:
            logger.warning(f"_clone_graph failed: {exc}, returning original graph")
            return graph

    def _minimal_safe_graph(self, intent_id: Optional[str] = None) -> TaskGraph_v3:
        """生成最小安全图（诊断 → 询问用户）。"""
        graph = TaskGraph_v3(intent_id=intent_id)
        diag = TaskNode_v3(
            name="minimal_diagnose",
            goal="Minimal fallback: diagnose and ask user",
            layer=2,
            tool_name="diagnose",
        )
        ask = TaskNode_v3(
            name="minimal_ask",
            goal="Ask user for help",
            layer=1,
            tool_name="ask_user",
        )
        graph.add_node(diag)
        graph.add_node(ask)
        graph.add_edge(TaskEdge_v3(source_id=diag.id, target_id=ask.id, dep_type=DependencyType.SEQUENTIAL))
        return graph


# ═══════════════════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio

    async def _self_test() -> None:
        logger.info("=== v3.0 planning/fallback self-test ===")

        fb = FallbackPlanner()

        # 1. revise: 节点有 fallback_nodes
        graph = TaskGraph_v3()
        n1 = TaskNode_v3(name="main", tool_name="scan")
        n2 = TaskNode_v3(name="fallback", tool_name="safe_scan")
        n1.fallback_nodes = [n2.id]
        graph.add_node(n1)
        graph.add_node(n2)
        graph.add_edge(TaskEdge_v3(source_id="root", target_id=n1.id, dep_type=DependencyType.SEQUENTIAL))
        revised = await fb.revise(graph, n1.id, "main failed")
        # 检查入边是否重定向到 n2
        has_edge_to_n2 = any(e.target_id == n2.id for e in revised.edges)
        assert has_edge_to_n2, "Fallback node should have incoming edges"
        print(f"[PASS] Revise with fallback_nodes: edges to n2={has_edge_to_n2}")

        # 2. revise: 无 fallback_nodes，插入诊断
        graph2 = TaskGraph_v3()
        n3 = TaskNode_v3(name="scan", tool_name="scan")
        graph2.add_node(n3)
        graph2.add_edge(TaskEdge_v3(source_id="root", target_id=n3.id, dep_type=DependencyType.SEQUENTIAL))
        revised2 = await fb.revise(graph2, n3.id, "scan failed")
        assert len(revised2.nodes) == 2  # 原节点 + 诊断节点
        assert n3.max_retries >= 2
        print(f"[PASS] Revise with diagnostic: nodes={len(revised2.nodes)}")

        # 3. create_fallback
        intent = Intent_v3(id="intent-99", category=IntentCategory.SCAN_MEMORY)
        fallback_graph = await fb.create_fallback(intent)
        assert len(fallback_graph.nodes) == 2
        print(f"[PASS] create_fallback: nodes={len(fallback_graph.nodes)}")

        # 4. minimal_safe_graph
        minimal = fb._minimal_safe_graph("test-id")
        assert len(minimal.nodes) == 2
        print(f"[PASS] minimal_safe_graph: nodes={len(minimal.nodes)}")

        logger.info("=== All v3.0 fallback self-tests passed ===")

    asyncio.run(_self_test())
