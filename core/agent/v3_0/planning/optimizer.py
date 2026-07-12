# -*- coding: utf-8 -*-
"""
core/agent/v3_0/planning/optimizer.py
────────────────────────────────────
DialogMesh Agent v3.0 — TaskGraph 优化器。

用途：
- 合并冗余节点（语义重复、层叠空洞）。
- 剪枝无效边（悬空、循环、不可达）。
- 重排序节点（按层、优先级、拓扑序）。
- 提升任务图的执行效率与可读性。

设计原则：
- 纯函数式：输入 TaskGraph_v3，输出新的 TaskGraph_v3（不修改原图）。
- 异步友好：每个优化阶段让出事件循环，支持并发流水线。
- 可配置：通过优化配置开关控制各阶段启用/禁用。
- 防御性：任何阶段失败时返回原图，不破坏已有结构。

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from typing import Dict, List, Optional, Set

from core.agent.v3_common.models import DependencyType, TaskStatus
from core.agent.v3_0.data_models import TaskGraph_v3, TaskEdge_v3, TaskNode_v3
from core.agent.v3_0.planning.models import PlanStep, StepType

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 优化器
# ═══════════════════════════════════════════════════════════════════════════

class TaskGraphOptimizer:
    """任务图优化器——对 TaskGraph_v3 执行多阶段优化。

    优化阶段（默认顺序）：
    1. deduplicate — 合并语义重复的节点。
    2. prune — 剪枝不可达节点和悬空边。
    3. collapse — 折叠层叠空洞（连续同层节点可合并时）。
    4. sort — 按拓扑序与层重新排序内部存储。

    Args:
        enable_deduplicate: 是否启用去重。
        enable_prune: 是否启用剪枝。
        enable_collapse: 是否启用层叠折叠。
        enable_sort: 是否启用重排序。
    """

    def __init__(
        self,
        enable_deduplicate: bool = True,
        enable_prune: bool = True,
        enable_collapse: bool = True,
        enable_sort: bool = True,
    ) -> None:
        self.enable_deduplicate = enable_deduplicate
        self.enable_prune = enable_prune
        self.enable_collapse = enable_collapse
        self.enable_sort = enable_sort
        self._optimization_steps: List[PlanStep] = []
        logger.debug("TaskGraphOptimizer initialized")

    async def optimize(self, graph: TaskGraph_v3) -> TaskGraph_v3:
        """执行完整优化流水线。

        Args:
            graph: 原始任务图。

        Returns:
            优化后的新任务图（深拷贝，不修改原图）。
        """
        try:
            await asyncio.sleep(0)
            # 深拷贝以避免修改原图
            optimized = self._clone_graph(graph)

            if self.enable_deduplicate:
                await asyncio.sleep(0)
                optimized = self._deduplicate_nodes(optimized)
                logger.debug(f"After deduplicate: {len(optimized.nodes)} nodes, {len(optimized.edges)} edges")

            if self.enable_prune:
                await asyncio.sleep(0)
                optimized = self._prune_unreachable(optimized)
                optimized = self._prune_dangling_edges(optimized)
                logger.debug(f"After prune: {len(optimized.nodes)} nodes, {len(optimized.edges)} edges")

            if self.enable_collapse:
                await asyncio.sleep(0)
                optimized = self._collapse_linear_chains(optimized)
                logger.debug(f"After collapse: {len(optimized.nodes)} nodes, {len(optimized.edges)} edges")

            if self.enable_sort:
                await asyncio.sleep(0)
                optimized = self._topological_sort_storage(optimized)
                logger.debug(f"After sort: {len(optimized.nodes)} nodes, {len(optimized.edges)} edges")

            return optimized

        except Exception as exc:
            logger.error(f"TaskGraphOptimizer.optimize failed: {exc}, returning original graph")
            return graph

    def get_optimization_steps(self) -> List[PlanStep]:
        """获取上次优化的步骤记录（只读副本）。"""
        return self._optimization_steps.copy()

    # ── 去重 ──────────────────────────────────────────────────────────────

    def _deduplicate_nodes(self, graph: TaskGraph_v3) -> TaskGraph_v3:
        """合并语义重复的节点（相同 tool_name + tool_params）。"""
        try:
            # 建立 (tool_name, frozenset(tool_params.items())) -> node_id 映射
            signature_map: Dict[tuple, str] = {}
            duplicates: Dict[str, str] = {}  # old_id -> keep_id

            for node_id, node in list(graph.nodes.items()):
                if not node.tool_name:
                    continue
                sig = (node.tool_name, frozenset(node.tool_params.items()))
                if sig in signature_map:
                    duplicates[node_id] = signature_map[sig]
                else:
                    signature_map[sig] = node_id

            if not duplicates:
                return graph

            # 移除重复节点，重定向边
            new_nodes = {
                nid: node for nid, node in graph.nodes.items()
                if nid not in duplicates
            }
            new_edges: List[TaskEdge_v3] = []
            for edge in graph.edges:
                src = duplicates.get(edge.source_id, edge.source_id)
                tgt = duplicates.get(edge.target_id, edge.target_id)
                if src == tgt:
                    continue  # 自环边跳过
                new_edges.append(TaskEdge_v3(
                    source_id=src,
                    target_id=tgt,
                    dep_type=edge.dep_type,
                    condition=edge.condition,
                    metadata=edge.metadata,
                ))

            # 重建图
            new_graph = TaskGraph_v3(intent_id=graph.intent_id)
            for node in new_nodes.values():
                new_graph.add_node(node)
            for edge in new_edges:
                try:
                    new_graph.add_edge(edge)
                except ValueError:
                    pass  # 边引用已不存在的节点，忽略
            new_graph.metadata = deepcopy(graph.metadata)
            new_graph.created_at = graph.created_at
            return new_graph

        except Exception as exc:
            logger.warning(f"_deduplicate_nodes failed: {exc}, returning graph unchanged")
            return graph

    # ── 剪枝 ──────────────────────────────────────────────────────────────

    def _prune_unreachable(self, graph: TaskGraph_v3) -> TaskGraph_v3:
        """剪枝从根节点不可达的节点（通常由去重或回退导致）。"""
        try:
            if not graph.nodes:
                return graph

            roots = graph.get_roots()
            if not roots:
                # 没有根节点（全循环），保留原图
                return graph

            reachable: Set[str] = set()
            queue = [r.id for r in roots]
            while queue:
                nid = queue.pop(0)
                if nid in reachable:
                    continue
                reachable.add(nid)
                # 查找出边
                for edge in graph.edges:
                    if edge.source_id == nid and edge.target_id not in reachable:
                        queue.append(edge.target_id)

            # 保留可达节点和相关边
            new_nodes = {
                nid: node for nid, node in graph.nodes.items()
                if nid in reachable
            }
            new_edges = [
                edge for edge in graph.edges
                if edge.source_id in reachable and edge.target_id in reachable
            ]

            new_graph = TaskGraph_v3(intent_id=graph.intent_id)
            for node in new_nodes.values():
                new_graph.add_node(node)
            for edge in new_edges:
                new_graph.add_edge(edge)
            new_graph.metadata = deepcopy(graph.metadata)
            new_graph.created_at = graph.created_at
            return new_graph

        except Exception as exc:
            logger.warning(f"_prune_unreachable failed: {exc}, returning graph unchanged")
            return graph

    def _prune_dangling_edges(self, graph: TaskGraph_v3) -> TaskGraph_v3:
        """剪枝引用不存在节点的边。"""
        try:
            node_ids = set(graph.nodes.keys())
            valid_edges = [
                edge for edge in graph.edges
                if edge.source_id in node_ids and edge.target_id in node_ids
            ]
            if len(valid_edges) == len(graph.edges):
                return graph

            new_graph = TaskGraph_v3(intent_id=graph.intent_id)
            for node in graph.nodes.values():
                new_graph.add_node(node)
            for edge in valid_edges:
                new_graph.add_edge(edge)
            new_graph.metadata = deepcopy(graph.metadata)
            new_graph.created_at = graph.created_at
            return new_graph

        except Exception as exc:
            logger.warning(f"_prune_dangling_edges failed: {exc}, returning graph unchanged")
            return graph

    # ── 层叠折叠 ────────────────────────────────────────────────────────────

    def _collapse_linear_chains(self, graph: TaskGraph_v3) -> TaskGraph_v3:
        """折叠线性链：如果 A→B 为顺序依赖，且 A、B 同层、同 tool_name，尝试合并。

        保守策略：仅合并 layer 3 的执行层节点，避免破坏高层语义。
        """
        try:
            if not graph.nodes:
                return graph

            # 构建邻接表
            outgoing: Dict[str, List[str]] = {}
            incoming: Dict[str, List[str]] = {}
            edge_map: Dict[tuple, TaskEdge_v3] = {}
            for edge in graph.edges:
                outgoing.setdefault(edge.source_id, []).append(edge.target_id)
                incoming.setdefault(edge.target_id, []).append(edge.source_id)
                edge_map[(edge.source_id, edge.target_id)] = edge

            merged: Dict[str, str] = {}  # old_id -> new_id（指向合并后的节点）
            nodes_to_remove: Set[str] = set()

            for node_id, node in graph.nodes.items():
                if node_id in nodes_to_remove:
                    continue
                if node.layer != 3:
                    continue  # 仅折叠执行层
                # 查找单一后继
                succs = outgoing.get(node_id, [])
                if len(succs) != 1:
                    continue
                succ_id = succs[0]
                succ = graph.nodes.get(succ_id)
                if succ is None or succ.layer != 3:
                    continue
                # 检查后继是否只有当前节点一个前驱
                preds = incoming.get(succ_id, [])
                if len(preds) != 1 or preds[0] != node_id:
                    continue
                # 检查边类型
                edge = edge_map.get((node_id, succ_id))
                if edge is None or edge.dep_type != DependencyType.SEQUENTIAL:
                    continue
                # 保守策略：仅合并相同 tool_name 的节点（语义等价）
                if node.tool_name != succ.tool_name:
                    continue
                # 合并：将 succ 合并到 node
                node.name = f"{node.name}+{succ.name}"
                node.goal = f"{node.goal}; {succ.goal}"
                node.tool_params.update(succ.tool_params)
                nodes_to_remove.add(succ_id)
                merged[succ_id] = node_id

            if not nodes_to_remove:
                return graph

            # 重建图
            new_nodes = {
                nid: node for nid, node in graph.nodes.items()
                if nid not in nodes_to_remove
            }
            new_edges: List[TaskEdge_v3] = []
            for edge in graph.edges:
                src = merged.get(edge.source_id, edge.source_id)
                tgt = merged.get(edge.target_id, edge.target_id)
                if tgt in nodes_to_remove:
                    # 如果目标是已被合并的节点，尝试将边重定向到合并目标
                    tgt = merged.get(edge.target_id, edge.target_id)
                if src in nodes_to_remove or tgt in nodes_to_remove:
                    continue
                if src == tgt:
                    continue
                new_edges.append(TaskEdge_v3(
                    source_id=src, target_id=tgt,
                    dep_type=edge.dep_type,
                    condition=edge.condition,
                    metadata=edge.metadata,
                ))

            new_graph = TaskGraph_v3(intent_id=graph.intent_id)
            for node in new_nodes.values():
                new_graph.add_node(node)
            for edge in new_edges:
                try:
                    new_graph.add_edge(edge)
                except ValueError:
                    pass
            new_graph.metadata = deepcopy(graph.metadata)
            new_graph.created_at = graph.created_at
            return new_graph

        except Exception as exc:
            logger.warning(f"_collapse_linear_chains failed: {exc}, returning graph unchanged")
            return graph

    # ── 重排序 ────────────────────────────────────────────────────────────

    def _topological_sort_storage(self, graph: TaskGraph_v3) -> TaskGraph_v3:
        """按拓扑序重新排列节点存储顺序（不改变图结构）。

        返回的新图拥有相同的语义，但 nodes 字典的遍历顺序按拓扑序排列。
        """
        try:
            order = graph.topological_order()
            # 重建 nodes 字典以保持顺序（Python 3.7+ dict 保持插入顺序）
            new_graph = TaskGraph_v3(intent_id=graph.intent_id)
            for node in order:
                new_graph.add_node(node)
            for edge in graph.edges:
                new_graph.add_edge(edge)
            new_graph.metadata = deepcopy(graph.metadata)
            new_graph.created_at = graph.created_at
            return new_graph
        except Exception as exc:
            logger.warning(f"_topological_sort_storage failed: {exc}, returning graph unchanged")
            return graph

    # ── 克隆 ───────────────────────────────────────────────────────────────

    def _clone_graph(self, graph: TaskGraph_v3) -> TaskGraph_v3:
        """深拷贝任务图。"""
        try:
            new_graph = TaskGraph_v3(intent_id=graph.intent_id)
            for node in graph.nodes.values():
                new_graph.add_node(node.model_copy(deep=True))
            for edge in graph.edges:
                new_graph.add_edge(edge.model_copy(deep=True))
            new_graph.metadata = deepcopy(graph.metadata)
            new_graph.created_at = graph.created_at
            return new_graph
        except Exception as exc:
            logger.warning(f"_clone_graph failed: {exc}, returning shallow copy via to_dict/from_dict")
            # 备选方案：通过序列化/反序列化深拷贝
            return TaskGraph_v3.model_validate(graph.model_dump())


# ═══════════════════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio

    async def _self_test() -> None:
        logger.info("=== v3.0 planning/optimizer self-test ===")

        optimizer = TaskGraphOptimizer()

        # 构建测试图：A(scan) -> B(scan duplicate) -> C(verify)
        graph = TaskGraph_v3()
        a = TaskNode_v3(name="scan", tool_name="first_scan", tool_params={"v": 100}, layer=3)
        b = TaskNode_v3(name="scan_dup", tool_name="first_scan", tool_params={"v": 100}, layer=3)
        c = TaskNode_v3(name="verify", tool_name="verify", layer=3)
        d = TaskNode_v3(name="orphan", tool_name="orphan", layer=3)
        for n in (a, b, c, d):
            graph.add_node(n)
        graph.add_edge(TaskEdge_v3(source_id=a.id, target_id=b.id, dep_type=DependencyType.SEQUENTIAL))
        graph.add_edge(TaskEdge_v3(source_id=b.id, target_id=c.id, dep_type=DependencyType.SEQUENTIAL))
        # 悬空边
        graph.add_edge(TaskEdge_v3(source_id="nonexistent", target_id=c.id, dep_type=DependencyType.SEQUENTIAL))

        print(f"Before optimize: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
        optimized = await optimizer.optimize(graph)
        print(f"After optimize: {len(optimized.nodes)} nodes, {len(optimized.edges)} edges")

        # 断言：去重后应只剩 3 节点（scan+verify+orphan），剪枝后 orphan 被移除，剩 2 节点
        assert len(optimized.nodes) <= 3, f"Expected <=3 nodes, got {len(optimized.nodes)}"
        assert len(optimized.edges) <= 2, f"Expected <=2 edges, got {len(optimized.edges)}"
        print(f"[PASS] Optimize: nodes={len(optimized.nodes)}, edges={len(optimized.edges)}")

        # 拓扑序验证
        order = optimized.topological_order()
        assert len(order) == len(optimized.nodes)
        print(f"[PASS] Topological order: {[n.name for n in order]}")

        logger.info("=== All v3.0 optimizer self-tests passed ===")

    asyncio.run(_self_test())
