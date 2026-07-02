# -*- coding: utf-8 -*-
"""
core/agent/v3_0/planning/planner.py
───────────────────────────────────
DialogMesh Agent v3.0 — PlanningSkill 核心规划器。

用途：
- 接收 ``Intent_v3`` 与 ``IntentContext_v3``，输出 ``PlanResult``（包含 ``TaskGraph_v3``）。
- 支持多种规划策略：RULE_BASED、TEMPLATE、HYBRID、LLM_DRIVEN、RECOVERY。
- 集成 ``StrategySelector`` 进行动态策略选择，``TaskGraphOptimizer`` 进行图优化。
- 异步 API 设计，所有耗时的 LLM 调用和图优化均不阻塞事件循环。

设计原则：
- 策略无关的骨架：公共入口 ``plan()`` 统一处理状态机、步骤追踪和异常回退。
- 策略子路由：``_plan_rule_based``、``_plan_llm_driven`` 等内部方法实现具体策略。
- 可观测性：每个步骤记录 ``PlanStep`` 到 ``PlanResult`` 中，便于调试。
- 错误回退：规划失败时自动尝试降级策略（LLM_DRIVEN → HYBRID → RULE_BASED）。

依赖模块：
- ``core.agent.v3_0.data_models`` — Intent_v3, TaskGraph_v3, TaskNode_v3, TaskEdge_v3, IntentContext_v3
- ``core.agent.v3_0.llm_providers.base`` — LLMProvider_v3, GenerateRequest_v3
- ``core.agent.v3_0.cognitive_tree.models`` — CognitiveTreeNode, CogType（记录规划决策）
- ``core.agent.v3_0.planning.strategy_selector`` — StrategySelector
- ``core.agent.v3_0.planning.optimizer`` — TaskGraphOptimizer
- ``core.agent.v3_0.planning.fallback`` — FallbackPlanner

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field

from core.agent.models import DependencyType, IntentCategory, TaskStatus
from core.agent.v3_0.data_models import (
    IntentContext_v3,
    Intent_v3,
    TaskEdge_v3,
    TaskGraph_v3,
    TaskNode_v3,
)
from core.agent.v3_0.planning.fallback import FallbackPlanner
from core.agent.v3_0.planning.models import (
    PlanResult,
    PlanRevision,
    PlanStep,
    PlannerConfig,
    PlannerState,
    PlanStrategy,
    StepType,
)
from core.agent.v3_0.planning.optimizer import TaskGraphOptimizer
from core.agent.v3_0.planning.strategy_selector import StrategySelector

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 核心规划器
# ═══════════════════════════════════════════════════════════════════════════

class PlanningSkill:
    """PlanningSkill v3.0 — 主规划器。

    将用户意图转化为可执行的任务图（TaskGraph_v3），支持策略自适应、
    图优化、回退重规划和执行状态追踪。

    Args:
        strategy_selector: 策略选择器实例（默认新建）。
        optimizer: 图优化器实例（默认新建）。
        fallback_planner: 回退规划器实例（默认新建）。
        config: 规划器配置（默认使用全局默认值）。
        llm_provider: 可选的 LLM Provider，用于 LLM_DRIVEN / HYBRID 策略。

    使用示例：

    .. code-block:: python

        planner = PlanningSkill(llm_provider=provider)
        plan_result = await planner.plan(intent, intent_context)
        if plan_result.success:
            task_graph = plan_result.task_graph
    """

    def __init__(
        self,
        strategy_selector: Optional[StrategySelector] = None,
        optimizer: Optional[TaskGraphOptimizer] = None,
        fallback_planner: Optional[FallbackPlanner] = None,
        config: Optional[PlannerConfig] = None,
        llm_provider: Optional[Any] = None,  # LLMProvider_v3 实例
    ) -> None:
        self.strategy_selector = strategy_selector or StrategySelector()
        self.optimizer = optimizer or TaskGraphOptimizer()
        self.fallback_planner = fallback_planner or FallbackPlanner()
        self.config = config or PlannerConfig()
        self.llm_provider = llm_provider
        self._state = PlannerState.IDLE
        self._trace_log: List[str] = []
        logger.info(f"PlanningSkill initialized (strategy={self.config.default_strategy.value})")

    # ── 公共 API ────────────────────────────────────────────────────────────

    async def plan(
        self,
        intent: Intent_v3,
        intent_context: Optional[IntentContext_v3] = None,
        forced_strategy: Optional[PlanStrategy] = None,
    ) -> PlanResult:
        """主规划入口——将意图转化为任务图。

        Args:
            intent: 解析后的用户意图。
            intent_context: PCR 输出的意图上下文（可选）。
            forced_strategy: 强制使用指定策略（可选，用于调试或上层覆盖）。

        Returns:
            PlanResult：包含 TaskGraph、策略、步骤追踪和错误信息。
        """
        start_time = time.time()
        result = PlanResult(intent_id=intent.id)
        self._state = PlannerState.ANALYZING
        self._trace_log.clear()

        try:
            await asyncio.sleep(0)
            self._trace_log.append(f"[PLAN] Start planning for intent {intent.id}")

            # Step 1: 选择策略
            self._state = PlannerState.SELECTING_STRATEGY
            strategy = await self._select_strategy(intent, intent_context, forced_strategy)
            result.strategy_used = strategy
            step_select = PlanStep(
                step_type=StepType.ANALYSIS,
                description="策略选择",
                output_data={"strategy": strategy.value},
            )
            step_select.mark_success({"strategy": strategy.value}, 0.0)
            result.add_step(step_select)
            self._trace_log.append(f"[PLAN] Selected strategy: {strategy.value}")

            # Step 2: 生成任务图
            self._state = PlannerState.GENERATING
            task_graph = await self._generate_task_graph(intent, strategy, result, intent_context)
            if task_graph is None:
                raise RuntimeError("Task graph generation returned None")
            result.task_graph = task_graph
            self._trace_log.append(f"[PLAN] Generated task graph: {len(task_graph.nodes)} nodes, {len(task_graph.edges)} edges")

            # Step 3: 优化（可选）
            if self.config.enable_optimization:
                self._state = PlannerState.OPTIMIZING
                task_graph = await self._optimize_task_graph(task_graph, result)
                result.task_graph = task_graph
                self._trace_log.append(f"[PLAN] Optimized task graph: {len(task_graph.nodes)} nodes, {len(task_graph.edges)} edges")

            # Step 4: 验证
            self._state = PlannerState.VALIDATING
            valid = await self._validate_task_graph(task_graph, result)
            if not valid:
                if self.config.fallback_on_validation_failure:
                    self._trace_log.append("[PLAN] Validation failed, invoking fallback planner")
                    task_graph = await self._invoke_fallback(intent, task_graph, result)
                    result.task_graph = task_graph
                else:
                    raise RuntimeError("Task graph validation failed and fallback is disabled")

            self._state = PlannerState.READY
            result.success = True
            result.planner_state = PlannerState.READY
            result.latency_ms = (time.time() - start_time) * 1000.0
            self._trace_log.append(f"[PLAN] Planning complete in {result.latency_ms:.1f}ms")
            return result

        except Exception as exc:
            logger.error(f"PlanningSkill.plan failed: {exc}")
            self._state = PlannerState.FAILED
            result.success = False
            result.error = str(exc)
            result.planner_state = PlannerState.FAILED
            result.latency_ms = (time.time() - start_time) * 1000.0

            # 自动重试：如果失败且未尝试降级，尝试降级策略
            if forced_strategy is None and result.latency_ms < 30000:  # 避免无限重试
                fallback_strategy = self._get_fallback_strategy(result.strategy_used)
                if fallback_strategy and fallback_strategy != result.strategy_used:
                    self._trace_log.append(f"[PLAN] Auto-retry with fallback strategy: {fallback_strategy.value}")
                    logger.info(f"Auto-retrying with fallback strategy: {fallback_strategy.value}")
                    return await self.plan(intent, intent_context, forced_strategy=fallback_strategy)

            return result

    async def revise_plan(
        self,
        plan_result: PlanResult,
        failed_node_id: str,
        revision_reason: str,
    ) -> PlanResult:
        """修订已有计划——当某个任务节点失败时，生成修订版任务图。

        Args:
            plan_result: 原始规划结果。
            failed_node_id: 失败节点 ID。
            revision_reason: 修订原因。

        Returns:
            新的 PlanResult（修订后）。
        """
        try:
            await asyncio.sleep(0)
            self._state = PlannerState.REVISING
            self._trace_log.append(f"[REVISE] Revising plan for failed node {failed_node_id}")

            original_graph = plan_result.task_graph
            if original_graph is None:
                raise ValueError("Cannot revise plan with None task_graph")

            revision = PlanRevision(
                reason=revision_reason,
                changed_nodes=[failed_node_id],
                before_graph_hash=f"nodes={len(original_graph.nodes)},edges={len(original_graph.edges)}",
            )

            # 使用 fallback planner 生成替代方案
            new_graph = await self.fallback_planner.revise(
                original_graph, failed_node_id, revision_reason
            )
            revision.after_graph_hash = f"nodes={len(new_graph.nodes)},edges={len(new_graph.edges)}"

            # 构造新的 PlanResult
            new_result = plan_result.model_copy(deep=True)
            new_result.task_graph = new_graph
            new_result.add_revision(revision)
            new_result.planner_state = PlannerState.READY
            new_result.success = True
            new_result.error = None

            self._state = PlannerState.READY
            self._trace_log.append(f"[REVISE] Revision complete: {revision.revision_id}")
            return new_result

        except Exception as exc:
            logger.error(f"PlanningSkill.revise_plan failed: {exc}")
            self._state = PlannerState.FAILED
            plan_result.success = False
            plan_result.error = f"Revision failed: {exc}"
            plan_result.planner_state = PlannerState.FAILED
            return plan_result

    def get_state(self) -> PlannerState:
        """获取当前规划器状态。"""
        return self._state

    def get_trace_log(self) -> List[str]:
        """获取规划追踪日志（只读副本）。"""
        return self._trace_log.copy()

    # ── 策略选择 ───────────────────────────────────────────────────────────

    async def _select_strategy(
        self,
        intent: Intent_v3,
        intent_context: Optional[IntentContext_v3],
        forced_strategy: Optional[PlanStrategy],
    ) -> PlanStrategy:
        """选择规划策略（异步包装，支持强制覆盖）。"""
        await asyncio.sleep(0)
        if forced_strategy is not None:
            logger.info(f"Strategy forced by caller: {forced_strategy.value}")
            return forced_strategy

        cognitive_profile = None
        if intent_context is not None:
            cognitive_profile = intent_context.cognitive_profile

        strategy, _ = self.strategy_selector.select(
            intent,
            cognitive_profile=cognitive_profile,
            config=self.config,
        )
        return strategy

    # ── 任务图生成（策略分发）─────────────────────────────────────────────

    async def _generate_task_graph(
        self,
        intent: Intent_v3,
        strategy: PlanStrategy,
        result: PlanResult,
        intent_context: Optional[IntentContext_v3],
    ) -> Optional[TaskGraph_v3]:
        """根据策略生成任务图。"""
        generators: Dict[PlanStrategy, Any] = {
            PlanStrategy.RULE_BASED: self._plan_rule_based,
            PlanStrategy.TEMPLATE: self._plan_template,
            PlanStrategy.HYBRID: self._plan_hybrid,
            PlanStrategy.LLM_DRIVEN: self._plan_llm_driven,
            PlanStrategy.RECOVERY: self._plan_recovery,
            PlanStrategy.REFLEXIVE: self._plan_reflexive,
        }

        generator = generators.get(strategy)
        if generator is None:
            raise ValueError(f"Unknown planning strategy: {strategy.value}")

        step = PlanStep(
            step_type=StepType.DECOMPOSITION,
            description=f"使用 {strategy.value} 策略生成任务图",
        )
        start_time = time.time()

        try:
            task_graph = await generator(intent, intent_context)
            latency_ms = (time.time() - start_time) * 1000.0
            step.mark_success(
                {"nodes": len(task_graph.nodes) if task_graph else 0},
                latency_ms,
            )
            result.add_step(step)
            return task_graph
        except Exception as exc:
            latency_ms = (time.time() - start_time) * 1000.0
            step.mark_failed(str(exc), latency_ms)
            result.add_step(step)
            raise

    # ── 具体策略实现 ──────────────────────────────────────────────────────

    async def _plan_rule_based(self, intent: Intent_v3, _: Optional[IntentContext_v3]) -> TaskGraph_v3:
        """基于规则的快速规划——适合简单、高置信度意图。

        为每个常见 IntentCategory 预定义任务图模板，无需 LLM。
        """
        await asyncio.sleep(0)
        graph = TaskGraph_v3(intent_id=intent.id)
        category = intent.category

        # 根据意图类别快速构建规则图
        if category == IntentCategory.READ_MEMORY:
            addr = self._extract_entity_value(intent, "memory_address") or "0x0"
            n1 = TaskNode_v3(
                name="read_memory", goal=f"Read memory at {addr}",
                layer=3, tool_name="memory_read",
                tool_params={"address": addr},
            )
            graph.add_node(n1)

        elif category == IntentCategory.SCAN_MEMORY:
            val = self._extract_entity_value(intent, "numeric_value") or "0"
            dtype = self._extract_entity_value(intent, "data_type") or "4 bytes"
            n1 = TaskNode_v3(
                name="first_scan", goal=f"Scan for {val} ({dtype})",
                layer=3, tool_name="first_scan",
                tool_params={"value": val, "data_type": dtype},
            )
            n2 = TaskNode_v3(
                name="return_results", goal="Return scan results",
                layer=1, tool_name="return_results",
            )
            graph.add_node(n1)
            graph.add_node(n2)
            graph.add_edge(TaskEdge_v3(source_id=n1.id, target_id=n2.id, dep_type=DependencyType.SEQUENTIAL))

        elif category == IntentCategory.WRITE_MEMORY:
            addr = self._extract_entity_value(intent, "memory_address") or "0x0"
            val = self._extract_entity_value(intent, "numeric_value") or "0"
            n1 = TaskNode_v3(
                name="write_memory", goal=f"Write {val} to {addr}",
                layer=3, tool_name="memory_write",
                tool_params={"address": addr, "value": val},
                is_destructive=True,
            )
            graph.add_node(n1)

        elif category == IntentCategory.HACK_VALUE:
            val = self._extract_entity_value(intent, "numeric_value") or "0"
            n1 = TaskNode_v3(name="first_scan", goal=f"Scan for {val}", layer=3, tool_name="first_scan")
            n2 = TaskNode_v3(name="verify_address", goal="Verify candidate address", layer=3, tool_name="verify_address")
            n3 = TaskNode_v3(name="write_value", goal="Write new value", layer=3, tool_name="memory_write", is_destructive=True)
            for n in (n1, n2, n3):
                graph.add_node(n)
            graph.add_edge(TaskEdge_v3(source_id=n1.id, target_id=n2.id, dep_type=DependencyType.SEQUENTIAL))
            graph.add_edge(TaskEdge_v3(source_id=n2.id, target_id=n3.id, dep_type=DependencyType.CONDITIONAL))

        else:
            # 默认：单节点兜底
            n1 = TaskNode_v3(
                name="execute_intent", goal=f"Execute {category.value}",
                layer=2, tool_name=category.value,
            )
            graph.add_node(n1)

        return graph

    async def _plan_template(self, intent: Intent_v3, _: Optional[IntentContext_v3]) -> TaskGraph_v3:
        """模板匹配规划——对常见多步骤意图使用预定义模板。"""
        await asyncio.sleep(0)
        # 模板与 RULE_BASED 类似，但支持更复杂的结构（如条件分支、并行）
        # 这里复用 rule_based 逻辑，但可扩展更多模板
        return await self._plan_rule_based(intent, _)

    async def _plan_hybrid(self, intent: Intent_v3, intent_context: Optional[IntentContext_v3]) -> TaskGraph_v3:
        """混合规划——规则生成骨架 + LLM 细化填充。

        1. 先用 rule_based 生成骨架图。
        2. 将骨架交给 LLM 进行细化（增加子步骤、条件、备选）。
        """
        await asyncio.sleep(0)
        skeleton = await self._plan_rule_based(intent, intent_context)
        if self.llm_provider is None:
            logger.warning("HYBRID strategy requested but no LLM provider available, returning skeleton")
            return skeleton

        # 构造 LLM 提示，要求对骨架图进行细化
        prompt = self._build_hybrid_prompt(intent, skeleton)
        try:
            refined_graph = await self._llm_refine_graph(prompt, skeleton)
            return refined_graph
        except Exception as exc:
            logger.warning(f"LLM refinement failed in HYBRID: {exc}, returning skeleton")
            return skeleton

    async def _plan_llm_driven(self, intent: Intent_v3, _: Optional[IntentContext_v3]) -> TaskGraph_v3:
        """LLM 驱动规划——完全由 LLM 生成任务图。

        要求 LLM 输出符合 JSON Schema 的 TaskGraph 表示。
        """
        await asyncio.sleep(0)
        if self.llm_provider is None:
            raise RuntimeError("LLM_DRIVEN strategy requires an LLM provider, but none was provided")

        prompt = self._build_llm_prompt(intent)
        try:
            return await self._llm_generate_graph(prompt)
        except Exception as exc:
            logger.error(f"LLM driven planning failed: {exc}")
            raise

    async def _plan_recovery(self, intent: Intent_v3, _: Optional[IntentContext_v3]) -> TaskGraph_v3:
        """恢复规划——用于回退场景，生成最小可执行图。"""
        await asyncio.sleep(0)
        graph = TaskGraph_v3(intent_id=intent.id)
        n1 = TaskNode_v3(
            name="diagnose_failure", goal="Diagnose previous failure",
            layer=2, tool_name="diagnose",
        )
        n2 = TaskNode_v3(
            name="fallback_execution", goal="Execute with safe defaults",
            layer=3, tool_name="fallback",
        )
        graph.add_node(n1)
        graph.add_node(n2)
        graph.add_edge(TaskEdge_v3(source_id=n1.id, target_id=n2.id, dep_type=DependencyType.SEQUENTIAL))
        return graph

    async def _plan_reflexive(self, intent: Intent_v3, _: Optional[IntentContext_v3]) -> TaskGraph_v3:
        """反射式规划——元认知干预时的特殊规划路径。

        生成包含自我验证步骤的任务图。
        """
        await asyncio.sleep(0)
        graph = TaskGraph_v3(intent_id=intent.id)
        # 主体步骤
        n1 = TaskNode_v3(name="plan_execution", goal="Execute user intent", layer=2)
        # 元认知验证步骤
        n2 = TaskNode_v3(name="meta_validate", goal="Validate plan against constraints", layer=1)
        # 反思步骤
        n3 = TaskNode_v3(name="reflect_outcome", goal="Reflect on execution outcome", layer=1)
        for n in (n1, n2, n3):
            graph.add_node(n)
        graph.add_edge(TaskEdge_v3(source_id=n2.id, target_id=n1.id, dep_type=DependencyType.CONDITIONAL))
        graph.add_edge(TaskEdge_v3(source_id=n1.id, target_id=n3.id, dep_type=DependencyType.SEQUENTIAL))
        return graph

    # ── 图优化 ────────────────────────────────────────────────────────────

    async def _optimize_task_graph(self, graph: TaskGraph_v3, result: PlanResult) -> TaskGraph_v3:
        """异步优化任务图。"""
        await asyncio.sleep(0)
        step = PlanStep(
            step_type=StepType.MERGE,
            description="优化任务图（合并冗余、剪枝、重排序）",
        )
        start_time = time.time()

        try:
            optimized = await self.optimizer.optimize(graph)
            latency_ms = (time.time() - start_time) * 1000.0
            step.mark_success(
                {
                    "before_nodes": len(graph.nodes),
                    "after_nodes": len(optimized.nodes),
                    "before_edges": len(graph.edges),
                    "after_edges": len(optimized.edges),
                },
                latency_ms,
            )
            result.add_step(step)
            return optimized
        except Exception as exc:
            latency_ms = (time.time() - start_time) * 1000.0
            step.mark_failed(str(exc), latency_ms)
            result.add_step(step)
            logger.warning(f"Graph optimization failed: {exc}, returning original graph")
            return graph

    # ── 验证 ──────────────────────────────────────────────────────────────

    async def _validate_task_graph(self, graph: TaskGraph_v3, result: PlanResult) -> bool:
        """异步验证任务图合法性。"""
        await asyncio.sleep(0)
        step = PlanStep(
            step_type=StepType.VALIDATION,
            description="验证任务图合法性",
        )
        start_time = time.time()

        try:
            errors: List[str] = []

            # 1. 检查空图
            if not graph.nodes:
                errors.append("Task graph has no nodes")

            # 2. 检查循环依赖
            if self.config.enable_cycle_detection:
                order = graph.topological_order()
                if len(order) != len(graph.nodes):
                    errors.append("Cycle detected in task graph")

            # 3. 检查悬空边
            node_ids = set(graph.nodes.keys())
            for edge in graph.edges:
                if edge.source_id not in node_ids or edge.target_id not in node_ids:
                    errors.append(f"Dangling edge: {edge.source_id} -> {edge.target_id}")

            # 4. 检查深度约束
            max_depth = 0
            for node in graph.nodes.values():
                max_depth = max(max_depth, node.layer)
            if max_depth > self.config.max_depth:
                errors.append(f"Max depth {max_depth} exceeds limit {self.config.max_depth}")

            # 5. 检查节点数约束
            if len(graph.nodes) > self.config.max_nodes:
                errors.append(f"Node count {len(graph.nodes)} exceeds limit {self.config.max_nodes}")

            latency_ms = (time.time() - start_time) * 1000.0
            if errors:
                step.mark_failed("; ".join(errors), latency_ms)
                result.add_step(step)
                logger.warning(f"Task graph validation failed: {'; '.join(errors)}")
                return False

            step.mark_success({"valid": True, "nodes": len(graph.nodes)}, latency_ms)
            result.add_step(step)
            return True

        except Exception as exc:
            latency_ms = (time.time() - start_time) * 1000.0
            step.mark_failed(str(exc), latency_ms)
            result.add_step(step)
            return False

    # ── 回退 ──────────────────────────────────────────────────────────────

    async def _invoke_fallback(
        self,
        intent: Intent_v3,
        graph: TaskGraph_v3,
        result: PlanResult,
    ) -> TaskGraph_v3:
        """调用回退规划器。"""
        await asyncio.sleep(0)
        step = PlanStep(
            step_type=StepType.FALLBACK,
            description="回退规划器介入",
        )
        start_time = time.time()

        try:
            fallback_graph = await self.fallback_planner.create_fallback(intent, graph)
            latency_ms = (time.time() - start_time) * 1000.0
            step.mark_success({"fallback_nodes": len(fallback_graph.nodes)}, latency_ms)
            result.add_step(step)
            return fallback_graph
        except Exception as exc:
            latency_ms = (time.time() - start_time) * 1000.0
            step.mark_failed(str(exc), latency_ms)
            result.add_step(step)
            logger.warning(f"Fallback planner failed: {exc}, returning original graph")
            return graph

    # ── 降级策略 ─────────────────────────────────────────────────────────

    def _get_fallback_strategy(self, current: PlanStrategy) -> Optional[PlanStrategy]:
        """获取降级策略（LLM_DRIVEN → HYBRID → TEMPLATE → RULE_BASED → RECOVERY）。"""
        fallback_chain = [
            PlanStrategy.LLM_DRIVEN,
            PlanStrategy.HYBRID,
            PlanStrategy.TEMPLATE,
            PlanStrategy.RULE_BASED,
            PlanStrategy.RECOVERY,
        ]
        try:
            idx = fallback_chain.index(current)
            if idx + 1 < len(fallback_chain):
                return fallback_chain[idx + 1]
        except ValueError:
            pass
        return None

    # ── LLM 辅助方法 ─────────────────────────────────────────────────────

    def _build_llm_prompt(self, intent: Intent_v3) -> str:
        """构造 LLM 驱动的规划提示。"""
        return (
            f"Given the user intent: '{intent.raw_input}' (category: {intent.category.value}),\n"
            f"generate a JSON task graph with the following structure:\n"
            f"{{\"nodes\": [{{\"id\": \"T-xxx\", \"name\": \"...\", \"layer\": 1|2|3, "
            f"\"goal\": \"...\", \"tool_name\": \"...\", \"tool_params\": {{...}}}}, ...], "
            f"\"edges\": [{{\"source_id\": \"...\", \"target_id\": \"...\", \"dep_type\": \"sequential|conditional|parallel|fallback\"}}, ...]}}\n"
            f"Layer 1 = concept, Layer 2 = engineering, Layer 3 = execution.\n"
            f"Return ONLY valid JSON, no markdown."
        )

    def _build_hybrid_prompt(self, intent: Intent_v3, skeleton: TaskGraph_v3) -> str:
        """构造混合规划的细化提示。"""
        nodes_summary = ", ".join(
            f"{n.name} (layer={n.layer})" for n in skeleton.nodes.values()
        )
        return (
            f"Given the user intent: '{intent.raw_input}' and the skeleton task graph:\n"
            f"Nodes: {nodes_summary}\n"
            f"Refine this graph by adding sub-steps, conditions, or fallbacks. "
            f"Return the complete refined graph as JSON."
        )

    async def _llm_generate_graph(self, prompt: str) -> TaskGraph_v3:
        """调用 LLM 生成任务图。"""
        if self.llm_provider is None:
            raise RuntimeError("LLM provider not available")

        from core.agent.v3_0.llm_providers.base import GenerateRequest_v3

        request = GenerateRequest_v3(
            prompt=prompt,
            max_tokens=self.config.llm_max_tokens,
            temperature=self.config.llm_temperature,
            timeout_ms=self.config.llm_timeout_ms,
            response_format="json",
        )

        result = await self.llm_provider.generate_async(request)
        if not result.success or not result.text:
            raise RuntimeError(f"LLM generation failed: {result.error_type}")

        try:
            # 尝试解析 JSON
            text = result.text.strip()
            # 去除 markdown 代码块包裹
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            data = json.loads(text)
            return self._parse_llm_graph_json(data)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"LLM output is not valid JSON: {exc}")
        except Exception as exc:
            raise RuntimeError(f"Failed to parse LLM graph: {exc}")

    async def _llm_refine_graph(self, prompt: str, skeleton: TaskGraph_v3) -> TaskGraph_v3:
        """调用 LLM 细化已有骨架图。"""
        # 与 _llm_generate_graph 类似，但失败时返回 skeleton
        try:
            return await self._llm_generate_graph(prompt)
        except Exception as exc:
            logger.warning(f"LLM refinement failed, returning skeleton: {exc}")
            return skeleton

    def _parse_llm_graph_json(self, data: Dict[str, Any]) -> TaskGraph_v3:
        """将 LLM 输出的 JSON 解析为 TaskGraph_v3。"""
        graph = TaskGraph_v3()
        nodes_data = data.get("nodes", [])
        edges_data = data.get("edges", [])

        for nd in nodes_data:
            node = TaskNode_v3(
                id=nd.get("id", f"T-{uuid.uuid4().hex[:8]}"),
                name=nd.get("name", ""),
                description=nd.get("description", ""),
                layer=nd.get("layer", 2),
                goal=nd.get("goal", ""),
                strategy=nd.get("strategy", ""),
                tool_name=nd.get("tool_name"),
                tool_params=nd.get("tool_params", {}),
                status=TaskStatus(nd.get("status", "pending")),
                tags=set(nd.get("tags", [])),
            )
            graph.add_node(node)

        for ed in edges_data:
            dep_type = DependencyType(ed.get("dep_type", "sequential"))
            edge = TaskEdge_v3(
                source_id=ed.get("source_id", ""),
                target_id=ed.get("target_id", ""),
                dep_type=dep_type,
                condition=ed.get("condition"),
            )
            graph.add_edge(edge)

        return graph

    # ── 工具辅助 ──────────────────────────────────────────────────────────

    def _extract_entity_value(self, intent: Intent_v3, entity_type_name: str) -> Optional[str]:
        """从意图中提取指定类型的实体值（字符串化）。"""
        from core.agent.models import EntityType
        try:
            etype = EntityType(entity_type_name.upper())
        except ValueError:
            return None
        entity = intent.get_entity(etype)
        if entity is None:
            return None
        return str(entity.value)


# ═══════════════════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import asyncio

    async def _self_test() -> None:
        logger.info("=== v3.0 planning/planner self-test ===")

        planner = PlanningSkill()

        # 1. RULE_BASED 规划
        intent = Intent_v3(
            category=IntentCategory.READ_MEMORY,
            raw_input="read 0x1000",
            confidence=0.95,
        )
        result = await planner.plan(intent)
        assert result.success is True
        assert result.task_graph is not None
        assert len(result.task_graph.nodes) == 1
        print(f"[PASS] RULE_BASED: {result.strategy_used.value}, nodes={len(result.task_graph.nodes)}")

        # 2. HACK_VALUE 多节点规划
        intent2 = Intent_v3(
            category=IntentCategory.HACK_VALUE,
            raw_input="hack health to 999",
            confidence=0.8,
        )
        result2 = await planner.plan(intent2)
        assert result2.success is True
        assert result2.task_graph is not None
        assert len(result2.task_graph.nodes) >= 3
        print(f"[PASS] HACK_VALUE: nodes={len(result2.task_graph.nodes)}, edges={len(result2.task_graph.edges)}")

        # 3. 状态追踪
        state = planner.get_state()
        assert state == PlannerState.READY
        print(f"[PASS] Planner state: {state.value}")

        # 4. 修订计划
        result3 = await planner.revise_plan(result2, list(result2.task_graph.nodes.keys())[0], "模拟失败")
        assert result3 is not None
        print(f"[PASS] Revise plan: revisions={len(result3.revisions)}")

        # 5. 降级策略
        fallback = planner._get_fallback_strategy(PlanStrategy.LLM_DRIVEN)
        assert fallback == PlanStrategy.HYBRID
        print(f"[PASS] Fallback strategy: LLM_DRIVEN → {fallback.value if fallback else 'None'}")

        logger.info("=== All v3.0 planning/planner self-tests passed ===")

    asyncio.run(_self_test())
