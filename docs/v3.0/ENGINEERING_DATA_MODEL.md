# DialogMesh 全系统数据模型 — 工程实现文档

> **文档编号**: ENGINEERING-DATA-MODEL-001  
> **版本**: v1.0  
> **日期**: 2026-07-19  
> **状态**: 工程待实现  
> **对应设计文档**: `DESIGN_FULL_CONCEPT.md` §1.3（核心数据契约）+ `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §4.2（Cognitive Tree）
> **锚文档**: `ENGINEERING_MULTILAYER_LLM.md`（认知双工架构）  
> **对应代码**: `core/agent/models.py`（现有）、`core/agent/serialization.py`（现有）  
> **原则**: 必须实现设计概念文档的完整数据契约，任何简化均需诚实标记。

---

## 目录

- [1. 文档目标与范围](#1-文档目标与范围)
- [2. 变更总览](#2-变更总览)
- [3. 核心数据模型架构](#3-核心数据模型架构)
- [4. Layer 0 数据模型（PCR 输出）](#4-layer-0-数据模型pcr-输出)
- [5. Layer 1 数据模型（意图解析）](#5-layer-1-数据模型意图解析)
- [6. Layer 1.5 数据模型（规划与工具）](#6-layer-15-数据模型规划与工具)
- [7. Layer 2 数据模型（对话状态）](#7-layer-2-数据模型对话状态)
- [8. Layer 3 数据模型（服务接口）](#8-layer-3-数据模型服务接口)
- [9. 横切数据模型（认知画像 v2.0）](#9-横切数据模型认知画像-v20)
- [10. 横切数据模型（记忆系统）](#10-横切数据模型记忆系统)
- [11. 横切数据模型（可观测性）](#11-横切数据模型可观测性)
- [12. v3.0 新增数据模型（LLM 认知层）](#12-v30-新增数据模型llm-认知层)
- [13. 序列化与持久化](#13-序列化与持久化)
- [14. 版本兼容策略](#14-版本兼容策略)
- [15. 测试策略](#15-测试策略)
- [16. 附录：简化与待讨论项](#16-附录简化与待讨论项)

---

## 1. 文档目标与范围

### 1.1 目标

本工程文档定义 DialogMesh 全系统的**数据模型规范**，作为所有模块的"施工蓝图"。所有模块的实现必须遵守本规范的数据结构、字段语义、类型约束和默认值。

### 1.2 范围

覆盖设计文档 `DESIGN_FULL_CONCEPT.md` §1.3 中定义的 **7 个核心数据契约**：

| 数据契约 | 设计文档位置 | 本章位置 | 说明 |
|---------|-------------|---------|------|
| `UserInput` | §1.3 | §8 | 用户原始输入 |
| `PCROutput` | §1.3 | §4 | PCR 路由输出 |
| `Intent` | §1.3 | §5 | 解析后的意图 |
| `TaskGraph` | §1.3 | §6 | 任务依赖图 |
| `DialogueState` | §1.3 | §7 | 对话状态（Topic Tree + Context Window） |
| `CognitiveProfileV2` | §1.3 | §9 | 双轨用户画像 |
| `MemorySnapshot` | §1.3 | §10.2 | 记忆快照（chunks + weights + stage_transitions） |

新增 v3.0 的 `CognitiveTree` 数据契约（§12）。

### 1.3 诚实标记原则

> ⚠️ **工程原则**：本规范要求实现设计文档的全部字段和语义。如果实现中必须简化（如性能限制、库依赖冲突、时间约束），必须在 §16 中明确标记，并给出：
> - 简化内容
> - 简化原因
> - 等效替代方案（如果有）
> - 恢复完整实现的路线图

---

## 2. 变更总览

### 2.1 新增文件

| 文件路径 | 职责 | 代码行估算 | 备注 |
|---------|------|----------|------|
| `core/agent/models_v3.py` | 全系统数据模型（v3.0 统一版本） | ~800 行 | 合并现有 models.py 的所有模型，新增 v3.0 字段 |
| `core/agent/models/__init__.py` | 包导出 | ~50 行 | 向后兼容别名 |
| `core/agent/models/layer0.py` | PCR 相关模型 | ~150 行 | 从 models_v3 中拆分 |
| `core/agent/models/layer1.py` | 意图解析相关模型 | ~200 行 | 从 models_v3 中拆分 |
| `core/agent/models/layer1_5.py` | 规划与工具相关模型 | ~200 行 | 从 models_v3 中拆分 |
| `core/agent/models/layer2.py` | 对话状态相关模型 | ~150 行 | 从 models_v3 中拆分 |
| `core/agent/models/crosscutting.py` | 横切关注点模型 | ~250 行 | 画像 + 记忆 + 可观测性 |
| `core/agent/models/v3_llm.py` | v3.0 LLM 认知层模型 | ~150 行 | CognitiveTree 等新增 |
| `core/agent/serialization_v3.py` | v3.0 序列化器 | ~200 行 | 支持版本化序列化 |

### 2.2 修改文件

| 文件路径 | 变更内容 | 影响范围 |
|---------|---------|---------|
| `core/agent/models.py` | 标记为 `DEPRECATED`，内部实现转发到 `models_v3` | 向后兼容 |
| `core/agent/serialization.py` | 新增 `VersionedSerializer` 类，支持 `to_dict(version=3)` | 序列化 |

### 2.3 向后兼容

- 现有 `models.py` 的所有导出类保留，但内部实现委托给 `models_v3` 的对应类。
- 序列化时默认输出 v3.0 格式，但支持 `version=2` 参数降级输出。
- 读取时自动检测版本号：`v2` 格式自动迁移到 `v3` 格式（缺失字段填充默认值）。

---

## 3. 核心数据模型架构

### 3.1 设计原则

**原则 1：纯数据容器**  
所有模型类为 `frozen=True` 或 `frozen=False` 的 `@dataclass`，不含业务逻辑方法（`to_dict`/`from_dict` 除外）。业务逻辑放在对应的服务类中。

**原则 2：版本化字段**  
每个模型包含 `__version__: str = "3.0"` 字段，用于序列化版本检测和向后兼容迁移。

**原则 3：可空性策略**  
- 可选字段使用 `Optional[T]`，默认值为 `None`。
- 关键字段（如 `session_id`）使用 `str` 且必须提供，无默认值。
- 列表/字典字段使用 `field(default_factory=list/dict)`，永不使用 `None` 作为默认值。

**原则 4：时间戳统一**  
所有时间戳使用 `float`（`time.time()`），而非 `datetime` 对象。序列化时自动转换为 ISO 8601 字符串。

**原则 5：枚举优先**  
状态、类型、模式等字段优先使用 `Enum`，而非裸字符串。

### 3.2 模型分层结构

```
core/agent/models/
├── __init__.py          # 统一导出，向后兼容别名
├── base.py              # 共享基类和工具（BaseModel, VersionedMixin, TimestampMixin）
├── layer0.py            # PCR 输出模型
├── layer1.py            # 意图解析模型（Intent, Entity, Ambiguity, TaskGraph, etc.）
├── layer1_5.py          # 规划与工具模型（ToolSchema, PlanningSkill, PlanResult, etc.）
├── layer2.py            # 对话状态模型（TopicTreeNode, ContextWindow, DialogueState, etc.）
├── layer3.py            # 服务接口模型（UserInput, Session, ResponsePayload, etc.）
├── crosscutting.py      # 横切关注点（CognitiveProfileV2, MemoryChunk, TelemetryEvent, etc.）
└── v3_llm.py            # v3.0 新增（CognitiveTreeNode, CognitiveTree, etc.）
```

---

## 4. Layer 0 数据模型（PCR 输出）

### 4.1 模型：`PCROutput`（设计文档 §2.4）

**实现方式**：`@dataclass(frozen=False)`，因为 PCR 输出可能在后续层被更新（如 Meta-Cognitive 层修正期望类型）。

```python
@dataclass
class PCROutput:
    """PCR 路由输出 — 后续所有层的控制信号。"""
    
    __version__: str = "3.0"
    
    # ── 核心推断 ────────────────────────────────
    expectation: UserExpectation = UserExpectation.UNKNOWN
    noise_level: float = 0.0          # [0, 1]，噪声度量
    complexity_level: float = 0.0    # [0, 1]，任务复杂度
    
    # ── 认知快照 ────────────────────────────────
    cognitive_profile: PCR_CognitiveSnapshot = field(default_factory=PCR_CognitiveSnapshot)
    # 设计文档 §2.2.3：四维度快速评估（元认知、发散性、稳定性、信心度）
    
    # ── 执行策略 ────────────────────────────────
    execution_mode: ExecutionMode = ExecutionMode.BALANCED
    # 枚举：CONSERVATIVE / BALANCED / AGGRESSIVE
    
    # ── 解析器参数覆盖 ──────────────────────────
    parser_config_overrides: Dict[str, Any] = field(default_factory=dict)
    # 如 {"auto_resolve_threshold": 0.7, "max_ambiguities_before_ask": 3}
    
    # ── 元数据 ─────────────────────────────────
    trace_log: List[str] = field(default_factory=list)  # PCR 决策轨迹
    created_at: float = field(default_factory=time.time)
    session_id: Optional[str] = None
    
    # ── 校验 ───────────────────────────────────
    def __post_init__(self):
        # 约束：noise_level 必须在 [0, 1]
        self.noise_level = max(0.0, min(1.0, self.noise_level))
        self.complexity_level = max(0.0, min(1.0, self.complexity_level))
```

### 4.2 子模型：`PCR_CognitiveSnapshot`

```python
@dataclass
class PCR_CognitiveSnapshot:
    """PCR 快速认知快照 — 四维度。"""
    
    metacognition: float = 0.0    # 元认知：输入精确性 + 自指性语言
    divergence: float = 0.0       # 发散性：主题切换频率 + 词汇多样性
    stability: float = 0.0      # 稳定性：表达风格一致性
    confidence: float = 0.0      # 信心度：情态动词频率的反面
    
    def __post_init__(self):
        for field_name in ["metacognition", "divergence", "stability", "confidence"]:
            value = getattr(self, field_name)
            setattr(self, field_name, max(0.0, min(1.0, value)))
```

### 4.3 枚举定义

```python
class UserExpectation(Enum):
    """用户期望类型 — 设计文档 §2.2.2。"""
    TOOL = "tool"
    ADVISOR = "advisor"
    COMPANION = "companion"
    UNKNOWN = "unknown"

class ExecutionMode(Enum):
    """执行模式 — 控制系统的保守/激进程度。"""
    CONSERVATIVE = "conservative"  # 高确认，低误报，适合金融/医疗
    BALANCED = "balanced"          # 默认平衡
    AGGRESSIVE = "aggressive"      # 快速响应，高误报容忍，适合探索性场景
```

---

## 5. Layer 1 数据模型（意图解析）

### 5.1 模型：`Intent`（设计文档 §3.3）

**实现方式**：`@dataclass(frozen=False)`，因为歧义消解可能修改 `ambiguities` 列表。

```python
@dataclass
class Intent:
    """解析后的意图 — Layer 1 的核心输出。"""
    
    __version__: str = "3.0"
    
    # ── 标识 ───────────────────────────────────
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    session_id: Optional[str] = None
    
    # ── 分类 ───────────────────────────────────
    category: IntentCategory = IntentCategory.UNKNOWN
    raw_input: str = ""              # 用户原始输入
    normalized_input: str = ""       # 规范化后的输入（预处理输出）
    
    # ── 实体 ───────────────────────────────────
    entities: List[Entity] = field(default_factory=list)
    
    # ── 置信度 ─────────────────────────────────
    confidence: float = 0.0          # 整体分类置信度
    
    # ── 多意图 ─────────────────────────────────
    sub_intents: List["Intent"] = field(default_factory=list)
    
    # ── 上下文标志 ─────────────────────────────
    requires_process: bool = True     # 是否需要附加进程
    is_destructive: bool = False      # 是否涉及写操作
    is_reversible: bool = False     # 是否可撤销
    
    # ── 歧义 ───────────────────────────────────
    ambiguities: List[Ambiguity] = field(default_factory=list)
    
    # ── 约束 ───────────────────────────────────
    temporal_constraint: Optional[str] = None   # 时间约束（如"5秒后"）
    scope_constraint: Optional[str] = None    # 范围约束（如"只扫描这个区域"）
    
    # ── 元数据 ─────────────────────────────────
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # ── 方法 ───────────────────────────────────
    def is_ambiguous(self) -> bool:
        return len(self.ambiguities) > 0 or len(self.sub_intents) > 1
    
    def get_entities(self, entity_type: EntityType) -> List[Entity]:
        return [e for e in self.entities if e.type == entity_type]
    
    def get_entity(self, entity_type: EntityType) -> Optional[Entity]:
        for e in self.entities:
            if e.type == entity_type:
                return e
        return None
```

### 5.2 子模型：`Entity`

```python
@dataclass(frozen=True)
class Entity:
    """提取的实体 — 不可变，确保跨轮引用安全。"""
    
    type: EntityType
    value: Any                        # 实际值（地址、数值、字符串等）
    raw_text: str = ""               # 原始文本子串
    confidence: float = 1.0          # 提取置信度 [0, 1]
    start_pos: int = -1              # 在输入中的起始位置
    end_pos: int = -1                # 在输入中的结束位置
    
    # 元认知标记：该实体是否继承自历史
    metadata: Dict[str, Any] = field(default_factory=dict)
    # 如 {"inherited": True, "source_turn": 5, "original_confidence": 0.9}
    
    def __post_init__(self):
        # 冻结后修改必须通过 object.__setattr__
        if not (0.0 <= self.confidence <= 1.0):
            object.__setattr__(self, "confidence", max(0.0, min(1.0, self.confidence)))
```

### 5.3 子模型：`Ambiguity`

```python
@dataclass
class Ambiguity:
    """检测到的歧义 — 需要澄清或自动消解。"""
    
    type: AmbiguityType
    description: str                  # 人类可读的歧义描述
    affected_entities: List[EntityType] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)  # 建议选项
    auto_resolvable: bool = False     # 是否可自动消解
    default_choice: Optional[str] = None  # 自动消解的默认值
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 5.4 枚举定义

```python
class IntentCategory(Enum):
    """意图类别 — 设计文档 §3.3.4 规则映射。"""
    # Memory
    SCAN_MEMORY = "scan_memory"
    READ_MEMORY = "read_memory"
    WRITE_MEMORY = "write_memory"
    RESOLVE_POINTER = "resolve_pointer"
    # Code
    DISASSEMBLE = "disassemble"
    DECOMPILE = "decompile"
    ANALYZE_PROTECTION = "analyze_protection"
    DEOBFUSCATE = "deobfuscate"
    UNPACK = "unpack"
    # Dynamic
    SET_BREAKPOINT = "set_breakpoint"
    GET_BREAKPOINT_HITS = "get_breakpoint_hits"
    TRACE_EXECUTION = "trace_execution"
    # Pattern
    FIND_PATTERN = "find_pattern"
    PATTERN_DETECT = "pattern_detect"
    # Symbolic
    BUILD_CFG = "build_cfg"
    SYMBOLIC_EXECUTE = "symbolic_execute"
    SOLVE_CONSTRAINTS = "solve_constraints"
    VERIFY_INPUT = "verify_input"
    # High-level
    ANALYZE_PROCESS = "analyze_process"
    HACK_VALUE = "hack_value"
    FIND_FUNCTION = "find_function"
    EXPLOIT_VULNERABILITY = "exploit_vulnerability"
    # Meta
    ASK_USER = "ask_user"
    FINISH = "finish"
    UNKNOWN = "unknown"
    CHITCHAT = "chitchat"

class EntityType(Enum):
    """实体类型 — 设计文档 §3.3.3。"""
    MEMORY_ADDRESS = "memory_address"
    POINTER_CHAIN = "pointer_chain"
    MEMORY_SIZE = "memory_size"
    NUMERIC_VALUE = "numeric_value"
    STRING_VALUE = "string_value"
    BYTE_PATTERN = "byte_pattern"
    PROCESS_NAME = "process_name"
    PID = "pid"
    MODULE_NAME = "module_name"
    FUNCTION_NAME = "function_name"
    SCAN_TYPE = "scan_type"
    DATA_TYPE = "data_type"
    BREAKPOINT_ADDRESS = "breakpoint_address"
    BREAKPOINT_TYPE = "breakpoint_type"
    SYMBOL_NAME = "symbol_name"
    TIME_EXPRESSION = "time_expression"
    CONDITION = "condition"

class AmbiguityType(Enum):
    """歧义类型 — 设计文档 §3.3.6。"""
    MISSING_ENTITY = "missing_entity"
    AMBIGUOUS_ENTITY = "ambiguous_entity"
    CONFLICTING_ENTITIES = "conflicting_entities"
    VAGUE_SCOPE = "vague_scope"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    MULTIPLE_INTENTS = "multiple_intents"
```

---

## 6. Layer 1.5 数据模型（规划与工具）

### 6.1 模型：`TaskGraph`（设计文档 §4.5 / §6.3）

**实现方式**：`@dataclass(frozen=False)`，使用 `__init__` 手动管理内部索引（`dict` 和 `set` 不能作为 frozen dataclass 的字段）。

```python
class TaskGraph:
    """任务依赖图 — DAG，支持拓扑排序和状态追踪。"""
    
    __version__: str = "3.0"
    
    def __init__(self, intent_id: Optional[str] = None):
        self.intent_id: Optional[str] = intent_id
        self.nodes: Dict[str, TaskNode] = {}      # node_id -> TaskNode
        self.edges: List[TaskEdge] = []           # 边列表
        self._incoming: Dict[str, Set[str]] = {}    # 入边索引
        self._outgoing: Dict[str, Set[str]] = {}    # 出边索引
        self.metadata: Dict[str, Any] = {}
        self.created_at: float = time.time()
    
    # ── 节点管理 ───────────────────────────────
    def add_node(self, node: TaskNode) -> TaskNode: ...
    def remove_node(self, node_id: str) -> Optional[TaskNode]: ...
    def get_node(self, node_id: str) -> Optional[TaskNode]: ...
    
    # ── 边管理 ─────────────────────────────────
    def add_edge(self, edge: TaskEdge) -> None: ...
    def add_dependency(self, source_id, target_id, dep_type, condition=None): ...
    
    # ── 查询与遍历 ────────────────────────────
    def get_roots(self) -> List[TaskNode]: ...       # 无入边的节点
    def get_leaves(self) -> List[TaskNode]: ...       # 无出边的节点
    def topological_order(self) -> List[TaskNode]: ...  # Kahn 算法
    def get_ready_nodes(self) -> List[TaskNode]: ...   # 所有依赖已 SUCCESS
    def get_blocked_nodes(self) -> List[TaskNode]: ... # 有 FAILED 依赖
    
    # ── 序列化 ─────────────────────────────────
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TaskGraph": ...
    def to_json(self, indent=None) -> str: ...
    @classmethod
    def from_json(cls, s: str) -> "TaskGraph": ...
```

### 6.2 子模型：`TaskNode`

```python
@dataclass
class TaskNode:
    """任务节点 — 代表 TaskGraph 中的一个步骤。"""
    
    id: str = field(default_factory=lambda: f"T-{uuid.uuid4().hex[:8]}")
    name: str = ""                    # 人类可读标签
    description: str = ""             # 详细说明
    
    # ── 层级 ───────────────────────────────────
    intent_id: Optional[str] = None   # 关联的 Intent
    layer: int = 1                    # 1=概念, 2=工程, 3=执行
    
    # ── 规划 ───────────────────────────────────
    goal: str = ""                    # 本步骤目标
    strategy: str = ""              # 达成策略
    
    # ── 执行 ───────────────────────────────────
    tool_name: Optional[str] = None   # 工具名（或占位符）
    tool_params: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    # ── 备选与回退 ─────────────────────────────
    alternative_strategies: List[str] = field(default_factory=list)
    fallback_nodes: List[str] = field(default_factory=list)  # 回退节点 ID 列表
    
    # ── 成本与优先级 ───────────────────────────
    estimated_cost: float = 1.0       # 预估 LLM token / 时间成本
    priority: int = 0                 # 优先级（高 = 更紧急）
    tags: Set[str] = field(default_factory=set)
    
    # ── 时间戳 ─────────────────────────────────
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    
    # ── 元数据 ─────────────────────────────────
    metadata: Dict[str, Any] = field(default_factory=dict)
    # v3.0 新增：绑定信息
    binding_confidence: Optional[float] = None  # 工具绑定置信度
    binding_reason: Optional[str] = None         # 绑定原因
    
    # ── 状态机方法 ────────────────────────────
    def mark_running(self): ...
    def mark_success(self, result): ...
    def mark_failed(self, error): ...
    def can_retry(self) -> bool: ...
```

### 6.3 子模型：`TaskEdge`

```python
@dataclass
class TaskEdge:
    """任务依赖边 — 有向边。"""
    
    source_id: str
    target_id: str
    dep_type: DependencyType = DependencyType.SEQUENTIAL
    condition: Optional[str] = None   # 条件表达式（如 "source.status == SUCCESS"）
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 6.4 枚举定义

```python
class TaskStatus(Enum):
    """任务生命周期状态。"""
    PENDING = "pending"         # 等待依赖
    RUNNING = "running"         # 正在执行
    SUCCESS = "success"         # 成功完成
    FAILED = "failed"           # 执行失败
    BLOCKED = "blocked"         # 上游失败阻塞
    CANCELLED = "cancelled"     # 显式取消
    SKIPPED = "skipped"         # 条件评估为假
    NEEDS_CLARIFICATION = "needs_clarification"  # 歧义等待用户

class DependencyType(Enum):
    """依赖边类型 — 设计文档 §4.5.3。"""
    SEQUENTIAL = "sequential"    # B 必须等待 A 完成
    CONDITIONAL = "conditional"  # B 仅在条件满足时运行
    ITERATIVE = "iterative"      # B 可能运行多次（A 产生结果时）
    PARALLEL = "parallel"        # B 可与 A 并行（同步点合并）
    FALLBACK = "fallback"        # B 是 A 失败时的替代
```

### 6.5 v3.0 新增：`ToolSchema`（设计文档 §4.6.1）

```python
@dataclass
class ToolSchema:
    """工具标准化 Schema — 兼容 OpenAPI + JSON Schema + MCP。"""
    
    name: str                          # 全局唯一：{source_id}_{operation_name}
    description: str                   # 功能描述（给 LLM 看的）
    parameters: Dict[str, Any]        # JSON Schema 格式参数定义
    required_params: List[str] = field(default_factory=list)
    
    # ── 来源与类型 ────────────────────────────
    source: ToolSource = ToolSource.BUILTIN
    tool_type: ToolType = ToolType.LOCAL_FUNCTION
    version: str = "1.0.0"
    tags: Set[str] = field(default_factory=set)
    
    # ── 执行 ───────────────────────────────────
    endpoint_url: Optional[str] = None    # HTTP_API 的目标 URL
    http_method: Optional[str] = None       # GET/POST/PUT/DELETE
    
    # ── 性能与成本 ───────────────────────────
    estimated_latency_ms: int = 100
    estimated_cost_tokens: int = 50
    
    # ── 权限与安全 ───────────────────────────
    requires_auth: bool = False
    auth_type: Optional[str] = None         # bearer / api_key / oauth2
    is_destructive: bool = False            # 是否写操作
    
    # ── 时间戳 ─────────────────────────────────
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    # ── 内部方法 ───────────────────────────────
    @property
    def schema_hash(self) -> str: ...       # SHA-256 内容哈希
    def to_llm_format(self) -> Dict[str, Any]: ...  # OpenAI Function Calling 格式

class ToolSource(Enum):
    BUILTIN = "builtin"
    API_DOC = "api_doc"
    MCP = "mcp"
    CUSTOM = "custom"

class ToolType(Enum):
    LOCAL_FUNCTION = "local_function"
    HTTP_API = "http_api"
    MCP_REMOTE = "mcp_remote"
```

### 6.6 v3.0 新增：`PlanningSkill`（设计文档 §4.4）

```python
@dataclass
class PlanningSkill:
    """领域规划模板 — 基于通用原语组合。"""
    
    skill_id: str
    name: str
    description: str
    version: str = "1.0.0"
    
    # ── 领域 ───────────────────────────────────
    domain_tags: Set[str] = field(default_factory=set)
    intent_categories: Set[str] = field(default_factory=set)
    
    # ── 原语组合 ───────────────────────────────
    primitives: List[str] = field(default_factory=list)
    
    # ── 步骤模板 ───────────────────────────────
    step_templates: List[Dict[str, Any]] = field(default_factory=list)
    
    # ── 工具提示（非强制绑定）──────────────────
    tool_hints: Dict[str, List[str]] = field(default_factory=dict)
    
    # ── 约束 ───────────────────────────────────
    constraints: List[Dict[str, Any]] = field(default_factory=list)
    
    # ── 详细程度 ───────────────────────────────
    level: SkillLevel = SkillLevel.STANDARD
    
    # ── 元数据 ─────────────────────────────────
    author: Optional[str] = None
    source: Optional[str] = None
    usage_count: int = 0
    success_rate: float = 0.0
    created_at: float = field(default_factory=time.time)

class SkillLevel(Enum):
    SKELETON = "skeleton"      # 仅骨架，LLM 填充全部
    STANDARD = "standard"      # 标准模板，LLM 可调整
    DETAILED = "detailed"      # 详细模板，LLM 仅填充占位符
```

---

## 7. Layer 2 数据模型（对话状态）

### 7.1 模型：`DialogueState`（设计文档 §5.2）

```python
@dataclass
class DialogueState:
    """对话状态 — 包含 Topic Tree 和 Context Window。"""
    
    __version__: str = "3.0"
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    
    # ── Topic Tree ────────────────────────────
    topic_tree: TopicTree = field(default_factory=TopicTree)
    
    # ── Context Window ────────────────────────
    context_window: ContextWindow = field(default_factory=ContextWindow)
    
    # ── 对话状态机 ────────────────────────────
    status: DialogueStatus = DialogueStatus.IDLE
    
    # ── 当前轮 ─────────────────────────────────
    current_turn: int = 0
    last_turn_timestamp: float = 0.0
    
    # ── 元数据 ─────────────────────────────────
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
```

### 7.2 子模型：`TopicTree`

```python
@dataclass
class TopicTree:
    """主题树 — 用户对话的长期结构。"""
    
    root: Optional[TopicTreeNode] = None
    nodes: Dict[str, TopicTreeNode] = field(default_factory=dict)  # node_id -> node
    active_node_id: Optional[str] = None
    
    # ── 序列化 ─────────────────────────────────
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TopicTree": ...

@dataclass
class TopicTreeNode:
    """主题树节点。"""
    
    node_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    content: str = ""                 # 主题内容（摘要或关键词）
    timestamp: float = field(default_factory=time.time)
    weight: float = 1.0               # EMA 权重 [0, 1]
    
    # ── 树结构 ─────────────────────────────────
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    
    # ── 交叉引用 ───────────────────────────────
    cog_refs: List[str] = field(default_factory=list)  # 引用的 Cognitive Tree 节点 ID
    
    # ── 状态 ───────────────────────────────────
    is_active: bool = True
    turn_count: int = 0               # 涉及此主题的轮数

class DialogueStatus(Enum):
    IDLE = "idle"
    PARSING = "parsing"
    ACTIONABLE = "actionable"
    CLARIFYING = "clarifying"
    EXECUTING = "executing"
    RESPONDING = "responding"
    ERROR = "error"
```

### 7.3 子模型：`ContextWindow`（设计文档 §5.3）

```python
@dataclass
class ContextWindow:
    """上下文窗口 — 分层工作记忆。"""
    
    # ── Hot Layer（最近 1-3 轮，完整保留）──────
    hot_layer: List[TurnRecord] = field(default_factory=list)
    hot_capacity: int = 3
    
    # ── Warm Layer（最近 4-10 轮，一级摘要）──
    warm_layer: List[TurnSummary] = field(default_factory=list)
    warm_capacity: int = 7
    
    # ── Cool Layer（最近 11-30 轮，二级摘要）─
    cool_layer: List[TopicSummary] = field(default_factory=list)
    cool_capacity: int = 20
    
    # ── Cold Layer（超过 30 轮，仅索引）──────
    cold_index: List[ColdIndexEntry] = field(default_factory=list)
    
    # ── 配置 ───────────────────────────────────
    base_size: int = 10
    complexity_factor: float = 1.0    # 由 PCR 输出调节
    user_preference_factor: float = 1.0  # 由追踪深度调节
    token_budget: int = 8000          # 剩余 token 预算

@dataclass
class TurnRecord:
    """Hot Layer：完整轮次记录。"""
    turn_id: int
    user_input: str
    intent: Intent
    response: str
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TurnSummary:
    """Warm Layer：单轮摘要。"""
    turn_id: int
    category: str                     # 意图类别
    key_entities: List[Dict[str, Any]]  # 关键实体
    result_status: str                # 执行结果状态
    timestamp: float

@dataclass
class TopicSummary:
    """Cool Layer：多轮合并摘要。"""
    topic_id: str
    summary_text: str                 # 自然语言摘要（50-100 字）
    key_decisions: List[str] = field(default_factory=list)
    unresolved_issues: List[str] = field(default_factory=list)
    user_preferences: List[str] = field(default_factory=list)
    start_turn: int = 0
    end_turn: int = 0

@dataclass
class ColdIndexEntry:
    """Cold Layer：仅索引。"""
    topic_id: str
    topic_tag: str
    key_decisions: List[str] = field(default_factory=list)
    user_preference_updates: List[str] = field(default_factory=list)
```

---

## 8. Layer 3 数据模型（服务接口）

### 8.1 模型：`UserInput`（设计文档 §1.3 / §6.3）

```python
@dataclass
class UserInput:
    """用户原始输入。"""
    
    text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    # 如 {"source": "websocket", "client_version": "1.2.3"}
    timestamp: float = field(default_factory=time.time)
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    
    # ── v3.0 新增：多媒体支持 ──────────────────
    attachments: List[Attachment] = field(default_factory=list)
    # 如图片、文件、语音等

@dataclass
class Attachment:
    """附件 — 支持多媒体输入。"""
    type: str                          # "image", "file", "audio", "openapi_doc"
    content: Optional[str] = None    # 文本内容（如文件内容）
    url: Optional[str] = None          # 外部 URL
    metadata: Dict[str, Any] = field(default_factory=dict)
    # 如 {"filename": "api.yaml", "format": "openapi_3"}
```

### 8.2 模型：`Session`（设计文档 §6.2）

```python
@dataclass
class Session:
    """会话 — 用户交互的完整上下文。"""
    
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    user_id: Optional[str] = None
    
    # ── 状态 ───────────────────────────────────
    dialogue_state: DialogueState = field(default_factory=DialogueState)
    status: SessionStatus = SessionStatus.ACTIVE
    
    # ── 认知画像 ───────────────────────────────
    cognitive_profile: Optional[CognitiveProfile] = None    # v1.0 兼容
    cognitive_profile_v2: Optional[CognitiveProfileV2] = None  # v2.0 新增
    
    # ── 解析上下文 ────────────────────────────
    parse_context: ParseContext = field(default_factory=ParseContext)
    
    # ── 可观测性 ───────────────────────────────
    trace_log: List[str] = field(default_factory=list)
    
    # ── 时间戳 ─────────────────────────────────
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    
    # ── 元数据 ─────────────────────────────────
    metadata: Dict[str, Any] = field(default_factory=dict)

class SessionStatus(Enum):
    ACTIVE = "active"
    IDLE = "idle"              # 超过超时时间无交互
    CLOSED = "closed"          # 用户显式关闭或系统回收
    ARCHIVED = "archived"      # 已归档到长期存储
```

### 8.3 模型：`ParseResult`（设计文档 §3.3.8）

```python
@dataclass
class ParseResult:
    """Intent Parser 的最终输出 — 可执行的图或澄清请求。"""
    
    intent: Intent
    task_graph: Optional[TaskGraph] = None
    is_actionable: bool = False
    clarification_message: Optional[str] = None
    suggestions: List[str] = field(default_factory=list)
    trace_log: List[str] = field(default_factory=list)
    
    # v3.0 新增：规划模式信息
    planning_mode: Optional[str] = None       # "DYNAMIC" / "SKILL_ENHANCED" / "MIXED"
    skill_used: Optional[str] = None          # 使用的 Skill ID
    
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ParseResult": ...
```

### 8.4 模型：`ParseContext`（设计文档 §3.3.7）

```python
@dataclass
class ParseContext:
    """跨轮解析上下文 — 实体缓存 + 历史意图。"""
    
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    history: List[Intent] = field(default_factory=list)       # 历史解析意图
    resolved_entities: Dict[str, Any] = field(default_factory=dict)  # 已确认实体
    pending_clarifications: List[Ambiguity] = field(default_factory=list)
    
    # ── 进程上下文 ────────────────────────────
    process_name: Optional[str] = None
    process_type: Optional[str] = None
    pid: Optional[int] = None
    
    # ── 内部缓存 ───────────────────────────────
    _entity_cache: Dict[str, List[Entity]] = field(default_factory=dict)
    
    # ── 元数据 ─────────────────────────────────
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # ── 方法 ───────────────────────────────────
    def add_intent(self, intent: Intent) -> None: ...
    def get_last_intent(self) -> Optional[Intent]: ...
    def get_resolved_value(self, entity_type: EntityType) -> Any: ...
    def to_dict(self) -> Dict[str, Any]: ...
```

---

## 9. 横切数据模型（认知画像 v2.0）

### 9.1 模型：`CognitiveProfileV2`（设计文档 §7.2 / §7.3）

**说明**：此模型已在 `ENGINEERING_COGNITIVE_PROFILE_V2.md` 中详细定义。本文件仅给出接口和与全系统的集成点，**完整实现请参考该文档**。

```python
@dataclass
class CognitiveProfileV2:
    """双轨用户画像 — v2.0 核心模型。"""
    
    # ── Track A: 认知动力学 ───────────────────
    track_a: TrackA = field(default_factory=TrackA)
    
    # ── Track B: 标签化信息 ───────────────────
    track_b: TrackB = field(default_factory=TrackB)
    
    # ── 时间状态 ───────────────────────────────
    temporal_state: TemporalState = field(default_factory=TemporalState)
    
    # ── g 因子 ─────────────────────────────────
    g_factor: GFactor = field(default_factory=GFactor)
    
    # ── 元数据 ─────────────────────────────────
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    version: str = "2.0"
    
    # ── 融合输出 ───────────────────────────────
    def get_effective_profile(self) -> EffectiveProfile:
        """融合 Track A 和 Track B，输出有效画像。"""
        ...
```

### 9.2 子模型：Track A（认知动力学）

```python
@dataclass
class TrackA:
    """认知动力学 — 实时可计算的行为特征。"""
    
    metacognition: float = 0.0      # 元认知
    divergence: float = 0.0         # 发散性
    tracking_depth: float = 0.0     # 追踪深度
    stability: float = 0.0          # 稳定性
    confidence: float = 0.0          # 信心度
    
    # ── 历史序列（用于时间序列分析）──────────
    history: List[TrackAHistoryPoint] = field(default_factory=list)

@dataclass
class TrackAHistoryPoint:
    """单时间点的 Track A 快照。"""
    timestamp: float
    metacognition: float
    divergence: float
    tracking_depth: float
    stability: float
    confidence: float
```

### 9.3 子模型：Track B（标签化信息）

```python
@dataclass
class TrackB:
    """标签化信息 — 静态/半静态用户标签。"""
    
    tags: Dict[str, UserTag] = field(default_factory=dict)
    # key: 标签名（如 "technical_level"）
    # value: UserTag 对象
    
    def get_tag(self, name: str) -> Optional[UserTag]: ...
    def add_tag(self, tag: UserTag) -> None: ...
    def update_tag(self, name: str, value: Any) -> None: ...

@dataclass
class UserTag:
    """单个用户标签。"""
    
    name: str
    value: Any                        # 标签值
    confidence: float = 0.0          # 标签置信度 [0, 1]
    source: TagSource = TagSource.L1  # 来源：L1/L2/L3/L4
    verification_count: int = 0      # 验证次数
    is_sensitive: bool = False       # 是否敏感
    created_at: float = field(default_factory=time.time)
    last_verified_at: Optional[float] = None
    
    # 状态
    status: TagStatus = TagStatus.ACTIVE
    user_resistant: bool = False       # 用户是否表现出反感

class TagSource(Enum):
    L1 = "l1"          # 被动观测
    L2 = "l2"          # 间接推断
    L3 = "l3"          # 暗示试探
    L4 = "l4"          # 主动询问

class TagStatus(Enum):
    ACTIVE = "active"
    STALE = "stale"    # 过时，需要重新验证
    DISPUTED = "disputed"  # 用户质疑
    ARCHIVED = "archived"  # 已归档
```

---

## 10. 横切数据模型（记忆系统）

### 10.1 模型：`MemoryChunk`（设计文档 §8.2）

```python
@dataclass
class MemoryChunk:
    """记忆组块 — 记忆的基本单位。"""
    
    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    content: str = ""                 # 内容（文本摘要、实体列表、决策结果）
    importance: float = 0.5          # 重要性 [0, 1]
    timestamp: float = field(default_factory=time.time)
    
    # ── 阶段 ───────────────────────────────────
    stage: MemoryStage = MemoryStage.HOT
    
    # ── 分类 ───────────────────────────────────
    tags: List[str] = field(default_factory=list)
    source_layer: str = ""           # 来源：L0/L1/L2/L3
    
    # ── 衰减参数 ───────────────────────────────
    initial_weight: float = 1.0
    time_constant: float = 86400.0  # 默认 24 小时（秒）
    
    # ── 交叉引用 ───────────────────────────────
    topic_refs: List[str] = field(default_factory=list)  # Topic Tree 节点 ID
    cog_refs: List[str] = field(default_factory=list)    # Cognitive Tree 节点 ID
    
    # ── 元数据 ─────────────────────────────────
    metadata: Dict[str, Any] = field(default_factory=dict)

class MemoryStage(Enum):
    HOT = "hot"         # < 1 小时，权重 1.0
    WARM = "warm"       # 1-24 小时，权重 0.8
    COOL = "cool"       # 1-7 天，权重 0.5
    COLD = "cold"       # 7-30 天，权重 0.2
    FROZEN = "frozen"   # > 30 天，权重 0.05
```

### 10.2 模型：`MemorySnapshot`（设计文档 §1.3）

**⚠️ 补充说明**：此模型是设计文档 §1.3 定义的 **7 个核心数据契约** 之一，但在工程文档前期版本中缺失。本次补充。

```python
@dataclass
class MemorySnapshot:
    """记忆快照 — 特定时间点记忆系统的完整状态捕获。横切 L1-L2，用于意图解析和对话状态同步。"""
    
    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    session_id: Optional[str] = None
    
    # ── 核心字段（设计文档 §1.3 定义）──────────
    chunks: List[MemoryChunk] = field(default_factory=list)       # 当前记忆组块
    weights: Dict[str, float] = field(default_factory=dict)     # chunk_id -> 有效权重
    stage_transitions: List[StageTransition] = field(default_factory=list)  # 阶段转换记录
    
    # ── 快照元数据 ──────────────────────────
    timestamp: float = field(default_factory=time.time)
    trigger: SnapshotTrigger = SnapshotTrigger.PERIODIC  # 触发原因
    
    # ── 上下文 ──────────────────────────────
    context: Dict[str, Any] = field(default_factory=dict)
    # 如 {"turn_id": 5, "intent_category": "scan_memory", "layer": "L1"}
    
    # ── 方法 ───────────────────────────────
    def get_active_chunks(self, threshold: float = 0.1) -> List[MemoryChunk]: ...
    def get_chunks_by_stage(self, stage: MemoryStage) -> List[MemoryChunk]: ...
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemorySnapshot": ...

@dataclass
class StageTransition:
    """记忆阶段转换记录 — 记录单个组块从一个阶段迁移到另一个阶段。"""
    
    chunk_id: str
    from_stage: MemoryStage
    to_stage: MemoryStage
    timestamp: float = field(default_factory=time.time)
    trigger: str = ""       # 触发原因：如 "decay", "recall", "promotion"
    reason: str = ""        # 人类可读的原因

class SnapshotTrigger(Enum):
    """快照触发原因。"""
    PERIODIC = "periodic"     # 周期性快照（如每轮对话结束时）
    ON_DEMAND = "on_demand"   # 按需快照（如用户查询时）
    TURN_END = "turn_end"     # 轮次结束
    RECALL = "recall"         # 用户主动回忆触发
    SYSTEM = "system"         # 系统级操作（如会话迁移）
```

### 10.3 衰减计算

```python
class MemoryDecayManager:
    """记忆衰减管理器 — 单例。"""
    
    def get_effective_weight(self, chunk: MemoryChunk, current_time: float) -> float:
        """
        计算记忆组块的有效权重。
        公式: W_eff = Importance * exp(-t/τ) * StageFactor
        """
        t = current_time - chunk.timestamp
        tau = chunk.time_constant
        stage_factor = self._get_stage_factor(chunk.stage)
        return chunk.importance * math.exp(-t / tau) * stage_factor
    
    def _get_stage_factor(self, stage: MemoryStage) -> float:
        factors = {
            MemoryStage.HOT: 1.0,
            MemoryStage.WARM: 0.8,
            MemoryStage.COOL: 0.5,
            MemoryStage.COLD: 0.2,
            MemoryStage.FROZEN: 0.05,
        }
        return factors.get(stage, 0.05)
    
    def promote_stage(self, chunk: MemoryChunk, target_stage: MemoryStage) -> None:
        """提升阶段（如用户主动回忆时，从 FROZEN 提升到 WARM）。"""
        chunk.stage = target_stage
        chunk.timestamp = time.time()  # 重置时间戳
```

---

## 11. 横切数据模型（可观测性）

### 11.1 模型：`TelemetryEvent`（设计文档 §9.2.3）

```python
@dataclass
class TelemetryEvent:
    """遥测事件 — 可观测性的基础数据单元。"""
    
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    event_type: TelemetryEventType
    metric_name: str
    value: float
    
    # ── 维度 ───────────────────────────────────
    session_id: Optional[str] = None
    layer: str = ""                   # 来源层：L0/L1/L1.5/L2/L3
    component: str = ""              # 组件名：如 "PCR", "IntentParser"
    
    # ── 时间 ───────────────────────────────────
    timestamp: float = field(default_factory=time.time)
    duration_ms: Optional[float] = None  # 事件持续时间
    
    # ── 标签 ───────────────────────────────────
    tags: Dict[str, str] = field(default_factory=dict)
    # 如 {"intent_category": "scan_memory", "planning_mode": "MIXED"}
    
    # ── 上下文 ─────────────────────────────────
    trace_id: Optional[str] = None      # 分布式追踪 ID
    parent_span_id: Optional[str] = None
    span_id: Optional[str] = None

class TelemetryEventType(Enum):
    COUNTER = "counter"      # 计数器（如请求数、错误数）
    GAUGE = "gauge"          # 仪表盘（如活跃 Session 数、内存使用）
    HISTOGRAM = "histogram"  # 直方图（如延迟分布）
    SUMMARY = "summary"      # 摘要（如成功率、满意度）
```

### 11.2 追踪模型：`TraceSpan`

```python
@dataclass
class TraceSpan:
    """追踪 Span — 记录单个处理步骤的完整上下文。"""
    
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    
    # ── 操作 ───────────────────────────────────
    operation_name: str               # 如 "PCR.noise_detect"
    layer: str = ""
    component: str = ""
    
    # ── 时间 ───────────────────────────────────
    start_time: float
    end_time: Optional[float] = None
    
    # ── 状态 ───────────────────────────────────
    status: SpanStatus = SpanStatus.OK
    error_message: Optional[str] = None
    
    # ── 输入/输出 ──────────────────────────────
    input_snapshot: Dict[str, Any] = field(default_factory=dict)
    output_snapshot: Dict[str, Any] = field(default_factory=dict)
    
    # ── 子 Span ────────────────────────────────
    child_spans: List["TraceSpan"] = field(default_factory=list)
    
    # ── 元数据 ─────────────────────────────────
    tags: Dict[str, str] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)

class SpanStatus(Enum):
    OK = "ok"
    ERROR = "error"
    CANCELLED = "cancelled"
```

---

## 12. v3.0 新增数据模型（LLM 认知层）

### 12.1 模型：`CognitiveTreeNode`（设计文档 §4.2）

**⚠️ 诚实标记**：此模型是 v3.0 全新设计，与现有代码 `topic_tree/models.py` 无对应关系。需要从零实现。

```python
@dataclass
class CognitiveTreeNode:
    """认知节点 — LLM 的心智空间中的单个认知事件。"""
    
    node_id: str = field(default_factory=lambda: f"C-{uuid.uuid4().hex[:8]}")
    
    # ── 认知类型 ───────────────────────────────
    cog_type: CogType = CogType.REASONING
    source_llm: str = ""              # 产生此节点的 LLM 实例（如 "Planning-LLM"）
    
    # ── 时间 ───────────────────────────────────
    timestamp: float = field(default_factory=time.time)
    
    # ── 内容 ───────────────────────────────────
    content: str = ""                 # 认知内容（推理文本、决策理由、反思）
    confidence: float = 0.5          # 该认知的置信度 [0, 1]
    
    # ── 证据 ───────────────────────────────────
    evidence: List[str] = field(default_factory=list)
    # 引用的其他节点 ID 或外部数据源
    
    # ── 行动 ───────────────────────────────────
    action: Optional[str] = None      # 由此认知产生的行动描述
    action_result: Optional[str] = None  # 行动结果
    
    # ── 状态 ───────────────────────────────────
    status: CogNodeStatus = CogNodeStatus.CREATED
    
    # ── 元认知 ─────────────────────────────────
    reflections: List[str] = field(default_factory=list)   # 反思列表（Meta-Cognitive 添加）
    validations: List[str] = field(default_factory=list)   # 验证结果
    version_history: List[str] = field(default_factory=list)  # 内容历史版本
    cross_refs: List[str] = field(default_factory=list)    # 跨会话硬拷贝节点 ID
    # 锚文档 ENGINEERING_MULTILAYER_LLM.md §16.2 D-03 决策：硬拷贝（非软引用）
    
    # ── 性能 ───────────────────────────────────
    metadata: Dict[str, Any] = field(default_factory=dict)
    # 如 {"latency_ms": 150, "token_cost": 500, "model_version": "gpt-4o"}
    
    # ── 交叉引用（Topic Tree）──────────────────
    topic_refs: List[str] = field(default_factory=list)   # 引用的 Topic Tree 节点 ID
    
    # ── 方法 ───────────────────────────────────
    def add_reflection(self, reflection: str) -> None: ...
    def add_validation(self, validation: str) -> None: ...
    def create_version(self, new_content: str) -> "CognitiveTreeNode": ...
    # 创建新版本，旧版本标记为 superseded

class CogType(Enum):
    """认知节点类型 — 设计文档 §4.2.2。"""
    PERCEPTION = "perception"
    HYPOTHESIS = "hypothesis"
    REASONING = "reasoning"
    DECISION = "decision"
    ACTION = "action"
    OBSERVATION = "observation"
    REFLECTION = "reflection"
    VALIDATION = "validation"
    LEARNING = "learning"
    COMMUNICATION = "communication"

class CogNodeStatus(Enum):
    """认知节点生命周期状态。"""
    CREATED = "created"          # 刚创建，未验证
    ACTIVE = "active"            # 被采纳，正在影响决策
    VALIDATED = "validated"      # 验证通过
    INVALIDATED = "invalidated"  # 验证失败
    SUPERSEDED = "superseded"    # 被新版本替代
    ARCHIVED = "archived"        # 已归档
```

### 12.2 模型：`CognitiveTree`

```python
class CognitiveTree:
    """认知树 — LLM 的共享心智空间。"""
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_id: Optional[str] = session_id
        self.nodes: Dict[str, CognitiveTreeNode] = {}   # node_id -> node
        self.edges: List[CognitiveTreeEdge] = []          # 边列表
        
        # ── 索引 ─────────────────────────────────
        self._by_type: Dict[CogType, List[str]] = {}     # 类型索引
        self._by_llm: Dict[str, List[str]] = {}          # LLM 来源索引
        self._by_status: Dict[CogNodeStatus, List[str]] = {}  # 状态索引
        
        # ── 树结构 ───────────────────────────────
        self.root: Optional[str] = None                   # 根节点 ID
        self.active_branch: List[str] = []                # 当前活跃分支的节点 ID 列表
        self.stale_branches: List[List[str]] = []        # 失效分支
        self.depth_limit: int = 10
    
    # ── 节点管理 ───────────────────────────────
    def add_node(self, node: CognitiveTreeNode) -> None: ...
    def get_node(self, node_id: str) -> Optional[CognitiveTreeNode]: ...
    def update_node_status(self, node_id: str, status: CogNodeStatus) -> None: ...
    
    # ── 边管理 ─────────────────────────────────
    def add_edge(self, edge: CognitiveTreeEdge) -> None: ...
    def get_outgoing(self, node_id: str) -> List[CognitiveTreeEdge]: ...
    def get_incoming(self, node_id: str) -> List[CognitiveTreeEdge]: ...
    
    # ── 查询 ───────────────────────────────────
    def find_by_type(self, cog_type: CogType) -> List[CognitiveTreeNode]: ...
    def find_by_llm(self, llm_name: str) -> List[CognitiveTreeNode]: ...
    def find_active_branch(self) -> List[CognitiveTreeNode]: ...
    def find_stale_branches(self) -> List[List[CognitiveTreeNode]]: ...
    
    # ── 遍历 ───────────────────────────────────
    def traverse_dfs(self, start_node: str) -> List[CognitiveTreeNode]: ...
    def traverse_bfs(self, start_node: str) -> List[CognitiveTreeNode]: ...
    
    # ── 序列化 ─────────────────────────────────
    def to_dict(self) -> Dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CognitiveTree": ...
```

### 12.3 子模型：`CognitiveTreeEdge`

```python
@dataclass
class CognitiveTreeEdge:
    """认知边 — 连接两个认知节点，表示推理关系。"""
    
    edge_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    source_id: str
    target_id: str
    edge_type: CogEdgeType = CogEdgeType.DERIVES
    weight: float = 1.0               # 依赖强度 [0, 1]
    condition: Optional[str] = None    # 条件表达式（如 "如果验证通过"）
    metadata: Dict[str, Any] = field(default_factory=dict)

class CogEdgeType(Enum):
    """认知边类型 — 设计文档 §4.2.2。"""
    DERIVES = "derives"           # 推导：A → B
    SUPPORTS = "supports"          # 支持：A ← B
    CONTRADICTS = "contradicts"    # 矛盾：A ↔ B
    CONDITIONAL = "conditional"    # 条件：A ⇒ B
    ALTERNATIVE = "alternative"    # 备选：A ∥ B
    REFINES = "refines"            # 细化：A ⊃ B
    SUMMARIZES = "summarizes"      # 摘要：A ⊂ B
    CROSS_REF = "cross_ref"        # 跨引用：A ~~ B
```

### 12.4 访问控制模型：`AccessControlMatrix`

```python
@dataclass
class AccessControlMatrix:
    """LLM 实例对 Cognitive Tree 的访问权限矩阵。"""
    
    # 权限定义：LLM 实例 -> (可创建类型, 可读取类型, 可修改类型, 不可触碰类型)
    permissions: Dict[str, LLMPermissions] = field(default_factory=dict)
    
    def check_create(self, llm_name: str, cog_type: CogType) -> bool: ...
    def check_read(self, llm_name: str, node_id: str) -> bool: ...
    def check_update(self, llm_name: str, node_id: str) -> bool: ...
    def check_delete(self, llm_name: str, node_id: str) -> bool: ...

@dataclass
class LLMPermissions:
    """单个 LLM 实例的权限。"""
    llm_name: str
    can_create: Set[CogType] = field(default_factory=set)
    can_read: Set[str] = field(default_factory=set)      # "all" 或节点类型列表
    can_update: Set[str] = field(default_factory=set)      # "own" 或 "all"
    can_delete: Set[str] = field(default_factory=set)      # "own" 或 "none"
```

**默认权限配置**（设计文档 §6.2）：

| LLM 实例 | 可创建 | 可读取 | 可修改 | 不可触碰 |
|---------|--------|--------|--------|---------|
| PCR-LLM | PERCEPTION, HYPOTHESIS | 所有 | 自己创建的 | VALIDATION, LEARNING |
| Intent-LLM | HYPOTHESIS, REASONING | 所有 | 自己创建的 | VALIDATION, DECISION(其他) |
| Planning-LLM | REASONING, DECISION, ALTERNATIVE | 所有 | 自己创建的 | VALIDATION |
| Meta-Cognitive-LLM | VALIDATION, REFLECTION | 所有 | 所有节点的 status | 无（只读权限例外） |
| Reflective-LLM | LEARNING, REFLECTION | 所有 | 无 | 无（只读） |
| Answer-LLM | HYPOTHESIS | 所有 | 自己创建的 | VALIDATION, DECISION(其他) |

---

## 13. 序列化与持久化

### 13.1 序列化架构

**设计文档要求**：所有模型支持 JSON 序列化，用于：
- 跨层通信（内存中传递）
- 持久化存储（SQLite / PostgreSQL / Redis）
- 跨服务传输（WebSocket / REST）
- 版本兼容（v2 → v3 自动迁移）

### 13.2 序列化器实现

```python
class VersionedSerializer:
    """版本化序列化器 — 支持多版本输出和自动迁移。"""
    
    CURRENT_VERSION = "3.0"
    SUPPORTED_VERSIONS = ["2.0", "3.0"]
    
    @staticmethod
    def to_dict(obj: Any, version: str = CURRENT_VERSION) -> Dict[str, Any]:
        """
        将对象序列化为字典。
        
        Args:
            obj: 要序列化的对象（dataclass 实例）
            version: 目标版本号（默认 3.0）
        
        Returns:
            字典，包含 `__version__` 字段标记版本
        """
        base_dict = obj.to_dict() if hasattr(obj, "to_dict") else asdict(obj)
        base_dict["__version__"] = version
        
        if version == "3.0":
            return base_dict
        elif version == "2.0":
            return VersionedSerializer._downgrade_to_v2(base_dict, type(obj))
        else:
            raise ValueError(f"Unsupported version: {version}")
    
    @staticmethod
    def from_dict(cls: Type[T], d: Dict[str, Any]) -> T:
        """
        从字典反序列化。
        
        自动检测版本号，如果是 v2 格式则自动迁移到 v3。
        """
        version = d.pop("__version__", "2.0")
        
        if version == "3.0":
            return cls.from_dict(d)
        elif version == "2.0":
            upgraded = VersionedSerializer._upgrade_to_v3(d, cls)
            return cls.from_dict(upgraded)
        else:
            raise ValueError(f"Unsupported version: {version}")
    
    @staticmethod
    def _upgrade_to_v2(d: Dict[str, Any], cls: Type) -> Dict[str, Any]:
        """v2 → v3 迁移：填充缺失字段为默认值。"""
        # 根据 cls 的字段定义，为缺失的 v3 字段填充默认值
        # 如：v2 的 Intent 没有 planning_mode 字段，填充 None
        ...
    
    @staticmethod
    def _downgrade_to_v2(d: Dict[str, Any], cls: Type) -> Dict[str, Any]:
        """v3 → v2 降级：删除 v3 特有字段。"""
        # 如：v3 的 ToolSchema 有 schema_hash 字段，v2 不需要，删除
        ...
```

### 13.3 持久化策略

| 数据类型 | 存储层 | 格式 | 保留策略 |
|---------|--------|------|---------|
| 活跃 Session | Redis（内存） | JSON | 会话活跃期间 |
| 非活跃 Session | PostgreSQL | JSONB | 30 天 |
| 归档 Session | S3 兼容对象存储 | Parquet/JSON | 1 年 |
| Topic Tree | PostgreSQL + Redis | JSONB + 内存索引 | 会话级 |
| Cognitive Tree | PostgreSQL | JSONB（完整） | 会话级 + 跨会话摘要 |
| 用户画像 | PostgreSQL | JSONB | 永久（用户级） |
| 遥测事件 | InfluxDB / Prometheus | 时序数据 | 30 天（原始），1 年（聚合） |
| 追踪 Span | Jaeger / Zipkin | OpenTelemetry | 7 天 |

---

## 14. 版本兼容策略

### 14.1 兼容矩阵

| 场景 | 读 → 写 | 行为 |
|------|---------|------|
| v2 客户端 → v3 服务 | 读 v2 格式，写 v3 格式 | 自动迁移 v2 → v3，响应 v3 格式 |
| v3 客户端 → v2 服务 | 读 v3 格式，写 v2 格式 | 降级 v3 → v2（删除 v3 字段），响应 v2 格式 |
| v3 客户端 → v3 服务 | 读 v3 格式，写 v3 格式 | 原生 v3 处理 |

### 14.2 迁移触发条件

- **自动迁移**：v2 数据在读取时自动升级到 v3（填充默认值）。
- **手动迁移**：批量迁移工具（CLI 命令），用于数据库升级。
- **降级响应**：v3 服务检测到 v2 客户端（通过 HTTP 头 `X-API-Version: 2.0`），自动降级输出。

---

## 15. 测试策略

### 15.1 测试目标

| 测试类型 | 覆盖率目标 | 关键验证点 |
|---------|----------|----------|
| 单元测试 | 100% | 每个模型的 `to_dict`/`from_dict`  round-trip |
| 集成测试 | 90% | 跨模型序列化/反序列化（如 TaskGraph → JSON → TaskGraph） |
| 版本兼容测试 | 100% | v2 → v3 迁移，v3 → v2 降级 |
| 性能测试 | 关键路径 | 1000 个节点的 TaskGraph 序列化 < 10ms |

### 15.2 关键测试用例

**用例 1：Round-Trip 测试**
```python
def test_intent_roundtrip():
    intent = Intent(
        category=IntentCategory.SCAN_MEMORY,
        entities=[Entity(type=EntityType.NUMERIC_VALUE, value="100", confidence=0.9)],
        ambiguities=[Ambiguity(type=AmbiguityType.MISSING_ENTITY, description="缺少地址")]
    )
    d = intent.to_dict()
    restored = Intent.from_dict(d)
    assert restored.category == intent.category
    assert len(restored.entities) == len(intent.entities)
    assert len(restored.ambiguities) == len(intent.ambiguities)
```

**用例 2：版本迁移测试**
```python
def test_v2_to_v3_migration():
    v2_data = {"category": "scan_memory", "entities": [], "confidence": 0.8}  # 无 v3 字段
    intent = VersionedSerializer.from_dict(Intent, {"__version__": "2.0", **v2_data})
    assert intent.planning_mode is None  # v3 新增字段，默认 None
    assert intent.__version__ == "3.0"
```

**用例 3：Cognitive Tree 验证**
```python
def test_cognitive_tree_permissions():
    tree = CognitiveTree()
    node = CognitiveTreeNode(cog_type=CogType.DECISION, source_llm="Planning-LLM")
    tree.add_node(node)
    
    # Meta-Cognitive-LLM 可以修改任何节点的 status
    assert tree.can_update("Meta-Cognitive-LLM", node.node_id)
    
    # Planning-LLM 不能修改 VALIDATION 节点
    val_node = CognitiveTreeNode(cog_type=CogType.VALIDATION, source_llm="Meta-Cognitive-LLM")
    assert not tree.can_update("Planning-LLM", val_node.node_id)
```

---

## 16. 附录：简化与待讨论项

### 16.1 诚实标记：简化项

| 编号 | 简化内容 | 设计文档要求 | 当前实现 | 简化原因 | 恢复路线图 |
|------|---------|-------------|---------|---------|-----------|
| **S-01** | `Attachment` 多媒体支持 | `UserInput.attachments` 支持 image/audio/file/openapi_doc | 仅 `openapi_doc` 类型实现 | 当前用户接口仅文本 + 文件上传；image/audio 需前端配合 | Phase 5 GUI 升级时实现 |
| **S-02** | `CognitiveTree` 并发控制 | 乐观锁（版本号检测） | 无并发锁，依赖 Python GIL 的单线程保护 | 初期单进程部署，并发场景有限 | Phase 3 多进程/多节点部署时实现乐观锁 |
| **S-03** | `AccessControlMatrix` 细粒度 | 每个节点级别的权限控制 | 仅按节点类型控制（如 Planning-LLM 不能修改任何 VALIDATION） | 节点级别控制需要额外的权限存储，增加复杂度 | Phase 2 引入 RBAC 完整模型时实现 |
| **S-04** | `ContextWindow` 的 LLM 驱动压缩 | Cool Layer 的二级摘要使用 LLM 生成 | 使用规则模板生成（提取关键词拼接） | LLM 压缩成本高，初期使用规则降低延迟 | Phase 2 引入轻量摘要 LLM（3B 参数）时实现 |
| **S-05** | `MemoryChunk` 双指数衰减 | 支持 $W(t) = A e^{-t/τ_1} + B e^{-t/τ_2}$ | 仅单指数衰减 $W(t) = W_0 e^{-t/τ} \cdot S(t)$ | 单指数已覆盖 95% 场景，双指数参数调优困难 | Phase 3 引入记忆系统优化时实现 |

### 16.2 待讨论项

| 编号 | 问题 | 选项 | 建议 |
|------|------|------|------|
| **D-01** | `CognitiveTree` 的存储引擎 | A) PostgreSQL JSONB  B) 图数据库（Neo4j）  C) 内存 + 定期快照 | 建议 A：团队熟悉 PostgreSQL，JSONB 支持树查询；图数据库增加运维成本 |
| **D-02** | 序列化格式 | A) 纯 JSON  B) JSON + MessagePack 二进制  C) Protobuf | 建议 B：JSON 用于调试和跨语言，MessagePack 用于内部高性能传输 |
| **D-03** | `Entity.value` 类型 | A) `Any`（泛型）  B) `Union[str, int, float, List]`  C) 强类型子类（`AddressEntity`, `NumericEntity`） | 建议 B：平衡灵活性和类型安全，C 选项增加类爆炸 |
| **D-04** | 用户画像的隐私存储 | A) 明文存储  B) 字段级加密  C) 全量加密 | 建议 B：敏感标签（如身份、职业）字段级加密，非敏感标签明文 |

### 16.3 设计文档等价性检查

| 设计文档章节 | 本工程文档覆盖 | 等价性 | 备注 |
|-------------|--------------|--------|------|
| `DESIGN_FULL_CONCEPT.md` §1.3 | §4-§11 | ✅ 等价 | 7 个核心数据契约全部覆盖（含 MemorySnapshot） |
| `DESIGN_FULL_CONCEPT.md` §1.3 (MemorySnapshot) | §10.2 | ✅ 等价 | `chunks` + `weights` + `stage_transitions` 全部覆盖 |
| `DESIGN_FULL_CONCEPT.md` §2.4 | §4.1 | ✅ 等价 | PCROutput 全部字段覆盖 |
| `DESIGN_FULL_CONCEPT.md` §3.3 | §5.1-§5.4 | ✅ 等价 | Intent + Entity + Ambiguity + TaskGraph 覆盖 |
| `DESIGN_FULL_CONCEPT.md` §4.2 | §6.5-§6.6 | ✅ 等价 | ToolSchema + PlanningSkill 覆盖 |
| `DESIGN_FULL_CONCEPT.md` §5.2 | §7.2 | ✅ 等价 | TopicTree 覆盖 |
| `DESIGN_FULL_CONCEPT.md` §5.3 | §7.3 | ✅ 等价 | ContextWindow 分层覆盖 |
| `DESIGN_FULL_CONCEPT.md` §7.2 | §9.1-§9.3 | ✅ 等价 | Track A + Track B 覆盖 |
| `DESIGN_FULL_CONCEPT.md` §8.2 | §10.1 | ✅ 等价 | MemoryChunk 覆盖 |
| `DESIGN_FULL_CONCEPT.md` §9.2 | §11.1-§11.2 | ✅ 等价 | Telemetry + Tracing 覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §4.2 | §12.1-§12.4 | ✅ 等价 | CognitiveTree + 节点 + 边 + 权限覆盖 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §3.1 | §5.1, §8.3 | ✅ 等价 | `PCROutput` + `ParseResult` 数据模型对齐，见锚文档 §7 |
| `DESIGN_MULTILAYER_LLM_COGNITIVE.md` §5 | §8.3 | ✅ 等价 | `UserInput` 数据模型对齐，见锚文档 §11 |

---

*本工程文档由 DialogMesh 工程团队基于设计概念文档生成。所有简化项已在 §16.1 中诚实标记，待讨论项在 §16.2 中列出，等待团队确认。*

---

## 17. 问题修复记录

### 修复 2026-07-19: 补充 MemorySnapshot 数据契约模型

**修复原因**: `REVIEW_FULL_CONCEPT_ENGINEERING.md` 审查报告指出，设计文档 `DESIGN_FULL_CONCEPT.md` §1.3 定义了 **7 个核心数据契约**（含 `MemorySnapshot`），但工程文档前期版本仅声称覆盖 6 个，且缺失 `MemorySnapshot` 模型定义。

**修改内容**:
1. **§1.2 范围表格**: 将核心数据契约数量从 6 个修正为 7 个，新增 `MemorySnapshot` 行（对应 §10.2）。
2. **§10.2 新增模型**: 在 `MemoryChunk` 之后、`MemoryDecayManager` 之前插入 `MemorySnapshot` 模型定义，包含：
   - `MemorySnapshot` 主模型（`chunks` + `weights` + `stage_transitions`）
   - `StageTransition` 子模型（记录组块阶段转换）
   - `SnapshotTrigger` 枚举（快照触发原因）
3. **§10.3 重编号**: 将原 `§10.2 衰减计算` 重编号为 `§10.3`，保持文档内部自洽。
4. **§16.3 等价性检查**: 修正 `DESIGN_FULL_CONCEPT.md` §1.3 的备注为 "7 个核心数据契约全部覆盖（含 MemorySnapshot）"，并新增 `MemorySnapshot` 独立覆盖行。

**修复验证**:
- 文档内部自洽性: ✅ — 所有 MemorySnapshot 引用与章节编号一致
- 等价性检查诚实性: ✅ — 7 个核心数据契约与设计文档 §1.3 完全对应
- 新增代码行估算: ~50 行（Python 模型 + 枚举）
