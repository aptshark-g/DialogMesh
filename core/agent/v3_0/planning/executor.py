# -*- coding: utf-8 -*-
"""
core/agent/v3_0/planning/executor.py
────────────────────────────────────
DialogMesh Agent v3.0 — TaskGraph 异步执行器。

用途：
- 异步调度 TaskGraph_v3 中的节点执行，支持拓扑序、并行和条件依赖。
- 提供执行状态机（ExecutionState）、检查点（Checkpoint）和实时事件推送。
- 支持取消、暂停、恢复和断点续传。
- 与认知树交互：将执行决策记录为 ACTION / OBSERVATION 节点。

设计原则：
- 异步优先：所有执行操作使用 asyncio，支持并发执行并行分支。
- 事件驱动：通过回调函数（on_event）向调用方推送状态变更。
- 容错：节点失败时触发回退（FallbackPlanner），或暂停等待用户澄清。
- 可观测：每个节点执行记录 latency、result、error，存入检查点。

依赖模块：
- ``core.agent.v3_0.data_models`` — TaskGraph_v3, TaskNode_v3, TaskEdge_v3, TaskStatus
- ``core.agent.v3_0.planning.models`` — ExecutionCheckpoint, PlanResult
- ``core.agent.v3_0.planning.fallback`` — FallbackPlanner

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from core.agent.v3_common.models import DependencyType, TaskStatus
from core.agent.v3_0.data_models import TaskGraph_v3, TaskNode_v3, TaskEdge_v3
from core.agent.v3_0.planning.fallback import FallbackPlanner
from core.agent.v3_0.planning.models import ExecutionCheckpoint, PlanResult

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 枚举与回调类型
# ═══════════════════════════════════════════════════════════════════════════

class ExecutionState(str, Enum):
    """执行器状态机。"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_CLARIFICATION = "waiting_clarification"


NodeExecutor = Callable[[TaskNode_v3], Any]
"""节点执行器类型签名——接收 TaskNode_v3，返回执行结果（同步或异步）。"""

EventCallback = Callable[[str, Dict[str, Any]], None]
"""事件回调类型签名——(event_type, payload)。"""


# ═══════════════════════════════════════════════════════════════════════════
# 异步执行器
# ═══════════════════════════════════════════════════════════════════════════

class TaskGraphExecutor:
    """TaskGraph 异步执行器。

    核心执行逻辑：
    1. 初始化：从 PlanResult 或 TaskGraph 构建执行状态。
    2. 调度循环：按拓扑序获取就绪节点，异步并发执行。
    3. 依赖检查：节点完成后，检查下游节点是否满足条件依赖。
    4. 失败处理：节点失败时调用 FallbackPlanner 修订图，或暂停执行。
    5. 事件推送：通过 ``on_event`` 回调推送 ``node_started`` / ``node_completed`` / ``node_failed`` / ``graph_completed``。

    Args:
        node_executor: 节点执行回调（必须提供）。若节点需要工具调用，此回调负责实际执行。
        fallback_planner: 可选的回退规划器，用于节点失败时自动重规划。
        on_event: 可选的事件回调，接收执行状态变更。
        max_concurrency: 最大并发数（默认 4）。
        enable_checkpoints: 是否启用检查点保存。
    """

    def __init__(
        self,
        node_executor: NodeExecutor,
        fallback_planner: Optional[FallbackPlanner] = None,
        on_event: Optional[EventCallback] = None,
        max_concurrency: int = 4,
        enable_checkpoints: bool = True,
    ) -> None:
        if node_executor is None:
            raise ValueError("node_executor must be provided")
        self.node_executor = node_executor
        self.fallback_planner = fallback_planner or FallbackPlanner()
        self.on_event = on_event
        self.max_concurrency = max(max_concurrency, 1)
        self.enable_checkpoints = enable_checkpoints

        self._state = ExecutionState.IDLE
        self._current_graph: Optional[TaskGraph_v3] = None
        self._plan_result: Optional[PlanResult] = None
        self._checkpoints: List[ExecutionCheckpoint] = []
        self._completed_nodes: Set[str] = set()
        self._failed_nodes: Set[str] = set()
        self._cancelled_nodes: Set[str] = set()
        self._pending_nodes: Set[str] = set()
        self._semaphore = asyncio.Semaphore(self.max_concurrency)
        self._cancel_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # 默认不暂停
        logger.info(f"TaskGraphExecutor initialized (max_concurrency={max_concurrency})")

    # ── 公共 API ───────────────────────────────────────────────────────────

    async def execute(
        self,
        plan_result: PlanResult,
        resume_from_checkpoint: Optional[ExecutionCheckpoint] = None,
    ) -> ExecutionResult:
        """执行规划结果中的任务图。

        Args:
            plan_result: PlanningSkill 输出的规划结果（包含 TaskGraph）。
            resume_from_checkpoint: 可选的检查点，用于断点续传。

        Returns:
            ExecutionResult：包含最终状态、已完成节点、失败节点和统计信息。
        """
        start_time = time.time()
        self._state = ExecutionState.RUNNING
        self._plan_result = plan_result
        self._cancel_event.clear()
        self._pause_event.set()

        if plan_result.task_graph is None:
            self._state = ExecutionState.FAILED
            return ExecutionResult(
                success=False,
                error="TaskGraph is None in PlanResult",
            )

        self._current_graph = plan_result.task_graph
        self._initialize_state(resume_from_checkpoint)

        try:
            await self._emit_event("graph_started", {
                "plan_id": plan_result.result_id,
                "nodes": len(self._current_graph.nodes),
                "edges": len(self._current_graph.edges),
            })

            await self._run_scheduler()

            total_time = (time.time() - start_time) * 1000.0
            success = len(self._failed_nodes) == 0 and len(self._pending_nodes) == 0
            if self._state == ExecutionState.CANCELLED:
                success = False

            final_state = ExecutionState.COMPLETED if success else ExecutionState.FAILED
            if self._state == ExecutionState.CANCELLED:
                final_state = ExecutionState.CANCELLED
            elif self._state == ExecutionState.WAITING_CLARIFICATION:
                final_state = ExecutionState.WAITING_CLARIFICATION

            self._state = final_state

            result = ExecutionResult(
                success=success,
                state=final_state,
                completed_nodes=list(self._completed_nodes),
                failed_nodes=list(self._failed_nodes),
                cancelled_nodes=list(self._cancelled_nodes),
                pending_nodes=list(self._pending_nodes),
                total_latency_ms=total_time,
                checkpoints=self._checkpoints.copy(),
            )

            await self._emit_event("graph_completed", {
                "plan_id": plan_result.result_id,
                "success": success,
                "state": final_state.value,
                "completed": len(self._completed_nodes),
                "failed": len(self._failed_nodes),
                "latency_ms": total_time,
            })

            return result

        except Exception as exc:
            logger.error(f"TaskGraphExecutor.execute failed: {exc}")
            self._state = ExecutionState.FAILED
            return ExecutionResult(
                success=False,
                state=ExecutionState.FAILED,
                error=str(exc),
            )

    async def pause(self) -> None:
        """暂停执行（当前正在运行的节点不会中断，但新节点不会被调度）。"""
        logger.info("Execution paused")
        self._state = ExecutionState.PAUSED
        self._pause_event.clear()
        await self._emit_event("execution_paused", {})

    async def resume(self) -> None:
        """恢复执行。"""
        logger.info("Execution resumed")
        self._state = ExecutionState.RUNNING
        self._pause_event.set()
        await self._emit_event("execution_resumed", {})

    async def cancel(self) -> None:
        """取消执行（当前节点继续运行，但调度循环会终止）。"""
        logger.info("Execution cancelled")
        self._state = ExecutionState.CANCELLED
        self._cancel_event.set()
        await self._emit_event("execution_cancelled", {})

    async def get_checkpoint(self) -> ExecutionCheckpoint:
        """获取当前执行检查点。"""
        await asyncio.sleep(0)
        return ExecutionCheckpoint(
            plan_result_id=self._plan_result.result_id if self._plan_result else "",
            completed_node_ids=list(self._completed_nodes),
            failed_node_ids=list(self._failed_nodes),
            pending_node_ids=list(self._pending_nodes),
            current_node_id=self._get_current_node_id(),
        )

    def get_state(self) -> ExecutionState:
        """获取当前执行状态。"""
        return self._state

    # ── 调度器核心 ─────────────────────────────────────────────────────────

    async def _run_scheduler(self) -> None:
        """主调度循环——持续获取就绪节点并并发执行。"""
        while self._state == ExecutionState.RUNNING:
            if self._cancel_event.is_set():
                break

            await self._pause_event.wait()

            ready_nodes = await self._get_ready_nodes()
            if not ready_nodes:
                if not self._pending_nodes:
                    break  # 全部完成
                # 还有 pending 但没有就绪，说明有节点被阻塞或等待澄清
                blocked = await self._get_blocked_nodes()
                if blocked and not self._pending_nodes - {n.id for n in blocked}:
                    logger.warning("All pending nodes are blocked, stopping scheduler")
                    break
                await asyncio.sleep(0.1)
                continue

            # 并发执行就绪节点（受信号量限制）
            tasks = [
                asyncio.create_task(self._execute_node_with_semaphore(node))
                for node in ready_nodes
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_node_with_semaphore(self, node: TaskNode_v3) -> None:
        """在信号量限制下执行单个节点。"""
        async with self._semaphore:
            await self._execute_node(node)

    async def _execute_node(self, node: TaskNode_v3) -> None:
        """执行单个节点并更新状态。"""
        if self._cancel_event.is_set():
            return

        node_id = node.id
        self._pending_nodes.discard(node_id)
        node.mark_running()

        await self._emit_event("node_started", {
            "node_id": node_id,
            "name": node.name,
            "layer": node.layer,
            "tool_name": node.tool_name,
        })

        start_time = time.time()
        try:
            # 调用外部节点执行器
            if asyncio.iscoroutinefunction(self.node_executor):
                result = await self.node_executor(node)
            else:
                result = self.node_executor(node)

            latency_ms = (time.time() - start_time) * 1000.0
            node.mark_success({"result": result, "latency_ms": latency_ms})
            self._completed_nodes.add(node_id)

            await self._emit_event("node_completed", {
                "node_id": node_id,
                "name": node.name,
                "result": result,
                "latency_ms": latency_ms,
            })

            if self.enable_checkpoints:
                await self._save_checkpoint()

        except Exception as exc:
            latency_ms = (time.time() - start_time) * 1000.0
            error_str = str(exc)
            node.mark_failed(error_str)
            node.retry_count += 1  # 修复：mark_failed 不增加 retry_count，导致 can_retry() 永远返回 True
            self._failed_nodes.add(node_id)

            await self._emit_event("node_failed", {
                "node_id": node_id,
                "name": node.name,
                "error": error_str,
                "latency_ms": latency_ms,
            })

            # 尝试回退
            if self.fallback_planner and node.can_retry():
                await self._handle_node_failure(node, error_str)

    async def _handle_node_failure(self, node: TaskNode_v3, error_str: str) -> None:
        """处理节点失败——尝试回退或暂停。"""
        try:
            await asyncio.sleep(0)
            if self._plan_result is None or self._current_graph is None:
                return

            # 尝试修订图
            revised_result = await self.fallback_planner.revise(
                self._current_graph, node.id, error_str
            )
            self._current_graph = revised_result
            self._plan_result.task_graph = revised_result

            # 更新 pending 状态（新插入的节点需要被执行）
            for nid in revised_result.nodes:
                if nid not in self._completed_nodes and nid not in self._failed_nodes:
                    self._pending_nodes.add(nid)

            await self._emit_event("graph_revised", {
                "failed_node_id": node.id,
                "reason": error_str,
                "new_nodes": len(revised_result.nodes),
            })

        except Exception as exc:
            logger.error(f"Fallback handling failed for node {node.id}: {exc}")
            # 标记为 NEEDS_CLARIFICATION，暂停执行
            node.status = TaskStatus.NEEDS_CLARIFICATION
            self._state = ExecutionState.WAITING_CLARIFICATION
            await self._emit_event("waiting_clarification", {
                "node_id": node.id,
                "error": error_str,
            })

    # ── 就绪/阻塞检测 ──────────────────────────────────────────────────────

    async def _get_ready_nodes(self) -> List[TaskNode_v3]:
        """获取所有依赖已完成的就绪节点。"""
        await asyncio.sleep(0)
        if self._current_graph is None:
            return []
        return await self._current_graph.async_get_ready_nodes()

    async def _get_blocked_nodes(self) -> List[TaskNode_v3]:
        """获取被阻塞的节点（至少一个依赖失败）。"""
        await asyncio.sleep(0)
        if self._current_graph is None:
            return []
        blocked: List[TaskNode_v3] = []
        incoming_map: Dict[str, Set[str]] = {}
        for edge in self._current_graph.edges:
            incoming_map.setdefault(edge.target_id, set()).add(edge.source_id)
        for node in self._current_graph.nodes.values():
            if node.status != TaskStatus.PENDING:
                continue
            deps = incoming_map.get(node.id, set())
            if any(
                self._current_graph.nodes[d].status in (TaskStatus.FAILED, TaskStatus.BLOCKED)
                for d in deps
            ):
                blocked.append(node)
        return blocked

    # ── 状态初始化 ─────────────────────────────────────────────────────────

    def _initialize_state(self, checkpoint: Optional[ExecutionCheckpoint] = None) -> None:
        """初始化执行状态，支持从检查点恢复。"""
        self._completed_nodes.clear()
        self._failed_nodes.clear()
        self._cancelled_nodes.clear()
        self._pending_nodes.clear()

        if checkpoint:
            self._completed_nodes.update(checkpoint.completed_node_ids)
            self._failed_nodes.update(checkpoint.failed_node_ids)
            self._pending_nodes.update(checkpoint.pending_node_ids)
            # 将已完成/失败的节点状态同步到图中
            for nid in self._completed_nodes:
                node = self._current_graph.nodes.get(nid)
                if node and node.status == TaskStatus.PENDING:
                    node.mark_success({"restored_from_checkpoint": True})
            for nid in self._failed_nodes:
                node = self._current_graph.nodes.get(nid)
                if node and node.status == TaskStatus.PENDING:
                    node.mark_failed("Restored from checkpoint as failed")
        else:
            # 所有 PENDING 节点加入 pending 集合
            for node in self._current_graph.nodes.values():
                if node.status == TaskStatus.PENDING:
                    self._pending_nodes.add(node.id)

    # ── 检查点 ───────────────────────────────────────────────────────────────

    async def _save_checkpoint(self) -> None:
        """保存当前检查点。"""
        try:
            await asyncio.sleep(0)
            cp = await self.get_checkpoint()
            self._checkpoints.append(cp)
            # 限制检查点数量
            if len(self._checkpoints) > 100:
                self._checkpoints = self._checkpoints[-50:]
            logger.debug(f"Checkpoint saved: {cp.checkpoint_id}")
        except Exception as exc:
            logger.warning(f"Checkpoint save failed: {exc}")

    # ── 事件推送 ───────────────────────────────────────────────────────────

    async def _emit_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """推送事件到回调。"""
        if self.on_event is None:
            return
        try:
            if asyncio.iscoroutinefunction(self.on_event):
                await self.on_event(event_type, payload)
            else:
                self.on_event(event_type, payload)
        except Exception as exc:
            logger.warning(f"Event callback failed for {event_type}: {exc}")

    # ── 工具方法 ───────────────────────────────────────────────────────────

    def _get_current_node_id(self) -> Optional[str]:
        """获取当前正在执行的节点 ID（简化：取第一个 running 状态的节点）。"""
        if self._current_graph is None:
            return None
        for node in self._current_graph.nodes.values():
            if node.status == TaskStatus.RUNNING:
                return node.id
        return None


# ═══════════════════════════════════════════════════════════════════════════
# 执行结果模型
# ═══════════════════════════════════════════════════════════════════════════

class ExecutionResult:
    """TaskGraph 执行结果——非 Pydantic 的轻量级结果类（用于执行器内部，避免循环导入）。"""

    def __init__(
        self,
        success: bool = False,
        state: ExecutionState = ExecutionState.IDLE,
        completed_nodes: Optional[List[str]] = None,
        failed_nodes: Optional[List[str]] = None,
        cancelled_nodes: Optional[List[str]] = None,
        pending_nodes: Optional[List[str]] = None,
        total_latency_ms: float = 0.0,
        checkpoints: Optional[List[ExecutionCheckpoint]] = None,
        error: Optional[str] = None,
    ) -> None:
        self.success = success
        self.state = state
        self.completed_nodes = completed_nodes or []
        self.failed_nodes = failed_nodes or []
        self.cancelled_nodes = cancelled_nodes or []
        self.pending_nodes = pending_nodes or []
        self.total_latency_ms = total_latency_ms
        self.checkpoints = checkpoints or []
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典。"""
        return {
            "success": self.success,
            "state": self.state.value,
            "completed_nodes": self.completed_nodes,
            "failed_nodes": self.failed_nodes,
            "cancelled_nodes": self.cancelled_nodes,
            "pending_nodes": self.pending_nodes,
            "total_latency_ms": self.total_latency_ms,
            "checkpoints": [cp.model_dump() for cp in self.checkpoints],
            "error": self.error,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio

    async def _self_test() -> None:
        logger.info("=== v3.0 planning/executor self-test ===")

        events: List[tuple] = []

        def event_handler(event_type: str, payload: Dict[str, Any]) -> None:
            events.append((event_type, payload))
            print(f"  [EVENT] {event_type}: {payload.get('node_id', payload.get('plan_id', ''))}")

        async def dummy_executor(node: TaskNode_v3) -> str:
            await asyncio.sleep(0.05)  # 模拟 50ms 执行
            if node.name == "fail_node":
                raise RuntimeError("Simulated failure")
            return f"ok:{node.name}"

        # 构建测试图: A -> B -> C; A -> D
        from core.agent.v3_0.data_models import TaskEdge_v3, TaskGraph_v3, TaskNode_v3
        graph = TaskGraph_v3()
        a = TaskNode_v3(name="A", layer=3)
        b = TaskNode_v3(name="B", layer=3)
        c = TaskNode_v3(name="C", layer=3)
        d = TaskNode_v3(name="D", layer=3)
        for n in (a, b, c, d):
            graph.add_node(n)
        graph.add_edge(TaskEdge_v3(source_id=a.id, target_id=b.id, dep_type=DependencyType.SEQUENTIAL))
        graph.add_edge(TaskEdge_v3(source_id=b.id, target_id=c.id, dep_type=DependencyType.SEQUENTIAL))
        graph.add_edge(TaskEdge_v3(source_id=a.id, target_id=d.id, dep_type=DependencyType.SEQUENTIAL))

        plan_result = PlanResult(
            result_id="plan-test-1",
            task_graph=graph,
            success=True,
        )

        executor = TaskGraphExecutor(
            node_executor=dummy_executor,
            on_event=event_handler,
            max_concurrency=2,
        )

        result = await executor.execute(plan_result)
        assert result.success is True
        assert len(result.completed_nodes) == 4
        print(f"[PASS] Execute success: completed={len(result.completed_nodes)}, latency={result.total_latency_ms:.1f}ms")

        # 检查点测试
        cp = await executor.get_checkpoint()
        assert cp.completed_node_ids == result.completed_nodes
        print(f"[PASS] Checkpoint: completed={len(cp.completed_node_ids)}")

        # 失败测试
        graph2 = TaskGraph_v3()
        f1 = TaskNode_v3(name="fail_node", layer=3)
        graph2.add_node(f1)
        plan_result2 = PlanResult(
            result_id="plan-test-2",
            task_graph=graph2,
            success=True,
        )
        executor2 = TaskGraphExecutor(
            node_executor=dummy_executor,
            on_event=event_handler,
            fallback_planner=None,
        )
        result2 = await executor2.execute(plan_result2)
        assert result2.success is False
        assert len(result2.failed_nodes) == 1
        print(f"[PASS] Execute failure: failed={len(result2.failed_nodes)}")

        logger.info("=== All v3.0 executor self-tests passed ===")

    asyncio.run(_self_test())
