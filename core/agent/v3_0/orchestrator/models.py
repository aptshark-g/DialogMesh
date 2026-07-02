# -*- coding: utf-8 -*-
"""
core/agent/v3_0/orchestrator/models.py
─────────────────────────────────────
DialogMesh Agent v3.0 Orchestrator 数据模型。

用途：
- 定义编排层专用的 Pydantic 数据模型。
- 包含 TurnContext、OrchestratorResult、SystemHealth、DialogMeshSystem 等。
- 支持 6 阶段启动流程的配置与状态追踪。

版本：3.0.0
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field

from core.agent.v3_0.data_models import (
    AgentMessage_v3,
    CognitiveProfile_v3,
    IntentContext_v3,
    Intent_v3,
    TaskGraph_v3,
    WebSocketEvent,
)
from core.agent.v3_0.cognitive_tree.models import CognitiveTreeNode


# ═══════════════════════════════════════════════════════════════════════════
# 枚举
# ═══════════════════════════════════════════════════════════════════════════

class TurnPhase(str, Enum):
    """单轮处理的阶段标识——用于追踪和遥测。"""
    IDLE = "idle"
    PCR_ANALYSIS = "pcr_analysis"           # PCR-LLM 感知分析
    INTENT_PARSING = "intent_parsing"       # Intent-LLM 意图解析
    PLANNING = "planning"                   # Planning-LLM 任务规划
    EXECUTION = "execution"                 # 工具执行
    META_COGNITIVE = "meta_cognitive"       # Meta-Cognitive-LLM 验证
    ANSWER_GENERATION = "answer_generation"  # Answer-LLM 回复生成
    REFLECTIVE = "reflective"               # Reflective-LLM 异步复盘
    COMPLETED = "completed"
    FAILED = "failed"


class SystemPhase(str, Enum):
    """系统启动阶段——对应 INTEGRATION.md §4 的 6 阶段启动流程。"""
    PHASE_1_INFRASTRUCTURE = "phase_1_infrastructure"   # 可观测性
    PHASE_2_DATA = "phase_2_data"                       # 持久化 + 数据模型
    PHASE_3_COGNITIVE = "phase_3_cognitive"             # 主题树 + 上下文 + 认知编译器
    PHASE_4_ORCHESTRATION = "phase_4_orchestration"     # LLM 提供者 + 编排器
    PHASE_5_SERVICE = "phase_5_service"                 # 服务层
    PHASE_6_HEALTH = "phase_6_health"                   # 健康检查
    COMPLETED = "completed"
    FAILED = "failed"


class FusionSource(str, Enum):
    """融合结果来源——认知双工的输出源。"""
    ALGORITHM = "algorithm"
    LLM = "llm"
    FUSED = "fused"
    FALLBACK = "fallback"
    ALGORITHM_CONFLICT_RESOLVED = "algorithm_conflict_resolved"
    LLM_CONFLICT_RESOLVED = "llm_conflict_resolved"


# ═══════════════════════════════════════════════════════════════════════════
# 配置模型
# ═══════════════════════════════════════════════════════════════════════════

class OrchestratorConfig(BaseModel):
    """编排器配置——控制各 LLM 实例的启用与降级策略。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    # 功能开关
    enable_pcr_llm: bool = True
    enable_intent_llm: bool = True
    enable_planning_llm: bool = True
    enable_meta_cognitive_llm: bool = True
    enable_answer_llm: bool = True
    enable_reflective_llm: bool = True

    # 融合引擎配置
    fusion_high_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    fusion_low_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    fusion_llm_weight: float = Field(default=0.5, ge=0.0, le=1.0)

    # 超时配置 (ms)
    pcr_timeout_ms: int = Field(default=3000, ge=100)
    intent_timeout_ms: int = Field(default=3000, ge=100)
    planning_timeout_ms: int = Field(default=5000, ge=100)
    answer_timeout_ms: int = Field(default=5000, ge=100)
    meta_cognitive_timeout_ms: int = Field(default=8000, ge=100)
    reflective_timeout_ms: int = Field(default=30000, ge=100)

    # 降级配置
    fallback_to_algorithm: bool = True
    fallback_to_single_task: bool = True
    clarification_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    max_ambiguities_before_ask: int = 3

    # 回复约束
    honesty_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    max_response_length: int = 2000
    response_style: str = "BALANCED"  # BALANCED | FORMAL | CASUAL | TECHNICAL

    # 遥测
    trace_every_turn: bool = True
    emit_websocket_events: bool = True


class BootstrapConfig(BaseModel):
    """系统引导配置——6 阶段启动的参数聚合。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    config_path: Optional[str] = None
    observability_db_path: Optional[str] = None
    persistence_db_path: str = "data/dialogmesh.db"
    enable_cognitive_tree: bool = True
    enable_health_monitor: bool = True
    auto_start_service: bool = False
    log_level: str = "INFO"


# ═══════════════════════════════════════════════════════════════════════════
# 运行时模型
# ═══════════════════════════════════════════════════════════════════════════

class TurnContext(BaseModel):
    """单轮上下文——记录一次用户交互的完整中间状态。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    turn_id: str = Field(default_factory=lambda: f"turn-{uuid.uuid4().hex[:8]}")
    session_id: str
    user_input: str = ""
    current_phase: TurnPhase = TurnPhase.IDLE

    # Layer 1.5 输出
    pcr_result: Optional[Dict[str, Any]] = None
    intent_result: Optional[Intent_v3] = None
    intent_context: Optional[IntentContext_v3] = None

    # Layer 2 输出
    task_graph: Optional[TaskGraph_v3] = None
    execution_result: Optional[Dict[str, Any]] = None

    # Layer 3 输出
    answer_text: str = ""
    answer_confidence: float = 0.0
    honesty_declared: bool = False
    cited_nodes: List[str] = Field(default_factory=list)

    # 元认知
    meta_cognitive_result: Optional[Dict[str, Any]] = None
    reflective_result: Optional[Dict[str, Any]] = None

    # 追踪
    phase_latencies_ms: Dict[str, float] = Field(default_factory=dict)
    trace_log: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    finished_at: Optional[float] = None

    def mark_phase(self, phase: TurnPhase, latency_ms: float) -> None:
        """标记阶段完成并记录延迟。"""
        self.current_phase = phase
        self.phase_latencies_ms[phase.value] = latency_ms

    def add_trace(self, message: str) -> None:
        """添加追踪日志。"""
        self.trace_log.append(f"[{time.time():.3f}] {message}")

    def add_error(self, error: str) -> None:
        """添加错误记录。"""
        self.errors.append(error)

    def finish(self) -> None:
        """标记本轮结束。"""
        self.current_phase = TurnPhase.COMPLETED
        self.finished_at = time.time()


class FusionResult(BaseModel):
    """认知双工融合结果——算法引擎与 LLM 引擎的加权融合输出。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    output: Optional[Dict[str, Any]] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: FusionSource = FusionSource.FALLBACK
    llm_pending: bool = False
    clarification_required: bool = False
    conflict_detected: bool = False
    resolved_nodes: List[str] = Field(default_factory=list)
    fallback_reason: Optional[str] = None  # MLLM-S-01: 记录降级原因


class LLMInstanceResult(BaseModel):
    """单个 LLM 实例的调用结果。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    llm_name: str = ""
    success: bool = False
    output: Optional[Dict[str, Any]] = None
    confidence: float = 0.0
    latency_ms: float = 0.0
    node_id: Optional[str] = None
    error: Optional[str] = None


class OrchestratorResult(BaseModel):
    """编排器最终输出——面向服务层的标准响应。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    turn_id: str = ""
    session_id: str = ""
    success: bool = False
    status: str = "unknown"  # ok | clarifying | error | fallback

    # 回复内容
    answer: str = ""
    answer_confidence: float = 0.0
    honesty_declared: bool = False

    # 结构化数据
    intent: Optional[Intent_v3] = None
    task_graph: Optional[TaskGraph_v3] = None
    clarifications: List[Dict[str, Any]] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    cited_cognitive_nodes: List[str] = Field(default_factory=list)

    # 遥测
    total_latency_ms: float = 0.0
    phase_latencies_ms: Dict[str, float] = Field(default_factory=dict)
    trace_log: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    fallback_reason: Optional[str] = None

    # 事件（用于 WebSocket 推送）
    events: List[WebSocketEvent] = Field(default_factory=list)

    def to_agent_message(self) -> AgentMessage_v3:
        """转换为 AgentMessage_v3（供 ContextManager 使用）。"""
        return AgentMessage_v3(
            session_id=self.session_id,
            content=self.answer,
            intent=self.intent,
            task_graph=self.task_graph,
            suggestions=self.suggestions,
            metadata={
                "turn_id": self.turn_id,
                "confidence": self.answer_confidence,
                "honesty_declared": self.honesty_declared,
                "cited_nodes": self.cited_cognitive_nodes,
                "fallback_reason": self.fallback_reason,
            },
        )


class SystemHealth(BaseModel):
    """系统健康状态——/health 端点的顶层响应。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    healthy: bool = False
    status: str = "unknown"  # healthy | degraded | unhealthy
    phase: SystemPhase = SystemPhase.COMPLETED
    components: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    uptime_seconds: float = 0.0
    version: str = "3.0.0"
    timestamp: float = Field(default_factory=time.time)


class DialogMeshSystem(BaseModel):
    """DialogMesh 系统容器——SystemBootstrap 的最终输出。"""
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    # 核心组件
    orchestrator: Optional[Any] = None  # Orchestrator instance
    service_layer: Optional[Any] = None  # ServiceLayer instance (optional)
    observability: Optional[Any] = None  # Telemetry instance

    # 基础设施
    config: Optional[BootstrapConfig] = None
    health: SystemHealth = Field(default_factory=SystemHealth)

    # 启动时间
    started_at: float = Field(default_factory=time.time)

    def get_uptime_seconds(self) -> float:
        """获取系统已运行秒数。"""
        return time.time() - self.started_at
