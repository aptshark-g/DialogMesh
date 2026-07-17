# DialogMesh v5：状态演化系统设计

## 状态：设计阶段 v0.1（2026年7月）
## 作者：APTShark + Agent

---

## 一、问题诊断

### 1.1 当前架构的根本缺陷

v4 构建了四个空间（Document、Semantic、Cognitive、Execution），但每个空间**各自维护自己的状态**：

```
ConceptGraph     → 自己维护 relation
BehaviorGraph    → 自己维护 behavior edge
CausalPlanner    → 自己维护 causal edge
ExecutionTrace   → 自己维护 trace
Reflection       → 自己维护 confidence
Prediction       → 自己维护 expectation
```

这不是 6 个独立的 Bug——这是**同一个根因**：**缺少统一的状态对象和状态演化语义**。

### 1.2 缺失的核心对象

当前系统有：Document、SemanticObject、Knowledge、Workspace、Observer、ReasoningTree、Runtime。

**缺失的是：Mind（长期心智）**。

Workspace 是一次思考。Mind 是经历了所有推理之后，系统最终学会的东西。Workspace 可以销毁。Mind 必须持久。

---

## 二、核心架构：Mind 驱动的状态演化系统

### 2.1 整体架构

```
                        ┌─────────────────────────────────┐
                        │            MIND                  │
                        │  (长期持久化认知结构)               │
                        │                                  │
                        │  Attention Prior                 │
                        │  Prediction Prior                │
                        │  Preference Model                │
                        │  Thinking Style                  │
                        │  Learned Strategy                │
                        │  Common Mistakes                 │
                        │  Reflection History              │
                        │  Relation Prior                  │
                        │  Behavior Prior                  │
                        │  Expectation Prior               │
                        └──────────┬──────────────────────┘
                                   │ 初始化
                                   ▼
                        ┌─────────────────────────────────┐
                        │          OBSERVER               │
                        │  (受 Mind 驱动的感知器)            │
                        └──────────┬──────────────────────┘
                                   │
                                   ▼
                        ┌─────────────────────────────────┐
                        │         WORKSPACE               │
                        │  (一次思考的瞬态空间)              │
                        │                                  │
                        │  SemanticObject (活跃对象)        │
                        │  RelationGraph  (统一关系图)       │
                        │  ReasoningTree  (推理路径)         │
                        │  Hypothesis     (假设集合)         │
                        └──────────┬──────────────────────┘
                                   │
                                   ▼
                        ┌─────────────────────────────────┐
                        │     EXECUTION TRACE              │
                        │  (状态快照序列)                    │
                        │                                  │
                        │  State(t0) → State(t1) → ...     │
                        │  每个快照包含:                     │
                        │    - 注意力分布                    │
                        │    - 活跃假设                      │
                        │    - 置信度分布                    │
                        │    - 关系激活状态                  │
                        │    - 冲突状态                      │
                        └──────────┬──────────────────────┘
                                   │
                                   ▼
                        ┌─────────────────────────────────┐
                        │         REFLECTION               │
                        │  (分析状态变迁, 提取学习信号)        │
                        └──────────┬──────────────────────┘
                                   │
                                   ▼
                        ┌─────────────────────────────────┐
                        │        MIND UPDATE               │
                        │  (将反思结果沉淀为长期心智)          │
                        └─────────────────────────────────┘
```

### 2.2 闭环

```
Mind → Observer → Workspace → ExecutionTrace → Reflection → Mind Update → (下次)
  ↑                                                                    │
  └────────────────────────────────────────────────────────────────────┘
```

这不是"处理对话"——这是**持续演化对用户的理解**。

---

## 三、Mind：长期持久化认知结构

### 3.1 定义

Mind 不是"大号的 Workspace"。Workspace 是一次推理的瞬态空间。Mind 是跨对话、跨工作区的持久化认知结构。

### 3.2 结构

```python
@dataclass
class Mind:
    """长期持久化认知结构。Workspace 每次初始化时从此继承先验。"""

    # ── 注意力先验 ──
    attention_prior: Dict[str, float]
    # 例: {"Runtime": 0.9, "Observation": 0.7, "Normalizer": 0.3}
    # 含义: 系统已经知道用户关心 Runtime 远多于 Normalizer

    # ── 预测先验 ──
    prediction_prior: Dict[str, float]
    # 例: {"simulation": 0.81, "topic_transition": 0.40}
    # 含义: LLM 模拟策略比主题转移有效得多

    # ── 偏好模型 ──
    preference_model: Dict[str, Any]
    # 例: {"perspective": "architecture", "depth": "high", "style": "bottom-up"}
    # 含义: 用户偏好架构视角、深度分析、自底向上

    # ── 思维风格 ──
    thinking_style: Dict[str, float]
    # 例: {"analytical": 0.85, "exploratory": 0.30, "emotional": 0.15}
    # 含义: 用户高度分析型思维

    # ── 已学策略 ──
    learned_strategies: Dict[str, StrategyRecord]
    # 例: {"explain_via_relation": StrategyRecord(effectiveness=0.88, uses=45)}
    # 含义: "通过关系解释"策略 88% 有效, 已使用 45 次

    # ── 常见错误 ──
    common_mistakes: List[MistakeRecord]
    # 例: [MistakeRecord("假设用户了解 Normalizer", frequency=12)]
    # 含义: 系统已经学会不要假设用户理解 Normalizer

    # ── 反思历史 ──
    reflection_history: List[ReflectionRecord]
    # 例: [ReflectionRecord("哪些反思真正改变了置信度")]
    # 含义: 用于元学习——学习哪些反思策略有效

    # ── 关系先验 ──
    relation_prior: Dict[str, float]
    # 例: {"depends_on": 0.9, "contains": 0.7, "causal": 0.4}
    # 含义: 用户问题更多涉及依赖关系而非因果关系

    # ── 行为先验 ──
    behavior_prior: Dict[str, float]
    # 例: {"drill_down": 0.75, "topic_switch": 0.20}
    # 含义: 用户倾向于深入而非频繁切换话题
```

### 3.3 Mind 的生命周期

```
[对话开始]
    │
    ▼
Mind.load(user_id)
    │
    ▼
Workspace.initialize(mind.attention_prior, mind.preference_model, ...)
    │
    ▼
[对话进行: 多轮 Workspace → ExecutionTrace]
    │
    ▼
Reflection.analyze(execution_trace)
    │
    ▼
Mind.update(reflection_result)
    │
    ▼
Mind.save(user_id)
```

### 3.4 Mind Update 的机制

Mind 不是每次整个替换——是**增量更新**：

```python
def update_mind(mind: Mind, reflection: ReflectionResult):
    # 1. 注意力先验：EMA 平滑
    for obj, att in reflection.final_attention.items():
        old = mind.attention_prior.get(obj, 0.5)
        mind.attention_prior[obj] = 0.7 * old + 0.3 * att

    # 2. 策略权重：增量调整
    for strategy, result in reflection.strategy_results.items():
        old = mind.learned_strategies.get(strategy)
        if old:
            old.effectiveness = 0.9 * old.effectiveness + 0.1 * result.effectiveness
            old.uses += 1
        else:
            mind.learned_strategies[strategy] = StrategyRecord(
                effectiveness=result.effectiveness, uses=1
            )

    # 3. 常见错误：频率累积
    for mistake in reflection.mistakes:
        existing = find(mind.common_mistakes, mistake)
        if existing:
            existing.frequency += 1
        else:
            mind.common_mistakes.append(mistake)

    # 4. 低质量记录淘汰
    mind.reflection_history = mind.reflection_history[-100:]  # 保留最近 100 条
```

---

## 四、统一关系图（Universal Relation Graph）

### 4.1 核心原则

**只有一种图——RelationGraph。边的类型决定语义。**

### 4.2 关系类型体系

```python
class RelationType(Enum):
    # ── 结构关系 ──
    CONTAINS = "contains"          # A 包含 B
    DEPENDS_ON = "depends_on"      # A 依赖 B
    IMPLEMENTS = "implements"      # A 实现 B
    DEFINES = "defines"            # A 定义 B

    # ── 语义关系 ──
    SEMANTIC_SIMILAR = "semantic"  # A 与 B 语义相似
    ANALOGOUS_TO = "analogous"     # A 类比于 B
    EVOLVES_TO = "evolves_to"      # A 演化为 B

    # ── 因果/逻辑关系 ──
    CAUSAL = "causal"              # A 导致 B
    CONTRADICTS = "contradicts"    # A 与 B 冲突
    SUPPORTS = "supports"          # A 支持 B

    # ── 行为关系 ──
    BEHAVIOR = "behavior"          # 用户行为模式
    ATTENTION = "attention"        # 注意力关联
    PREDICT = "predict"            # 预测关系
```

### 4.3 统一边结构

```python
@dataclass
class RelationEdge:
    source: str                     # 源对象 ID
    target: str                     # 目标对象 ID
    type: RelationType              # 关系类型
    confidence: float               # 置信度 [0, 1]
    evidence: List[str]             # 证据来源
    created_at: float               # 创建时间
    last_activated: float           # 最后激活时间
    activation_count: int = 0       # 激活次数
    metadata: Dict[str, Any] = {}   # 扩展字段
```

### 4.4 当前三系统的迁移

```
ConceptGraph edges     → RelationGraph(type=CONTAINS|DEPENDS_ON|IMPLEMENTS)
RelationSubstrate      → RelationGraph(type=SEMANTIC|ANALOGOUS|EVOLVES_TO)
BehaviorGraph          → RelationGraph(type=BEHAVIOR, metadata={"pattern": "drill_down"})
CausalPlanner          → RelationGraph(type=CAUSAL|SUPPORTS|CONTRADICTS, confidence >= 0.7)
```

因果链不是独立系统——是 RelationGraph 中 `type=CAUSAL 且 confidence >= 0.7` 的子集。

### 4.5 图操作

```python
class RelationGraph:
    def add(source, target, type, confidence, evidence) -> RelationEdge
    def query(source=None, target=None, type=None, min_confidence=0.0) -> List[RelationEdge]
    def activate(edge_id) -> None                    # 激活计数+1
    def get_causal_chain(start_node) -> List[RelationEdge]  # 高置信因果链
    def get_attention_subgraph(focus_nodes) -> Graph        # 注意力子图
    def merge(other_graph) -> None                          # 合并另一图
```

---

## 五、ExecutionTrace v2：状态快照序列

### 5.1 当前问题

v4 的 ExecutionTrace 记录的是：

```
PERCEIVE → REASON → REFLECT
```

这太浅了——它记录的是**函数调用**，不是**认知状态的变化**。

### 5.2 v2 设计：Workspace Snapshot 序列

```python
@dataclass
class WorkspaceSnapshot:
    """某一时刻的完整认知状态。"""
    timestamp: float

    # 注意力分布
    attention: Dict[str, float]
    # 例: {"Runtime": 0.6, "Scheduler": 0.3, "Observation": 0.1}

    # 活跃假设
    active_hypotheses: List[Hypothesis]
    # 例: [Hypothesis("用户不理解 Normalizer", confidence=0.47)]

    # 拒绝假设
    rejected_hypotheses: List[Hypothesis]

    # 置信度分布（每个候选答案的置信度）
    confidence_distribution: Dict[str, float]

    # 关系激活状态
    activated_relations: List[str]   # 本步激活的关系边 ID

    # 冲突状态
    conflicts: List[Conflict]        # 检测到的冲突

    # 工作区对象快照
    workspace_objects: Dict[str, Any]


@dataclass
class ExecutionTraceV2:
    """状态快照序列。"""
    session_id: str
    snapshots: List[WorkspaceSnapshot]   # 按时间排序

    def delta(self, from_idx: int, to_idx: int) -> StateDelta:
        """计算两次快照间的状态变化。"""
        ...

    def replay(self, from_idx: int) -> WorkspaceSnapshot:
        """从指定快照恢复状态并重新推理。"""
        ...
```

### 5.3 一个真实的 Trace 示例

```
t=0 (初始)
  attention: {Runtime: 0.6, Scheduler: 0.3}
  confidence: {A: 0.0, B: 0.0}
  hypotheses: []

t=1 (检索后)
  attention: {Runtime: 0.4, Scheduler: 0.5, Observation: 0.1}
  confidence: {A: 0.28}
  hypotheses: [A: "用户需要理解 Runtime→Scheduler 流程"]

t=2 (关系激活后)
  attention: {Scheduler: 0.7, Observation: 0.2}
  confidence: {A: 0.47, B: 0.31}
  hypotheses: [A, B: "用户可能对 Observation 机制困惑"]
  activated_relations: ["Runtime-depends_on-Scheduler", "Scheduler-uses-Observation"]

t=3 (冲突解决后)
  attention: {Scheduler: 0.7, Observation: 0.3}
  confidence: {B: 0.81}
  hypotheses: [B]
  rejected_hypotheses: [A]
  conflicts: [Conflict("假设 A 被证据否定: Scheduler 不直接调用 Runtime")]

t=4 (反思后)
  attention: {Scheduler: 0.5, Observation: 0.5}
  confidence: {B: 0.88}
  committed_knowledge: ["Scheduler 依赖 Observation 组件"]
```

### 5.4 Trace 的能力

有了状态快照序列，以下问题都可回答：

| 问题 | 方法 |
|------|------|
| 哪一步提升了置信度？ | `delta(from=1, to=3).confidence_diff` |
| 哪个关系激活最有效？ | `find_max(delta.activated_relations)` |
| 为什么拒绝了假设 A？ | `snapshots[3].conflicts` |
| 可以从中途重放吗？ | `replay(from_idx=1)` |
| 两次推理有何不同？ | `trace_a.diff(trace_b)` |

---

## 六、统一的数据流

### 6.1 完整流程

```
User Input
    │
    ▼
┌─────────────────────────────────────────────┐
│ Mind.load(user_id)                          │
│   ↓                                         │
│ Observer(attention_prior, preference_model)  │
│   ↓                                         │
│ Workspace.initialize(mind)                   │
│   - 从 Mind 继承 Attention Prior            │
│   - 从 Mind 继承 Preference Model            │
│   - 从 Mind 继承 Learned Strategies          │
│   - 从 KnowledgeSpace 加载相关 SemanticObject │
│   - 从 RelationGraph 加载相关关系子图          │
└──────────┬──────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────┐
│ Reasoning Loop (多步)                        │
│                                              │
│   for step in reasoning_steps:               │
│     1. 检索相关对象 (SemanticObject)          │
│     2. 激活关系 (RelationGraph.activate)       │
│     3. 生成假设 (Hypothesis)                  │
│     4. 解决冲突                               │
│     5. 更新置信度                             │
│     6. 记录快照 (WorkspaceSnapshot)            │
│                                              │
│   每个快照记录:                               │
│     - attention 变化                         │
│     - hypothesis 增删                        │
│     - confidence 变迁                        │
│     - relation 激活                          │
│     - conflict 状态                          │
└──────────┬──────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────┐
│ Reflection                                   │
│                                              │
│   analyze(trace):                            │
│     - 哪些步骤真正提升了置信度？                 │
│     - 哪个关系激活最有效？                      │
│     - 哪些假设被错误拒绝了？                    │
│     - 用户的认知缺口在哪里？                    │
│     - 哪些策略应该加强/减弱？                   │
└──────────┬──────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────┐
│ Mind Update                                  │
│                                              │
│   mind.attention_prior ← EMA(trace.final)    │
│   mind.prediction_prior ← sim_feedback       │
│   mind.preference_model ← trace.patterns     │
│   mind.learned_strategies ← reflection       │
│   mind.common_mistakes ← trace.conflicts     │
│                                              │
│   mind.save(user_id)                         │
└──────────┬──────────────────────────────────┘
           │
           ▼
        Knowledge Commit
  (高置信知识 → KnowledgeSpace)
```

---

## 七、实现路线图

### Phase A：统一关系图（1-2 天）

| 任务 | 内容 |
|------|------|
| A1 | 定义 `RelationType` 枚举和 `RelationEdge` 统一结构 |
| A2 | 实现 `UnifiedRelationGraph` 类 |
| A3 | 迁移 `ConceptGraph` 边 → 统一图 |
| A4 | 迁移 `RelationSubstrate` 边 → 统一图 |
| A5 | 迁移 `CausalPlanner` 因果边 → 统一图（高置信子集） |
| A6 | 删除旧的三套图系统 |

### Phase B：ExecutionTrace v2（1 天）

| 任务 | 内容 |
|------|------|
| B1 | 定义 `WorkspaceSnapshot` 结构 |
| B2 | 实现 `ExecutionTraceV2` 的 `snapshot()` / `delta()` / `replay()` |
| B3 | 接入 Workspace：每步推理后记录快照 |
| B4 | 替换旧 `ExecutionTrace` |

### Phase C：Mind 持久化认知结构（2-3 天）

| 任务 | 内容 |
|------|------|
| C1 | 定义 `Mind` 数据结构 |
| C2 | 实现 `Mind.load()` / `Mind.save()` / `Mind.update()` |
| C3 | 实现 `Workspace.initialize(mind)` |
| C4 | 实现 `Reflection → Mind Update` 闭环 |
| C5 | 端到端验证：多轮对话后 Mind 正确演化 |

### Phase D：模拟引擎与 Mind 集成（1 天）

| 任务 | 内容 |
|------|------|
| D1 | Simulation 引擎从 Mind 读取 Prediction Prior |
| D2 | 模拟结果失败/成功 → 更新 Mind.prediction_prior |
| D3 | 用户偏好影响模拟策略选择 |

---

## 八、从"组织知识的系统"到"演化认知的系统"

### 8.1 关键的范式转变

| 维度 | v4（当前） | v5（目标） |
|------|-----------|-----------|
| 核心对象 | Document, Concept, Knowledge | **State**, **Transition**, **Mind** |
| 关系 | 三套并行图 | 统一 RelationGraph |
| 追踪 | 函数调用序列 | 状态快照序列 |
| 学习 | 无 | Mind 增量更新 |
| 成长 | 每次对话从零开始 | Mind 跨对话持续演化 |
| 反思 | 事后文本 | 分析状态变迁 |
| 元认知 | 分散在各模块 | 统一在 Mind + Trace |

### 8.2 系统从此能做什么

- **跨对话记忆**：用户 3 天前的偏好仍在 Mind 中
- **自适应策略**：自动学习哪种解释方式对特定用户最有效
- **可回放推理**：Trace 允许从任意步骤重新推理
- **可解释性**：状态变迁序列就是推理过程的完整解释
- **元学习**：学习"如何学习"，而不只是学习知识
