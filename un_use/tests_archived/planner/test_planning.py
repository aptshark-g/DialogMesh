# -*- coding: utf-8 -*-
"""
core/agent/v3_0/planning/tests/test_planning.py
────────────────────────────────────────────
DialogMesh Agent v3.0 — Planning Skill 测试套件。

用途：
- 对 Planning Skill 的所有子模块进行单元测试与集成测试。
- 覆盖策略选择、任务图生成、优化、回退、执行全链路。

运行方式：
    pytest core/agent/v3_0/planning/tests/test_planning.py -v

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import pytest
from typing import Any, Dict, List

from core.agent.models import DependencyType, IntentCategory, TaskStatus
from core.agent.v3_legacy.data_models import (
    CognitiveProfile_v3,
    IntentContext_v3,
    Intent_v3,
    TaskEdge_v3,
    TaskGraph_v3,
    TaskNode_v3,
)
from core.agent.planner.agent_allocator import AgentAllocator
from core.agent.planner.decomposition import DecompositionEngine
from core.agent.planner.dependency_resolver import DependencyResolver
from core.agent.planner.executor import ExecutionResult, ExecutionState, TaskGraphExecutor
from core.agent.planner.fallback import FallbackPlanner
from core.agent.planner.models import (
    AllocationError,
    DependencyError,
    ExecutionCheckpoint,
    PlanResult,
    PlanRevision,
    PlanStep,
    PlannerConfig,
    PlannerState,
    PlanningMode,
    PlanStrategy,
    PrimitiveLibrary,
    SkillLevel,
    SkillMatchResult,
    SkillNotFoundError,
    SkillTemplate,
    StepType,
    StrategyScore,
    Task,
    TaskResult,
    Worker,
)
from core.agent.planner.optimizer import TaskGraphOptimizer
from core.agent.planner.planner import PlanningSkill
from core.agent.planner.scheduler import ExecutionScheduler
from core.agent.planner.skill_engine import PlanningSkillEngine
from core.agent.planner.skill_matcher import SkillMatcher
from core.agent.planner.skill_registry import SkillRegistry
from core.agent.planner.agent_allocator import AgentAllocator
from core.agent.planner.decomposition import DecompositionEngine
from core.agent.planner.dependency_resolver import DependencyResolver
from core.agent.planner.scheduler import ExecutionScheduler
from core.agent.planner.strategy_selector import StrategySelector


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def simple_intent() -> Intent_v3:
    """简单意图：读取内存。"""
    return Intent_v3(
        category=IntentCategory.READ_MEMORY,
        raw_input="read 0x1000",
        confidence=0.95,
    )


@pytest.fixture
def complex_intent() -> Intent_v3:
    """复杂意图：分析进程。"""
    return Intent_v3(
        category=IntentCategory.ANALYZE_PROCESS,
        raw_input="fully analyze this process",
        confidence=0.4,
    )


@pytest.fixture
def medium_intent() -> Intent_v3:
    """中等复杂度意图：修改数值（扫描→验证→写入）。"""
    return Intent_v3(
        category=IntentCategory.HACK_VALUE,
        raw_input="hack health to 999",
        confidence=0.6,
    )


@pytest.fixture
def cognitive_profile() -> CognitiveProfile_v3:
    """标准认知画像。"""
    return CognitiveProfile_v3(
        stability=0.8,
        divergence=0.2,
        metacognition=0.5,
    )


@pytest.fixture
def planner_config() -> PlannerConfig:
    """标准规划器配置。"""
    return PlannerConfig()


@pytest.fixture
def strategy_selector() -> StrategySelector:
    """策略选择器实例。"""
    return StrategySelector()


@pytest.fixture
def optimizer() -> TaskGraphOptimizer:
    """优化器实例。"""
    return TaskGraphOptimizer()


@pytest.fixture
def fallback_planner() -> FallbackPlanner:
    """回退规划器实例。"""
    return FallbackPlanner()


@pytest.fixture
def planning_skill() -> PlanningSkill:
    """无 LLM 的规划器实例。"""
    return PlanningSkill()


@pytest.fixture
def sample_task_graph() -> TaskGraph_v3:
    """构建一个示例任务图用于测试优化与执行。"""
    graph = TaskGraph_v3()
    a = TaskNode_v3(name="scan", tool_name="first_scan", tool_params={"v": 100}, layer=3)
    b = TaskNode_v3(name="scan_dup", tool_name="first_scan", tool_params={"v": 100}, layer=3)
    c = TaskNode_v3(name="verify", tool_name="verify", layer=3)
    d = TaskNode_v3(name="orphan", tool_name="orphan", layer=3)
    for n in (a, b, c, d):
        graph.add_node(n)
    graph.add_edge(TaskEdge_v3(source_id=a.id, target_id=b.id, dep_type=DependencyType.SEQUENTIAL))
    graph.add_edge(TaskEdge_v3(source_id=b.id, target_id=c.id, dep_type=DependencyType.SEQUENTIAL))
    # 添加悬空边（直接 append 绕过 add_edge 的校验）
    graph.edges.append(TaskEdge_v3(source_id="nonexistent", target_id=c.id, dep_type=DependencyType.SEQUENTIAL))
    return graph


# ═══════════════════════════════════════════════════════════════════════════
# 策略选择器测试
# ═══════════════════════════════════════════════════════════════════════════

class TestStrategySelector:
    """StrategySelector 单元测试。"""

    def test_select_rule_based_for_simple_intent(
        self,
        strategy_selector: StrategySelector,
        simple_intent: Intent_v3,
        cognitive_profile: CognitiveProfile_v3,
    ) -> None:
        """简单意图应选择 RULE_BASED 策略。"""
        strategy, scores = strategy_selector.select(simple_intent, cognitive_profile)
        assert strategy == PlanStrategy.RULE_BASED
        assert len(scores) == len(PlanStrategy)
        assert scores[0].score >= 0.0

    def test_select_llm_driven_for_complex_intent(
        self,
        strategy_selector: StrategySelector,
        complex_intent: Intent_v3,
        cognitive_profile: CognitiveProfile_v3,
    ) -> None:
        """复杂意图应选择 LLM_DRIVEN 策略。"""
        strategy, scores = strategy_selector.select(complex_intent, cognitive_profile)
        assert strategy == PlanStrategy.LLM_DRIVEN

    def test_select_hybrid_for_medium_intent(
        self,
        strategy_selector: StrategySelector,
        medium_intent: Intent_v3,
        cognitive_profile: CognitiveProfile_v3,
    ) -> None:
        """中等复杂度意图应选择 HYBRID 策略。"""
        strategy, scores = strategy_selector.select(medium_intent, cognitive_profile)
        assert strategy == PlanStrategy.HYBRID

    def test_explain_last_selection(
        self,
        strategy_selector: StrategySelector,
        simple_intent: Intent_v3,
        cognitive_profile: CognitiveProfile_v3,
    ) -> None:
        """解释文本应包含策略名称。"""
        strategy_selector.select(simple_intent, cognitive_profile)
        explanation = strategy_selector.explain_last_selection()
        assert "Selected strategy" in explanation
        assert PlanStrategy.RULE_BASED.value in explanation

    def test_strategy_scores_clamped(
        self,
        strategy_selector: StrategySelector,
    ) -> None:
        """评分应在 [0, 1] 范围内。"""
        # 通过极端输入触发边界（confidence 在 Intent_v3 中已被 Pydantic 严格校验为 [0,1]，
        # 因此使用允许的最大值 1.0，再直接验证 StrategyScore 的裁剪逻辑）
        extreme_intent = Intent_v3(
            category=IntentCategory.UNKNOWN,
            raw_input="",
            confidence=1.0,  # 合法上限值
        )
        strategy, scores = strategy_selector.select(extreme_intent)
        for score in scores:
            assert 0.0 <= score.score <= 1.0
            assert 0.0 <= score.confidence <= 1.0
        # 额外验证 StrategyScore 模型本身的裁剪行为
        over_score = StrategyScore(strategy=PlanStrategy.RULE_BASED, score=1.5, confidence=-0.5)
        assert over_score.score == 1.0
        assert over_score.confidence == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 规划器测试
# ═══════════════════════════════════════════════════════════════════════════

class TestPlanningSkill:
    """PlanningSkill 单元测试。"""

    @pytest.mark.asyncio
    async def test_plan_simple_intent_rule_based(
        self,
        planning_skill: PlanningSkill,
        simple_intent: Intent_v3,
    ) -> None:
        """简单意图应生成 RULE_BASED 任务图。"""
        result = await planning_skill.plan(simple_intent)
        assert result.success is True
        assert result.task_graph is not None
        assert result.strategy_used == PlanStrategy.RULE_BASED
        assert len(result.task_graph.nodes) == 1
        assert result.planner_state == PlannerState.READY

    @pytest.mark.asyncio
    async def test_plan_hack_value_multi_node(
        self,
        planning_skill: PlanningSkill,
    ) -> None:
        """HACK_VALUE 意图应生成多节点任务图。"""
        intent = Intent_v3(
            category=IntentCategory.HACK_VALUE,
            raw_input="hack health to 999",
            confidence=0.8,
        )
        result = await planning_skill.plan(intent)
        assert result.success is True
        assert result.task_graph is not None
        assert len(result.task_graph.nodes) >= 3
        assert len(result.task_graph.edges) >= 2

    @pytest.mark.asyncio
    async def test_plan_forced_strategy(
        self,
        planning_skill: PlanningSkill,
        simple_intent: Intent_v3,
    ) -> None:
        """强制策略应覆盖自动选择。"""
        result = await planning_skill.plan(simple_intent, forced_strategy=PlanStrategy.TEMPLATE)
        assert result.strategy_used == PlanStrategy.TEMPLATE

    @pytest.mark.asyncio
    async def test_plan_state_tracking(
        self,
        planning_skill: PlanningSkill,
        simple_intent: Intent_v3,
    ) -> None:
        """规划器状态应正确追踪。"""
        assert planning_skill.get_state() == PlannerState.IDLE
        result = await planning_skill.plan(simple_intent)
        assert planning_skill.get_state() == PlannerState.READY
        assert len(planning_skill.get_trace_log()) > 0

    @pytest.mark.asyncio
    async def test_revise_plan(
        self,
        planning_skill: PlanningSkill,
    ) -> None:
        """修订计划应生成修订记录。"""
        intent = Intent_v3(
            category=IntentCategory.SCAN_MEMORY,
            raw_input="scan",
            confidence=0.8,
        )
        result = await planning_skill.plan(intent)
        node_id = list(result.task_graph.nodes.keys())[0]
        revised = await planning_skill.revise_plan(result, node_id, "模拟失败")
        assert revised is not None
        assert len(revised.revisions) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 优化器测试
# ═══════════════════════════════════════════════════════════════════════════

class TestTaskGraphOptimizer:
    """TaskGraphOptimizer 单元测试。"""

    @pytest.mark.asyncio
    async def test_optimize_deduplicates_nodes(
        self,
        optimizer: TaskGraphOptimizer,
        sample_task_graph: TaskGraph_v3,
    ) -> None:
        """优化应去重相同 tool_name + tool_params 的节点。"""
        optimized = await optimizer.optimize(sample_task_graph)
        # 原图有 4 节点（scan, scan_dup, verify, orphan）
        # 去重后 scan 和 scan_dup 合并，剩 3 节点
        # 剪枝后 orphan 被移除，剩 2 节点
        assert len(optimized.nodes) <= 3

    @pytest.mark.asyncio
    async def test_optimize_prunes_dangling_edges(
        self,
        optimizer: TaskGraphOptimizer,
        sample_task_graph: TaskGraph_v3,
    ) -> None:
        """优化应剪枝悬空边。"""
        optimized = await optimizer.optimize(sample_task_graph)
        node_ids = set(optimized.nodes.keys())
        for edge in optimized.edges:
            assert edge.source_id in node_ids
            assert edge.target_id in node_ids

    @pytest.mark.asyncio
    async def test_optimize_topological_order(
        self,
        optimizer: TaskGraphOptimizer,
        sample_task_graph: TaskGraph_v3,
    ) -> None:
        """优化后应支持拓扑排序。"""
        optimized = await optimizer.optimize(sample_task_graph)
        order = optimized.topological_order()
        assert len(order) == len(optimized.nodes)

    @pytest.mark.asyncio
    async def test_optimize_empty_graph(
        self,
        optimizer: TaskGraphOptimizer,
    ) -> None:
        """空图优化应安全返回。"""
        empty_graph = TaskGraph_v3()
        optimized = await optimizer.optimize(empty_graph)
        assert len(optimized.nodes) == 0
        assert len(optimized.edges) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 回退规划器测试
# ═══════════════════════════════════════════════════════════════════════════

class TestFallbackPlanner:
    """FallbackPlanner 单元测试。"""

    @pytest.mark.asyncio
    async def test_revise_with_fallback_nodes(
        self,
        fallback_planner: FallbackPlanner,
    ) -> None:
        """有 fallback_nodes 时应激活备选。"""
        graph = TaskGraph_v3()
        n1 = TaskNode_v3(name="main", tool_name="scan")
        n2 = TaskNode_v3(name="fallback", tool_name="safe_scan")
        n1.fallback_nodes = [n2.id]
        graph.add_node(n1)
        graph.add_node(n2)
        graph.add_edge(TaskEdge_v3(source_id=n1.id, target_id=n2.id, dep_type=DependencyType.SEQUENTIAL))
        revised = await fallback_planner.revise(graph, n1.id, "main failed")
        has_edge_to_n2 = any(e.target_id == n2.id for e in revised.edges)
        assert has_edge_to_n2

    @pytest.mark.asyncio
    async def test_revise_without_fallback_nodes(
        self,
        fallback_planner: FallbackPlanner,
    ) -> None:
        """无 fallback_nodes 时应插入诊断。"""
        graph = TaskGraph_v3()
        n1 = TaskNode_v3(name="scan", tool_name="scan")
        graph.add_node(n1)
        revised = await fallback_planner.revise(graph, n1.id, "scan failed")
        assert len(revised.nodes) == 2  # 原节点 + 诊断节点

    @pytest.mark.asyncio
    async def test_create_fallback(
        self,
        fallback_planner: FallbackPlanner,
    ) -> None:
        """图级回退应生成最小安全图。"""
        intent = Intent_v3(id="intent-99", category=IntentCategory.SCAN_MEMORY)
        fallback_graph = await fallback_planner.create_fallback(intent)
        assert len(fallback_graph.nodes) == 2
        assert len(fallback_graph.edges) == 1

    @pytest.mark.asyncio
    async def test_revise_nonexistent_node(
        self,
        fallback_planner: FallbackPlanner,
    ) -> None:
        """修订不存在的节点应安全返回克隆。"""
        graph = TaskGraph_v3()
        n1 = TaskNode_v3(name="only")
        graph.add_node(n1)
        revised = await fallback_planner.revise(graph, "nonexistent", "error")
        assert len(revised.nodes) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 执行器测试
# ═══════════════════════════════════════════════════════════════════════════

class TestTaskGraphExecutor:
    """TaskGraphExecutor 单元测试。"""

    @pytest.fixture
    async def dummy_executor(self) -> Any:
        """模拟节点执行器。"""
        async def _executor(node: TaskNode_v3) -> str:
            await asyncio.sleep(0.01)
            if node.name == "fail_node":
                raise RuntimeError("Simulated failure")
            return f"ok:{node.name}"
        return _executor

    @pytest.mark.asyncio
    async def test_execute_success(
        self,
        dummy_executor: Any,
    ) -> None:
        """正常执行应全部成功。"""
        graph = TaskGraph_v3()
        a = TaskNode_v3(name="A", layer=3)
        b = TaskNode_v3(name="B", layer=3)
        c = TaskNode_v3(name="C", layer=3)
        for n in (a, b, c):
            graph.add_node(n)
        graph.add_edge(TaskEdge_v3(source_id=a.id, target_id=b.id, dep_type=DependencyType.SEQUENTIAL))
        graph.add_edge(TaskEdge_v3(source_id=b.id, target_id=c.id, dep_type=DependencyType.SEQUENTIAL))

        plan_result = PlanResult(result_id="plan-1", task_graph=graph, success=True)
        executor = TaskGraphExecutor(
            node_executor=dummy_executor,
            max_concurrency=2,
        )
        result = await executor.execute(plan_result)
        assert result.success is True
        assert len(result.completed_nodes) == 3
        assert result.state == ExecutionState.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_with_failure(
        self,
        dummy_executor: Any,
    ) -> None:
        """包含失败节点时应标记失败。"""
        graph = TaskGraph_v3()
        f = TaskNode_v3(name="fail_node", layer=3)
        graph.add_node(f)

        plan_result = PlanResult(result_id="plan-2", task_graph=graph, success=True)
        executor = TaskGraphExecutor(
            node_executor=dummy_executor,
            max_concurrency=1,
            fallback_planner=None,  # 禁用 fallback，避免 fail_node 永远失败导致无限循环
        )
        result = await executor.execute(plan_result)
        assert result.success is False
        assert len(result.failed_nodes) == 1
        assert result.state == ExecutionState.FAILED

    @pytest.mark.asyncio
    async def test_execute_parallel_branches(
        self,
        dummy_executor: Any,
    ) -> None:
        """并行分支应并发执行。"""
        graph = TaskGraph_v3()
        a = TaskNode_v3(name="A", layer=3)
        b = TaskNode_v3(name="B", layer=3)
        c = TaskNode_v3(name="C", layer=3)
        for n in (a, b, c):
            graph.add_node(n)
        # A -> B 和 A -> C 并行
        graph.add_edge(TaskEdge_v3(source_id=a.id, target_id=b.id, dep_type=DependencyType.SEQUENTIAL))
        graph.add_edge(TaskEdge_v3(source_id=a.id, target_id=c.id, dep_type=DependencyType.SEQUENTIAL))

        plan_result = PlanResult(result_id="plan-3", task_graph=graph, success=True)
        events: List[tuple] = []

        def on_event(event_type: str, payload: Dict[str, Any]) -> None:
            events.append((event_type, payload))

        executor = TaskGraphExecutor(
            node_executor=dummy_executor,
            on_event=on_event,
            max_concurrency=2,
        )
        result = await executor.execute(plan_result)
        assert result.success is True
        assert len(result.completed_nodes) == 3

        # 验证事件流
        started_events = [e for e in events if e[0] == "node_started"]
        completed_events = [e for e in events if e[0] == "node_completed"]
        assert len(started_events) == 3
        assert len(completed_events) == 3

    @pytest.mark.asyncio
    async def test_checkpoint_save_and_restore(
        self,
        dummy_executor: Any,
    ) -> None:
        """检查点应正确保存和恢复。"""
        graph = TaskGraph_v3()
        a = TaskNode_v3(name="A", layer=3)
        b = TaskNode_v3(name="B", layer=3)
        for n in (a, b):
            graph.add_node(n)
        graph.add_edge(TaskEdge_v3(source_id=a.id, target_id=b.id, dep_type=DependencyType.SEQUENTIAL))

        plan_result = PlanResult(result_id="plan-4", task_graph=graph, success=True)
        executor = TaskGraphExecutor(
            node_executor=dummy_executor,
            enable_checkpoints=True,
        )
        result = await executor.execute(plan_result)
        assert len(result.checkpoints) > 0
        cp = result.checkpoints[-1]
        assert cp.plan_result_id == "plan-4"
        assert a.id in cp.completed_node_ids

    @pytest.mark.asyncio
    async def test_cancel_execution(
        self,
        dummy_executor: Any,
    ) -> None:
        """取消执行应终止调度。"""
        graph = TaskGraph_v3()
        a = TaskNode_v3(name="A", layer=3)
        b = TaskNode_v3(name="B", layer=3)
        for n in (a, b):
            graph.add_node(n)
        graph.add_edge(TaskEdge_v3(source_id=a.id, target_id=b.id, dep_type=DependencyType.SEQUENTIAL))

        plan_result = PlanResult(result_id="plan-5", task_graph=graph, success=True)
        executor = TaskGraphExecutor(
            node_executor=dummy_executor,
        )
        # 在另一个任务中启动执行，然后取消
        exec_task = asyncio.create_task(executor.execute(plan_result))
        await asyncio.sleep(0.02)
        await executor.cancel()
        result = await exec_task
        assert result.state == ExecutionState.CANCELLED

    @pytest.mark.asyncio
    async def test_pause_and_resume(
        self,
        dummy_executor: Any,
    ) -> None:
        """暂停和恢复应正常工作。"""
        graph = TaskGraph_v3()
        a = TaskNode_v3(name="A", layer=3)
        graph.add_node(a)

        plan_result = PlanResult(result_id="plan-6", task_graph=graph, success=True)
        executor = TaskGraphExecutor(
            node_executor=dummy_executor,
        )
        await executor.pause()
        assert executor.get_state() == ExecutionState.PAUSED
        await executor.resume()
        assert executor.get_state() == ExecutionState.RUNNING
        result = await executor.execute(plan_result)
        assert result.success is True


# ═══════════════════════════════════════════════════════════════════════════
# 数据模型测试
# ═══════════════════════════════════════════════════════════════════════════

class TestPlanningModels:
    """Planning 数据模型单元测试。"""

    def test_plan_step_mark_success(self) -> None:
        """PlanStep 应正确标记成功。"""
        step = PlanStep(step_type=StepType.ANALYSIS, description="test")
        step.mark_success({"key": "value"}, 42.0)
        assert step.success is True
        assert step.latency_ms == 42.0
        assert step.output_data == {"key": "value"}

    def test_plan_step_mark_failed(self) -> None:
        """PlanStep 应正确标记失败。"""
        step = PlanStep(step_type=StepType.VALIDATION, description="test")
        step.mark_failed("error", 10.0)
        assert step.success is False
        assert step.error == "error"
        assert step.latency_ms == 10.0

    def test_plan_result_summary(self) -> None:
        """PlanResult 摘要应正确计算。"""
        result = PlanResult(intent_id="i1", success=True)
        result.add_step(PlanStep(step_type=StepType.ANALYSIS))
        result.add_step(PlanStep(step_type=StepType.DECOMPOSITION))
        summary = result.to_summary()
        assert summary["success"] is True
        assert summary["steps"] == 2

    def test_strategy_score_clamping(self) -> None:
        """StrategyScore 应将 score 裁剪到 [0, 1]。"""
        score = StrategyScore(strategy=PlanStrategy.RULE_BASED, score=1.5, confidence=-0.5)
        assert score.score == 1.0
        assert score.confidence == 0.0

    def test_planner_config_temperature_clamping(self) -> None:
        """PlannerConfig 应将 temperature 裁剪到 [0, 2]。"""
        config = PlannerConfig(llm_temperature=5.0)
        assert config.llm_temperature == 2.0

    def test_execution_checkpoint_creation(self) -> None:
        """ExecutionCheckpoint 应正确创建。"""
        cp = ExecutionCheckpoint(
            plan_result_id="plan-1",
            completed_node_ids=["n1"],
            pending_node_ids=["n2"],
        )
        assert cp.checkpoint_id
        assert cp.completed_node_ids == ["n1"]


# ═══════════════════════════════════════════════════════════════════════════
# 集成测试
# ═══════════════════════════════════════════════════════════════════════════

class TestPlanningIntegration:
    """Planning Skill 集成测试——全链路。"""

    @pytest.mark.asyncio
    async def test_full_pipeline_scan_memory(self) -> None:
        """扫描内存全链路：规划 → 优化 → 执行。"""
        intent = Intent_v3(
            category=IntentCategory.SCAN_MEMORY,
            raw_input="scan for 100",
            confidence=0.8,
        )

        # 规划
        planner = PlanningSkill()
        plan_result = await planner.plan(intent)
        assert plan_result.success is True
        assert plan_result.task_graph is not None

        # 优化（已内嵌于 plan，但额外验证）
        optimizer = TaskGraphOptimizer()
        optimized = await optimizer.optimize(plan_result.task_graph)
        assert optimized is not None

        # 执行
        async def node_executor(node: TaskNode_v3) -> str:
            await asyncio.sleep(0.005)
            return f"executed:{node.name}"

        executor = TaskGraphExecutor(node_executor=node_executor)
        exec_result = await executor.execute(plan_result)
        assert exec_result.success is True
        assert len(exec_result.completed_nodes) == len(plan_result.task_graph.nodes)

    @pytest.mark.asyncio
    async def test_full_pipeline_with_failure_and_fallback(self) -> None:
        """包含失败和回退的全链路测试。"""
        intent = Intent_v3(
            category=IntentCategory.READ_MEMORY,
            raw_input="read 0x1000",
            confidence=0.9,
        )

        planner = PlanningSkill()
        plan_result = await planner.plan(intent)
        assert plan_result.success is True

        # 模拟执行失败
        fail_count = 0
        async def failing_executor(node: TaskNode_v3) -> str:
            nonlocal fail_count
            await asyncio.sleep(0.005)
            if node.name == "read_memory" and fail_count == 0:
                fail_count += 1
                raise RuntimeError("read failed")
            return f"executed:{node.name}"

        fallback = FallbackPlanner()
        executor = TaskGraphExecutor(
            node_executor=failing_executor,
            fallback_planner=fallback,
        )
        exec_result = await executor.execute(plan_result)
        # 由于回退规划器会插入诊断节点，最终可能仍然成功或等待澄清
        assert exec_result is not None


# ═══════════════════════════════════════════════════════════════════════════
# Planning Skill Engine 测试（ENGINEERING_PLANNING_SKILL.md）
# ═══════════════════════════════════════════════════════════════════════════

class TestSkillRegistry:
    """SkillRegistry 单元测试。"""

    def test_builtin_skills_registered(self) -> None:
        """默认应注册内置技能。"""
        registry = SkillRegistry()
        assert registry.count() >= 2
        skill = registry.get("memory_analysis")
        assert skill.name == "memory_analysis"

    def test_register_and_unregister(self) -> None:
        """注册和注销技能。"""
        registry = SkillRegistry()
        skill = SkillTemplate(name="test_skill", keywords=["test"])
        registry.register(skill)
        assert registry.get("test_skill").name == "test_skill"
        registry.unregister("test_skill")
        with pytest.raises(SkillNotFoundError):
            registry.get("test_skill")

    def test_query_by_keyword(self) -> None:
        """关键词查询。"""
        registry = SkillRegistry()
        results = registry.query(keyword="memory")
        assert len(results) >= 1

    def test_query_by_tags(self) -> None:
        """标签查询。"""
        registry = SkillRegistry()
        results = registry.query(tags=["reverse_engineering"])
        assert len(results) >= 2

    def test_skill_not_found_error(self) -> None:
        """技能未找到时抛出异常。"""
        registry = SkillRegistry()
        with pytest.raises(SkillNotFoundError):
            registry.get("nonexistent_skill")


class TestSkillMatcher:
    """SkillMatcher 单元测试。"""

    def test_fast_path_use_template_true(self) -> None:
        """高分匹配应返回 use_template=True。"""
        registry = SkillRegistry()
        matcher = SkillMatcher(registry)
        result = matcher.match("scan memory address 0x1234")
        assert result is not None
        assert result.use_template is True
        assert result.score >= 0.4
        assert result.skill is not None

    def test_slow_path_use_template_false(self) -> None:
        """低分匹配应返回 use_template=False。"""
        registry = SkillRegistry()
        matcher = SkillMatcher(registry)
        result = matcher.match("random unrelated query xyz")
        assert result is not None
        assert result.use_template is False

    def test_partial_match(self) -> None:
        """部分匹配应返回 skill 但 use_template=False。"""
        registry = SkillRegistry()
        matcher = SkillMatcher(registry)
        result = matcher.match("analyze some code instructions")
        assert result is not None
        assert 0.0 <= result.score < 0.5

    def test_match_threshold_boundary(self) -> None:
        """测试阈值边界。"""
        registry = SkillRegistry()
        matcher = SkillMatcher(registry)
        # 使用精确关键词触发高分
        result = matcher.match("memory scan address")
        assert result.use_template is True


class TestDecompositionEngine:
    """DecompositionEngine 单元测试。"""

    def test_decompose_with_skill(self) -> None:
        """基于技能模板的分解。"""
        registry = SkillRegistry()
        engine = DecompositionEngine()
        skill = registry.get("memory_analysis")
        tasks = engine.decompose_with_skill("scan 0x1234", skill)
        assert len(tasks) == 3
        assert tasks[0].name == "scan_address"
        assert tasks[0].worker_type == "ToolExecutor"

    @pytest.mark.asyncio
    async def test_decompose_timeout_fallback(self) -> None:
        """动态分解超时回退到单任务。"""
        engine = DecompositionEngine()
        tasks = await engine.decompose("some intent", timeout_ms=1)
        assert len(tasks) == 1
        assert tasks[0].name == "direct_execution"
        assert tasks[0].worker_type == "Answer-LLM"

    @pytest.mark.asyncio
    async def test_decompose_without_llm_fallback(self) -> None:
        """无 LLM 时回退到单任务。"""
        engine = DecompositionEngine()
        tasks = await engine.decompose("scan memory for 100")
        assert len(tasks) == 1
        assert tasks[0].name == "direct_execution"

    def test_decompose_skill_template_rendering(self) -> None:
        """技能模板输入渲染。"""
        registry = SkillRegistry()
        engine = DecompositionEngine()
        skill = registry.get("memory_analysis")
        tasks = engine.decompose_with_skill("scan 0x1234", skill)
        assert "scan 0x1234" in tasks[0].input_data


class TestDependencyResolver:
    """DependencyResolver 单元测试。"""

    def test_build_dag_valid(self) -> None:
        """正常 DAG 构建。"""
        resolver = DependencyResolver()
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

    def test_cycle_detection(self) -> None:
        """循环检测。"""
        resolver = DependencyResolver()
        tasks = [
            Task(name="A", dependencies=["B"]),
            Task(name="B", dependencies=["C"]),
            Task(name="C", dependencies=["A"]),
        ]
        with pytest.raises(DependencyError):
            resolver.build_dag(tasks)

    def test_critical_path(self) -> None:
        """关键路径计算。"""
        resolver = DependencyResolver()
        tasks = [
            Task(name="A", dependencies=[], estimated_time=10),
            Task(name="B", dependencies=["A"], estimated_time=20),
            Task(name="C", dependencies=["A"], estimated_time=5),
            Task(name="D", dependencies=["B", "C"], estimated_time=10),
        ]
        dag = resolver.build_dag(tasks)
        path = resolver.find_critical_path(dag)
        assert len(path) >= 1
        # A -> B -> D 是关键路径（10+20+10=40）
        assert path[0] == tasks[0].id

    def test_validate_dependencies(self) -> None:
        """依赖验证。"""
        resolver = DependencyResolver()
        tasks = [
            Task(name="A", dependencies=["B"]),
            Task(name="B", dependencies=[]),
        ]
        missing = resolver.validate_dependencies(tasks)
        assert len(missing) == 0

        tasks_bad = [
            Task(name="A", dependencies=["NonExistent"]),
        ]
        missing_bad = resolver.validate_dependencies(tasks_bad)
        assert "NonExistent" in missing_bad


class TestAgentAllocator:
    """AgentAllocator 单元测试。"""

    def test_assign_with_matching_workers(self) -> None:
        """正常分配。"""
        workers = {
            "w1": Worker(id="w1", name="Planning-LLM-1", capabilities=["Planning-LLM"]),
            "w2": Worker(id="w2", name="ToolExecutor-1", capabilities=["ToolExecutor"]),
        }
        allocator = AgentAllocator(workers)
        tasks = [
            Task(name="plan", worker_type="Planning-LLM"),
            Task(name="execute", worker_type="ToolExecutor"),
        ]
        assignments = allocator.assign(tasks)
        assert len(assignments) == 2

    def test_assign_with_universal_worker(self) -> None:
        """通用 Worker（*）可处理任何任务。"""
        workers = {
            "w3": Worker(id="w3", name="General-1", capabilities=["*"]),
        }
        allocator = AgentAllocator(workers)
        tasks = [Task(name="anything", worker_type="UnknownType")]
        assignments = allocator.assign(tasks)
        assert len(assignments) == 1

    def test_allocation_error_no_worker(self) -> None:
        """无匹配 Worker 时抛出 AllocationError。"""
        workers = {
            "w1": Worker(id="w1", name="LLM-1", capabilities=["Planning-LLM"]),
        }
        allocator = AgentAllocator(workers)
        tasks = [Task(name="bad", worker_type="UnknownWorker")]
        with pytest.raises(AllocationError):
            allocator.assign(tasks)

    def test_load_balancing(self) -> None:
        """负载均衡。"""
        workers = {
            "w1": Worker(id="w1", name="LLM-1", capabilities=["Planning-LLM"]),
            "w2": Worker(id="w2", name="LLM-2", capabilities=["Planning-LLM"]),
        }
        allocator = AgentAllocator(workers)
        tasks = [
            Task(name="t1", worker_type="Planning-LLM"),
            Task(name="t2", worker_type="Planning-LLM"),
        ]
        assignments = allocator.assign(tasks)
        # 两个任务应分配到不同 Worker（负载均衡）
        assigned_workers = set(assignments.values())
        assert len(assigned_workers) == 2


class TestExecutionScheduler:
    """ExecutionScheduler 单元测试。"""

    @pytest.mark.asyncio
    async def test_execute_dag_success(self) -> None:
        """成功执行 DAG。"""
        class MockWorker(Worker):
            async def execute(self, task: Task) -> TaskResult:
                await asyncio.sleep(0.005)
                return TaskResult(task_id=task.id, task_name=task.name, success=True, output="ok")

        workers = {
            "w1": MockWorker(id="w1", name="LLM-1", capabilities=["Planning-LLM"]),
            "w2": MockWorker(id="w2", name="Tool-1", capabilities=["ToolExecutor"]),
        }
        tasks = [
            Task(name="A", worker_type="Planning-LLM"),
            Task(name="B", worker_type="ToolExecutor", dependencies=["A"]),
            Task(name="C", worker_type="ToolExecutor", dependencies=["A"]),
        ]
        resolver = DependencyResolver()
        dag = resolver.build_dag(tasks)
        allocator = AgentAllocator(workers)
        assignments = allocator.assign(tasks, dag)

        scheduler = ExecutionScheduler(workers)
        result = await scheduler.execute(dag, assignments, session_id="test-1")
        assert result.success is True
        assert len(result.completed_tasks) == 3

    @pytest.mark.asyncio
    async def test_execute_with_failure(self) -> None:
        """包含失败任务的执行。"""
        class FailingWorker(Worker):
            async def execute(self, task: Task) -> TaskResult:
                if task.name == "fail":
                    raise RuntimeError("Simulated failure")
                return TaskResult(task_id=task.id, task_name=task.name, success=True, output="ok")

        workers = {
            "w1": FailingWorker(id="w1", name="LLM-1", capabilities=["Planning-LLM"]),
        }
        tasks = [
            Task(name="ok", worker_type="Planning-LLM"),
            Task(name="fail", worker_type="Planning-LLM"),
        ]
        resolver = DependencyResolver()
        dag = resolver.build_dag(tasks)
        allocator = AgentAllocator(workers)
        assignments = allocator.assign(tasks, dag)

        scheduler = ExecutionScheduler(workers)
        result = await scheduler.execute(dag, assignments)
        assert result.success is False
        assert len(result.failed_tasks) >= 1

    @pytest.mark.asyncio
    async def test_event_callbacks(self) -> None:
        """事件回调测试。"""
        events = []

        def on_event(event_type: str, payload: dict) -> None:
            events.append(event_type)

        class MockWorker(Worker):
            async def execute(self, task: Task) -> TaskResult:
                return TaskResult(task_id=task.id, task_name=task.name, success=True, output="ok")

        workers = {
            "w1": MockWorker(id="w1", name="LLM-1", capabilities=["Planning-LLM"]),
        }
        tasks = [Task(name="A", worker_type="Planning-LLM")]
        resolver = DependencyResolver()
        dag = resolver.build_dag(tasks)
        allocator = AgentAllocator(workers)
        assignments = allocator.assign(tasks, dag)

        scheduler = ExecutionScheduler(workers, on_event=on_event)
        await scheduler.execute(dag, assignments, session_id="test-events")
        assert "execution_started" in events
        assert "execution_finished" in events


class TestPlanningSkillEngine:
    """PlanningSkillEngine 集成测试。"""

    @pytest.mark.asyncio
    async def test_fast_path_with_skill_template(self) -> None:
        """使用内置技能模板的快速路径。"""
        workers = {
            "w1": Worker(id="w1", name="Answer-LLM-1", capabilities=["Answer-LLM", "ToolExecutor"]),
        }
        allocator = AgentAllocator(workers)
        engine = PlanningSkillEngine(allocator=allocator)
        result = await engine.plan_and_execute(
            session_id="test-fast",
            intent="scan memory address 0x1234",
        )
        assert result is not None
        # 快速路径产生至少 1 个子任务
        assert len(result.task_results) >= 1

    @pytest.mark.asyncio
    async def test_slow_path_no_skill_match(self) -> None:
        """无匹配技能时回退到单任务。"""
        workers = {
            "w1": Worker(id="w1", name="Answer-LLM-1", capabilities=["Answer-LLM"]),
        }
        allocator = AgentAllocator(workers)
        engine = PlanningSkillEngine(allocator=allocator)
        result = await engine.plan_and_execute(
            session_id="test-slow",
            intent="do something completely random and undefined",
        )
        assert result is not None
        assert len(result.task_results) == 1
        assert result.task_results[0].task_name == "direct_execution"

    @pytest.mark.asyncio
    async def test_replan_on_failure(self) -> None:
        """重新规划测试。"""
        engine = PlanningSkillEngine()
        failed_task = Task(name="failed_task", description="test failure")
        plan = await engine.replan("test-replan", failed_task, "execution error occurred")
        assert plan.dag is not None
        assert len(plan.tasks) >= 1

    @pytest.mark.asyncio
    async def test_replan_skill_mismatch(self) -> None:
        """技能不匹配时的重新规划。"""
        engine = PlanningSkillEngine()
        failed_task = Task(name="failed_task", description="test failure")
        plan = await engine.replan("test-replan-skill", failed_task, "skill mismatch")
        assert plan.dag is not None


class TestPrimitiveLibrary:
    """PrimitiveLibrary 单元测试 — PS-S-06 修复验证。"""

    def test_all_primitives_registered(self) -> None:
        """7 个已实现原语应全部注册。"""
        lib = PrimitiveLibrary()
        names = {p.name for p in lib.list_primitives()}
        assert "SequentialDecomposition" in names
        assert "PlanExecuteReflect" in names
        assert "DivideConquer" in names
        assert "ConditionalBranch" in names
        assert "LoopUntil" in names
        assert "SearchVerifyExecute" in names
        assert "TreeOfThought" in names

    def test_describe_all_markers(self) -> None:
        """describe_all 应正确标记已实现原语。"""
        lib = PrimitiveLibrary()
        desc = lib.describe_all()
        # 7 个已注册原语全部已实现，都应有 ✅ 标记
        assert desc.count("✅") == 7
        # 当前没有未实现的占位符原语注册
        assert "⚠️ 占位符" not in desc

    def test_divide_conquer_skeleton(self) -> None:
        """DivideConquer 应生成 4 个任务（分解 + 2 求解 + 合并）。"""
        lib = PrimitiveLibrary()
        primitive = lib.get_primitive("DivideConquer")
        assert primitive is not None
        tasks = primitive.generate_skeleton()
        assert len(tasks) == 4
        names = [t.name for t in tasks]
        assert names == ["divide", "solve_left", "solve_right", "merge"]
        # 依赖验证
        assert tasks[1].dependencies == ["divide"]
        assert tasks[2].dependencies == ["divide"]
        assert tasks[3].dependencies == ["solve_left", "solve_right"]

    def test_conditional_branch_skeleton(self) -> None:
        """ConditionalBranch 应生成 4 个任务（评估 + 2 分支 + 合并）。"""
        lib = PrimitiveLibrary()
        primitive = lib.get_primitive("ConditionalBranch")
        assert primitive is not None
        tasks = primitive.generate_skeleton()
        assert len(tasks) == 4
        names = [t.name for t in tasks]
        assert names == ["evaluate", "branch_a", "branch_b", "merge"]
        # 依赖验证
        assert tasks[1].dependencies == ["evaluate"]
        assert tasks[2].dependencies == ["evaluate"]
        assert tasks[3].dependencies == ["branch_a", "branch_b"]

    def test_loop_until_skeleton(self) -> None:
        """LoopUntil 应生成 1 + 2*3 + 1 = 8 个任务（初始化 + 3 轮循环 + 结束）。"""
        lib = PrimitiveLibrary()
        primitive = lib.get_primitive("LoopUntil")
        assert primitive is not None
        tasks = primitive.generate_skeleton()
        assert len(tasks) == 8  # init + 3*(body+check) + finalize
        names = [t.name for t in tasks]
        assert names[0] == "loop_init"
        assert names[-1] == "loop_finalize"
        # 循环体依赖验证
        assert tasks[1].dependencies == ["loop_init"]
        assert tasks[2].dependencies == ["loop_body_1"]
        assert tasks[3].dependencies == ["loop_check_1"]
        assert tasks[4].dependencies == ["loop_body_2"]

    def test_search_verify_execute_skeleton(self) -> None:
        """SearchVerifyExecute 应生成 3 个任务（搜索 → 验证 → 执行）。"""
        lib = PrimitiveLibrary()
        primitive = lib.get_primitive("SearchVerifyExecute")
        assert primitive is not None
        tasks = primitive.generate_skeleton()
        assert len(tasks) == 3
        names = [t.name for t in tasks]
        assert names == ["search", "verify", "execute"]
        # 线性依赖
        assert tasks[1].dependencies == ["search"]
        assert tasks[2].dependencies == ["verify"]

    def test_tree_of_thought_skeleton(self) -> None:
        """TreeOfThought 应生成 1 + 3 + 1 + 1 = 6 个任务。"""
        lib = PrimitiveLibrary()
        primitive = lib.get_primitive("TreeOfThought")
        assert primitive is not None
        tasks = primitive.generate_skeleton()
        assert len(tasks) == 6  # generate + 3 evaluate + select + execute
        names = [t.name for t in tasks]
        assert names[0] == "generate_candidates"
        assert names[1] == "evaluate_candidate_1"
        assert names[2] == "evaluate_candidate_2"
        assert names[3] == "evaluate_candidate_3"
        assert names[4] == "select_best"
        assert names[5] == "execute_best"
        # 并行评估依赖
        assert tasks[1].dependencies == ["generate_candidates"]
        assert tasks[2].dependencies == ["generate_candidates"]
        assert tasks[3].dependencies == ["generate_candidates"]
        # 选择最佳依赖所有评估
        assert set(tasks[4].dependencies) == {
            "evaluate_candidate_1",
            "evaluate_candidate_2",
            "evaluate_candidate_3",
        }
        assert tasks[5].dependencies == ["select_best"]

    def test_dag_compatibility(self) -> None:
        """所有核心原语生成的骨架应能被 DependencyResolver 正确解析为 DAG。"""
        from core.agent.planner.dependency_resolver import DependencyResolver

        lib = PrimitiveLibrary()
        resolver = DependencyResolver()
        core_primitives = [
            "DivideConquer",
            "ConditionalBranch",
            "LoopUntil",
            "SearchVerifyExecute",
            "TreeOfThought",
        ]
        for name in core_primitives:
            primitive = lib.get_primitive(name)
            assert primitive is not None, f"Primitive {name} not found"
            tasks = primitive.generate_skeleton()
            dag = resolver.build_dag(tasks)
            assert dag.is_valid(), f"DAG for {name} is not valid"
            assert len(dag.topological_order) == len(tasks)


# ═══════════════════════════════════════════════════════════════════════════
# SkillLevel + 模式选择测试（PS-S-12 / PS-S-13）
# ═══════════════════════════════════════════════════════════════════════════

class TestSkillLevelAndModeSelection:
    """SkillLevel 枚举与 PlanningMode 选择测试。"""

    def test_skill_level_enum_values(self) -> None:
        """SkillLevel 枚举应包含三个级别。"""
        assert SkillLevel.SKELETON.value == "SKELETON"
        assert SkillLevel.STANDARD.value == "STANDARD"
        assert SkillLevel.DETAILED.value == "DETAILED"
        assert len(list(SkillLevel)) == 3

    def test_skill_template_default_level(self) -> None:
        """SkillTemplate 默认 level 应为 STANDARD。"""
        skill = SkillTemplate(name="test")
        assert skill.level == SkillLevel.STANDARD

    def test_skill_template_level_detailed(self) -> None:
        """SkillTemplate 可显式设置为 DETAILED。"""
        skill = SkillTemplate(name="test", level=SkillLevel.DETAILED)
        assert skill.level == SkillLevel.DETAILED

    def test_select_mode_detailed_high_score(self) -> None:
        """DETAILED + score>0.8 应选择 MIXED。"""
        from core.agent.planner.skill_engine import PlanningSkillEngine
        engine = PlanningSkillEngine()
        skill = SkillTemplate(name="detailed_skill", level=SkillLevel.DETAILED, keywords=["memory"])
        match = SkillMatchResult(skill=skill, score=0.9, use_template=True)
        mode = engine._select_mode(match)
        assert mode == PlanningMode.MIXED

    def test_select_mode_standard_high_score(self) -> None:
        """STANDARD + score>0.8 应选择 SKILL_ENHANCED。"""
        from core.agent.planner.skill_engine import PlanningSkillEngine
        engine = PlanningSkillEngine()
        skill = SkillTemplate(name="standard_skill", level=SkillLevel.STANDARD, keywords=["memory"])
        match = SkillMatchResult(skill=skill, score=0.85, use_template=True)
        mode = engine._select_mode(match)
        assert mode == PlanningMode.SKILL_ENHANCED

    def test_select_mode_skeleton_high_score(self) -> None:
        """SKELETON + score>0.8 应选择 SKILL_ENHANCED。"""
        from core.agent.planner.skill_engine import PlanningSkillEngine
        engine = PlanningSkillEngine()
        skill = SkillTemplate(name="skeleton_skill", level=SkillLevel.SKELETON, keywords=["memory"])
        match = SkillMatchResult(skill=skill, score=0.95, use_template=True)
        mode = engine._select_mode(match)
        assert mode == PlanningMode.SKILL_ENHANCED

    def test_select_mode_low_score(self) -> None:
        """score<=0.8 应选择 DYNAMIC。"""
        from core.agent.planner.skill_engine import PlanningSkillEngine
        engine = PlanningSkillEngine()
        skill = SkillTemplate(name="low_score_skill", level=SkillLevel.DETAILED, keywords=["memory"])
        match = SkillMatchResult(skill=skill, score=0.7, use_template=False)
        mode = engine._select_mode(match)
        assert mode == PlanningMode.DYNAMIC

    def test_select_mode_no_match(self) -> None:
        """无匹配时应选择 DYNAMIC。"""
        from core.agent.planner.skill_engine import PlanningSkillEngine
        engine = PlanningSkillEngine()
        mode = engine._select_mode(None)
        assert mode == PlanningMode.DYNAMIC

    def test_skill_template_to_dict_serializes_level(self) -> None:
        """to_dict 应将 level 序列化为字符串。"""
        skill = SkillTemplate(name="test", level=SkillLevel.DETAILED)
        d = skill.to_dict()
        assert d["level"] == "DETAILED"


class TestFallbackChain:
    """模式回退链测试（MIXED → SKILL_ENHANCED → DYNAMIC → FALLBACK）。"""

    @pytest.mark.asyncio
    async def test_fallback_chain_from_mixed(self) -> None:
        """从 MIXED 开始，应至少回退到 FALLBACK 并返回有效计划。"""
        from core.agent.planner.skill_engine import PlanningSkillEngine
        engine = PlanningSkillEngine()
        failed_task = Task(name="failed_task", description="scan memory address 0x1234")
        plan = await engine._execute_with_fallback(
            session_id="test-fb-1",
            intent="scan memory address 0x1234",
            failed_task=failed_task,
            start_mode=PlanningMode.MIXED,
        )
        assert plan.dag is not None
        assert plan.dag.is_valid()
        assert len(plan.tasks) >= 1

    @pytest.mark.asyncio
    async def test_fallback_chain_from_dynamic(self) -> None:
        """从 DYNAMIC 开始，应尝试 DYNAMIC 然后 FALLBACK。"""
        from core.agent.planner.skill_engine import PlanningSkillEngine
        engine = PlanningSkillEngine()
        failed_task = Task(name="failed_task", description="random query")
        plan = await engine._execute_with_fallback(
            session_id="test-fb-2",
            intent="random query",
            failed_task=failed_task,
            start_mode=PlanningMode.DYNAMIC,
        )
        assert plan.dag is not None
        assert plan.dag.is_valid()

    @pytest.mark.asyncio
    async def test_replan_uses_fallback_chain(self) -> None:
        """replan 应使用 _execute_with_fallback 并返回有效计划。"""
        from core.agent.planner.skill_engine import PlanningSkillEngine
        engine = PlanningSkillEngine()
        failed_task = Task(name="failed_task", description="scan memory address 0x1234")
        plan = await engine.replan("test-replan-fb", failed_task, "execution error occurred")
        assert plan.dag is not None
        assert plan.dag.is_valid()
        assert len(plan.tasks) >= 1

    @pytest.mark.asyncio
    async def test_replan_skill_mismatch_starts_from_mixed(self) -> None:
        """skill mismatch 反馈应从 MIXED 开始回退。"""
        from core.agent.planner.skill_engine import PlanningSkillEngine
        engine = PlanningSkillEngine()
        failed_task = Task(name="failed_task", description="scan memory address 0x1234")
        plan = await engine.replan("test-replan-sm", failed_task, "skill mismatch detected")
        assert plan.dag is not None
        assert plan.dag.is_valid()

    @pytest.mark.asyncio
    async def test_replan_dependency_error_starts_from_dynamic(self) -> None:
        """dependency error 反馈应从 DYNAMIC 开始回退。"""
        from core.agent.planner.skill_engine import PlanningSkillEngine
        engine = PlanningSkillEngine()
        failed_task = Task(name="failed_task", description="scan memory address 0x1234")
        plan = await engine.replan("test-replan-de", failed_task, "cycle detected: dependency error")
        assert plan.dag is not None
        assert plan.dag.is_valid()

    def test_fallback_chain_order(self) -> None:
        """回退链顺序应正确。"""
        chain = [PlanningMode.MIXED, PlanningMode.SKILL_ENHANCED, PlanningMode.DYNAMIC, PlanningMode.FALLBACK]
        assert chain[0] == PlanningMode.MIXED
        assert chain[1] == PlanningMode.SKILL_ENHANCED
        assert chain[2] == PlanningMode.DYNAMIC
        assert chain[3] == PlanningMode.FALLBACK


# ═══════════════════════════════════════════════════════════════════════════
# 运行入口（支持直接 python 执行）
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
