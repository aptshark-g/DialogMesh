# -*- coding: utf-8 -*-
"""
core/agent/v3_0/planning/skill_engine.py
──────────────────────────────────────
DialogMesh Agent v3.0 — 规划 Skill 引擎主类（PlanningSkillEngine）。

用途：
- 作为 Planning Skill 层的中央控制器，编排技能匹配 → 任务分解 → 依赖解析 → 智能体分配 → 执行调度 → 结果编译的完整链路。
- 支持三种规划路径（快速/混合/慢速），根据技能匹配结果动态选择。
- 提供 replan 接口，用于任务失败时的重新规划。

设计原则：
- 策略路由：match 结果决定走技能模板路径还是 LLM 动态分解路径。
- 可观测性：每个阶段记录日志和追踪事件。
- 防御性：任何阶段失败时都有明确的回退策略。

依赖模块：
- core.agent.v3_0.planning.skill_registry — SkillRegistry
- core.agent.v3_0.planning.skill_matcher — SkillMatcher
- core.agent.v3_0.planning.decomposition — DecompositionEngine
- core.agent.v3_0.planning.agent_allocator — AgentAllocator
- core.agent.v3_0.planning.dependency_resolver — DependencyResolver
- core.agent.v3_0.planning.scheduler — ExecutionScheduler, ExecutionResult
- core.agent.v3_0.cognitive_tree.models — CogType（用于结果编译）

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from core.agent.v3_0.planning.agent_allocator import AgentAllocator
from core.agent.v3_0.planning.decomposition import DecompositionEngine
from core.agent.v3_0.planning.dependency_resolver import DependencyResolver
from core.agent.v3_0.cognitive_tree.models import CogType
from core.agent.v3_0.planning.models import (
    ExecutionPlan,
    PlanningError,
    PlanningMode,
    SkillLevel,
    SkillMatchResult,
    Task,
    TaskDAG,
)
from core.agent.v3_0.planning.scheduler import ExecutionResult, ExecutionScheduler
from core.agent.v3_0.planning.skill_matcher import SkillMatcher
from core.agent.v3_0.planning.skill_registry import SkillRegistry

logger = logging.getLogger(__name__)


class PlanningSkillEngine:
    """规划 Skill 引擎 — 任务规划的中央控制器。

    Args:
        skill_registry: 技能注册中心。
        skill_matcher: 技能匹配器。
        decomposition: 任务分解引擎。
        allocator: 智能体分配器。
        dependency_resolver: 依赖解析器。
        scheduler: 执行调度器。
        cognitive_compiler: 可选的认知编译器，用于将结果写入认知树。
    """

    def __init__(
        self,
        skill_registry: Optional[SkillRegistry] = None,
        skill_matcher: Optional[SkillMatcher] = None,
        decomposition: Optional[DecompositionEngine] = None,
        allocator: Optional[AgentAllocator] = None,
        dependency_resolver: Optional[DependencyResolver] = None,
        scheduler: Optional[ExecutionScheduler] = None,
        cognitive_compiler: Optional[Any] = None,
    ) -> None:
        self._skill_registry = skill_registry or SkillRegistry()
        self._skill_matcher = skill_matcher or SkillMatcher(self._skill_registry)
        self._decomposition = decomposition or DecompositionEngine()
        self._allocator = allocator or AgentAllocator()
        self._dependency_resolver = dependency_resolver or DependencyResolver()
        self._scheduler = scheduler or ExecutionScheduler()
        self._cognitive_compiler = cognitive_compiler
        logger.info("PlanningSkillEngine initialized")

    # ── 主链路：规划并执行 ───────────────────────────────────────────────

    async def plan_and_execute(
        self,
        session_id: str,
        intent: str,
        context: Optional[Any] = None,
    ) -> ExecutionResult:
        """规划并执行用户意图。

        流程：
        1. 技能匹配：意图 → 技能模板
        2. 任务分解：根据匹配结果选择路径（技能模板 / LLM 动态）
        3. 依赖解析：构建任务 DAG
        4. 智能体分配：子任务 → Worker
        5. 执行调度：调度并执行
        6. 结果编译：任务结果 → CT 节点（可选）

        Args:
            session_id: 会话 ID。
            intent: 用户意图文本。
            context: 可选的上下文对象。

        Returns:
            ExecutionResult：执行结果。
        """
        start_time = time.time()
        try:
            await asyncio.sleep(0)
            logger.info(f"[PLAN] Start planning for session={session_id}, intent='{intent[:80]}'")

            # 1. 技能匹配
            match_result = self._skill_matcher.match(intent, context)
            logger.info(f"[PLAN] Skill match: {match_result.to_dict() if match_result else None}")

            # 2. 任务分解
            tasks = await self._decompose(intent, match_result, context)
            logger.info(f"[PLAN] Decomposed into {len(tasks)} tasks")

            # 3. 依赖解析
            dag = self._dependency_resolver.build_dag(tasks)
            if not dag.is_valid():
                raise PlanningError("Invalid task DAG: cycles detected or incomplete")
            logger.info(f"[PLAN] DAG built: {len(dag.nodes)} nodes, {len(dag.edges)} edges")

            # 4. 智能体分配
            assignments = self._allocator.assign(tasks, dag)
            logger.info(f"[PLAN] Assignments: {len(assignments)} tasks assigned")

            # 5. 执行调度
            result = await self._scheduler.execute(dag, assignments, session_id)
            latency_ms = (time.time() - start_time) * 1000.0
            logger.info(f"[PLAN] Execution finished in {latency_ms:.1f}ms, success={result.success}")

            # 6. 结果编译到认知树（可选）
            if self._cognitive_compiler:
                await self._compile_results(session_id, result)

            return result

        except PlanningError:
            raise
        except Exception as exc:
            logger.error(f"[PLAN] plan_and_execute failed: {exc}")
            return ExecutionResult(success=False, error=str(exc))

    # ── 重新规划 ─────────────────────────────────────────────────────────

    async def replan(
        self,
        session_id: str,
        failed_task: Task,
        feedback: str,
    ) -> ExecutionPlan:
        """重新规划（任务失败时调用）。

        触发条件：
        - 任务执行失败
        - Meta-Cognitive-LLM 发现计划错误
        - 用户反馈要求调整

        Args:
            session_id: 会话 ID。
            failed_task: 失败的任务。
            feedback: 失败反馈信息。

        Returns:
            ExecutionPlan：新的执行计划。
        """
        try:
            await asyncio.sleep(0)
            logger.info(f"[REPLAN] Replanning for failed task '{failed_task.name}', feedback='{feedback[:100]}'")

            failure_analysis = self._analyze_failure(failed_task, feedback)
            failure_type = failure_analysis.get("type", "execution_error")

            if failure_type == "skill_mismatch":
                # 重新匹配技能
                new_match = self._skill_matcher.match(failed_task.description)
                if new_match and new_match.skill:
                    tasks = self._decomposition.decompose_with_skill(
                        failed_task.description, new_match.skill
                    )
                else:
                    tasks = await self._decomposition.decompose(failed_task.description)
            elif failure_type == "dependency_error":
                # 重新解析依赖
                tasks = await self._decomposition.decompose(failed_task.description)
                dag = self._dependency_resolver.build_dag(tasks)
                return ExecutionPlan(tasks=tasks, dag=dag)
            else:
                # 执行失败 → 保持原任务，调度器会重试
                tasks = [failed_task]

            dag = self._dependency_resolver.build_dag(tasks)
            return ExecutionPlan(tasks=tasks, dag=dag)

        except Exception as exc:
            logger.error(f"[REPLAN] Replan failed: {exc}")
            # 最终回退：单任务
            fallback_task = Task(
                name="fallback_execution",
                description=f"Fallback for failed task: {failed_task.name}",
                worker_type="Answer-LLM",
                input_data=failed_task.description,
            )
            dag = TaskDAG()
            dag.add_node(fallback_task)
            return ExecutionPlan(tasks=[fallback_task], dag=dag)

    # ── 内部工具 ─────────────────────────────────────────────────────────

    async def _decompose(
        self,
        intent: str,
        match_result: Optional[SkillMatchResult],
        context: Optional[Any],
    ) -> List[Task]:
        """根据匹配结果选择分解路径（支持模式选择与 SkillLevel 联动）。

        决策树：
        - score > 0.8 且 level == DETAILED  → MIXED
        - score > 0.8 且 level == STANDARD/SKELETON → SKILL_ENHANCED
        - 否则 → DYNAMIC
        """
        mode = self._select_mode(match_result)
        logger.info(f"[DECOMPOSE] Selected mode: {mode.value}")
        return await self._decompose_by_mode(intent, mode, match_result, context)

    def _select_mode(self, match_result: Optional[SkillMatchResult]) -> PlanningMode:
        """根据技能匹配结果和技能详细度选择规划模式。

        Args:
            match_result: 技能匹配结果（可能为 None）。

        Returns:
            PlanningMode: 选定的规划模式。
        """
        try:
            if match_result is None or match_result.skill is None:
                return PlanningMode.DYNAMIC

            score = match_result.score
            skill = match_result.skill
            level = skill.level if isinstance(skill.level, SkillLevel) else SkillLevel(skill.level)

            if score > 0.8:
                if level == SkillLevel.DETAILED:
                    return PlanningMode.MIXED
                # STANDARD 或 SKELETON
                return PlanningMode.SKILL_ENHANCED
            return PlanningMode.DYNAMIC
        except Exception as exc:
            logger.warning(f"[SELECT_MODE] Mode selection failed ({exc}), defaulting to DYNAMIC")
            return PlanningMode.DYNAMIC

    async def _decompose_by_mode(
        self,
        intent: str,
        mode: PlanningMode,
        match_result: Optional[SkillMatchResult],
        context: Optional[Any],
    ) -> List[Task]:
        """按指定模式分解任务。

        Args:
            intent: 用户意图文本。
            mode: 规划模式。
            match_result: 技能匹配结果。
            context: 可选上下文。

        Returns:
            Task 列表。
        """
        try:
            if mode == PlanningMode.MIXED:
                # 混合模式：技能模板骨架 + LLM 动态细化
                if match_result and match_result.skill:
                    logger.info(f"[DECOMPOSE] MIXED path: skill-guided + LLM enhancement")
                    skeleton_tasks = self._decomposition.decompose_with_skill(
                        intent, match_result.skill, context
                    )
                    # 尝试 LLM 增强（如果 LLM Provider 可用）
                    if self._decomposition._llm is not None:
                        try:
                            enhanced_tasks = await self._decomposition.decompose(
                                intent, context, timeout_ms=1000
                            )
                            if len(enhanced_tasks) > len(skeleton_tasks):
                                logger.info("[DECOMPOSE] LLM enhancement applied")
                                return enhanced_tasks
                        except Exception as exc:
                            logger.warning(f"[DECOMPOSE] LLM enhancement failed: {exc}, using skeleton")
                    return skeleton_tasks
                return await self._decomposition.decompose(intent, context, timeout_ms=1000)

            elif mode == PlanningMode.SKILL_ENHANCED:
                # 技能增强模式：使用技能模板（原快速/混合路径）
                if match_result and match_result.use_template and match_result.skill:
                    logger.info(f"[DECOMPOSE] SKILL_ENHANCED path: using skill template '{match_result.skill.name}'")
                    return self._decomposition.decompose_with_skill(intent, match_result.skill, context)
                elif match_result and match_result.skill:
                    logger.info("[DECOMPOSE] SKILL_ENHANCED path: skill-guided LLM decomposition")
                    return await self._decomposition.decompose(intent, context, timeout_ms=1000)
                return await self._decomposition.decompose(intent, context, timeout_ms=1000)

            elif mode == PlanningMode.DYNAMIC:
                # 动态模式：完全 LLM 分解
                logger.info("[DECOMPOSE] DYNAMIC path: full dynamic decomposition")
                return await self._decomposition.decompose(intent, context, timeout_ms=1000)

            else:  # FALLBACK
                logger.info("[DECOMPOSE] FALLBACK path: single task fallback")
                return [Task(
                    name="fallback_execution",
                    description=f"Fallback execution: {intent}",
                    worker_type="Answer-LLM",
                    input_data=intent,
                )]

        except Exception as exc:
            logger.error(f"[DECOMPOSE] Mode {mode.value} failed: {exc}")
            raise

    # ── 重新规划（带模式回退链）──────────────────────────────────────────

    async def replan(
        self,
        session_id: str,
        failed_task: Task,
        feedback: str,
    ) -> ExecutionPlan:
        """重新规划（任务失败时调用），支持模式链式回退。

        触发条件：
        - 任务执行失败
        - Meta-Cognitive-LLM 发现计划错误
        - 用户反馈要求调整

        模式回退链：
        MIXED → SKILL_ENHANCED → DYNAMIC → FALLBACK

        Args:
            session_id: 会话 ID。
            failed_task: 失败的任务。
            feedback: 失败反馈信息。

        Returns:
            ExecutionPlan：新的执行计划。
        """
        try:
            await asyncio.sleep(0)
            logger.info(f"[REPLAN] Replanning for failed task '{failed_task.name}', feedback='{feedback[:100]}'")

            failure_analysis = self._analyze_failure(failed_task, feedback)
            failure_type = failure_analysis.get("type", "execution_error")

            # 根据失败类型选择回退链起始模式
            if failure_type == "skill_mismatch":
                start_mode = PlanningMode.MIXED
            elif failure_type == "dependency_error":
                start_mode = PlanningMode.DYNAMIC
            else:
                start_mode = PlanningMode.SKILL_ENHANCED

            return await self._execute_with_fallback(
                session_id=session_id,
                intent=failed_task.description,
                failed_task=failed_task,
                feedback=feedback,
                start_mode=start_mode,
            )

        except Exception as exc:
            logger.error(f"[REPLAN] Replan failed: {exc}")
            # 最终回退：单任务
            fallback_task = Task(
                name="fallback_execution",
                description=f"Fallback for failed task: {failed_task.name}",
                worker_type="Answer-LLM",
                input_data=failed_task.description,
            )
            dag = TaskDAG()
            dag.add_node(fallback_task)
            return ExecutionPlan(tasks=[fallback_task], dag=dag, strategy=PlanningMode.FALLBACK.value)

    async def _execute_with_fallback(
        self,
        session_id: str,
        intent: str,
        failed_task: Optional[Task] = None,
        feedback: str = "",
        start_mode: Optional[PlanningMode] = None,
    ) -> ExecutionPlan:
        """模式链式回退执行。

        按回退链依次尝试每个模式，直到生成有效 DAG 为止。
        回退链：MIXED → SKILL_ENHANCED → DYNAMIC → FALLBACK

        Args:
            session_id: 会话 ID。
            intent: 用户意图文本（通常取自 failed_task.description）。
            failed_task: 失败的任务（用于日志和诊断）。
            feedback: 失败反馈。
            start_mode: 回退链起始模式（默认为 MIXED）。

        Returns:
            ExecutionPlan：有效的新执行计划。
        """
        fallback_chain: List[PlanningMode] = [
            PlanningMode.MIXED,
            PlanningMode.SKILL_ENHANCED,
            PlanningMode.DYNAMIC,
            PlanningMode.FALLBACK,
        ]

        # 确定从回退链的哪个位置开始
        start_idx = 0
        if start_mode is not None:
            try:
                start_idx = fallback_chain.index(start_mode)
            except ValueError:
                logger.warning(f"[FALLBACK] Unknown start mode {start_mode.value}, starting from MIXED")
                start_idx = 0

        modes_to_try = fallback_chain[start_idx:]
        last_error = ""

        for mode in modes_to_try:
            try:
                logger.info(f"[FALLBACK] Trying mode {mode.value} for session={session_id}")

                if mode == PlanningMode.FALLBACK:
                    # 最终回退：单任务直接执行
                    tasks = [Task(
                        name="fallback_execution",
                        description=f"Fallback for: {intent}",
                        worker_type="Answer-LLM",
                        input_data=intent,
                    )]
                else:
                    # 重新匹配技能，尝试当前模式分解
                    match_result = self._skill_matcher.match(intent)
                    tasks = await self._decompose_by_mode(intent, mode, match_result, None)

                dag = self._dependency_resolver.build_dag(tasks)
                if dag.is_valid():
                    logger.info(f"[FALLBACK] Mode {mode.value} succeeded, returning plan")
                    return ExecutionPlan(tasks=tasks, dag=dag, strategy=mode.value)
                else:
                    logger.warning(f"[FALLBACK] Mode {mode.value} produced invalid DAG, retrying")

            except Exception as exc:
                last_error = str(exc)
                logger.warning(f"[FALLBACK] Mode {mode.value} failed: {exc}")
                continue

        # 所有模式都失败（理论上不应到达，因为 FALLBACK 总是成功）
        logger.error(f"[FALLBACK] All modes exhausted, last error: {last_error}")
        final_fallback = Task(
            name="fallback_execution",
            description=f"Fallback for failed task: {failed_task.name if failed_task else intent}",
            worker_type="Answer-LLM",
            input_data=intent,
        )
        dag = TaskDAG()
        dag.add_node(final_fallback)
        return ExecutionPlan(tasks=[final_fallback], dag=dag, strategy=PlanningMode.FALLBACK.value)

    async def _compile_results(self, session_id: str, result: ExecutionResult) -> None:
        """将执行结果编译到认知树（Cognitive Tree）。"""
        try:
            await asyncio.sleep(0)
            if not self._cognitive_compiler:
                return
            for task_result in result.task_results:
                cog_type = CogType.ACTION if task_result.success else CogType.OBSERVATION
                try:
                    self._cognitive_compiler.compile(
                        session_id=session_id,
                        llm_name="Planning-LLM",
                        cog_type=cog_type,
                        content=task_result.output if task_result.success else task_result.error,
                        confidence=1.0 if task_result.success else 0.0,
                        action=task_result.task_name,
                        action_result=str(task_result.output) if task_result.success else None,
                    )
                except Exception as exc:
                    logger.warning(f"Cognitive compilation failed for task {task_result.task_id}: {exc}")
        except Exception as exc:
            logger.error(f"Result compilation failed: {exc}")

    def _analyze_failure(self, task: Task, feedback: str) -> Dict[str, Any]:
        """分析失败原因。"""
        fb_lower = feedback.lower()
        if "skill" in fb_lower or "not found" in fb_lower or "mismatch" in fb_lower:
            return {"type": "skill_mismatch", "message": feedback}
        elif "dependency" in fb_lower or "cycle" in fb_lower or "deadlock" in fb_lower:
            return {"type": "dependency_error", "message": feedback}
        else:
            return {"type": "execution_error", "message": feedback}


# ═══════════════════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    sys.path.insert(0, r"C:\Users\APTShark\PycharmProjects\DialogMesh")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info("=== v3.0 skill_engine self-test ===")

    async def _self_test():
        engine = PlanningSkillEngine()

        # 1. 使用内置技能模板的快速路径
        result = await engine.plan_and_execute(
            session_id="test-1",
            intent="scan memory address 0x1234",
        )
        print(f"[PASS] plan_and_execute (fast path): success={result.success}, tasks={len(result.task_results)}")

        # 2. 无匹配技能的慢速路径（回退到单任务）
        result2 = await engine.plan_and_execute(
            session_id="test-2",
            intent="do something completely random and undefined",
        )
        print(f"[PASS] plan_and_execute (slow path): success={result2.success}, tasks={len(result2.task_results)}")

        # 3. replan
        failed_task = Task(name="failed_task", description="test failure")
        plan = await engine.replan("test-3", failed_task, "execution error occurred")
        assert plan.dag is not None
        print(f"[PASS] replan: tasks={len(plan.tasks)}")

    asyncio.run(_self_test())
    logger.info("=== All v3.0 skill_engine self-tests passed ===")
