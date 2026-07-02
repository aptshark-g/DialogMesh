# -*- coding: utf-8 -*-
"""
core/agent/v3_0/planning/agent_allocator.py
──────────────────────────────────────────
DialogMesh Agent v3.0 — 智能体分配器（AgentAllocator）。

用途：
- 将任务列表分配给合适的 Worker。
- 支持能力匹配、负载均衡和亲和性策略。
- 当无可用 Worker 时抛出 AllocationError。

设计原则：
- 纯本地计算，不依赖外部 LLM。
- 防御性：找不到 Worker 时明确报错，而非静默失败。
- 线程安全：Worker 内部使用锁保护负载状态。

版本：3.0.0
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.agent.v3_0.planning.models import (
    AllocationError,
    Task,
    TaskDAG,
    Worker,
)

logger = logging.getLogger(__name__)


class AgentAllocator:
    """智能体分配器 — 将任务分配给合适的 Worker。

    分配策略：
    1. 能力匹配：筛选能处理该 worker_type 的 Worker。
    2. 负载均衡：在 capable Workers 中选择负载最低的。
    3. 亲和性：优先分配给上次处理相关任务的 Worker（Phase 1 简化）。

    Args:
        workers: Worker ID -> Worker 实例的字典。
    """

    def __init__(self, workers: Optional[Dict[str, Worker]] = None) -> None:
        self._workers: Dict[str, Worker] = workers or {}
        self._affinity_map: Dict[str, str] = {}  # task_name -> worker_id
        logger.info(f"AgentAllocator initialized (workers={len(self._workers)})")

    # ── 公共 API ─────────────────────────────────────────────────────────

    def assign(self, tasks: List[Task], dag: Optional[TaskDAG] = None) -> Dict[str, str]:
        """分配任务到 Worker。

        Args:
            tasks: 待分配的任务列表。
            dag: 可选的任务 DAG（用于辅助决策，当前版本未使用）。

        Returns:
            task_id -> worker_id 的映射字典。

        Raises:
            AllocationError: 当某个任务找不到合适的 Worker 时抛出。
        """
        try:
            assignments: Dict[str, str] = {}
            for task in tasks:
                capable_workers = self._find_capable_workers(task.worker_type)
                if not capable_workers:
                    raise AllocationError(
                        f"No worker capable of handling {task.worker_type} for task '{task.name}'"
                    )

                # 负载均衡：选择当前负载最低的 Worker
                best_worker = min(capable_workers, key=lambda w: w.current_load())

                # 亲和性：如果存在历史记录，优先使用
                if task.name in self._affinity_map:
                    preferred_id = self._affinity_map[task.name]
                    preferred = self._workers.get(preferred_id)
                    if preferred and preferred in capable_workers:
                        best_worker = preferred

                assignments[task.id] = best_worker.id
                best_worker.assign(task)
                self._affinity_map[task.name] = best_worker.id
                logger.debug(
                    f"Task '{task.name}' ({task.id}) assigned to Worker '{best_worker.id}'"
                )

            logger.info(f"Assignment complete: {len(assignments)} tasks assigned")
            return assignments

        except AllocationError:
            raise
        except Exception as exc:
            logger.error(f"Assignment failed: {exc}")
            raise

    def update_workers(self, workers: Dict[str, Worker]) -> None:
        """更新 Worker 池。"""
        try:
            self._workers = workers
            logger.info(f"Worker pool updated: {len(workers)} workers")
        except Exception as exc:
            logger.error(f"Worker pool update failed: {exc}")
            raise

    def get_worker(self, worker_id: str) -> Optional[Worker]:
        """按 ID 获取 Worker。"""
        return self._workers.get(worker_id)

    def get_worker_load(self) -> Dict[str, int]:
        """获取所有 Worker 的当前负载。"""
        try:
            return {wid: w.current_load() for wid, w in self._workers.items()}
        except Exception as exc:
            logger.error(f"Load query failed: {exc}")
            return {}

    # ── 内部工具 ─────────────────────────────────────────────────────────

    def _find_capable_workers(self, worker_type: str) -> List[Worker]:
        """查找能处理某类型任务的 Worker。"""
        try:
            return [
                w for w in self._workers.values()
                if worker_type in w.capabilities or "*" in w.capabilities
            ]
        except Exception as exc:
            logger.warning(f"Capable worker search failed: {exc}")
            return []


# ═══════════════════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    sys.path.insert(0, r"C:\Users\APTShark\PycharmProjects\DialogMesh")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info("=== v3.0 agent_allocator self-test ===")

    workers = {
        "w1": Worker(id="w1", name="Planning-LLM-1", capabilities=["Planning-LLM", "Answer-LLM"]),
        "w2": Worker(id="w2", name="ToolExecutor-1", capabilities=["ToolExecutor"]),
        "w3": Worker(id="w3", name="General-1", capabilities=["*"]),
    }
    allocator = AgentAllocator(workers)

    tasks = [
        Task(name="plan", worker_type="Planning-LLM"),
        Task(name="execute", worker_type="ToolExecutor"),
        Task(name="fallback", worker_type="Answer-LLM"),
    ]

    assignments = allocator.assign(tasks)
    assert len(assignments) == 3
    for tid, wid in assignments.items():
        print(f"[PASS] Task {tid} -> Worker {wid}")

    # 负载检查
    load = allocator.get_worker_load()
    print(f"[PASS] Worker loads: {load}")

    # 无匹配 Worker 时应报错
    bad_task = Task(name="bad", worker_type="UnknownWorker")
    try:
        allocator.assign([bad_task])
        assert False, "Should raise AllocationError"
    except AllocationError:
        print("[PASS] AllocationError raised correctly for unknown worker type")

    logger.info("=== All v3.0 agent_allocator self-tests passed ===")
