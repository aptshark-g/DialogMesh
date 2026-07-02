# -*- coding: utf-8 -*-
"""
core/agent/v3_0/observability/models.py
─────────────────────────────────────
DialogMesh v3.0 可观测性数据模型定义。

用途：
  - 定义所有可观测性相关的数据类型（日志、指标、追踪、告警）
  - 提供统一的事件结构，支持类型安全的序列化与反序列化
  - 兼容现有 core/agent/models.py 中的 IntentCategory 枚举

版本：3.0.0
"""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from core.agent.models import IntentCategory


# ═══════════════════════════════════════════════════════════════════════════════
# 枚举定义
# ═══════════════════════════════════════════════════════════════════════════════

class LogLevel(str, enum.Enum):
    """日志级别。"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertSeverity(str, enum.Enum):
    """告警严重级别。"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SpanStatus(str, enum.Enum):
    """追踪 Span 状态。"""
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class MetricType(str, enum.Enum):
    """指标类型。"""
    COUNTER = "counter"      # 单调递增计数器
    GAUGE = "gauge"          # 可上下浮动的数值
    HISTOGRAM = "histogram"  # 分布直方图
    TIMER = "timer"          # 时间度量


# ═══════════════════════════════════════════════════════════════════════════════
# 数据模型：日志
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class LogEntry:
    """
    结构化日志条目。

    字段说明：
      - timestamp: 事件发生时间（Unix 时间戳，秒）
      - level: 日志级别
      - source: 日志来源模块名
      - message: 日志消息（截断到 500 字符）
      - session_id: 关联会话 ID（可选）
      - turn_index: 关联轮次索引（可选）
      - metadata: 附加键值对
      - trace_id: 关联追踪 ID（可选）
    """
    timestamp: float
    level: LogLevel
    source: str
    message: str
    session_id: Optional[str] = None
    turn_index: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict, hash=False)
    trace_id: Optional[str] = None

    def __post_init__(self):
        # 截断过长消息
        if len(self.message) > 500:
            object.__setattr__(self, "message", self.message[:500] + "...")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "level": self.level.value,
            "source": self.source,
            "message": self.message,
            "session_id": self.session_id,
            "turn_index": self.turn_index,
            "metadata": self.metadata,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LogEntry:
        return cls(
            timestamp=data.get("timestamp", time.time()),
            level=LogLevel(data.get("level", "info")),
            source=data.get("source", "unknown"),
            message=data.get("message", ""),
            session_id=data.get("session_id"),
            turn_index=data.get("turn_index"),
            metadata=data.get("metadata", {}),
            trace_id=data.get("trace_id"),
        )


@dataclass(frozen=True)
class DecisionLogEntry:
    """
    单轮决策链日志条目（专用于意图解析流水线）。

    与现有 v1 版本相比，v3.0 新增：
      - 明确的 LogLevel 分级
      - 支持 pcr_cohesion 字段
      - 支持 strategy_action 枚举
    """
    timestamp: float
    session_id: str
    turn_index: int
    query: str

    # 决策链
    pcr_expectation: Optional[str] = None
    pcr_noise: Optional[float] = None
    pcr_complexity: Optional[float] = None
    pcr_cohesion: Optional[float] = None
    intent_category: Optional[str] = None
    intent_confidence: Optional[float] = None
    execution_status: Optional[str] = None
    strategy_action: Optional[str] = None

    # 性能
    total_latency_ms: float = 0.0
    llm_used: bool = False
    llm_latency_ms: float = 0.0

    # 质量信号
    required_clarification: bool = False
    confidence_below_threshold: bool = False
    llm_fallback_triggered: bool = False

    # 窗口统计
    window_total_turns: Optional[int] = None
    window_compressed: Optional[bool] = None
    window_token_cost: Optional[int] = None

    metadata: Dict[str, Any] = field(default_factory=dict, hash=False)

    def __post_init__(self):
        if len(self.query) > 200:
            object.__setattr__(self, "query", self.query[:200] + "...")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "session_id": self.session_id[:8] + "..." if self.session_id else None,
            "turn_index": self.turn_index,
            "query": self.query,
            "pcr_expectation": self.pcr_expectation,
            "pcr_noise": self.pcr_noise,
            "pcr_complexity": self.pcr_complexity,
            "pcr_cohesion": self.pcr_cohesion,
            "intent_category": self.intent_category,
            "intent_confidence": self.intent_confidence,
            "execution_status": self.execution_status,
            "strategy_action": self.strategy_action,
            "total_latency_ms": round(self.total_latency_ms, 3),
            "llm_used": self.llm_used,
            "llm_latency_ms": round(self.llm_latency_ms, 3),
            "required_clarification": self.required_clarification,
            "confidence_below_threshold": self.confidence_below_threshold,
            "llm_fallback_triggered": self.llm_fallback_triggered,
            "window_total_turns": self.window_total_turns,
            "window_compressed": self.window_compressed,
            "window_token_cost": self.window_token_cost,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DecisionLogEntry:
        return cls(
            timestamp=data.get("timestamp", time.time()),
            session_id=data.get("session_id", ""),
            turn_index=data.get("turn_index", 0),
            query=data.get("query", ""),
            pcr_expectation=data.get("pcr_expectation"),
            pcr_noise=data.get("pcr_noise"),
            pcr_complexity=data.get("pcr_complexity"),
            pcr_cohesion=data.get("pcr_cohesion"),
            intent_category=data.get("intent_category"),
            intent_confidence=data.get("intent_confidence"),
            execution_status=data.get("execution_status"),
            strategy_action=data.get("strategy_action"),
            total_latency_ms=data.get("total_latency_ms", 0.0),
            llm_used=data.get("llm_used", False),
            llm_latency_ms=data.get("llm_latency_ms", 0.0),
            required_clarification=data.get("required_clarification", False),
            confidence_below_threshold=data.get("confidence_below_threshold", False),
            llm_fallback_triggered=data.get("llm_fallback_triggered", False),
            window_total_turns=data.get("window_total_turns"),
            window_compressed=data.get("window_compressed"),
            window_token_cost=data.get("window_token_cost"),
            metadata=data.get("metadata", {}),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 数据模型：指标
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MetricPoint:
    """
    单个指标采样点。

    字段说明：
      - name: 指标名称
      - metric_type: 指标类型（counter / gauge / histogram / timer）
      - value: 数值
      - labels: 标签字典（用于维度切分）
      - timestamp: 采样时间
    """
    name: str
    metric_type: MetricType
    value: Union[int, float]
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "metric_type": self.metric_type.value,
            "value": self.value,
            "labels": self.labels,
            "timestamp": self.timestamp,
        }


@dataclass
class SessionMetricsSnapshot:
    """
    单会话指标快照。

    v3.0 改进：
      - 显式记录 rule_hit_count 和 direct_reply_count
      - 支持 p95 / p99 延迟分位点
      - 支持 intent_category 分布（引用 IntentCategory）
    """
    session_id: str
    timestamp: float = field(default_factory=time.time)

    total_turns: int = 0
    clarification_count: int = 0
    llm_fallback_count: int = 0
    rule_hit_count: int = 0
    direct_reply_count: int = 0
    error_count: int = 0

    avg_confidence: float = 0.0
    avg_latency_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0

    health_score: float = 100.0

    # 意图分布：IntentCategory.value -> count
    intent_distribution: Dict[str, int] = field(default_factory=dict)

    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id[:8] + "..." if self.session_id else None,
            "timestamp": self.timestamp,
            "total_turns": self.total_turns,
            "clarification_count": self.clarification_count,
            "llm_fallback_count": self.llm_fallback_count,
            "rule_hit_count": self.rule_hit_count,
            "direct_reply_count": self.direct_reply_count,
            "error_count": self.error_count,
            "avg_confidence": round(self.avg_confidence, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "latency_p95_ms": round(self.latency_p95_ms, 2),
            "latency_p99_ms": round(self.latency_p99_ms, 2),
            "health_score": round(self.health_score, 1),
            "intent_distribution": dict(self.intent_distribution),
            "metadata": self.metadata,
        }


@dataclass
class GlobalMetricsSnapshot:
    """全局指标快照（跨会话聚合）。"""
    timestamp: float = field(default_factory=time.time)
    session_count: int = 0
    total_turns: int = 0
    avg_clarification_rate: float = 0.0
    avg_llm_fallback_rate: float = 0.0
    avg_error_rate: float = 0.0
    avg_health_score: float = 0.0
    avg_latency_ms: float = 0.0
    intent_distribution: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "session_count": self.session_count,
            "total_turns": self.total_turns,
            "avg_clarification_rate": round(self.avg_clarification_rate, 3),
            "avg_llm_fallback_rate": round(self.avg_llm_fallback_rate, 3),
            "avg_error_rate": round(self.avg_error_rate, 3),
            "avg_health_score": round(self.avg_health_score, 1),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "intent_distribution": dict(self.intent_distribution),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 数据模型：追踪（Tracing）
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Span:
    """
    分布式追踪中的单个 Span。

    v3.0 改进：
      - 使用 nanosecond 精度时间戳
      - 支持 parent_id 构建层级关系
      - 支持 async context manager 语义
    """
    name: str
    start_ns: int
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    parent_id: Optional[str] = None
    end_ns: Optional[int] = None
    status: SpanStatus = SpanStatus.OK
    input_summary: str = ""
    output_summary: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        """计算耗时（毫秒）。"""
        if self.end_ns is None:
            return 0.0
        return (self.end_ns - self.start_ns) / 1_000_000.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "start_ns": self.start_ns,
            "end_ns": self.end_ns,
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status.value,
            "input_summary": self.input_summary[:100],
            "output_summary": self.output_summary[:100],
            "metadata": self.metadata,
        }


@dataclass
class TurnTrace:
    """
    单轮对话的完整链路追踪。

    包含多个 Span，形成树状层级结构。
    """
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    session_id: str = ""
    turn_index: int = 0
    query: str = ""
    spans: List[Span] = field(default_factory=list)
    start_ns: int = field(default_factory=lambda: time.time_ns())
    end_ns: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_duration_ms(self) -> float:
        if self.end_ns is None:
            return (time.time_ns() - self.start_ns) / 1_000_000.0
        return (self.end_ns - self.start_ns) / 1_000_000.0

    @property
    def has_error(self) -> bool:
        return any(s.status == SpanStatus.ERROR for s in self.spans)

    def add_span(self, name: str, **kwargs) -> Span:
        """添加并返回一个 Span。"""
        span = Span(name=name, start_ns=time.time_ns(), **kwargs)
        self.spans.append(span)
        return span

    def finish(self) -> None:
        """标记 trace 结束，自动关闭未关闭的 span。"""
        self.end_ns = time.time_ns()
        for span in self.spans:
            if span.end_ns is None:
                span.end_ns = self.end_ns
                if span.status == SpanStatus.OK:
                    span.status = SpanStatus.TIMEOUT

    def get_span(self, name: str) -> Optional[Span]:
        """按名称查找第一个匹配 span。"""
        for s in self.spans:
            if s.name == name:
                return s
        return None

    def get_span_tree(self) -> Dict[str, Any]:
        """
        构建层级化的 span 树。
        返回以 span_id 为键的嵌套字典结构。
        """
        span_map: Dict[str, Dict[str, Any]] = {}
        for s in self.spans:
            span_map[s.span_id] = {
                "span": s.to_dict(),
                "children": [],
            }
        root_nodes: List[Dict[str, Any]] = []
        for s in self.spans:
            node = span_map[s.span_id]
            if s.parent_id and s.parent_id in span_map:
                span_map[s.parent_id]["children"].append(node)
            else:
                root_nodes.append(node)
        return {"trace_id": self.trace_id, "roots": root_nodes}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id[:8] + "..." if self.session_id else None,
            "turn_index": self.turn_index,
            "query": self.query[:100],
            "total_duration_ms": round(self.total_duration_ms, 3),
            "has_error": self.has_error,
            "span_count": len(self.spans),
            "spans": [s.to_dict() for s in self.spans],
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 数据模型：告警
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Alert:
    """
    告警记录。

    v3.0 改进：
      - 支持 dedup_key 用于去重
      - 支持 metric_tags 用于多维度告警归类
    """
    severity: AlertSeverity
    message: str
    metric_name: str
    threshold: float
    actual_value: float
    timestamp: float
    session_id: Optional[str] = None
    dedup_key: Optional[str] = None
    metric_tags: Dict[str, str] = field(default_factory=dict, hash=False)

    def __post_init__(self):
        # 自动生成去重键
        if self.dedup_key is None:
            key = f"{self.session_id or 'global'}:{self.metric_name}"
            object.__setattr__(self, "dedup_key", key)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity.value,
            "message": self.message,
            "metric_name": self.metric_name,
            "threshold": self.threshold,
            "actual_value": round(self.actual_value, 3),
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "dedup_key": self.dedup_key,
            "metric_tags": self.metric_tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Alert:
        return cls(
            severity=AlertSeverity(data.get("severity", "warning")),
            message=data.get("message", ""),
            metric_name=data.get("metric_name", ""),
            threshold=data.get("threshold", 0.0),
            actual_value=data.get("actual_value", 0.0),
            timestamp=data.get("timestamp", time.time()),
            session_id=data.get("session_id"),
            dedup_key=data.get("dedup_key"),
            metric_tags=data.get("metric_tags", {}),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 数据模型：事件（Event Bus 使用）
# ═══════════════════════════════════════════════════════════════════════════════

class EventType(str, enum.Enum):
    """可观测性事件类型。"""
    LOG_EMITTED = "log_emitted"
    METRIC_RECORDED = "metric_recorded"
    TRACE_STARTED = "trace_started"
    TRACE_ENDED = "trace_ended"
    SPAN_STARTED = "span_started"
    SPAN_ENDED = "span_ended"
    ALERT_TRIGGERED = "alert_triggered"
    SESSION_CLOSED = "session_closed"


@dataclass(frozen=True)
class ObservabilityEvent:
    """
    可观测性统一事件。

    用于内部事件总线，实现各组件间的解耦通信。
    """
    event_type: EventType
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }
