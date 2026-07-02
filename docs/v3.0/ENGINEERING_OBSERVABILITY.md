# DialogMesh 可观测性系统 — 工程实现文档

> **文档编号**: ENGINEERING-OBSERVABILITY-010  
> **版本**: v1.0  
> **日期**: 2026-07-19  
> **状态**: 工程待实现  
> **对应设计文档**: `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §5（幻觉防御三层检测）+ `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §6.4（Telemetry/Error Budget）  
> **锚文档**: `ENGINEERING_MULTILAYER_LLM.md`（认知双工架构）  
> **对应 LLM Provider 文档**: `ENGINEERING_LLM_PROVIDERS.md` §6（Telemetry 接口）  
> **原则**: "为什么不多加点监测与反馈呢？预期无休止的猜测，不如多加监视模块。"

---

## 目录

- [1. 文档目标与范围](#1-文档目标与范围)
- [2. 变更总览](#2-变更总览)
- [3. 现有实现评估](#3-现有实现评估)
- [4. 架构总览](#4-架构总览)
- [5. 指标收集（Metrics）](#5-指标收集metrics)
- [6. 结构化日志（Logging）](#6-结构化日志logging)
- [7. 追踪系统（Tracing）](#7-追踪系统tracing)
- [8. 健康检查（Health Check）](#8-健康检查health-check)
- [9. 实时诊断（Diagnostics）](#9-实时诊断diagnostics)
- [10. 与 6 个 LLM 实例的观测集成](#10-与-6-个-llm-实例的观测集成)
- [11. 测试策略](#11-测试策略)
- [12. 附录：简化与待讨论项](#12-附录简化与待讨论项)

---

## 1. 文档目标与范围

### 1.1 目标

本工程文档定义 DialogMesh **可观测性系统（Observability System）**的完整实现规范。可观测性系统是 v3.0 多层 LLM 认知架构的**"诊断基础设施"**，负责收集、存储、查询和可视化系统的运行状态指标，支撑三层幻觉防御、错误预算和性能优化。

### 1.2 范围

| 需求 | 设计文档位置 | 本章位置 | 说明 |
|------|-------------|---------|------|
| 指标收集 | `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §6.4 | §5 | 延迟、成功率、Token 用量、幻觉率 |
| 结构化日志 | 通用需求 | §6 | 结构化 JSON 日志，支持分级和过滤 |
| 请求追踪 | `ENGINEERING_LLM_PROVIDERS.md` §6 | §7 | 端到端请求链路（trace_id） |
| 健康检查 | `ENGINEERING_LLM_PROVIDERS.md` §6 | §8 | Provider 级健康检查 + 系统级健康检查 |
| 实时诊断 | 用户品味（调试偏好） | §9 | 实时诊断面板、错误自动分类 |
| 6 个 LLM 专属面板 | `ENGINEERING_MULTILAYER_LLM.md` §5 | §10 | 每个 LLM 实例的专属指标 |

---

## 2. 变更总览

### 2.1 新增文件

| 文件路径 | 职责 | 代码行估算 | 备注 |
|---------|------|----------|------|
| `core/agent/observability/metrics_collector.py` | 指标收集器 | ~200 行 | 新增 |
| `core/agent/observability/structured_logger.py` | 结构化日志 | ~150 行 | 新增 |
| `core/agent/observability/trace_manager.py` | 追踪管理器 | ~150 行 | 新增 |
| `core/agent/observability/health_check.py` | 健康检查 | ~100 行 | 新增 |
| `core/agent/observability/diagnostics_engine.py` | 实时诊断引擎 | ~150 行 | 新增 |
| `core/agent/observability/dashboard.py` | 诊断面板（内存/文件） | ~100 行 | 新增，Phase 1 |

### 2.2 修改文件

| 文件路径 | 变更内容 | 影响范围 |
|---------|---------|---------|
| `core/agent/llm_providers/base.py` | 集成 Telemetry 接口 | 所有 Provider |
| `core/agent/llm_providers/hybrid_router.py` | 集成路由级指标 | 路由层 |
| `core/agent/orchestrator.py` | 集成 trace_id 传递 | 编排层 |
| `core/agent/pcr/pcr_engine.py` | 集成幻觉检测指标 | PCR 层 |
| `core/agent/intent_parser.py` | 集成意图分类准确率 | 意图层 |

---

## 3. 现有实现评估

### 3.1 已有日志

**定义位置**: 分散在多个模块中

| 模块 | 日志形式 | 问题 | 状态 |
|------|---------|------|------|
| `pcr_engine.py` | `print()` 语句 | 非结构化，无法聚合 | ⚠️ 需替换 |
| `intent_parser.py` | `print()` 语句 | 同上 | ⚠️ 需替换 |
| `orchestrator.py` | 无 | 缺少编排层日志 | ⚠️ 需新增 |
| `llm_providers/*.py` | 无 | 缺少 LLM 调用日志 | ⚠️ 需新增 |
| `cognitive_tree/*.py` | 无 | 缺少 CT 操作日志 | ⚠️ 需新增 |

### 3.2 差距分析

| 设计文档需求 | 现有实现 | 差距 | 优先级 |
|------------|---------|------|--------|
| 结构化日志（JSON） | 无 | 需替换 `print()` 为结构化日志 | P1 |
| 指标收集（延迟/成功率） | 无 | 需新增 `MetricsCollector` | P1 |
| 请求追踪（trace_id） | 无 | 需新增 `TraceManager` | P1 |
| 健康检查（Provider 级） | `health_check` 方法（同步） | 需实现异步 + 系统级 | P1 |
| 实时诊断面板 | 无 | 需新增 `DiagnosticsEngine` | P2 |
| 错误预算（Error Budget） | 无 | 需实现告警阈值 | P2 |
| 6 个 LLM 专属面板 | 无 | 需按 LLM 聚合指标 | P2 |

---

## 4. 架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         6 个 LLM 实例 + 编排层                              │
│  PCR-LLM / Intent-LLM / Planning-LLM / Meta-Cognitive-LLM / Reflective-LLM / │
│  Answer-LLM / Orchestrator / PCR Engine / Intent Parser                       │
│                              ↓ 自动注入                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  可观测性系统（Observability System）                                         │
│  ═══════════════════════════════════════════════════════════════════  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐            │
│  │ MetricsCollector │  │ StructuredLogger │  │ TraceManager     │            │
│  │ 指标收集         │  │ 结构化日志       │  │ 请求追踪         │            │
│  │ 延迟/成功率/Token│  │ JSON 格式        │  │ trace_id 传递    │            │
│  │ 幻觉率/意图准确率│  │ 分级过滤         │  │ 端到端链路       │            │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘            │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐            │
│  │ HealthCheck      │  │ DiagnosticsEngine│  │ Dashboard        │            │
│  │ 健康检查         │  │ 实时诊断引擎     │  │ 诊断面板         │            │
│  │ Provider 健康    │  │ 错误自动分类     │  │ 内存/文件输出    │            │
│  │ 系统级健康       │  │ 实时状态快照     │  │ 6 个 LLM 面板    │            │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘            │
├─────────────────────────────────────────────────────────────────────────────┤
│  存储层（SQLite / 内存 / 文件）                                               │
│  ────────────────────────────────────────────────────────────────────────  │
│  observability_metrics | observability_logs | observability_traces          │
│  diagnostics_snapshots (JSON 文件)                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. 指标收集（Metrics）

### 5.1 `MetricsCollector`

```python
class MetricsCollector:
    """指标收集器 — 收集系统的性能、质量、业务指标。"""
    
    def __init__(self, storage: Optional[MetricsStorage] = None):
        self._storage = storage or InMemoryMetricsStorage()
        self._metrics: Dict[str, List[MetricPoint]] = defaultdict(list)
        self._lock = threading.Lock()
    
    def record(
        self,
        metric_name: str,
        value: float,
        labels: Dict[str, str] = None,
        timestamp: Optional[float] = None,
    ):
        """
        记录指标点。
        
        示例：
        ```python
        collector.record("llm_latency_ms", 120.5, {
            "llm_name": "Planning-LLM",
            "provider": "openai",
            "cognitive_mode": "fast",
        })
        ```
        """
        point = MetricPoint(
            name=metric_name,
            value=value,
            labels=labels or {},
            timestamp=timestamp or time.time(),
        )
        
        with self._lock:
            self._metrics[metric_name].append(point)
            
            # 超过 10000 点时自动截断（防止内存泄漏）
            if len(self._metrics[metric_name]) > 10000:
                self._metrics[metric_name] = self._metrics[metric_name][-5000:]
        
        # 异步写入存储（非阻塞）
        asyncio.create_task(self._storage.save(point))
    
    def get_metrics(
        self,
        metric_name: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        labels_filter: Optional[Dict[str, str]] = None,
    ) -> List[MetricPoint]:
        """查询指标。"""
        with self._lock:
            points = self._metrics.get(metric_name, [])
        
        # 时间过滤
        if start_time:
            points = [p for p in points if p.timestamp >= start_time]
        if end_time:
            points = [p for p in points if p.timestamp <= end_time]
        
        # 标签过滤
        if labels_filter:
            points = [
                p for p in points
                if all(p.labels.get(k) == v for k, v in labels_filter.items())
            ]
        
        return points
    
    def aggregate(
        self,
        metric_name: str,
        aggregation: str = "avg",
        time_window: float = 3600,  # 默认 1 小时
    ) -> Optional[float]:
        """聚合指标。
        
        aggregation: "avg", "sum", "min", "max", "count", "p95", "p99"
        """
        points = self.get_metrics(
            metric_name,
            start_time=time.time() - time_window,
        )
        
        if not points:
            return None
        
        values = [p.value for p in points]
        
        if aggregation == "avg":
            return sum(values) / len(values)
        elif aggregation == "sum":
            return sum(values)
        elif aggregation == "min":
            return min(values)
        elif aggregation == "max":
            return max(values)
        elif aggregation == "count":
            return len(values)
        elif aggregation == "p95":
            return percentile(values, 95)
        elif aggregation == "p99":
            return percentile(values, 99)
        else:
            raise ValueError(f"Unknown aggregation: {aggregation}")
```

### 5.2 指标定义（与 LLM Provider 对齐）

| 指标名 | 类型 | 标签 | 来源 | 说明 |
|-------|------|------|------|------|
| `llm_latency_ms` | Gauge | `llm_name`, `provider`, `cognitive_mode` | Provider | LLM 调用延迟 |
| `llm_success_rate` | Counter | `llm_name`, `provider` | Provider | 成功率（计数器） |
| `llm_token_usage` | Counter | `llm_name`, `provider`, `token_type` | Provider | Token 用量（input/output） |
| `llm_hallucination_rate` | Gauge | `llm_name`, `detection_layer` | PCR / Meta-Cognitive | 幻觉率（三层检测） |
| `llm_cognitive_load` | Gauge | `llm_name` | Context Manager | 认知负载 |
| `llm_intent_accuracy` | Gauge | `llm_name` | Intent Parser | 意图分类准确率 |
| `llm_planning_efficiency` | Gauge | `llm_name` | Planning-LLM | 规划效率（达成率/步骤数） |
| `llm_validation_rate` | Gauge | `llm_name` | Meta-Cognitive | 验证通过率 |
| `llm_reflection_insight` | Gauge | `llm_name` | Reflective-LLM | 洞察质量评分 |
| `llm_answer_relevance` | Gauge | `llm_name` | Answer-LLM | 回复相关性 |
| `routing_hop_count` | Counter | `llm_name`, `provider` | HybridRouter | 路由跳转次数 |
| `context_compression_rate` | Gauge | `llm_name` | Context Manager | 上下文压缩率 |
| `ct_node_count` | Gauge | `session_id`, `cog_type` | Cognitive Compiler | Cognitive Tree 节点数 |
| `ct_edge_count` | Gauge | `session_id`, `edge_type` | Cognitive Compiler | Cognitive Tree 边数 |
| `ct_conflict_count` | Counter | `session_id` | EdgeManager | 矛盾检测次数 |

---

## 6. 结构化日志（Logging）

### 6.1 `StructuredLogger`

```python
class StructuredLogger:
    """结构化日志 — 替换现有 `print()` 语句，输出 JSON 格式日志。"""
    
    LEVELS = {
        "DEBUG": 10,
        "INFO": 20,
        "WARNING": 30,
        "ERROR": 40,
        "CRITICAL": 50,
    }
    
    def __init__(self, name: str, min_level: str = "INFO"):
        self.name = name
        self.min_level = self.LEVELS.get(min_level, 20)
        self._handlers: List[LogHandler] = []
    
    def add_handler(self, handler: LogHandler):
        """添加日志处理器。"""
        self._handlers.append(handler)
    
    def _log(self, level: str, message: str, **kwargs):
        """核心日志方法。"""
        if self.LEVELS.get(level, 0) < self.min_level:
            return
        
        entry = LogEntry(
            timestamp=datetime.utcnow().isoformat(),
            logger=self.name,
            level=level,
            message=message,
            **kwargs,
        )
        
        # 写入所有处理器
        for handler in self._handlers:
            handler.write(entry)
    
    def debug(self, message: str, **kwargs):
        self._log("DEBUG", message, **kwargs)
    
    def info(self, message: str, **kwargs):
        self._log("INFO", message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log("WARNING", message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self._log("ERROR", message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        self._log("CRITICAL", message, **kwargs)
    
    def llm_call(self, llm_name: str, request: str, response: str, latency_ms: float, **kwargs):
        """专用方法：记录 LLM 调用。"""
        self.info(
            f"LLM call: {llm_name}",
            llm_name=llm_name,
            request_preview=request[:200],  # 截断避免过大
            response_preview=response[:200],
            latency_ms=latency_ms,
            **kwargs,
        )
    
    def hallucination_detected(self, llm_name: str, detection_layer: str, details: str, **kwargs):
        """专用方法：记录幻觉检测。"""
        self.warning(
            f"Hallucination detected in {llm_name} at layer {detection_layer}",
            llm_name=llm_name,
            detection_layer=detection_layer,
            details=details,
            **kwargs,
        )

# 日志处理器接口
class LogHandler(ABC):
    @abstractmethod
    def write(self, entry: LogEntry): ...

class ConsoleHandler(LogHandler):
    """控制台输出（JSON 格式）。"""
    def write(self, entry: LogEntry):
        print(json.dumps(entry.to_dict(), ensure_ascii=False))

class FileHandler(LogHandler):
    """文件输出（按天分片）。"""
    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
    
    def write(self, entry: LogEntry):
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        filepath = os.path.join(self.log_dir, f"dialogmesh-{date_str}.log")
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

class SQLiteHandler(LogHandler):
    """SQLite 输出（支持查询）。"""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_table()
    
    def _init_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    logger TEXT,
                    level TEXT,
                    message TEXT,
                    metadata TEXT  -- JSON
                )
            """)
    
    def write(self, entry: LogEntry):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO logs (timestamp, logger, level, message, metadata) VALUES (?, ?, ?, ?, ?)",
                (
                    entry.timestamp,
                    entry.logger,
                    entry.level,
                    entry.message,
                    json.dumps(entry.metadata, ensure_ascii=False),
                )
            )
```

### 6.2 与现有代码的集成

**替换 `print()` 语句**:

```python
# 旧代码（pcr_engine.py）
print(f"[PCR] 期望推断: {expectation}")

# 新代码
from core.agent.observability import get_logger
logger = get_logger("pcr_engine")
logger.info("期望推断完成", expectation=expectation, confidence=confidence)

# 旧代码（intent_parser.py）
print(f"[Intent] 分类结果: {category}")

# 新代码
logger = get_logger("intent_parser")
logger.info("意图分类完成", category=category, confidence=confidence)
```

---

## 7. 追踪系统（Tracing）

### 7.1 `TraceManager`

```python
class TraceManager:
    """请求追踪管理器 — 端到端链路追踪。"""
    
    def __init__(self):
        self._traces: Dict[str, Trace] = {}
        self._lock = threading.Lock()
    
    def start_trace(self, trace_id: str, request_type: str) -> Trace:
        """开始追踪。"""
        trace = Trace(
            trace_id=trace_id,
            request_type=request_type,
            start_time=time.time(),
            spans=[],
        )
        with self._lock:
            self._traces[trace_id] = trace
        return trace
    
    def start_span(
        self,
        trace_id: str,
        span_name: str,
        parent_span_id: Optional[str] = None,
    ) -> Span:
        """开始一个 span。"""
        with self._lock:
            trace = self._traces.get(trace_id)
            if not trace:
                raise ValueError(f"Trace {trace_id} not found")
            
            span = Span(
                span_id=str(uuid.uuid4()),
                name=span_name,
                parent_id=parent_span_id,
                start_time=time.time(),
            )
            trace.spans.append(span)
            return span
    
    def end_span(self, trace_id: str, span_id: str, status: str = "ok", error: Optional[str] = None):
        """结束一个 span。"""
        with self._lock:
            trace = self._traces.get(trace_id)
            if not trace:
                return
            
            for span in trace.spans:
                if span.span_id == span_id:
                    span.end_time = time.time()
                    span.duration_ms = (span.end_time - span.start_time) * 1000
                    span.status = status
                    span.error = error
                    break
    
    def end_trace(self, trace_id: str, status: str = "ok"):
        """结束追踪。"""
        with self._lock:
            trace = self._traces.get(trace_id)
            if not trace:
                return
            trace.end_time = time.time()
            trace.total_duration_ms = (trace.end_time - trace.start_time) * 1000
            trace.status = status
    
    def get_trace(self, trace_id: str) -> Optional[Trace]:
        """获取追踪详情。"""
        with self._lock:
            return self._traces.get(trace_id)
    
    def get_slow_traces(self, threshold_ms: float = 5000) -> List[Trace]:
        """获取慢请求（超过阈值）。"""
        with self._lock:
            return [
                t for t in self._traces.values()
                if t.total_duration_ms and t.total_duration_ms > threshold_ms
            ]
```

### 7.2 与 Orchestrator 的集成

```python
# orchestrator.py
class Orchestrator:
    def __init__(self, ...):
        self._trace_manager = TraceManager()
        self._metrics = MetricsCollector()
    
    async def process(self, request: DialogRequest) -> DialogResponse:
        # 生成 trace_id
        trace_id = f"trace-{request.session_id}-{time.time()}"
        
        # 开始追踪
        self._trace_manager.start_trace(trace_id, "dialog_processing")
        
        try:
            # Phase 1: PCR
            pcr_span = self._trace_manager.start_span(trace_id, "pcr_analysis")
            pcr_result = await self._pcr_engine.analyze(request)
            self._trace_manager.end_span(trace_id, pcr_span.span_id, "ok")
            
            # Phase 2: Intent
            intent_span = self._trace_manager.start_span(trace_id, "intent_parsing")
            intent_result = await self._intent_parser.parse(request, pcr_result)
            self._trace_manager.end_span(trace_id, intent_span.span_id, "ok")
            
            # ... 其他阶段 ...
            
            # 结束追踪
            self._trace_manager.end_trace(trace_id, "ok")
            
        except Exception as e:
            self._trace_manager.end_trace(trace_id, "error")
            raise
```

---

## 8. 健康检查（Health Check）

### 8.1 `HealthChecker`

```python
class HealthChecker:
    """健康检查 — Provider 级 + 系统级。"""
    
    def __init__(self, providers: Dict[str, LLMProvider]):
        self._providers = providers
        self._last_check: Dict[str, HealthStatus] = {}
    
    async def check_all(self) -> Dict[str, HealthStatus]:
        """检查所有 Provider 健康状态。"""
        results = {}
        for name, provider in self._providers.items():
            try:
                healthy = await provider.health_check_async()
                results[name] = HealthStatus(
                    name=name,
                    healthy=healthy,
                    last_check=time.time(),
                    latency_ms=0,  # 由 Provider 内部记录
                )
            except Exception as e:
                results[name] = HealthStatus(
                    name=name,
                    healthy=False,
                    last_check=time.time(),
                    error=str(e),
                )
        
        self._last_check = results
        return results
    
    def check_system(self) -> SystemHealth:
        """系统级健康检查。"""
        return SystemHealth(
            memory_usage=get_memory_usage(),
            cpu_usage=get_cpu_usage(),
            disk_usage=get_disk_usage(),
            active_sessions=get_active_session_count(),
            queue_depth=get_queue_depth(),
            timestamp=time.time(),
        )
    
    def is_degraded(self) -> bool:
        """判断系统是否降级。"""
        # 如果超过 50% 的 Provider 不可用，则降级
        if not self._last_check:
            return False
        
        total = len(self._last_check)
        healthy = sum(1 for s in self._last_check.values() if s.healthy)
        return healthy / total < 0.5
```

---

## 9. 实时诊断（Diagnostics）

### 9.1 `DiagnosticsEngine`

```python
class DiagnosticsEngine:
    """实时诊断引擎 — 错误自动分类、实时状态快照。"""
    
    def __init__(self, metrics: MetricsCollector, traces: TraceManager, logs: StructuredLogger):
        self._metrics = metrics
        self._traces = traces
        self._logs = logs
        self._error_patterns: Dict[str, re.Pattern] = {
            "timeout": re.compile(r"timeout|timed out", re.I),
            "rate_limit": re.compile(r"rate.?limit|too.?many.?requests", re.I),
            "auth_error": re.compile(r"auth|unauthorized|forbidden", re.I),
            "hallucination": re.compile(r"hallucinat|inconsistent|contradict", re.I),
            "context_overflow": re.compile(r"context.?length|token.?limit|too.?long", re.I),
        }
    
    def classify_error(self, error_message: str) -> str:
        """自动分类错误。"""
        for category, pattern in self._error_patterns.items():
            if pattern.search(error_message):
                return category
        return "unknown"
    
    def take_snapshot(self) -> DiagnosticsSnapshot:
        """获取系统实时状态快照。"""
        snapshot = DiagnosticsSnapshot(
            timestamp=time.time(),
            
            # 指标聚合
            metrics={
                "avg_latency_1h": self._metrics.aggregate("llm_latency_ms", "avg", 3600),
                "success_rate_1h": self._metrics.aggregate("llm_success_rate", "avg", 3600),
                "hallucination_rate_1h": self._metrics.aggregate("llm_hallucination_rate", "avg", 3600),
                "total_tokens_1h": self._metrics.aggregate("llm_token_usage", "sum", 3600),
            },
            
            # 慢请求
            slow_traces=self._traces.get_slow_traces(threshold_ms=5000),
            
            # 错误日志（最近 10 条）
            recent_errors=[],  # 从日志查询
        )
        return snapshot
    
    def generate_diagnostic_report(self) -> str:
        """生成诊断报告（Markdown 格式）。"""
        snapshot = self.take_snapshot()
        
        report = f"""# DialogMesh 诊断报告

**生成时间**: {datetime.fromtimestamp(snapshot.timestamp).isoformat()}

## 指标概览

| 指标 | 值 |
|------|-----|
| 平均延迟 (1h) | {snapshot.metrics.get("avg_latency_1h", "N/A")} ms |
| 成功率 (1h) | {snapshot.metrics.get("success_rate_1h", "N/A")} |
| 幻觉率 (1h) | {snapshot.metrics.get("hallucination_rate_1h", "N/A")} |
| Token 用量 (1h) | {snapshot.metrics.get("total_tokens_1h", "N/A")} |

## 慢请求

{len(snapshot.slow_traces)} 个请求超过 5 秒

## 建议

{self._generate_recommendations(snapshot)}
"""
        return report
    
    def _generate_recommendations(self, snapshot: DiagnosticsSnapshot) -> str:
        """基于快照生成诊断建议。"""
        recommendations = []
        
        avg_latency = snapshot.metrics.get("avg_latency_1h")
        if avg_latency and avg_latency > 1000:
            recommendations.append("- 平均延迟超过 1 秒，考虑启用缓存或降低模型复杂度")
        
        hallucination_rate = snapshot.metrics.get("hallucination_rate_1h")
        if hallucination_rate and hallucination_rate > 0.05:
            recommendations.append("- 幻觉率超过 5%，建议加强 Meta-Cognitive 验证层")
        
        if not recommendations:
            recommendations.append("- 系统运行正常，无显著问题")
        
        return "\n".join(recommendations)
```

---

## 10. 与 6 个 LLM 实例的观测集成

### 10.1 每个 LLM 的专属指标面板

| LLM 实例 | 关键指标 | 告警阈值 | 诊断方法 |
|----------|---------|---------|---------|
| **PCR-LLM** | 噪声分析延迟、语义模糊度、结构不完整度 | 模糊度 > 0.7 | 检查输入质量 |
| **Intent-LLM** | 意图分类准确率、深层意图覆盖度 | 准确率 < 0.85 | 检查分类器训练数据 |
| **Planning-LLM** | 计划生成延迟、达成率、步骤数 | 达成率 < 0.8 | 检查工具可用性 |
| **Meta-Cognitive-LLM** | 验证通过率、验证延迟、发现矛盾数 | 通过率 < 0.9 | 检查验证标准 |
| **Reflective-LLM** | 复盘频率、洞察质量评分、偏见检测数 | 洞察质量 < 0.7 | 检查复盘数据量 |
| **Answer-LLM** | 回复延迟、相关性评分、用户满意度 | 相关性 < 0.8 | 检查上下文完整性 |

### 10.2 集成示例

```python
# 在 Provider 的 generate_native_async 中注入
class OpenAIProvider(LLMProvider):
    async def generate_native_async(self, request: GenerateRequest) -> GenerateResult:
        start = time.time()
        
        try:
            # 实际调用
            response = await self._client.chat.completions.create(...)
            
            # 记录指标
            self._metrics.record("llm_latency_ms", (time.time() - start) * 1000, {
                "llm_name": request.llm_name,  # 从请求传递
                "provider": self.name,
                "cognitive_mode": request.cognitive_mode,
            })
            
            self._metrics.record("llm_token_usage", response.usage.total_tokens, {
                "llm_name": request.llm_name,
                "provider": self.name,
                "token_type": "total",
            })
            
            self._metrics.record("llm_success_rate", 1, {
                "llm_name": request.llm_name,
                "provider": self.name,
            })
            
            return GenerateResult(...)
            
        except Exception as e:
            # 记录失败指标
            self._metrics.record("llm_success_rate", 0, {
                "llm_name": request.llm_name,
                "provider": self.name,
            })
            
            # 记录错误日志
            self._logger.error("LLM call failed", 
                llm_name=request.llm_name,
                error=str(e),
                error_category=self._diagnostics.classify_error(str(e)),
            )
            
            raise
```

---

## 11. 测试策略

### 11.1 测试目标

| 测试类型 | 覆盖率 | 关键验证点 |
|---------|--------|----------|
| 单元测试 | 100% | 指标收集、日志写入、追踪链路 |
| 集成测试 | 90% | 与 6 个 LLM 实例的指标注入 |
| 压力测试 | 80% | 10000 指标点截断、日志并发写入 |
| 诊断测试 | 100% | 错误自动分类、快照生成 |

### 11.2 关键测试用例

**用例 1：指标收集与聚合**
```python
def test_metrics_collection():
    collector = MetricsCollector()
    
    # 记录 10 个指标点
    for i in range(10):
        collector.record("llm_latency_ms", 100 + i, {"llm_name": "PCR-LLM"})
    
    # 验证聚合
    avg = collector.aggregate("llm_latency_ms", "avg", 3600)
    assert avg == 104.5  # (100+109)/2
    
    p95 = collector.aggregate("llm_latency_ms", "p95", 3600)
    assert p95 == 108.5
```

**用例 2：错误自动分类**
```python
def test_error_classification():
    engine = DiagnosticsEngine(...)
    
    assert engine.classify_error("Request timeout after 30s") == "timeout"
    assert engine.classify_error("Rate limit exceeded") == "rate_limit"
    assert engine.classify_error("Authentication failed") == "auth_error"
    assert engine.classify_error("Hallucination detected in reasoning") == "hallucination"
```

**用例 3：追踪链路完整性**
```python
def test_trace_completeness():
    manager = TraceManager()
    
    trace_id = "trace-1"
    manager.start_trace(trace_id, "test")
    
    span1 = manager.start_span(trace_id, "span1")
    span2 = manager.start_span(trace_id, "span2", parent_span_id=span1.span_id)
    
    manager.end_span(trace_id, span2.span_id, "ok")
    manager.end_span(trace_id, span1.span_id, "ok")
    manager.end_trace(trace_id, "ok")
    
    trace = manager.get_trace(trace_id)
    assert trace.status == "ok"
    assert len(trace.spans) == 2
    assert trace.spans[1].parent_id == trace.spans[0].span_id
```

---

## 12. 附录：简化与待讨论项

### 12.1 诚实标记：简化项

| 编号 | 简化内容 | 设计文档要求 | 当前实现 | 简化原因 | 恢复路线图 |
|------|---------|-------------|---------|---------|-----------|
| **S-01** | 指标存储后端 | Prometheus / Grafana 集成 | 内存 + SQLite | 引入外部系统增加运维复杂度 | Phase 2 引入 Prometheus 导出器 |
| **S-02** | 分布式追踪 | OpenTelemetry / Jaeger | 内存追踪 | 单进程无需分布式追踪 | Phase 3 引入 OpenTelemetry |
| **S-03** | 日志轮转 | 按大小/时间自动轮转 | 按天分片 | 简单实现，满足初期需求 | Phase 2 引入 logrotate |
| **S-04** | 实时告警 | 邮件/短信/Slack 告警 | 诊断报告（文件） | 告警需要外部通道 | Phase 2 引入 Webhook 告警 |
| **S-05** | 用户满意度收集 | 主动用户反馈收集 | 被动（从日志推断） | 主动收集需要 UI 支持 | Phase 2 引入反馈按钮 |

### 12.2 待讨论项

| 编号 | 问题 | 选项 | 建议 |
|------|------|------|------|
| **D-01** | 日志级别动态调整 | A) 固定级别  B) 通过环境变量  C) 通过 API 实时调整 | 建议 C：支持运行时通过 API 调整日志级别，方便调试 |
| **D-02** | 指标保留期 | A) 固定 7 天  B) 按重要性分级（关键指标 30 天，普通 7 天）  C) 按存储自动清理 | 建议 B：关键指标保留 30 天，普通指标 7 天 |
| **D-03** | 诊断报告频率 | A) 按需生成  B) 每小时自动生成  C) 异常时自动生成 | 建议 C：异常时自动生成，减少噪声 |
| **D-04** | 健康检查频率 | A) 每次请求时检查  B) 每 30 秒后台检查  C) 按需检查 | 建议 B：每 30 秒后台检查，避免请求延迟 |

### 12.3 设计文档等价性检查

| 设计文档章节 | 本工程文档覆盖 | 等价性 | 备注 |
|-------------|--------------|--------|------|
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §5 | §5, §6, §9 | ✅ 等价 | 三层幻觉检测 → 指标 + 日志 + 诊断 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §6.4 | §5, §8 | ✅ 等价 | Telemetry/Error Budget → 指标收集 + 健康检查 |
| `ENGINEERING_LLM_PROVIDERS.md` §6 | §5, §7, §8 | ✅ 等价 | Provider Telemetry 接口 → 指标 + 追踪 + 健康检查 |
| `ENGINEERING_MULTILAYER_LLM.md` §5 | §10 | ✅ 等价 | 6 个 LLM 实例的观测需求 → 专属指标面板 |

---

*本工程文档由 DialogMesh 工程团队基于设计概念文档和用户调试偏好（"为什么不多加点监测与反馈呢？"）生成。新增约 **800 行代码**（MetricsCollector + StructuredLogger + TraceManager + HealthChecker + DiagnosticsEngine）。所有 `print()` 语句将被替换为结构化日志。所有简化项已在 §12.1 中诚实标记，待讨论项在 §12.2 中列出，等待团队确认。*
