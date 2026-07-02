# -*- coding: utf-8 -*-
"""
core/agent/v3_0/planning/scheduler.py
────────────────────────────────────
DialogMesh Agent v3.0 — 执行调度器（ExecutionScheduler）。

用途：
- 按拓扑顺序调度 DAG 中的任务执行。
- 支持并行执行（无依赖关系的任务并发）和串行执行（有依赖时等待）。
- 包含超时控制、重试策略和失败回退。
- 与 Worker 层交互，通过 Worker.execute() 执行具体任务。

设计原则：
- 异步优先：所有执行调度基于 asyncio，支持并发。
- 事件驱动：通过 on_event 回调推送执行状态变更。
- 防御性：任务失败时尝试重试，重试耗尽后标记为失败。

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set

from core.agent.v3_0.planning.models import (
    Task,
    TaskDAG,
    TaskResult,
    Worker,
)

logger = logging.getLogger(__name__)

EventCallback = Callable[[str, Dict[str, Any]], None]


class ExecutionScheduler:
    """执行调度器 — 调度并执行 TaskDAG 中的任务。

    Args:
        workers: Worker ID -> Worker 实例的字典。
        on_event: 可选的事件回调。
        default_task_timeout: 单个任务的默认超时（秒）。
    """

    def __init__(
        self,
        workers: Optional[Dict[str, Worker]] = None,
        on_event: Optional[EventCallback] = None,
        default_task_timeout: float = 60.0,
    ) -> None:
        self._workers = workers or {}
        self._on_event = on_event
        self._default_task_timeout = default_task_timeout
        logger.info(f"ExecutionScheduler initialized (workers={len(self._workers)})")

    # ── 公共 API ─────────────────────────────────────────────────────────

    async def execute(
        self,
        dag: TaskDAG,
        assignments: Dict[str, str],
        session_id: str = "",
    ) -> "ExecutionResult":
        """执行 DAG 中的任务。

        调度策略：
        - 按拓扑排序顺序执行。
        - 无依赖关系的任务可并行执行（由 asyncio.gather 实现）。
        - 有依赖关系的任务在依赖完成后才可执行。

        Args:
            dag: 任务 DAG。
            assignments: task_id -> worker_id 映射。
            session_id: 会话 ID（用于日志和事件）。

        Returns:
            ExecutionResult：包含执行状态、结果和统计。
        """
        try:
            await self._emit_event("execution_started", {"session_id": session_id, "task_count": len(dag.nodes)})

            completed: Set[str] = set()
            failed: Set[str] = set()
            results: List[TaskResult] = []

            # 计算入度映射（用于就绪检测）
            in_degree: Dict[str, int] = {nid: 0 for nid in dag.nodes}
            for from_id, to_id in dag.edges:
                in_degree[to_id] += 1

            # 按拓扑顺序调度，但并发执行无依赖的任务
            pending = list(dag.topological_order) if dag.topological_order else list(dag.nodes.keys())
            running_tasks: Dict[str, asyncio.Task] = {}

            while pending or running_tasks:
                # 启动所有就绪任务
                ready = []
                for nid in list(pending):
                    if in_degree.get(nid, 0) == 0 or all(dep in completed for dep in self._get_predecessors(dag, nid)):
                        ready.append(nid)
                        pending.remove(nid)

                for nid in ready:
                    if nid in running_tasks:
                        continue
                    asyncio_task = asyncio.create_task(self._run_task(nid, dag, assignments, session_id))
                    running_tasks[nid] = asyncio_task

                if not running_tasks:
                    if pending:
                        logger.warning("Deadlock detected: pending tasks but none running")
                        break
                    break

                # 等待至少一个任务完成
                done, _ = await asyncio.wait(
                    running_tasks.values(),
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for asyncio_task in done:
                    # 找到对应的节点 ID
                    nid = next((k for k, v in running_tasks.items() if v == asyncio_task), None)
                    if nid is None:
                        continue
                    running_tasks.pop(nid, None)

                    try:
                        result = asyncio_task.result()
                        results.append(result)
                        if result.success:
                            completed.add(nid)
                            await self._emit_event("task_completed", {"task_id": nid, "task_name": result.task_name})
                        else:
                            failed.add(nid)
                            await self._emit_event("task_failed", {"task_id": nid, "error": result.error})
                    except Exception as exc:
                        logger.error(f"Task {nid} execution raised exception: {exc}")
                        failed.add(nid)
                        results.append(TaskResult(task_id=nid, success=False, error=str(exc)))
                        await self._emit_event("task_failed", {"task_id": nid, "error": str(exc)})

            exec_result = ExecutionResult(
                success=len(failed) == 0,
                completed_tasks=list(completed),
                failed_tasks=list(failed),
                task_results=results,
            )

            await self._emit_event("execution_finished", {
                "session_id": session_id,
                "success": exec_result.success,
                "completed": len(completed),
                "failed": len(failed),
            })

            return exec_result

        except Exception as exc:
            logger.error(f"Execution scheduler failed: {exc}")
            await self._emit_event("execution_error", {"session_id": session_id, "error": str(exc)})
            return ExecutionResult(success=False, error=str(exc))

    # ── 内部执行逻辑 ──────────────────────────────────────────────────────

    async def _run_task(
        self,
        nid: str,
        dag: TaskDAG,
        assignments: Dict[str, str],
        session_id: str,
    ) -> TaskResult:
        """运行单个任务（含重试逻辑）。"""
        task = dag.nodes[nid]
        worker_id = assignments.get(nid)

        if not worker_id:
            logger.error(f"No worker assigned for task {nid}")
            return TaskResult(task_id=nid, task_name=task.name, success=False, error="No worker assigned")

        worker = self._workers.get(worker_id)
        if not worker:
            return TaskResult(task_id=nid, task_name=task.name, success=False, error=f"Worker {worker_id} not found")

        await self._emit_event("task_started", {"task_id": nid, "task_name": task.name, "worker": worker_id})

        start = time.time()
        try:
            # 执行主逻辑
            result = await self._execute_with_timeout(task, worker, session_id)
            result.latency_ms = (time.time() - start) * 1000.0
            worker.complete(task)
            return result
        except Exception as exc:
            latency_ms = (time.time() - start) * 1000.0
            error_str = str(exc)
            logger.error(f"Task {nid} failed: {error_str}")

            # 重试逻辑
            if self._should_retry(task, error_str):
                retry_result = await self._retry_task(task, worker, session_id)
                retry_result.latency_ms = latency_ms
                worker.complete(task)
                return retry_result

            worker.complete(task)
            return TaskResult(
                task_id=nid,
                task_name=task.name,
                success=False,
                error=error_str,
                latency_ms=latency_ms,
            )

    async def _execute_with_timeout(
        self,
        task: Task,
        worker: Worker,
        session_id: str,
    ) -> TaskResult:
        """带超时的任务执行。"""
        timeout = self._default_task_timeout
        try:
            if asyncio.iscoroutinefunction(worker.execute):
                return await asyncio.wait_for(worker.execute(task), timeout=timeout)
            else:
                loop = asyncio.get_event_loop()
                return await asyncio.wait_for(
                    loop.run_in_executor(None, worker.execute, task),
                    timeout=timeout,
                )
        except asyncio.TimeoutError:
            return TaskResult(task_id=task.id, task_name=task.name, success=False, error=f"Task timeout after {timeout}s")

    async def _retry_task(self, task: Task, worker: Worker, session_id: str) -> TaskResult:
        """重试任务。"""
        task.retry_count += 1
        delay = task.retry_policy.get_delay(task.retry_count)
        logger.info(f"Retrying task {task.id} (attempt {task.retry_count}, delay={delay}s)")
        await asyncio.sleep(delay)
        return await self._execute_with_timeout(task, worker, session_id)

    def _should_retry(self, task: Task, error_str: str) -> bool:
        """判断是否应该重试。"""
        return task.retry_policy.should_retry(error_str, task.retry_count)

    def _get_predecessors(self, dag: TaskDAG, node_id: str) -> Set[str]:
        """获取节点的前驱节点。"""
        preds: Set[str] = set()
        for from_id, to_id in dag.edges:
            if to_id == node_id:
                preds.add(from_id)
        return preds

    async def _emit_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """推送事件。"""
        if self._on_event is None:
            return
        try:
            if asyncio.iscoroutinefunction(self._on_event):
                await self._on_event(event_type, payload)
            else:
                self._on_event(event_type, payload)
        except Exception as exc:
            logger.warning(f"Event callback failed: {exc}")


class ExecutionResult:
    """执行结果（轻量级类，避免循环导入）。"""

    def __init__(
        self,
        success: bool = False,
        completed_tasks: Optional[List[str]] = None,
        failed_tasks: Optional[List[str]] = None,
        task_results: Optional[List[TaskResult]] = None,
        error: Optional[str] = None,
    ) -> None:
        self.success = success
        self.completed_tasks = completed_tasks or []
        self.failed_tasks = failed_tasks or []
        self.task_results = task_results or []
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "task_results": [r.to_dict() for r in self.task_results],
            "error": self.error,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    sys.path.insert(0, r"C:\Users\APTShark\PycharmProjects\DialogMesh")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info("=== v3.0 scheduler self-test ===")

    async def _self_test():
        from core.agent.v3_0.planning.dependency_resolver import DependencyResolver
        from core.agent.v3_0.planning.agent_allocator import AgentAllocator

        # 创建 Worker 和任务
        class MockWorker(Worker):
            async def execute(self, task):
                await asyncio.sleep(0.01)
                return TaskResult(task_id=task.id, task_name=task.name, success=True, output="ok")

        workers = {
            "w1": MockWorker(id="w1", name="LLM-1", capabilities=["Planning-LLM"]),
            "w2": MockWorker(id="w2", name="Tool-1", capabilities=["ToolExecutor"]),
        }

        tasks = [
            Task(name="A", worker_type="Planning-LLM"),
            Task(name="B", worker_type="ToolExecutor", dependencies=["A"]),
            Task(name="C", worker_type="ToolExecutor", dependencies=["A"]),
            Task(name="D", worker_type="Planning-LLM", dependencies=["B", "C"]),
        ]

        resolver = DependencyResolver()
        dag = resolver.build_dag(tasks)
        allocator = AgentAllocator(workers)
        assignments = allocator.assign(tasks, dag)

        scheduler = ExecutionScheduler(workers)
        result = await scheduler.execute(dag, assignments, session_id="test-1")

        assert result.success is True
        assert len(result.completed_tasks) == 4
        print(f"[PASS] Execute DAG: completed={len(result.completed_tasks)}, failed={len(result.failed_tasks)}")

    asyncio.run(_self_test())
    logger.info("=== All v3.0 scheduler self-tests passed ===")
