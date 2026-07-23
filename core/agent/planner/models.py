# -*- coding: utf-8 -*-
"""
core/agent/v3_0/planning/models.py
──────────────────────────────────
DialogMesh Agent v3.0 — Planning Skill 数据模型。

用途：
- 定义规划器相关的 Pydantic v2 数据模型：策略、配置、步骤、结果、修订。
- 支持规划状态机（PlannerState）、规划策略枚举（PlanStrategy）。
- 所有模型支持异步验证钩子 ``async_validate``，兼容 FastAPI Schema 生成。

设计原则：
- 与 ``core.agent.v3_0.data_models`` 共享 TaskGraph_v3 / TaskNode_v3 / Intent_v3，不重复定义。
- 规划层特有的语义（如 PlanStep、PlanRevision）在此文件集中定义。
- 枚举使用 ``str, Enum`` 以支持 Pydantic 自动序列化。

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from collections import defaultdict

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.agent.v3_0.data_models import (
    CognitiveProfile_v3,
    Intent_v3,
    TaskGraph_v3,
    TaskNode_v3,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 枚举定义
# ═══════════════════════════════════════════════════════════════════════════

class PlanStrategy(str, Enum):
    """规划策略——由 StrategySelector 根据认知画像与意图复杂度动态选择。"""
    RULE_BASED = "rule_based"           # 纯规则驱动（低复杂度、高置信度）
    LLM_DRIVEN = "llm_driven"           # LLM 全程生成（高复杂度、低置信度）
    HYBRID = "hybrid"                   # 规则生成骨架 + LLM 细化
    TEMPLATE = "template"               # 模板匹配（常见意图类型）
    REFLEXIVE = "reflexive"             # 反射式规划（元认知干预时）
    RECOVERY = "recovery"               # 恢复/回退规划（任务失败后）


class PlannerState(str, Enum):
    """规划器状态机——用于追踪单次规划请求的生命周期。"""
    IDLE = "idle"                       # 空闲，等待输入
    ANALYZING = "analyzing"             # 分析意图与上下文
    SELECTING_STRATEGY = "selecting_strategy"  # 选择规划策略
    GENERATING = "generating"           # 生成任务图
    OPTIMIZING = "optimizing"           # 优化任务图
    VALIDATING = "validating"           # 验证任务图合法性
    READY = "ready"                     # 规划完成，可执行
    FAILED = "failed"                   # 规划失败
    REVISING = "revising"               # 正在修订（回退后重规划）


class StepType(str, Enum):
    """规划步骤类型——用于 PlanStep 的语义分类。"""
    ANALYSIS = "analysis"               # 分析步骤（理解意图）
    DECOMPOSITION = "decomposition"     # 分解步骤（意图拆分为子任务）
    TOOL_CALL = "tool_call"             # 工具调用步骤
    LLM_INFERENCE = "llm_inference"    # LLM 推理步骤
    VALIDATION = "validation"           # 验证步骤
    CLARIFICATION = "clarification"     # 澄清步骤（需要用户确认）
    FALLBACK = "fallback"               # 回退步骤
    MERGE = "merge"                     # 合并步骤（并行结果聚合）


class SkillLevel(str, Enum):
    """技能模板详细度级别 — 决定规划路径的精细程度。

    对应工程文档: ENGINEERING_PLANNING_SKILL.md §6.2
    - SKELETON: 骨架级，仅含基本分解结构，走 DYNAMIC 路径
    - STANDARD: 标准级，含完整子任务模板，走 SKILL_ENHANCED 路径
    - DETAILED: 详细级，含增强元数据（primitives、constraints、tool_hints），走 MIXED 路径
    """
    SKELETON = "SKELETON"
    STANDARD = "STANDARD"
    DETAILED = "DETAILED"


class PlanningMode(str, Enum):
    """规划模式 — 由 _select_mode() 根据 skill.level 和匹配分数动态选择。

    回退链: MIXED → SKILL_ENHANCED → DYNAMIC → FALLBACK
    """
    MIXED = "mixed"                     # 混合模式：技能模板骨架 + LLM 动态细化
    SKILL_ENHANCED = "skill_enhanced"   # 技能增强模式：基于技能模板（原快速/混合路径）
    DYNAMIC = "dynamic"                 # 动态模式：完全 LLM 驱动分解
    FALLBACK = "fallback"               # 回退模式：单任务直接执行（Answer-LLM）


# ═══════════════════════════════════════════════════════════════════════════
# 基础模型
# ═══════════════════════════════════════════════════════════════════════════

class PlanStep(BaseModel):
    """规划步骤——任务图生成过程中的一个原子操作记录。

    用于可观测性（追踪规划器如何一步步构造 TaskGraph）和调试。
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    step_id: str = Field(default_factory=lambda: f"PS-{str(uuid.uuid4())[:8]}")
    step_type: StepType = StepType.ANALYSIS
    description: str = ""
    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_data: Dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)

    def mark_success(self, output: Dict[str, Any], latency_ms: float) -> None:
        """标记步骤成功并记录输出。"""
        self.success = True
        self.output_data = output
        self.latency_ms = latency_ms
        self.error = None

    def mark_failed(self, error: str, latency_ms: float) -> None:
        """标记步骤失败并记录错误。"""
        self.success = False
        self.error = error
        self.latency_ms = latency_ms


class PlanRevision(BaseModel):
    """规划修订记录——追踪任务图的变更历史。

    当回退或优化导致任务图变更时，生成修订记录，便于审计与调试。
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    revision_id: str = Field(default_factory=lambda: f"REV-{str(uuid.uuid4())[:8]}")
    reason: str = ""                      # 修订原因（如 "节点 N 失败，切换到备选方案"）
    changed_nodes: List[str] = Field(default_factory=list)  # 变更的节点 ID
    added_nodes: List[str] = Field(default_factory=list)
    removed_nodes: List[str] = Field(default_factory=list)
    before_graph_hash: Optional[str] = None  # 修订前的图摘要（如节点数+边数）
    after_graph_hash: Optional[str] = None
    cognitive_trigger: Optional[str] = None   # 触发修订的认知事件（如 "Meta-Cognitive 检测到冲突"）
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)


class PlannerConfig(BaseModel):
    """规划器运行时配置——支持策略调参与动态开关。

    由 StrategySelector 根据 IntentContext 动态生成，也可由外部系统注入。
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    # 策略选择
    default_strategy: PlanStrategy = PlanStrategy.HYBRID
    enable_llm_planning: bool = True
    enable_rule_fallback: bool = True
    enable_template_matching: bool = True
    enable_reflexive_planning: bool = False

    # 复杂度阈值
    complexity_threshold_hybrid: float = 0.5      # 超过此值使用 HYBRID 而非 RULE_BASED
    complexity_threshold_llm: float = 0.8       # 超过此值使用 LLM_DRIVEN
    confidence_threshold_fast_path: float = 0.85  # 置信度高于此值走快速路径

    # 任务图约束
    max_nodes: int = Field(default=50, ge=1)
    max_depth: int = Field(default=5, ge=1)
    max_parallel_branches: int = Field(default=4, ge=1)
    enable_optimization: bool = True
    enable_cycle_detection: bool = True

    # LLM 调参（用于 LLM_DRIVEN / HYBRID 策略）
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=2048, ge=1)
    llm_timeout_ms: int = Field(default=30000, ge=1000)
    llm_system_prompt: str = (
        "You are a task planner for a reverse-engineering assistant. "
        "Given a user intent, output a JSON task graph with nodes and edges."
    )

    # 重试与回退
    max_planning_retries: int = Field(default=2, ge=0)
    fallback_on_validation_failure: bool = True
    auto_retry_on_llm_error: bool = True

    # 可观测性
    trace_every_step: bool = False
    max_trace_log_entries: int = 100

    @field_validator("llm_temperature", mode="before")
    @classmethod
    def _clamp_temperature(cls, v: Union[float, int]) -> float:
        """将 temperature 裁剪到合法范围。"""
        try:
            return float(max(0.0, min(2.0, v)))
        except Exception as exc:
            logger.warning(f"llm_temperature validation error ({exc}), defaulting to 0.2")
            return 0.2


class PlanResult(BaseModel):
    """规划结果——PlanningSkill 的最终输出。

    包含生成的 TaskGraph、采用策略、规划步骤追踪、修订历史。
    当 ``success`` 为 False 时，``error`` 与 ``fallback_suggestion`` 提供诊断信息。
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    result_id: str = Field(default_factory=lambda: f"PLAN-{str(uuid.uuid4())[:8]}")
    intent_id: str = ""
    success: bool = True
    task_graph: Optional[TaskGraph_v3] = None
    strategy_used: PlanStrategy = PlanStrategy.HYBRID
    planner_state: PlannerState = PlannerState.READY
    steps: List[PlanStep] = Field(default_factory=list)
    revisions: List[PlanRevision] = Field(default_factory=list)
    latency_ms: float = 0.0
    token_cost: int = 0
    error: Optional[str] = None
    fallback_suggestion: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)

    def add_step(self, step: PlanStep) -> None:
        """添加规划步骤。"""
        self.steps.append(step)

    def add_revision(self, revision: PlanRevision) -> None:
        """添加修订记录。"""
        self.revisions.append(revision)

    def to_summary(self) -> Dict[str, Any]:
        """生成摘要字典，用于前端渲染与日志。"""
        return {
            "result_id": self.result_id,
            "intent_id": self.intent_id,
            "success": self.success,
            "strategy": self.strategy_used.value,
            "state": self.planner_state.value,
            "nodes": len(self.task_graph.nodes) if self.task_graph else 0,
            "edges": len(self.task_graph.edges) if self.task_graph else 0,
            "steps": len(self.steps),
            "revisions": len(self.revisions),
            "latency_ms": self.latency_ms,
            "error": self.error,
        }

    async def async_validate(self) -> None:
        """异步验证：确保 task_graph 的节点与边引用一致。"""
        try:
            await asyncio.sleep(0)
            if self.task_graph is None:
                return
            node_ids = set(self.task_graph.nodes.keys())
            for edge in self.task_graph.edges:
                if edge.source_id not in node_ids or edge.target_id not in node_ids:
                    raise ValueError(
                        f"Edge references non-existent node: {edge.source_id} -> {edge.target_id}"
                    )
        except Exception as exc:
            logger.error(f"PlanResult async_validate failed: {exc}")
            raise


class ExecutionCheckpoint(BaseModel):
    """执行检查点——异步执行器在执行过程中保存的快照。

    用于长任务中断恢复、断点续传和调试。
    """
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    checkpoint_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    plan_result_id: str = ""
    completed_node_ids: List[str] = Field(default_factory=list)
    failed_node_ids: List[str] = Field(default_factory=list)
    pending_node_ids: List[str] = Field(default_factory=list)
    current_node_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)


# ═══════════════════════════════════════════════════════════════════════════
# 策略评分模型（StrategySelector 内部使用）
# ═══════════════════════════════════════════════════════════════════════════

class StrategyScore(BaseModel):
    """策略评分——StrategySelector 对每种策略的量化评估。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    strategy: PlanStrategy
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    estimated_latency_ms: float = 0.0
    estimated_cost: float = 0.0
    reason: str = ""

    @field_validator("score", "confidence", mode="before")
    @classmethod
    def _clamp_float(cls, v: Union[float, int]) -> float:
        """将浮点值裁剪到 [0.0, 1.0]。"""
        try:
            return float(max(0.0, min(1.0, v)))
        except Exception as exc:
            logger.warning(f"Float clamping error ({exc}), defaulting to 0.0")
            return 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════
# Planning Skill Engine 数据模型（ENGINEERING_PLANNING_SKILL.md §6）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=False)
class SkillTemplate:
    """技能模板 — 定义一个可复用的任务模式。

    对应工程文档: ENGINEERING_PLANNING_SKILL.md §6.2
    """
    name: str                              # 技能名称（如 "memory_analysis"）
    version: str = "1.0.0"                 # 版本号
    description: str = ""                  # 技能描述
    keywords: List[str] = field(default_factory=list)   # 匹配关键词
    tags: List[str] = field(default_factory=list)         # 分类标签
    domain_tags: List[str] = field(default_factory=list)  # 领域标签
    intent_categories: List[str] = field(default_factory=list)  # 意图类别
    primitives: List[str] = field(default_factory=list)     # 通用原语组合
    tool_hints: Dict[str, List[str]] = field(default_factory=dict)  # 工具提示
    constraints: List[Dict[str, Any]] = field(default_factory=list)  # 领域约束
    level: SkillLevel = SkillLevel.STANDARD           # SKELETON / STANDARD / DETAILED
    decomposition_pattern: str = "sequential"  # sequential/parallel/conditional
    subtasks: List["SubtaskTemplate"] = field(default_factory=list)   # 子任务模板
    dependencies: List[Dict[str, Any]] = field(default_factory=list)   # 依赖定义
    retry_policy: "RetryPolicy" = field(default_factory=lambda: RetryPolicy())
    timeout_seconds: float = 300.0
    fallback_skill: Optional[str] = None   # 失败时回退到的技能

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典。"""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "keywords": list(self.keywords),
            "tags": list(self.tags),
            "domain_tags": list(self.domain_tags),
            "intent_categories": list(self.intent_categories),
            "primitives": list(self.primitives),
            "tool_hints": dict(self.tool_hints),
            "constraints": list(self.constraints),
            "level": self.level.value if isinstance(self.level, SkillLevel) else str(self.level),
            "decomposition_pattern": self.decomposition_pattern,
            "subtasks": [s.to_dict() for s in self.subtasks],
            "timeout_seconds": self.timeout_seconds,
            "fallback_skill": self.fallback_skill,
        }


@dataclass(frozen=False)
class SubtaskTemplate:
    """子任务模板。"""
    name: str
    description: str
    worker_type: str                       # Worker 类型（如 "PCR-LLM", "ToolExecutor"）
    input_template: str = ""               # 输入模板（Jinja2）
    output_schema: Dict[str, Any] = field(default_factory=dict)
    required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "worker_type": self.worker_type,
            "input_template": self.input_template,
            "output_schema": self.output_schema,
            "required": self.required,
        }


@dataclass(frozen=False)
class RetryPolicy:
    """重试策略。"""
    max_retries: int = 3
    backoff_factor: float = 2.0           # 指数退避基数
    retryable_errors: List[str] = field(default_factory=lambda: ["timeout", "rate_limit"])

    def should_retry(self, error_str: str, current_retry_count: int) -> bool:
        """判断是否应该重试。"""
        if current_retry_count >= self.max_retries:
            return False
        error_lower = error_str.lower()
        return any(retryable in error_lower for retryable in self.retryable_errors)

    def get_delay(self, retry_count: int) -> float:
        """获取第 retry_count 次重试的延迟（秒）。"""
        return self.backoff_factor ** retry_count


@dataclass(frozen=False)
class Task:
    """任务 — 可执行的工作单元。"""
    name: str
    description: str = ""
    worker_type: str = "Planning-LLM"   # 执行者类型
    input_data: Any = None
    output_schema: Dict[str, Any] = field(default_factory=dict)
    required: bool = True
    estimated_time: int = 10              # 估计执行时间（秒）
    dependencies: List[str] = field(default_factory=list)  # 依赖的任务名称列表
    retry_count: int = 0
    max_retries: int = 3
    retry_policy: RetryPolicy = field(default_factory=lambda: RetryPolicy())
    tool_name: Optional[str] = None       # 占位符或实际工具名
    id: str = field(init=False)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """初始化后自动生成 ID。"""
        try:
            object.__setattr__(self, "id", str(uuid.uuid4())[:8])
        except Exception as exc:
            logger.warning(f"Task ID generation failed: {exc}, using fallback")
            object.__setattr__(self, "id", f"T-{int(time.time() * 1000) % 1000000}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "worker_type": self.worker_type,
            "input_data": self.input_data,
            "output_schema": self.output_schema,
            "required": self.required,
            "estimated_time": self.estimated_time,
            "dependencies": list(self.dependencies),
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "tool_name": self.tool_name,
            "metadata": dict(self.metadata),
        }


class TaskDAG:
    """任务 DAG — 表示任务间的依赖关系。

    对应工程文档: ENGINEERING_PLANNING_SKILL.md §9.2
    """

    def __init__(self) -> None:
        self.nodes: Dict[str, Task] = {}
        self.edges: List[Tuple[str, str]] = []  # (from_id, to_id)
        self.neighbors: Dict[str, Set[str]] = defaultdict(set)
        self.topological_order: List[str] = []
        self.metadata: Dict[str, Any] = {}

    def add_node(self, task: Task) -> None:
        """添加任务节点。"""
        self.nodes[task.id] = task

    def add_edge(self, from_id: str, to_id: str) -> None:
        """添加依赖边。"""
        if from_id not in self.nodes or to_id not in self.nodes:
            raise ValueError(f"Edge references non-existent node: {from_id} -> {to_id}")
        self.edges.append((from_id, to_id))
        self.neighbors[from_id].add(to_id)

    def has_cycle(self) -> bool:
        """检测循环（DFS）。"""
        try:
            visited: Set[str] = set()
            rec_stack: Set[str] = set()

            def dfs(node: str) -> bool:
                visited.add(node)
                rec_stack.add(node)
                for neighbor in self.neighbors.get(node, set()):
                    if neighbor not in visited:
                        if dfs(neighbor):
                            return True
                    elif neighbor in rec_stack:
                        return True
                rec_stack.remove(node)
                return False

            for node in self.nodes:
                if node not in visited:
                    if dfs(node):
                        return True
            return False
        except Exception as exc:
            logger.error(f"Cycle detection failed: {exc}")
            return True  # 保守策略：检测失败时假设有循环

    def topological_sort(self) -> List[str]:
        """拓扑排序（Kahn 算法）。"""
        try:
            in_degree: Dict[str, int] = {node: 0 for node in self.nodes}
            for from_id, to_id in self.edges:
                in_degree[to_id] = in_degree.get(to_id, 0) + 1

            queue = [node for node, degree in in_degree.items() if degree == 0]
            order: List[str] = []
            while queue:
                node = queue.pop(0)
                order.append(node)
                for neighbor in self.neighbors.get(node, set()):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)
            return order
        except Exception as exc:
            logger.error(f"Topological sort failed: {exc}")
            return []

    def is_valid(self) -> bool:
        """DAG 是否有效（无循环且拓扑序包含所有节点）。"""
        return not self.has_cycle() and len(self.topological_order) == len(self.nodes)

    def get_ready_nodes(self) -> List[Task]:
        """获取无入边的节点（可立即执行）。"""
        incoming: Set[str] = set()
        for _, to_id in self.edges:
            incoming.add(to_id)
        return [self.nodes[nid] for nid in self.nodes if nid not in incoming]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": self.edges,
            "topological_order": self.topological_order,
            "metadata": self.metadata,
        }


@dataclass(frozen=False)
class TaskResult:
    """任务执行结果。"""
    task_id: str = ""
    task_name: str = ""
    success: bool = False
    output: Optional[Any] = None
    error: Optional[str] = None
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=False)
class ExecutionPlan:
    """执行计划。"""
    tasks: List[Task] = field(default_factory=list)
    dag: Optional[TaskDAG] = None
    strategy: str = "sequential"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tasks": [t.to_dict() for t in self.tasks],
            "dag": self.dag.to_dict() if self.dag else None,
            "strategy": self.strategy,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=False)
class SkillMatchResult:
    """技能匹配结果 — 包含技能模板和是否使用模板的标志。"""
    skill: Optional[SkillTemplate] = None
    score: float = 0.0
    use_template: bool = False  # True: 使用预定义子任务模板（快速）
                               # False: 调用 Planning-LLM 动态分解（慢速）
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill": self.skill.to_dict() if self.skill else None,
            "score": self.score,
            "use_template": self.use_template,
            "reason": self.reason,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 通用规划原语（ENGINEERING_PLANNING_SKILL.md §6.5）
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=False)
class PlanningPrimitive:
    """通用规划原语 — 跨领域、跨任务、不依赖具体工具的认知模式抽象。"""
    name: str = ""
    description: str = ""
    category: str = "decomposition"  # decomposition / allocation / ordering / resource / reflection

    def generate_skeleton(self, steps: Optional[List[Dict[str, Any]]] = None) -> List[Task]:
        """生成任务列表骨架（工具名为占位符，由 ToolBindingEngine 绑定）。"""
        raise NotImplementedError("Subclasses must implement generate_skeleton")


@dataclass(frozen=False)
class SequentialDecomposition(PlanningPrimitive):
    """线性顺序分解：将目标拆分为依次执行的步骤。"""
    name: str = "SequentialDecomposition"
    description: str = "将目标分解为线性顺序执行的步骤"
    category: str = "decomposition"

    def generate_skeleton(self, steps: Optional[List[Dict[str, Any]]] = None) -> List[Task]:
        tasks: List[Task] = []
        prev_name: Optional[str] = None
        for step in steps or []:
            task = Task(
                name=step.get("name", "step"),
                description=step.get("description", ""),
                worker_type=step.get("worker_type", "Planning-LLM"),
                input_data=f"placeholder: {step.get('tool_placeholder', 'unknown_tool')}",
                tool_name=step.get("tool_placeholder", "unknown_tool"),
            )
            if prev_name:
                task.dependencies = [prev_name]
            tasks.append(task)
            prev_name = task.name
        return tasks


@dataclass(frozen=False)
class PlanExecuteReflect(PlanningPrimitive):
    """计划-执行-反思循环：PDCA 的 Agent 版本。"""
    name: str = "PlanExecuteReflect"
    description: str = "计划→执行→评估→反思→迭代的循环"
    category: str = "reflection"
    max_iterations: int = 5

    def generate_skeleton(self, steps: Optional[List[Dict[str, Any]]] = None) -> List[Task]:
        plan = Task(name="plan", description="制定计划", worker_type="Planning-LLM", tool_name="plan_tool")
        exec_ = Task(name="execute", description="执行计划", worker_type="Planning-LLM", tool_name="execute_tool")
        reflect = Task(name="reflect", description="反思改进", worker_type="Planning-LLM", tool_name="reflect_tool")
        finish = Task(name="finalize", description="输出结果", worker_type="Planning-LLM", tool_name="finish_tool")
        exec_.dependencies = [plan.name]
        reflect.dependencies = [exec_.name]
        finish.dependencies = [reflect.name]
        return [plan, exec_, reflect, finish]


# ═══════════════════════════════════════════════════════════════════════════
# PS-S-06 修复：5 个核心规划原语
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=False)
class DivideConquer(PlanningPrimitive):
    """分治分解：将问题拆分为若干子问题，递归求解后合并结果。

    对应工程文档: ENGINEERING_PLANNING_SKILL.md §6.5.2 (P3)
    """
    name: str = "DivideConquer"
    description: str = "将问题拆分为若干子问题，递归求解后合并结果"
    category: str = "decomposition"

    def generate_skeleton(self, steps: Optional[List[Dict[str, Any]]] = None) -> List[Task]:
        """生成分治骨架：分解 → 求解子问题 → 合并结果。

        Args:
            steps: 可选的子步骤定义，支持 ``divide``、``solve``、``merge`` 字段。

        Returns:
            Task 列表，包含分解、并行求解、合并三个阶段。
        """
        try:
            # 分解阶段：将问题拆分为子问题
            divide = Task(
                name="divide",
                description="将问题拆分为若干子问题",
                worker_type="Planning-LLM",
                tool_name="divide_tool",
            )
            # 并行求解阶段（左/右分支，实际可扩展为更多分支）
            solve_left = Task(
                name="solve_left",
                description="求解左子问题",
                worker_type="Planning-LLM",
                tool_name="solve_tool",
            )
            solve_right = Task(
                name="solve_right",
                description="求解右子问题",
                worker_type="Planning-LLM",
                tool_name="solve_tool",
            )
            # 合并阶段：将子问题结果合并
            merge = Task(
                name="merge",
                description="合并子问题结果",
                worker_type="Planning-LLM",
                tool_name="merge_tool",
            )
            # 建立依赖：分解 → 求解（并行） → 合并
            solve_left.dependencies = [divide.name]
            solve_right.dependencies = [divide.name]
            merge.dependencies = [solve_left.name, solve_right.name]
            return [divide, solve_left, solve_right, merge]
        except Exception as exc:
            logger.error(f"DivideConquer.generate_skeleton failed: {exc}")
            # 退化回退：返回单任务
            return [Task(
                name="direct_divide",
                description="DivideConquer fallback single task",
                worker_type="Answer-LLM",
            )]


@dataclass(frozen=False)
class ConditionalBranch(PlanningPrimitive):
    """条件分支：先评估条件，再根据评估结果选择不同执行路径。

    对应工程文档: ENGINEERING_PLANNING_SKILL.md §6.5.2 (P8)
    """
    name: str = "ConditionalBranch"
    description: str = "先评估条件，再根据评估结果选择不同执行路径"
    category: str = "ordering"

    def generate_skeleton(self, steps: Optional[List[Dict[str, Any]]] = None) -> List[Task]:
        """生成条件分支骨架：评估 → 分支 A / 分支 B → 合并。

        Args:
            steps: 可选的子步骤定义，支持 ``evaluate``、``branch_a``、``branch_b`` 字段。

        Returns:
            Task 列表，包含条件评估、两个互斥分支、最终合并。
        """
        try:
            # 条件评估阶段
            evaluate = Task(
                name="evaluate",
                description="评估条件以决定分支路径",
                worker_type="Planning-LLM",
                tool_name="evaluate_tool",
            )
            # 分支 A：条件为真时的执行路径
            branch_a = Task(
                name="branch_a",
                description="条件为真时的执行路径",
                worker_type="Planning-LLM",
                tool_name="branch_a_tool",
            )
            # 分支 B：条件为假时的执行路径
            branch_b = Task(
                name="branch_b",
                description="条件为假时的执行路径",
                worker_type="Planning-LLM",
                tool_name="branch_b_tool",
            )
            # 合并阶段：无论走哪个分支，最终汇聚
            merge = Task(
                name="merge",
                description="合并分支结果",
                worker_type="Planning-LLM",
                tool_name="merge_tool",
            )
            # 建立依赖：评估 → 分支（并行互斥） → 合并
            branch_a.dependencies = [evaluate.name]
            branch_b.dependencies = [evaluate.name]
            merge.dependencies = [branch_a.name, branch_b.name]
            return [evaluate, branch_a, branch_b, merge]
        except Exception as exc:
            logger.error(f"ConditionalBranch.generate_skeleton failed: {exc}")
            return [Task(
                name="direct_branch",
                description="ConditionalBranch fallback single task",
                worker_type="Answer-LLM",
            )]


@dataclass(frozen=False)
class LoopUntil(PlanningPrimitive):
    """循环直到：重复执行直到满足终止条件。

    在 DAG 中无法直接表达回边，因此采用有限展开（3 次迭代）模拟循环。

    对应工程文档: ENGINEERING_PLANNING_SKILL.md §6.5.2 (P9)
    """
    name: str = "LoopUntil"
    description: str = "重复执行直到满足终止条件（DAG 中以有限展开模拟）"
    category: str = "ordering"
    max_iterations: int = 3

    def generate_skeleton(self, steps: Optional[List[Dict[str, Any]]] = None) -> List[Task]:
        """生成循环骨架：初始化 → 循环体 → 条件检查（迭代 3 次）。

        Args:
            steps: 可选的子步骤定义，支持 ``init``、``body``、``check`` 字段。

        Returns:
            Task 列表，包含初始化与 3 轮循环体+条件检查。
        """
        try:
            max_iter: int = self.max_iterations
            tasks: List[Task] = []
            # 初始化阶段
            init = Task(
                name="loop_init",
                description="初始化循环状态",
                worker_type="Planning-LLM",
                tool_name="loop_init_tool",
            )
            tasks.append(init)
            prev_task: str = init.name
            # 有限展开循环（DAG 不支持回边，以线性展开代替）
            for i in range(1, max_iter + 1):
                body = Task(
                    name=f"loop_body_{i}",
                    description=f"第 {i} 轮循环体执行",
                    worker_type="Planning-LLM",
                    tool_name="loop_body_tool",
                )
                check = Task(
                    name=f"loop_check_{i}",
                    description=f"第 {i} 轮终止条件检查",
                    worker_type="Planning-LLM",
                    tool_name="loop_check_tool",
                )
                body.dependencies = [prev_task]
                check.dependencies = [body.name]
                tasks.extend([body, check])
                prev_task = check.name
            # 最终确定阶段
            finalize = Task(
                name="loop_finalize",
                description="循环结束，输出最终结果",
                worker_type="Planning-LLM",
                tool_name="finalize_tool",
            )
            finalize.dependencies = [prev_task]
            tasks.append(finalize)
            return tasks
        except Exception as exc:
            logger.error(f"LoopUntil.generate_skeleton failed: {exc}")
            return [Task(
                name="direct_loop",
                description="LoopUntil fallback single task",
                worker_type="Answer-LLM",
            )]


@dataclass(frozen=False)
class SearchVerifyExecute(PlanningPrimitive):
    """搜索验证执行：先搜索候选方案，验证合法性后执行。

    对应工程文档: ENGINEERING_PLANNING_SKILL.md §6.5.2 (P12)
    """
    name: str = "SearchVerifyExecute"
    description: str = "搜索候选方案 → 验证合法性 → 执行"
    category: str = "resource"

    def generate_skeleton(self, steps: Optional[List[Dict[str, Any]]] = None) -> List[Task]:
        """生成搜索-验证-执行骨架。

        Args:
            steps: 可选的子步骤定义，支持 ``search``、``verify``、``execute`` 字段。

        Returns:
            Task 列表，包含搜索、验证、执行三个阶段。
        """
        try:
            search = Task(
                name="search",
                description="搜索候选方案或资源",
                worker_type="Planning-LLM",
                tool_name="search_tool",
            )
            verify = Task(
                name="verify",
                description="验证候选方案的合法性",
                worker_type="Planning-LLM",
                tool_name="verify_tool",
            )
            execute = Task(
                name="execute",
                description="执行验证通过的方案",
                worker_type="Planning-LLM",
                tool_name="execute_tool",
            )
            # 线性依赖：搜索 → 验证 → 执行
            verify.dependencies = [search.name]
            execute.dependencies = [verify.name]
            return [search, verify, execute]
        except Exception as exc:
            logger.error(f"SearchVerifyExecute.generate_skeleton failed: {exc}")
            return [Task(
                name="direct_sve",
                description="SearchVerifyExecute fallback single task",
                worker_type="Answer-LLM",
            )]


@dataclass(frozen=False)
class TreeOfThought(PlanningPrimitive):
    """思维树：生成多个候选路径，并行评估后选择最佳方案执行。

    对应工程文档: ENGINEERING_PLANNING_SKILL.md §6.5.2 (P15)
    """
    name: str = "TreeOfThought"
    description: str = "生成多候选路径 → 并行评估 → 选择最佳 → 执行"
    category: str = "reflection"
    num_candidates: int = 3

    def generate_skeleton(self, steps: Optional[List[Dict[str, Any]]] = None) -> List[Task]:
        """生成思维树骨架：生成候选 → 并行评估 → 选择最佳 → 执行。

        Args:
            steps: 可选的子步骤定义，支持 ``generate``、``evaluate``、``select``、``execute`` 字段。

        Returns:
            Task 列表，包含候选生成、并行评估、选择、执行四个阶段。
        """
        try:
            num_cands: int = self.num_candidates
            # 生成候选路径
            generate = Task(
                name="generate_candidates",
                description="生成多个候选解决路径",
                worker_type="Planning-LLM",
                tool_name="generate_tool",
            )
            # 并行评估每个候选
            evaluate_tasks: List[Task] = []
            for i in range(1, num_cands + 1):
                ev = Task(
                    name=f"evaluate_candidate_{i}",
                    description=f"评估候选路径 {i}",
                    worker_type="Planning-LLM",
                    tool_name="evaluate_tool",
                )
                ev.dependencies = [generate.name]
                evaluate_tasks.append(ev)
            # 选择最佳方案
            select = Task(
                name="select_best",
                description="选择评分最高的候选方案",
                worker_type="Planning-LLM",
                tool_name="select_tool",
            )
            for ev in evaluate_tasks:
                select.dependencies.append(ev.name)
            # 执行最佳方案
            execute = Task(
                name="execute_best",
                description="执行选中的最佳方案",
                worker_type="Planning-LLM",
                tool_name="execute_tool",
            )
            execute.dependencies = [select.name]
            return [generate, *evaluate_tasks, select, execute]
        except Exception as exc:
            logger.error(f"TreeOfThought.generate_skeleton failed: {exc}")
            return [Task(
                name="direct_tot",
                description="TreeOfThought fallback single task",
                worker_type="Answer-LLM",
            )]


class PrimitiveLibrary:
    """通用规划原语库 — 管理所有 PlanningPrimitive 的注册与查询。"""

    def __init__(self) -> None:
        self._primitives: Dict[str, PlanningPrimitive] = {}
        self._register_defaults()
        logger.info("PrimitiveLibrary initialized")

    def _register_defaults(self) -> None:
        """注册默认的 17 个原语（当前实现 7 个，剩余 10 个为占位符）。"""
        self.register(SequentialDecomposition())
        self.register(PlanExecuteReflect())
        # S-06 修复：新增 5 个核心原语
        self.register(DivideConquer())
        self.register(ConditionalBranch())
        self.register(LoopUntil())
        self.register(SearchVerifyExecute())
        self.register(TreeOfThought())
        # 以下 10 个原语为占位符，待 Phase 2 实现
        # P2: HierarchicalDecomposition, P4: SingleAgent, P5: ParallelMap
        # P6: RoleBasedCollaboration, P7: SequentialFlow, P10: PriorityQueue
        # P11: SearchRetrieve, P13: MemoryAugmented, P16: ReflectRetry, P17: EarlyTermination

    def register(self, primitive: PlanningPrimitive) -> None:
        """注册原语。"""
        self._primitives[primitive.name] = primitive

    def get_primitive(self, name: str) -> Optional[PlanningPrimitive]:
        """获取指定原语。"""
        return self._primitives.get(name)

    def list_primitives(self) -> List[PlanningPrimitive]:
        """列出所有已注册原语。"""
        return list(self._primitives.values())

    def describe_all(self) -> str:
        """返回所有原语的人类可读描述，用于注入 LLM 提示词。"""
        implemented: Set[str] = {
            "SequentialDecomposition",
            "PlanExecuteReflect",
            "DivideConquer",
            "ConditionalBranch",
            "LoopUntil",
            "SearchVerifyExecute",
            "TreeOfThought",
        }
        lines: List[str] = []
        for p in self._primitives.values():
            status = "✅" if p.name in implemented else "⚠️ 占位符"
            lines.append(f"- {p.name} ({p.category}): {p.description} {status}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# 工具绑定与验证（ENGINEERING_PLANNING_SKILL.md §7.5 / §10.5）
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=False)
class ValidationResult:
    """Schema 验证结果。"""
    valid: bool = True
    errors: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


@dataclass(frozen=False)
class BindingResult:
    """工具绑定结果。"""
    tool_name: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    reason: str = ""


@dataclass(frozen=False)
class Worker:
    """Worker — 可执行任务的智能体。"""
    id: str = ""
    name: str = ""
    capabilities: List[str] = field(default_factory=list)
    max_concurrent: int = 5

    _assigned_tasks: List[Task] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def current_load(self) -> int:
        """当前负载（正在执行的任务数）。"""
        try:
            with self._lock:
                return len(self._assigned_tasks)
        except Exception as exc:
            logger.warning(f"Worker.current_load failed: {exc}")
            return 999  # 返回高负载以避免分配

    def assign(self, task: Task) -> None:
        """分配任务。"""
        try:
            with self._lock:
                self._assigned_tasks.append(task)
        except Exception as exc:
            logger.error(f"Worker.assign failed: {exc}")
            raise

    def complete(self, task: Task) -> None:
        """完成任务。"""
        try:
            with self._lock:
                if task in self._assigned_tasks:
                    self._assigned_tasks.remove(task)
        except Exception as exc:
            logger.error(f"Worker.complete failed: {exc}")
            raise

    def is_available(self) -> bool:
        """是否可用（负载未满）。"""
        return self.current_load() < self.max_concurrent

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "capabilities": list(self.capabilities),
            "max_concurrent": self.max_concurrent,
            "current_load": self.current_load(),
        }


# ═══════════════════════════════════════════════════════════════════════════
# 异常类型
# ═══════════════════════════════════════════════════════════════════════════

class PlanningError(Exception):
    """规划层通用异常。"""
    pass


class DependencyError(Exception):
    """依赖解析异常。"""
    pass


class AllocationError(Exception):
    """智能体分配异常。"""
    pass


class SkillNotFoundError(Exception):
    """技能未找到异常。"""
    pass


if __name__ == "__main__":
    import asyncio

    async def _self_test() -> None:
        logger.info("=== v3.0 planning/models self-test ===")

        # 1. PlanStep
        step = PlanStep(step_type=StepType.DECOMPOSITION, description="分解意图为扫描+验证")
        step.mark_success({"nodes_created": 2}, 45.0)
        assert step.success is True
        print(f"[PASS] PlanStep: {step.step_type.value}")

        # 2. PlanRevision
        rev = PlanRevision(reason="节点失败，切换备选", changed_nodes=["T-abc123"])
        assert rev.revision_id.startswith("REV-")
        print(f"[PASS] PlanRevision: {rev.reason}")

        # 3. PlannerConfig
        cfg = PlannerConfig(llm_temperature=3.0)
        assert cfg.llm_temperature == 2.0
        print(f"[PASS] PlannerConfig: temp={cfg.llm_temperature}")

        # 4. PlanResult
        tg = TaskGraph_v3()
        n1 = TaskNode_v3(name="scan", goal="find address")
        n2 = TaskNode_v3(name="verify", goal="check value")
        tg.add_node(n1)
        tg.add_node(n2)
        result = PlanResult(
            intent_id="intent-123",
            task_graph=tg,
            strategy_used=PlanStrategy.HYBRID,
        )
        result.add_step(step)
        result.add_revision(rev)
        assert result.success is True
        print(f"[PASS] PlanResult: nodes={len(result.task_graph.nodes)}")

        # 5. async_validate
        await result.async_validate()
        print(f"[PASS] PlanResult async_validate")

        # 6. ExecutionCheckpoint
        cp = ExecutionCheckpoint(
            plan_result_id=result.result_id,
            completed_node_ids=[n1.id],
            pending_node_ids=[n2.id],
        )
        assert cp.checkpoint_id
        print(f"[PASS] ExecutionCheckpoint")

        # 7. StrategyScore
        ss = StrategyScore(strategy=PlanStrategy.LLM_DRIVEN, score=1.2, confidence=-0.5)
        assert ss.score == 1.0 and ss.confidence == 0.0
        print(f"[PASS] StrategyScore: score={ss.score}")

        logger.info("=== All v3.0 planning/models self-tests passed ===")

    asyncio.run(_self_test())
