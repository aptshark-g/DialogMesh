# -*- coding: utf-8 -*-
"""
core/agent/v3_0/planning/__init__.py
────────────────────────────────────
DialogMesh Agent v3.0 — Planning Skill 模块入口。

用途：
- 统一导出 Planning Skill 的公共 API（Planner, StrategySelector, Optimizer 等）。
- 提供 ``PlanningSkill`` 主类作为上层系统的直接入口。
- 兼容 ``from core.agent.v3_0.planning import PlanningSkill`` 的简洁导入。

版本：3.0.0
"""

from __future__ import annotations

from core.agent.v3_0.planning.agent_allocator import AgentAllocator
from core.agent.v3_0.planning.decomposition import DecompositionEngine
from core.agent.v3_0.planning.dependency_resolver import DependencyResolver
from core.agent.v3_0.planning.fallback import FallbackPlanner
from core.agent.v3_0.planning.models import (
    ConditionalBranch,
    DivideConquer,
    ExecutionPlan,
    LoopUntil,
    PlannerConfig,
    PlannerState,
    PlanResult,
    PlanRevision,
    PlanStep,
    PlanStrategy,
    PrimitiveLibrary,
    RetryPolicy,
    SearchVerifyExecute,
    SequentialDecomposition,
    SkillMatchResult,
    SkillTemplate,
    SubtaskTemplate,
    Task,
    TaskDAG,
    TaskResult,
    TreeOfThought,
    Worker,
)
from core.agent.v3_0.planning.optimizer import TaskGraphOptimizer
from core.agent.v3_0.planning.planner import PlanningSkill
from core.agent.v3_0.planning.scheduler import ExecutionScheduler, ExecutionResult
from core.agent.v3_0.planning.skill_engine import PlanningSkillEngine
from core.agent.v3_0.planning.skill_matcher import SkillMatcher
from core.agent.v3_0.planning.skill_registry import SkillRegistry
from core.agent.v3_0.planning.strategy_selector import StrategySelector

__all__ = [
    # 旧版 API
    "PlanningSkill",
    "StrategySelector",
    "TaskGraphOptimizer",
    "FallbackPlanner",
    "PlanStrategy",
    "PlannerConfig",
    "PlannerState",
    "PlanResult",
    "PlanStep",
    "PlanRevision",
    # 新版 Planning Skill Engine
    "PlanningSkillEngine",
    "SkillRegistry",
    "SkillMatcher",
    "DecompositionEngine",
    "AgentAllocator",
    "DependencyResolver",
    "ExecutionScheduler",
    "ExecutionResult",
    # 数据模型
    "SkillTemplate",
    "SkillMatchResult",
    "SubtaskTemplate",
    "RetryPolicy",
    "Task",
    "TaskDAG",
    "TaskResult",
    "ExecutionPlan",
    "Worker",
    # 通用规划原语库
    "PrimitiveLibrary",
    "SequentialDecomposition",
    "DivideConquer",
    "ConditionalBranch",
    "LoopUntil",
    "SearchVerifyExecute",
    "TreeOfThought",
]
