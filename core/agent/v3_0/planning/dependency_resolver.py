# -*- coding: utf-8 -*-
"""
core/agent/v3_0/planning/dependency_resolver.py
─────────────────────────────────────────────
DialogMesh Agent v3.0 — 依赖解析器（DependencyResolver）。

用途：
- 根据 Task 列表的依赖关系构建 TaskDAG。
- 检测循环依赖并抛出 DependencyError。
- 计算拓扑排序和关键路径。

设计原则：
- 纯图算法，无外部依赖。
- 防御性：循环检测失败时保守返回 True（假设有循环）。
- 关键路径使用动态规划，基于 estimated_time。

版本：3.0.0
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.agent.v3_0.planning.models import (
    DependencyError,
    Task,
    TaskDAG,
)

logger = logging.getLogger(__name__)


class DependencyResolver:
    """依赖解析器 — 构建和验证任务依赖 DAG。

    对应工程文档: ENGINEERING_PLANNING_SKILL.md §9
    """

    def __init__(self) -> None:
        logger.info("DependencyResolver initialized")

    # ── 公共 API ─────────────────────────────────────────────────────────

    def build_dag(self, tasks: List[Task]) -> TaskDAG:
        """构建任务 DAG。

        步骤：
        1. 创建节点
        2. 添加边（依赖关系）
        3. 检测循环
        4. 拓扑排序

        Args:
            tasks: 任务列表。

        Returns:
            TaskDAG 实例。

        Raises:
            DependencyError: 检测到循环依赖时抛出。
        """
        try:
            dag = TaskDAG()

            # 1. 创建节点
            for task in tasks:
                dag.add_node(task)

            # 2. 添加边（按任务名称匹配）
            for task in tasks:
                for dep_name in task.dependencies:
                    dep_task = self._find_task_by_name(tasks, dep_name)
                    if dep_task is None:
                        logger.warning(
                            f"Task '{task.name}' depends on '{dep_name}' which does not exist"
                        )
                        continue
                    dag.add_edge(dep_task.id, task.id)

            # 3. 检测循环
            if dag.has_cycle():
                raise DependencyError("Circular dependency detected in task graph")

            # 4. 拓扑排序
            dag.topological_order = dag.topological_sort()
            dag.metadata["task_count"] = len(tasks)
            dag.metadata["edge_count"] = len(dag.edges)

            logger.info(
                f"DAG built: {len(dag.nodes)} nodes, {len(dag.edges)} edges, "
                f"topological_order_valid={dag.is_valid()}"
            )
            return dag

        except DependencyError:
            raise
        except Exception as exc:
            logger.error(f"DAG build failed: {exc}")
            raise

    def find_critical_path(self, dag: TaskDAG) -> List[str]:
        """查找关键路径（影响总执行时间的最长路径）。

        使用动态规划计算最长路径（基于 estimated_time）。

        Args:
            dag: 已构建并验证的 TaskDAG。

        Returns:
            任务 ID 列表（从起点到终点的最长路径）。
        """
        try:
            if not dag.topological_order:
                dag.topological_order = dag.topological_sort()

            # 计算每个节点的最长距离
            dist: Dict[str, float] = {node_id: 0.0 for node_id in dag.nodes}
            predecessors: Dict[str, Optional[str]] = {node_id: None for node_id in dag.nodes}

            for node_id in dag.topological_order:
                task = dag.nodes[node_id]
                for neighbor in dag.neighbors.get(node_id, set()):
                    neighbor_task = dag.nodes[neighbor]
                    edge_weight = float(neighbor_task.estimated_time)
                    if dist[neighbor] < dist[node_id] + edge_weight:
                        dist[neighbor] = dist[node_id] + edge_weight
                        predecessors[neighbor] = node_id

            # 回溯关键路径
            if not dist:
                return []
            max_node = max(dist, key=dist.get)
            path: List[str] = []
            current: Optional[str] = max_node
            while current is not None:
                path.insert(0, current)
                current = predecessors.get(current)

            logger.info(f"Critical path found: length={len(path)}, total_time={dist[max_node]:.1f}s")
            return path

        except Exception as exc:
            logger.error(f"Critical path calculation failed: {exc}")
            return []

    def validate_dependencies(self, tasks: List[Task]) -> List[str]:
        """验证依赖的完整性，返回缺失的依赖名称列表。"""
        try:
            task_names = {t.name for t in tasks}
            missing: List[str] = []
            for task in tasks:
                for dep_name in task.dependencies:
                    if dep_name not in task_names:
                        missing.append(dep_name)
            if missing:
                logger.warning(f"Missing dependencies detected: {missing}")
            return missing
        except Exception as exc:
            logger.error(f"Dependency validation failed: {exc}")
            return []

    # ── 内部工具 ─────────────────────────────────────────────────────────

    def _find_task_by_name(self, tasks: List[Task], name: str) -> Optional[Task]:
        """按名称查找任务。"""
        try:
            for task in tasks:
                if task.name == name:
                    return task
            return None
        except Exception as exc:
            logger.warning(f"Task lookup by name failed: {exc}")
            return None


# ═══════════════════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    sys.path.insert(0, r"C:\Users\APTShark\PycharmProjects\DialogMesh")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info("=== v3.0 dependency_resolver self-test ===")

    resolver = DependencyResolver()

    # 1. 正常 DAG
    tasks = [
        Task(name="A", dependencies=[]),
        Task(name="B", dependencies=["A"]),
        Task(name="C", dependencies=["A"]),
        Task(name="D", dependencies=["B", "C"]),
    ]
    dag = resolver.build_dag(tasks)
    assert dag.is_valid()
    assert len(dag.topological_order) == 4
    order = dag.topological_order
    assert order.index(tasks[0].id) < order.index(tasks[1].id)
    assert order.index(tasks[0].id) < order.index(tasks[2].id)
    assert order.index(tasks[1].id) < order.index(tasks[3].id)
    assert order.index(tasks[2].id) < order.index(tasks[3].id)
    print(f"[PASS] DAG build & topological sort: {order}")

    # 2. 循环检测
    cyclic_tasks = [
        Task(name="A", dependencies=["B"]),
        Task(name="B", dependencies=["C"]),
        Task(name="C", dependencies=["A"]),
    ]
    try:
        resolver.build_dag(cyclic_tasks)
        assert False, "Should raise DependencyError"
    except DependencyError:
        print("[PASS] Cycle detection: DependencyError raised correctly")

    # 3. 关键路径
    critical_path = resolver.find_critical_path(dag)
    assert len(critical_path) >= 1
    print(f"[PASS] Critical path: {critical_path}")

    # 4. 依赖验证
    missing = resolver.validate_dependencies(tasks)
    assert len(missing) == 0
    print(f"[PASS] Dependency validation: no missing")

    logger.info("=== All v3.0 dependency_resolver self-tests passed ===")
