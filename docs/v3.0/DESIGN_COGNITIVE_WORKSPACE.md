# DESIGN_COGNITIVE_WORKSPACE v1.0

> **版本**: 1.0  
> **状态**: 设计讨论  
> **核心命题**: 系统缺失的不是 RAG、Context、或更多子模块——而是一个让 LLM 在推理过程中"有地方想"的内部认知空间。

---

## 1. 问题定义

### 1.1 四个 P1 问题的共同根因

| 阻塞模块 | 表象 | 根因 |
|---------|------|------|
| 元认知 (Metacognition) | "LLM 在哪里反思？" | 没有 Cognitive Space 存放反思对象 |
| Tree of Thought | "ThoughtNode 属于什么空间？" | 临时推理对象无处归属 |
| 因果链 (Causal Chain) | "BehaviorGraph 记录的是事件" | Observation→Hypothesis→Revision→Belief 链无容器 |
| Meta Loop | "反思什么？" | 反思对象是整个内部状态，不只最终答案 |

**不是四个独立问题——是一个共同缺口暴露在四个地方。**

### 1.2 当前设计的局限

```
当前推理路径:
  EventIR → PerspectivePlanner → ContextAssembler → LLM → response
  
问题:
  推理过程是线性的、一次性的。没有中间状态可被观察、回溯、反思。
  LLM 的输出是文本——不是可查询的认知对象。
```

---

## 2. 四个空间模型

```
                External World
                      │
                      ▼
            ┌──────────────────┐
            │ Document Space    │  ← 物理组织：文件、代码、对话记录
            │ ObservationPool   │
            │ DocumentPipeline  │
            └──────────────────┘
                      │
              Observation Compiler
                      │
                      ▼
            ┌──────────────────┐
            │ Concept Space     │  ← 语义组织：对象、关系、投影
            │ SemanticObject    │
            │ RelationSubstrate │
            │ SemanticPath      │
            └──────────────────┘
                      │
          Hypothesis / Association Engine
                      │
                      ▼
            ┌──────────────────┐
            │ Knowledge Space   │  ← 冻结事实：信仰、已证实知识
            │ Belief State      │
            │ Frozen Facts      │
            │ Causal Rules      │
            └──────────────────┘
                      │
          Internal Reasoning
                      │
                      ▼
            ┌──────────────────┐
            │ Cognitive Space   │  ← 当前思考：视角、推理、反思
            │ Perspective       │
            │ Reasoning Tree    │
            │ Reflection Queue  │
            │ Hypothesis Pool   │
            └──────────────────┘
```

**前三个空间回答"知识如何组织"。第四个回答"推理时内部状态如何演化"。**

---

## 3. Cognitive Workspace 定义

### 3.1 核心数据结构

```python
@dataclass
class CognitiveWorkspace:
    """LLM 当前的大脑状态——所有会思考的模块共享此容器。"""

    # ── 观察者状态 (Observer) ──
    current_perspective: Optional[Perspective] = None
    current_horizon: Optional[Horizon] = None
    attention_distribution: Dict[str, float] = field(default_factory=dict)

    # ── 工作记忆 (Working Memory) ──
    active_objects: List[str] = field(default_factory=list)
    active_relations: List[RelationEdge] = field(default_factory=list)

    # ── 推理过程 (Reasoning) ──
    reasoning_tree: Optional[ReasoningNode] = None
    candidate_answers: List[CandidateAnswer] = field(default_factory=list)

    # ── 假设池 (Hypotheses) ──
    hypotheses: List[Hypothesis] = field(default_factory=list)
    conflicts: List[ConflictPair] = field(default_factory=list)

    # ── 自我监控 (Meta-Cognition) ──
    confidence: float = 0.5
    pending_questions: List[str] = field(default_factory=list)
    reflection_log: List[ReflectionEntry] = field(default_factory=list)

    # ── 预算 (Economics) ──
    token_budget_remaining: int = 0
    reasoning_depth: int = 0
    max_reasoning_depth: int = 3
```

### 3.2 与其他空间的关系

| 空间 | 关系 | 示例 |
|------|------|------|
| Document Space | 不直接访问 | - |
| Concept Space | **读**: Workspace 展开 SemanticObject 获取定义 | `active_objects = ["ContextCompiler"]` |
| Knowledge Space | **读/写**: 冰冻事实被工作记忆引用；推理结果可冰冻 | `belief_score += 0.1` |
| Cognitive Space | **自身** | 所有推理过程中间状态 |

**Workspace 不是替代其他空间——是给它们提供了一个"当前关注窗口"。**

### 3.3 Workspace 的生命周期

```
一次 LLM 推理调用 = 一个 CognitiveWorkspace 实例

  PerspectivePlanner.plan()
    → workspace.current_perspective = ...

  ObjectRuntime.render(obj, lod, persp)
    → workspace.active_objects.add(obj.name)

  RelationSubstrate.query()
    → workspace.active_relations = edges

  HypothesisEngine.submit()
    → workspace.hypotheses = matches

  LLM.generate()
    → workspace.reasoning_tree = parse_thoughts(response)

  MetaCognition.reflect(workspace)
    → workspace.reflection_log.append(entry)
    → workspace.confidence = update(entry)

  推理结束 → Workspace 可序列化到 Knowledge Space (冰冻)
```

---

## 4. 如何解决四个 P1 问题

### 4.1 元认知

**之前**: 不知道反思什么。  
**之后**: `MetaCognition.reflect(workspace)` 遍历 workspace 全部状态——不只答案，而是 perspective/hypotheses/conflicts/confidence。

```python
def reflect(workspace: CognitiveWorkspace) -> ReflectionEntry:
    checks = [
        ("confidence_too_low", workspace.confidence < 0.4),
        ("single_hypothesis", len(workspace.hypotheses) == 1),
        ("shallow_reasoning", workspace.reasoning_depth < 2),
        ("no_alternative_perspective", len(workspace.attention_distribution) < 2),
    ]
    triggers = [name for name, triggered in checks if triggered]
    return ReflectionEntry(triggers=triggers, suggestion=action_map[triggers])
```

### 4.2 Tree of Thought

**之前**: ThoughtNode 不知道属于什么空间。  
**之后**: `workspace.reasoning_tree` 是 Workspace 的属性。

```python
@dataclass
class ReasoningNode:
    id: str
    hypothesis: str          # "ContextCompiler 负责跨域编译"
    evidence_for: List[str]   # "文档 §3.1 提到 compile_context()"
    evidence_against: List[str]
    children: List[ReasoningNode]
    confidence: float
    # 不属于 Knowledge——是临时推理对象
    # 不属于 Concept——是可展开/可修剪的动态节点
    # 属于 Cognitive Workspace
```

### 4.3 因果链

**之前**: BehaviorGraph 记录的是 User→Assistant 事件链。  
**之后**: Workspace 记录的是认知因果链：

```
Observation → Hypothesis → CounterEvidence → Revision → Belief

不是"用户问了什么"——是"LLM 内部如何从观察到信仰"。
```

### 4.4 Meta Loop

**之前**: 不知道循环反思想干什么。  
**之后**: Meta Loop 就是 `CognitiveWorkspace` 的状态转换：

```
Workspace(t=1) → LLM → Workspace(t=2) → MetaCognition.reflect() → Workspace(t=3) → ...
```

每次转换，Workspace 的 confidence/concepts/hypotheses 可能变化。Meta Loop 监控这些变化。

---

## 5. 四棵树的重新定义

四种树不是独立的——它们共享 SemanticObject，但用途不同：

| 树 | 空间 | 表示 | 构建者 |
|----|------|------|--------|
| **Conversation Tree** | Document Space | 对话历史 | DiscourseBlockTree |
| **Topic Tree** | Concept Space | 讨论主题 | TopicTreeManager |
| **Semantic Tree** | Concept Space | 对象展开 | ObjectRuntime.render() |
| **Reasoning Tree** | **Cognitive Space** | 当前推理 | MetaCognition.build_tree() |

**同一个 SemanticObject 在四棵树里出现，但角色不同**：

```
Observation:
  Conversation Tree: "昨天讨论Observation"       ← 时间维度
  Topic Tree:        "Runtime > Observation"      ← 话题分类
  Semantic Tree:     "Runtime > Observation       ← 对象展开
                       > Normalizer
                       > Projector"
  Reasoning Tree:    "Question → NeedRuntime →   ← 推理路径
                       NeedObservation → Stop"
```

---

## 6. Observer 模式

Perspective 不是数据的属性——是观察者的状态：

```
之前: SemanticObject.projection = design_perspective  ← 属于对象
之后: Observer.perspective = architecture             ← 属于观察者
      Observer.attention = {"ContextCompiler": 0.6,
                            "DomainSelector":  0.3,
                            "BudgetAllocator": 0.1}
```

```python
@dataclass
class Observer:
    """观察者——LSM 的认知主体。"""
    perspective: Perspective
    attention: Dict[str, float]          # 对象名 → 注意力权重
    horizon: Horizon
    working_memory_capacity: int = 7     # 7±2 记忆限制
    cognitive_load: float = 0.0          # 0-1，当前负担
```

**Observer + CognitiveWorkspace = LLM 的完整认知状态。**

---

## 7. 与现有模块的精确映射

| 现有模块 | 输出目标 | 规则 |
|---------|---------|------|
| PerspectivePlanner | `workspace.current_perspective` | 写入 |
| ObjectRuntime.render() | `workspace.active_objects` | 写入 |
| RelationSubstrate.query() | `workspace.active_relations` | 写入 |
| HypothesisEngine.submit() | `workspace.hypotheses` | 写入 |
| MetaCognition | `workspace.reflection_log`, `workspace.confidence` | 读写 |
| LLM.generate() | `workspace.reasoning_tree` | 写入 |
| DiscourseBlockTree | 保持不变（属于 Document Space） | - |

**现有模块不需要重写——加一个写入目标即可。**

---

## 8. 实现优先级

| Phase | 内容 | 接口变化 |
|-------|------|---------|
| **Phase 2a** | CognitiveWorkspace 数据类 + Workspace 在编译管线中的创建和填充 | 0 个现有接口改动 |
| **Phase 2b** | MetaCognition.reflect(workspace) | 新增 1 个方法 |
| **Phase 2c** | ReasoningTree 构建和展开 | 新增 1 个数据类 |
| **Phase 2d** | Observer 模式 + 注意力分配 | PerspectivePlanner 微调 |

---

## 附录 A: 与设计文档的继承关系

| 被修订的设计 | 修订内容 |
|------------|---------|
| DESIGN_PERSPECTIVE_PLANNER §6 | Capability Space → 明确为 Observer 模式的一部分 |
| DESIGN_SEMANTIC_OBJECT §3 | projections → 从对象属性变为观察者视角渲染结果 |
| DESIGN_RELATION_SUBSTRATE §7 | Causal mechanism → 定义归属从 BehaviorGraph 到 CognitiveWorkspace.reasoning_tree |
| DESIGN_FULL_CONCEPT §4.3 | 元认知 → 从抽象概念到具体 `reflect(workspace)` 接口 |
| DESIGN_MULTILAYER_LLM_COGNITIVE §4 | LLM Cognitive Tree → 重新定义为 ReasoningTree，归属 CognitiveWorkspace |
