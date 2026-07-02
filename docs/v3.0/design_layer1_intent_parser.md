# Layer 1：意图解析器（Intent Parser）设计文档

**版本**：v1.0  
**日期**：2025-06-24  
**状态**：设计完成，待实现  
**作者**：Kimi Work Agent  

---

## 1. 设计目标与定位

Intent Parser 是整个分层 Agent 架构的 **Layer 1（入口层）**。它负责将用户输入（自然语言、快捷指令、结构化消息）转化为一个 **可执行的任务依赖图（TaskGraph）**，或转化为一个 **需要用户澄清的明确请求**。它不是简单的正则匹配工具，而是一个具备以下能力的工业级解析引擎：

1. **多模态输入处理**：纯文本、结构化JSON、混合输入（文本+参数）
2. **多意图并发解析**：一句话中包含多个任务时，拆分为独立的 Intent + 构建 DAG
3. **强实体提取**：地址、数值、PID、模块名、函数名、字节特征等带类型和置信度
4. **上下文继承与补全**：跨轮对话中自动继承已确认实体，减少重复输入
5. **歧义检测与消解**：不确定时不是猜，而是标记 Ambiguity 并选择最优策略（自动消解或请求用户）
6. **可追溯性（Traceability）**：每个解析步骤都有 trace_log，便于调试与审计
7. **零外部依赖解析**：核心规则引擎 100% 确定性，不依赖 LLM 即可处理 80%+ 常见输入，LLM 仅作为 fallback

---

## 2. 核心设计原则

| 原则 | 说明 |
|------|------|
| **确定性优先（Deterministic First）** | 规则引擎（Rule Engine）优先处理，LLM Fallback 仅用于未覆盖的语义或复杂复合意图 |
| **歧义即显式（Ambiguity is First-Class）** | 任何不确定性不通过猜测消除，而是生成 Ambiguity 对象并路由到消解策略 |
| **单一职责与分层** | 每个子模块只做一件事：Preprocessor（清洗）→ Extractor（实体）→ Classifier（分类）→ Decomposer（拆分）→ Builder（DAG） |
| **上下文不可变（Immutable History）** | 已解析的 Intent 历史只追加不修改，上下文继承通过显式 Merge 操作完成 |
| **向后兼容与可扩展** | 新增 IntentCategory / EntityType / Tool 只需注册到 Registry，无需修改核心解析逻辑 |
| **可测试与可观测** | 每个中间产物（Intermediate）都可序列化，每个决策点都有 confidence + trace_log |

---

## 3. 总体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        用户输入（多模态）                              │
│  [自然语言]  /  [结构化JSON]  /  [快捷指令模板]  /  [语音转文本]       │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Stage 0: Input Preprocessor（输入预处理）                           │
│  - 统一编码（UTF-8 NFC）                                            │
│  - 中文/英文混合规范化（全角转半角）                                  │
│  - 地址格式统一（0x0040_0000 → 0x00400000）                         │
│  - 数字分组符移除（1,000,000 → 1000000）                             │
│  - 语义无关符号过滤（多余标点、表情、URL 截断）                        │
│  - 输出: NormalizedText                                              │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Stage 1: Entity Extractor（实体提取引擎）                           │
│  - 规则提取器（Regex / Keyword / Pattern）                             │
│  - 启发式提取器（地址上下文推断、数值范围推断）                         │
│  - 上下文补全（从 ParseContext 继承未明确但已确认的实体）               │
│  - 输出: List[Entity]（每个带 type, value, confidence, pos）          │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Stage 2: Intent Classifier（意图分类器）                            │
│  - 规则分类器（Rule Classifier）：基于 pattern + entity 组合打分        │
│  - 置信度聚合（Confidence Aggregation）：匹配分 + 实体覆盖分 + 语境分    │
│  - 输出: IntentCategory + confidence + 匹配的 rule trace             │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Stage 3: Multi-Intent Splitter（多意图拆分器）                       │
│  - 连词检测（"and then", "先...再...", "同时", "然后"）               │
│  - 语义切分：基于 entity 位置和 punctuation 进行句子边界推断            │
│  - 每个子句生成独立 Intent，标记主次关系                              │
│  - 输出: List[Intent]（含 sub_intents）                              │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Stage 4: Ambiguity Detector（歧义检测器）                           │
│  - 缺失实体检测（Missing Entity）：required 字段未匹配               │
│  - 歧义实体检测（Ambiguous Entity）：同一文本匹配多个实体类型           │
│  - 冲突检测（Conflicting Entities）：数值矛盾、范围冲突               │
│  - 模糊范围检测（Vague Scope）：未指定进程/模块/内存区域               │
│  - 输出: List[Ambiguity] + 消解建议（Suggestions）                    │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Stage 5: Ambiguity Resolver（歧义消解器）                           │
│  - 自动消解策略（Auto-Resolve）：单候选时默认继承、高置信度推断         │
│  - 延迟消解（Deferred）：保留 Ambiguity，交给上层或用户               │
│  - 快速失败（Fast Fail）：歧义过多或不可消解时直接 ask_user           │
│  - 输出: 消解后的 Intent（可能仍有待解歧义标记）                       │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Stage 6: Context Merger（上下文合并器）                             │
│  - 继承历史 Intent 中已确认的高置信度实体（> 0.8）                    │
│  - 继承 process_name, pid, process_type 等会话级上下文                │
│  - 识别代词消解（"这个地址", "刚才的值" → 回溯最近相关实体）             │
│  - 输出: 补全后的 Intent                                             │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Stage 7: TaskGraph Builder（任务图构建器）                           │
│  - 概念层映射（Concept → TaskNode）：每个 Intent 对应一个或多个 Node   │
│  - 依赖边构建（Dependency Edge）：SEQUENTIAL / CONDITIONAL / ITERATIVE   │
│  - 复合意图分解（Compound Decomposition）：如 HACK_VALUE → 3 个子节点 │
│  - Fallback 节点注册：为每个关键节点预设替代策略节点                     │
│  - 输出: TaskGraph（DAG，可拓扑排序）                                  │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         ParseResult                                  │
│  - 可执行: task_graph + is_actionable=True                           │
│  - 需澄清: clarification_message + suggestions + is_actionable=False  │
│  - 全链路 trace_log（可序列化用于审计与调试）                          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. 数据模型详细定义

### 4.1 Entity（实体）

```python
@dataclass(frozen=True, slots=True)
class Entity:
    type: EntityType            # 枚举: MEMORY_ADDRESS, NUMERIC_VALUE, FUNCTION_NAME, ...
    value: Any                  # 规范化后的值: int, str, float, List[int], ...
    raw_text: str               # 原始文本片段（用于溯源）
    confidence: float           # 0.0–1.0，基于提取规则质量 + 上下文一致性
    start_pos: int              # 在原始文本中的起始位置（-1 表示非文本来源）
    end_pos: int                # 结束位置
    metadata: Dict              # 扩展信息: { "radix": 16, "is_pointer": True, ... }
```

**关键设计**：`frozen=True, slots=True` → 不可变、内存高效、可安全哈希。这保证了一旦提取完成，Entity 不会因为后续处理被意外修改，所有后续操作都基于创建新实例。

### 4.2 Intent（意图）

```python
@dataclass
class Intent:
    id: str                     # 短 UUID（8字符），全局唯一标识
    category: IntentCategory    # 枚举: SCAN_MEMORY, DISASSEMBLE, HACK_VALUE, ...
    raw_input: str              # 用户原始输入
    normalized_input: str       # 预处理后输入
    entities: List[Entity]      # 提取到的所有实体
    confidence: float           # 整体意图分类置信度
    sub_intents: List[Intent]   # 多意图拆分时存放子意图
    # 上下文标志
    requires_process: bool      # 是否需要 attached 进程（默认 True）
    is_destructive: bool        # 是否修改内存/进程状态（如 WRITE_MEMORY）
    is_reversible: bool         # 是否可自动撤销（如 write 后恢复）
    # 歧义
    ambiguities: List[Ambiguity]
    # 修饰符
    temporal_constraint: Optional[str]   # "after 5 seconds", "when it changes"
    scope_constraint: Optional[str]      # "in module X", "in .text section"
    # 元信息
    created_at: float
    session_id: Optional[str]
    metadata: Dict
```

**关键设计**：`sub_intents` 不是递归嵌套的 JSON，而是平级列表（内部可能嵌套），便于序列化。`is_destructive` 和 `is_reversible` 在后续 Layer 4（Meta Controller）中用于权限控制与回滚策略。

### 4.3 Ambiguity（歧义）

```python
@dataclass
class Ambiguity:
    type: AmbiguityType         # MISSING_ENTITY / AMBIGUOUS_ENTITY / ...
    description: str            # 人类可读描述
    affected_entities: List[EntityType]  # 哪些实体类型受影响
    suggestions: List[str]      # 建议选项（用于 UI 按钮或 LLM 提示）
    auto_resolvable: bool       # 是否可通过启发式自动消解
    default_choice: Optional[str]      # 自动消解时的默认选择
    metadata: Dict
```

**关键设计**：每个歧义都带 `suggestions`，这意味着前端可以直接渲染为快捷回复按钮，无需 LLM 再生成一次选项。

### 4.4 TaskNode（任务节点）

```python
@dataclass
class TaskNode:
    id: str                     # 节点唯一标识（T-{uuid[:8]}）
    name: str                   # 人类可读标签，如 "精确扫描生命值"
    description: str            # 详细说明，如 "使用 first_scan 在 PID 1234 中扫描 4字节整型 100"
    intent_id: Optional[str]    # 回溯到原始 Intent
    layer: int                  # 1=概念层, 2=工程设计层, 3=API 执行层
    # 规划信息
    goal: str                   # 概念目标: "定位血量内存地址"
    strategy: str               # 当前策略: "exact_scan_4byte"
    # 执行信息
    tool_name: Optional[str]    # 具体工具名（Layer 3 填写）
    tool_params: Dict[str, Any] # 参数（经过 _normalize_params 归一化）
    status: TaskStatus          # PENDING / RUNNING / SUCCESS / FAILED / BLOCKED / ...
    result: Optional[Dict]      # 执行结果
    error: Optional[str]        # 失败原因
    retry_count: int            # 当前已重试次数
    max_retries: int            # 最大重试次数（默认 3）
    # 回退链
    alternative_strategies: List[str]   # 替代策略列表（如 ["aob_scan", "pointer_chain"]）
    fallback_nodes: List[str]   # 指向 TaskGraph 中其他节点 ID（回退 DAG）
    # 元信息
    estimated_cost: float       # 预估 token / 时间开销（用于调度）
    priority: int               # 优先级（越高越优先）
    tags: Set[str]              # 标签，如 {"destructive", "reversible", "interactive"}
    created_at / started_at / finished_at: float
    metadata: Dict
```

### 4.5 TaskGraph（任务依赖图）

```python
class TaskGraph:
    intent_id: Optional[str]
    nodes: Dict[str, TaskNode]          # 节点池
    edges: List[TaskEdge]               # 有向边
    _incoming: Dict[str, Set[str]]      # 反向索引（依赖）
    _outgoing: Dict[str, Set[str]]      # 正向索引（后继）
    metadata: Dict
    created_at: float
```

**关键设计**：
- 使用 Kahn 算法进行拓扑排序，检测环路（DAG 保证）。
- `get_ready_nodes()` 返回所有依赖已 SUCCESS 的 PENDING 节点，供 Layer 4（Executor）消费。
- `get_blocked_nodes()` 返回因上游 FAILED 而被阻塞的节点，用于触发回退（Fallback）逻辑。
- `get_fallback_chain(node_id)` 返回按序排列的回退节点列表，实现自动策略替换。

### 4.6 ParseResult（解析结果）

```python
@dataclass
class ParseResult:
    intent: Intent
    task_graph: Optional[TaskGraph]       # 如果可执行，非 None
    is_actionable: bool                   # 是否可直接执行（无未消解歧义）
    clarification_message: Optional[str]  # 如果不 actionable，给用户的提示
    suggestions: List[str]                # 快速回复选项
    trace_log: List[str]                  # 全链路日志，便于调试与审计
```

---

## 5. 核心算法流程

### 5.1 意图分类算法（Rule-Based + Score Aggregation）

每个 `IntentRule` 包含多个 `patterns`（正则）、`required_entities`（必需实体类型）、`optional_entities`（可选实体类型）、`priority`（优先级）、`min_confidence`（最低置信度）。

**打分公式**：

```
score(pattern) = 1.0 if full match else 0.5 if partial match else 0.0
score(entity_cover) = (matched_required / total_required) * 0.4 + (matched_optional / total_optional) * 0.2
score(context) = 1.0 if previous_intent.category 与当前 rule.category 存在已知关联 else 0.0

confidence = score(pattern) * 0.4 + score(entity_cover) * 0.4 + score(context) * 0.2
```

**流程**：
1. 按 `priority` 降序遍历所有 `_RULES`
2. 对每个 rule，计算所有 patterns 的匹配得分（取最高）
3. 检查必需实体是否满足（不满足则 score 归 0）
4. 汇总 confidence，若 `>= min_confidence` 则记录候选
5. 若存在多个候选，取 confidence 最高；若 confidence 相同，取 `priority` 更高；若仍相同，标记 `AmbiguityType.AMBIGUOUS_ENTITY`
6. 若无任何候选满足 `min_confidence`：进入 **LLM Fallback 分类**（只调用一次，将结果缓存）

### 5.2 多意图拆分算法（Multi-Intent Splitting）

**触发条件**：输入中存在以下任一模式：
- 连词：`"and"`, `"and then"`, `"also"`, `"同时"`, `"并且"`, `"然后"`, `"接着"`, `"再"`, `"先...再..."`, `"first... then..."`, `"...之后..."`
- 标点：分号 `;`、多个句号构成的独立句子
- 实体分布：多个同类型实体（如 2 个地址）且间隔距离较大，暗示两个独立操作

**算法**：
1. 使用分词 + 连词正则切分输入为多个 `segments`
2. 对每个 segment，独立执行 **Stage 1-2**（提取 + 分类）
3. 如果某个 segment 无有效分类，则尝试从上下文推断（如 "先扫描 100，然后改为 999" → segment 2 继承 segment 1 的 SCAN_MEMORY 分类但变为 WRITE_MEMORY）
4. 构建 `sub_intents`，并标记主次关系（主 Intent 是用户最后强调的，或包含复合操作如 HACK_VALUE）
5. 如果所有子意图可独立执行，且没有依赖关系，标记为 `PARALLEL` 边；如果有先后顺序，标记为 `SEQUENTIAL` 边

### 5.3 歧义消解策略矩阵

| AmbiguityType | 检测方式 | 自动消解条件 | 延迟条件 | 快速失败条件 |
|---|---|---|---|---|
| MISSING_ENTITY | 必需实体类型在 entities 中不存在 | 上下文中有已确认值（>0.8） | 上下文无值，但有合理默认值 | 缺失 3+ 个必需实体 |
| AMBIGUOUS_ENTITY | 同一文本匹配多个不同类型实体 | 其中一候选置信度显著高于其他（>0.2 差距） | 差距 < 0.2 | 两个候选都高置信度 |
| CONFLICTING_ENTITIES | 数值矛盾（如地址范围越界、值不兼容） | 单个冲突可自动修正（如 0x1000 写到 0x10 的模块 → 修正为模块基址） | 多个冲突或逻辑不可调和 | 冲突涉及 destructive 操作 |
| VAGUE_SCOPE | 未指定进程/模块/区域 | 当前只有一个 attached 进程 | 多进程环境下 | 无进程 attached |
| UNSUPPORTED_OPERATION | 分类为 UNKNOWN，且无法 LLM fallback | 无 | 无 | 直接快速失败 |
| MULTIPLE_INTENTS | 拆分后超过 max_sub_intents（默认 5） | 无 | 超过 5 个 | 超过 10 个或拆分失败 |

---

## 6. 上下文继承机制

### 6.1 继承规则

`ParseContext` 维护一个跨轮次的状态容器：

```python
class ParseContext:
    session_id: str
    history: List[Intent]                    # 已解析的意图历史
    resolved_entities: Dict[str, Any]      # 已确认实体值（key = EntityType.value）
    process_name, process_type, pid        # 会话级进程上下文
```

**继承策略**：
1. **高置信度继承**：历史 Intent 中 `confidence >= 0.8` 的实体自动加入 `resolved_entities`
2. **代词消解**："这个地址" → 查找最近一轮含有 `MEMORY_ADDRESS` 的 Intent，取最高置信度地址
3. **类型补全**：用户说 "扫描 100"，上一轮用了 4 字节扫描 → 本轮自动补全 `DATA_TYPE=4 bytes`（仅当用户未明确指定时）
4. **进程上下文补全**：如果用户未指定 PID/进程名，但 `ParseContext` 中有 `pid`，自动注入 `Entity(PID, pid, confidence=1.0)`

### 6.2 继承边界

以下实体**不继承**：
- `NUMERIC_VALUE`（扫描值、写入值）—— 每次操作通常不同
- `MEMORY_ADDRESS`（具体地址）—— 除非是 "这个地址" 代词引用
- `BREAKPOINT_ADDRESS` —— 每次断点通常不同

以下实体**继承**：
- `PID` / `PROCESS_NAME` / `MODULE_NAME`（会话级上下文）
- `DATA_TYPE`（数据类型偏好，如用户一直用 float）
- `SCAN_TYPE`（扫描策略偏好）

---

## 7. TaskGraph 构建规则

### 7.1 原子意图映射（单节点）

| IntentCategory | TaskNode.goal | TaskNode.strategy | 默认 tool_name |
|---|---|---|---|
| SCAN_MEMORY | 定位目标数值内存地址 | exact_scan / unknown_scan / changed_scan | first_scan / next_scan |
| READ_MEMORY | 读取目标地址内存内容 | direct_read | read_memory |
| WRITE_MEMORY | 修改目标地址内存值 | direct_write | write_memory |
| DISASSEMBLE | 分析代码段指令 | linear_disasm | disassemble |
| DISASSEMBLE_REGION | 分析代码区域指令 | region_disasm | disassemble_region |
| DECOMPILE | 获取函数伪代码 | ghidra_decompile | （Phase 2 工具） |
| FIND_PATTERN | 搜索字节特征 | aob_scan | find_pattern |
| SET_BREAKPOINT | 监控内存访问 | memory_watch | set_breakpoint |
| HACK_VALUE | 定位并修改数值 | scan_then_write | （复合：见 7.2） |
| ANALYZE_PROCESS | 全面分析进程 | full_process_analysis | refresh_analysis |
| ... | ... | ... | ... |

### 7.2 复合意图分解（Compound Decomposition）

**HACK_VALUE（找到并修改数值）** → 3 个节点 + 2 条边：

```
[Node 1: scan_locate] ──SEQUENTIAL──> [Node 2: verify_address] ──CONDITIONAL("count==1")──> [Node 3: write_value]
                                     └─FALLBACK──> [Node 4: aob_fallback]
```

- Node 1: `first_scan`（精确扫描）→ 如果 count > 1，进入 Node 2（`next_scan` 过滤）；如果 count == 1，直接进入 Node 3（`write_memory`）
- Node 2: `next_scan`（变化过滤）→ 若过滤后仍 > 1，生成 Ambiguity 请求用户确认；若 == 1，进入 Node 3
- Node 3: `write_memory`（写入目标值）→ 标记为 `is_destructive=True, is_reversible=True`
- Node 4（Fallback）: 若扫描失败（count == 0），改用 `find_pattern` 或 `set_breakpoint` 等待数值变化

### 7.3 Fallback 链注册

每个关键节点在创建时自动注册 fallback 节点：

```python
# 扫描节点默认 fallback
scan_node.fallback_nodes = [aob_node.id, pointer_scan_node.id]
# 反汇编节点默认 fallback
asm_node.fallback_nodes = [read_then_asm_node.id, capstone_node.id]
# 断点节点默认 fallback
bp_node.fallback_nodes = [pattern_detect_node.id]
```

这些 fallback 节点初始状态为 `PENDING`，仅在主节点 `FAILED` 时由 Meta Controller 激活。

---

## 8. 与上下游的接口契约

### 8.1 上游输入（From User / Frontend）

```json
{
  "session_id": "sess-abc123",
  "text": "帮我找到血量并改成999",
  "structured": null,           // 可选：前端预解析的结构化数据
  "previous_context": {         // 可选：前端缓存的上轮上下文
    "pid": 1234,
    "process_name": "Game.exe"
  }
}
```

### 8.2 下游输出（To Layer 2 / Planner）

```json
{
  "intent": { ... },
  "task_graph": {
    "intent_id": "abc123",
    "nodes": { "T-xxx": { ... }, "T-yyy": { ... } },
    "edges": [
      { "source_id": "T-xxx", "target_id": "T-yyy", "dep_type": "sequential" }
    ]
  },
  "is_actionable": true,
  "clarification_message": null,
  "suggestions": [],
  "trace_log": [
    "[Stage 0] Normalized: '帮我找到血量并改成999'",
    "[Stage 1] Extracted: Entity(NUMERIC_VALUE=999, conf=1.0)",
    "[Stage 2] Classified: HACK_VALUE (conf=0.95)",
    "[Stage 3] Decomposed into 3 sub-intents",
    "[Stage 4] No ambiguity detected",
    "[Stage 6] Inherited PID=1234 from context",
    "[Stage 7] Built TaskGraph: 4 nodes, 3 edges"
  ]
}
```

### 8.3 回退接口（To Layer 4 / Meta Controller）

当 TaskNode 执行失败时，Meta Controller 调用：

```python
graph.get_fallback_chain(node_id: str) -> List[TaskNode]
```

按序尝试 fallback 节点，直到成功或全部失败。全部失败时，向上抛到 `NEEDS_CLARIFICATION` 状态，生成包含失败原因和选项的 `ParseResult`（复用 `clarification_message` 和 `suggestions`）。

---

## 9. 性能与可靠性设计

### 9.1 性能指标

| 指标 | 目标 | 说明 |
|---|---|---|
| 端到端解析延迟 | < 50ms（Rule Engine） | 纯正则+数据结构的解析，在 Python 中单线程即可达标 |
| LLM Fallback 延迟 | < 500ms（本地 LM Studio） | 仅在 20% 未覆盖输入时触发，且结果缓存 300s |
| 多意图拆分上限 | 5 个子意图 | 超过 5 个时拒绝拆分，要求用户分句输入 |
| 实体提取上限 | 50 个实体 / 输入 | 防止极端长文本导致内存爆炸 |
| 上下文历史窗口 | 最近 10 轮 | 超过 10 轮时，摘要压缩旧历史，保留最近 2 轮完整 |

### 9.2 可靠性机制

1. **规则引擎永不抛异常**：任何正则编译失败或提取异常都被捕获，记录到 `trace_log`，不影响其他规则执行
2. **LLM Fallback 隔离**：如果 LLM 返回不可解析 JSON，使用预置的 `safe_json_load`（容忍多余引号、换行、注释）尝试恢复；仍失败则降级为 `UNKNOWN` 并请求用户确认
3. **循环检测**：TaskGraph Builder 在构建边时自动检测环路（拓扑排序失败），发现时自动断开最后一条边并记录警告
4. **并发安全**：Registry 注册使用 `_RULES_LOCK`，但解析本身是只读操作（只读 Registry + 新建对象），可多线程并行解析不同用户输入

---

## 10. 扩展性设计

### 10.1 新增 IntentCategory

```python
register_intent_rule(IntentRule(
    category=IntentCategory.NEW_CATEGORY,
    patterns=_compile([r"new\s+pattern", r"新模式"]),
    required_entities=[EntityType.MEMORY_ADDRESS],
    optional_entities=[EntityType.NUMERIC_VALUE],
    priority=80,
))
```

无需修改任何核心解析逻辑。

### 10.2 新增 EntityType

1. 在 `EntityType` 枚举中新增成员
2. 在 `EntityExtractor` 中注册新的提取规则（Regex + Normalizer）
3. 在 `_PARAM_ALIASES` 中更新参数映射（如果涉及新类型）

### 10.3 新增复合意图分解模板

```python
# 在 TaskGraphBuilder 中注册新的分解器
@compound_decomposer.register(IntentCategory.NEW_COMPOUND)
def decompose_new_compound(intent: Intent) -> List[TaskNode]:
    node1 = TaskNode(goal="...", strategy="...", tool_name="tool_a")
    node2 = TaskNode(goal="...", strategy="...", tool_name="tool_b")
    return [node1, node2]
```

---

## 11. 实现优先级（Roadmap）

| Phase | 内容 | 预估代码量 | 依赖 |
|---|---|---|---|
| P0 | `models.py` 完整数据模型 + 单元测试 | 600 行 | 无 |
| P1 | `preprocessor.py` 输入预处理 | 200 行 | 无 |
| P2 | `entity_extractor.py` 规则实体提取 + 上下文补全 | 800 行 | P0, P1 |
| P3 | `intent_classifier.py` 规则分类 + 置信度聚合 | 400 行 | P0, P2 |
| P4 | `multi_intent_splitter.py` 多意图拆分 | 300 行 | P3 |
| P5 | `ambiguity_detector.py` + `ambiguity_resolver.py` 歧义处理 | 600 行 | P2, P3, P4 |
| P6 | `context_merger.py` 上下文合并 | 300 行 | P2, P5 |
| P7 | `task_graph_builder.py` DAG 构建 + 复合意图分解 | 700 行 | P0, P6 |
| P8 | `intent_parser.py` 主入口（Pipeline 编排）+ LLM Fallback | 500 行 | P1-P7 |
| P9 | 集成测试（100+ 测试用例） | 500 行 | P8 |
| **总计** | | **~4900 行** | |

---

## 12. 待决策问题（Open Questions）

1. **LLM Fallback 触发阈值**：当 Rule Engine 最高 confidence < 0.3 时触发 LLM？还是 < 0.5？需要在真实数据上校准。
2. **多意图拆分的 LLM 辅助**：如果拆分后的子意图之间存在隐含依赖（如 "找到地址然后写入"），是否让 LLM 辅助判断依赖类型？还是全部用规则推断 `SEQUENTIAL`？
3. **实体归一化的国际化**：俄文/日文地址格式（如 `0x00400000` 的全角变体）是否需要额外处理？
4. **TaskGraph 与现有 `intent_agent.py` 的集成方式**：直接替换 `_react_loop` 的解析部分，还是并行运行、逐步切换？

---

*文档结束。此设计文档作为后续 4900 行代码实现的根本依据。任何代码变更若与设计文档冲突，需先更新文档或记录偏离原因。*
