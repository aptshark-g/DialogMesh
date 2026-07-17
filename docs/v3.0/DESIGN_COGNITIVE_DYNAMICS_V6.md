# DialogMesh v6：认知动力学（Cognitive Dynamics）

## 状态：设计阶段 v0.1（2026年7月）
## 作者：APTShark + Agent

---

## 一、从 Object 到 State 到 Transition 到 Dynamics

### 1.1 四个范式层级

```
v1-v4:  Object Paradigm
        "系统里有什么？"  Document, SemanticObject, Relation, Workspace, Knowledge

v5:     State Paradigm
        "系统现在的状态是什么？"  State, Snapshot, Evolution, Mind

v6:     Transition Paradigm  ← 当前设计目标
        "状态为什么变化？"  Transition, Reason, Cause, Effect

v7:     Dynamics Paradigm  ← 远景
        "变化的规律是什么？"  Mind(t) → Mind(t+1), 认知动力学
```

### 1.2 核心洞察

**真正的智能不在状态——在状态的变化。**

以前的 DialogMesh 回答："系统里有什么？"（对象）或"系统现在是什么状态？"（状态）。但从 v6 开始，系统回答的是：**"状态为什么从 A 变成了 B？"**

---

## 二、StateObject：统一状态体系

### 2.1 核心抽象

所有"东西"本质都是 State，只是生命周期不同：

```
StateObject
├── Snapshot      (1 second)      — 瞬态快照
├── Workspace     (1 conversation) — 一次推理
├── Mind          (1 month)       — 长期心智
└── Knowledge     (forever)       — 冻结知识
```

### 2.2 统一操作

```python
class StateObject:
    lifespan: Lifespan          # SNAPSHOT | WORKSPACE | MIND | KNOWLEDGE
    created_at: float
    last_modified: float
    data: Dict[str, Any]

    def evolve(transition: Transition) -> StateObject:
        """应用一个状态转换，返回新状态。"""

    def freeze() -> StateObject:
        """冻结为更长的生命周期。"""

    def snapshot() -> StateObject:
        """创建当前状态的快照。"""
```

### 2.3 生命周期升级路径

```
Snapshot ──(accumulate)──→ Workspace ──(reflect)──→ Mind ──(commit)──→ Knowledge
    ↑                          ↑                      ↑                   ↑
    瞬态                       一次推理                长期心智             永久知识
```

---

## 三、Transition：v6 的核心一等公民

### 3.1 定义

Transition 不是状态的附属——它是**独立的一等对象**。

```python
@dataclass
class Transition:
    """从一个 State 到另一个 State 的变化。"""

    id: str
    from_state: StateObject
    to_state: StateObject

    # ── 变化的原因 ──
    reason: TransitionReason       # 为什么会发生这个转换？

    # ── 变化的证据 ──
    evidence: List[Evidence]       # 支持这个转换的证据

    # ── 变化的影响 ──
    effects: List[StateDelta]      # 对系统各部分的具体影响

    # ── 元信息 ──
    confidence: float              # 转换本身的置信度
    timestamp: float
```

### 3.2 TransitionReason 类型体系

```python
class TransitionReason(Enum):
    # ── 观察驱动 ──
    OBSERVE = "observe"            # 新观察到了什么
    NEW_EVIDENCE = "new_evidence"  # 新证据出现

    # ── 推理驱动 ──
    INFER = "infer"                # 推理出了新结论
    COMPARE = "compare"            # 比较后发现了差异
    ANALOGIZE = "analogize"        # 类比迁移

    # ── 冲突驱动 ──
    CONTRADICT = "contradict"      # 发现矛盾
    REJECT = "reject"              # 拒绝假设
    RESOLVE = "resolve"            # 解决冲突

    # ── 整合驱动 ──
    MERGE = "merge"                # 合并两个状态
    FREEZE = "freeze"              # 冻结为长期知识
    GENERALIZE = "generalize"      # 泛化提升

    # ── 反思驱动 ──
    REFLECT = "reflect"            # 元认知反思
    REVISE = "revise"              # 修正之前的判断
    STRENGTHEN = "strengthen"      # 增强置信度
    WEAKEN = "weaken"              # 减弱置信度

    # ── 视角驱动 ──
    CHANGE_PERSPECTIVE = "change_perspective"  # 切换视角
    SHIFT_ATTENTION = "shift_attention"        # 注意力转移
```

### 3.3 真实示例

```
t=0: State(snapshot_0)
  confidence: {A: 0.28}
  attention: {Runtime: 0.6}

       ↓ Transition(reason=OBSERVE)
       │ evidence: [Evidence("Runtime 文档显示 depends_on Scheduler")]
       │ effects: [StateDelta("attention", Scheduler: +0.2)]

t=1: State(snapshot_1)
  confidence: {A: 0.47, B: 0.31}
  attention: {Runtime: 0.4, Scheduler: 0.5}

       ↓ Transition(reason=CONTRADICT)
       │ evidence: [Evidence("假设 A 假设 Runtime 直接调用, 但实际通过 Scheduler")]
       │ effects: [StateDelta("rejected_hypotheses", +A)]

t=2: State(snapshot_2)
  confidence: {B: 0.81}
  attention: {Scheduler: 0.7, Observation: 0.3}
  rejected_hypotheses: [A]

       ↓ Transition(reason=STRENGTHEN)
       │ evidence: [Evidence("BGE 检索确认 Scheduler-Observation 依赖")]
       │ effects: [StateDelta("confidence.B", +0.07)]

t=3: State(snapshot_3)
  confidence: {B: 0.88}
```

### 3.4 Transition 的价值

| 能力 | 方法 |
|------|------|
| **可解释性** | 不只是"最终答案是什么"——而是"每一步为什么这么走" |
| **可回放** | `replay(from=snapshot_1)` 可以从中途重新推理 |
| **可比较** | `diff(trace_a, trace_b)` 比较两条推理路径 |
| **元认知** | 检查 Transition 模式："为什么连续 REJECT？""为什么一直 INFER？" |
| **学习** | 学习哪些 Transition 类型在什么 Context 下最有效 |

---

## 四、Contextual Learning：从"什么策略好"到"什么情况下什么策略好"

### 4.1 问题

v5 的 Mind 用 EMA 和频率统计学习策略效果。但这是**经验统计**——只看次数，不看 Context。

### 4.2 升级：Strategy Context

```python
@dataclass
class StrategyContext:
    """策略生效的具体上下文。"""
    perspective: str            # 当前视角 (architecture/engineering/...)
    depth: int                  # 当前推理深度
    domain: str                 # 问题领域 (Runtime/Scheduler/...)
    time_of_day: str            # 时间段
    discussion_mode: str        # 连续讨论 / 新话题 / 纠正
    user_cognitive_state: str   # 用户当前认知状态


@dataclass
class ContextualStrategy:
    """上下文感知的策略记录。"""
    strategy_name: str
    contexts: Dict[str, StrategyRecord]  # 按 context hash 分组

    def best_for(self, context: StrategyContext) -> str:
        """在当前上下文中，哪个策略最有效？"""
        ctx_hash = context.hash()
        return max(self.contexts[ctx_hash], key=lambda r: r.effectiveness)

    def record(self, context: StrategyContext, effectiveness: float):
        """记录某个策略在特定上下文中的效果。"""
```

### 4.3 对比

```
之前: Strategy A 用了 45 次，平均效果 0.88

之后: Strategy A 在 [Architecture + Depth=3 + Runtime + morning + continuous]
      下效果 0.94
      但在 [Engineering + Depth=1 + UI + afternoon + new_topic]
      下效果 0.52
      
→ 所以当前 Context 是 Architecture/Runtime → 用 A
  当前 Context 是 Engineering/UI → 不用 A，换 B
```

---

## 五、Interaction Graph：从静态关系到动态影响

### 5.1 Relation vs Interaction

```
Relation（关系）：   A 和 B 之间有什么联系？        静态
Interaction（交互）：A 的变化如何影响 B？            动态
```

### 5.2 升级

```python
@dataclass
class InteractionEdge(RelationEdge):
    """关系边 + 影响传播能力。"""

    # 继承 RelationEdge 的字段: source, target, type, confidence

    # ── 动态影响 ──
    propagation_rule: Callable   # 状态如何从 source 传播到 target
    # 例: lambda src_state: src_state.confidence * 0.7

    influence_weight: float      # 影响强度
    # 例: Scheduler 的 state 变化对 Observation 的影响权重 = 0.8

    activation_threshold: float  # 激活阈值
    # 例: 只有当 Runtime.confidence > 0.6 时，这个 interaction 才激活
```

### 5.3 示例

```
Runtime ──(depends_on, influence=0.9)──→ Scheduler
   ↑                                        │
   │                                   (uses, influence=0.7)
   │                                        ↓
   └──(contains, influence=0.3)──→ Observation

当 Runtime.confidence 从 0.3 升到 0.8:
  1. Runtime→Scheduler:  Scheduler.confidence += 0.8 * 0.9 = +0.72
  2. Scheduler→Observation: Observation.attention += Scheduler.confidence * 0.7
```

这就是**状态传播**——不再是静态关系，而是动态影响流。

---

## 六、ExecutionTrace v3：State → Transition → State

### 6.1 v2 vs v3

```
v2: State(t0) → State(t1) → State(t2) → State(t3)
    只记录"是什么"，不记录"为什么"

v3: State(t0) → Transition(reason, evidence) → State(t1)
               → Transition(reason, evidence) → State(t2)
               → Transition(reason, evidence) → State(t3)
    每个变化都有原因、证据和影响
```

### 6.2 新结构

```python
@dataclass
class ExecutionTraceV3:
    session_id: str
    states: List[StateObject]        # 状态序列
    transitions: List[Transition]    # 转换序列

    @property
    def reasoning_path(self) -> str:
        """可读的推理路径。"""
        return " → ".join(
            f"[{t.reason.value}]{t.evidence_summary}" for t in self.transitions
        )

    def why_did_state_change(self, index: int) -> Transition:
        """第 index 步状态为什么变化？"""
        return self.transitions[index]

    def transitions_of_type(self, reason: TransitionReason) -> List[Transition]:
        """筛选特定类型的转换。"""
        return [t for t in self.transitions if t.reason == reason]

    def meta_analyze(self) -> MetaReport:
        """元认知分析：哪些转换类型占主导？"""
        # 例: "80% 的转换是 INFER，10% 是 CONTRADICT，5% 是 REJECT"
        # → "推理流畅，很少遇到冲突"
```

### 6.3 元认知通过 Transition 来分析

```
不再是：检查 Workspace 状态
而是：  检查 Transition 模式

问题示例：
  "为什么连续 3 次 REJECT？"    → 某个假设基础不稳
  "为什么一直 INFER 没有 OBSERVE？" → 缺少外部证据，纯推理
  "为什么突然 CHANGE_PERSPECTIVE？" → 某个冲突触发了视角切换
  "为什么 MERGE 后置信度下降了？"  → 合并引入了矛盾
```

---

## 七、认知动力学（Cognitive Dynamics）——远景

### 7.1 定义

认知动力学研究的不是"系统是什么状态"，而是**"状态为什么这样变化"**。

```
Mind(t) ──(为什么?)──→ Mind(t+1)
```

### 7.2 核心问题

| 问题 | 动力学视角 |
|------|-----------|
| 为什么 Perspective 突然切换？ | 检测到 CHANGE_PERSPECTIVE 触发条件 |
| 为什么 Hypothesis 冻结了？ | FREEZE 转换的触发阈值被满足 |
| 为什么 Relation 消失了？ | REJECT 或 WEAKEN 转换消除了它 |
| 为什么连续犯错？ | OBSERVE→INFER→REJECT 的循环模式 |
| 什么条件下学习最快？ | 哪些 Context + Transition 组合效果最好 |

### 7.3 从 v6 到 v7

```
v6: Transition 是一等公民
    - 每个状态变化都有原因
    - 元认知检查 Transition 模式
    - 学习哪些 Transition 在什么 Context 下有效

v7: Dynamics 是一等公民
    - 系统有自己的认知动力学模型
    - 预测: "在这种状态下，下一步可能发生什么 Transition？"
    - 调节: "为了避免连续 REJECT，提前切换 Perspective"
    - 自我演化: 动力学规律本身也在学习和改进
```

---

## 八、整个架构发展史的统一视角

```
v1-v2: Memory     → "记住东西"
v3:    Knowledge  → "组织知识"
v4:    Object     → "组织概念" (SemanticObject)
v5:    State      → "组织状态" (Mind, Workspace, Trace)
v6:    Transition → "理解变化" (Transition, Interaction, Contextual Learning)
v7:    Dynamics   → "预测和调节变化" (Cognitive Dynamics)
```

**真正的分水岭不在 v5→v6 之间——在 Object→State 之间。** 一旦系统开始以 State 为中心组织自己，Transition 和 Dynamics 就是自然的下一步。

---

## 九、与外部前沿的定位

| 研究 | 关注的层次 | DialogMesh v6 的层次 |
|------|----------|---------------------|
| Reflexion | 一次失败的 Transition（事后） | 所有 Transition 的结构化记录 |
| Self-Refine | State 内部的微调 | State 之间的 Transition |
| Anthropic J-space | LLM 内部的 State | LLM 外部的 State → Transition 体系 |
| Active Inference | 预测 State Transition | 记录和学习了 State Transition |
| Cognitive Architectures (ACT-R, SOAR) | 认知状态的符号化 | 认知 Transition 的结构化 + 元学习 |

DialogMesh v6 的独特定位：**不是 LLM 内部的状态——是围绕 LLM 运行的外部认知状态机。**

---

## 十、实现优先级

| 优先级 | 组件 | 原因 |
|--------|------|------|
| P0 | StateObject 统一抽象 | 所有后续工作的基础 |
| P0 | Transition + TransitionReason | v6 的核心一等公民 |
| P1 | ExecutionTrace v3 (State→Transition→State) | 替代 v2 |
| P1 | ContextualStrategy (Mind 升级) | EMA → Context-Aware |
| P2 | Interaction Graph | RelationGraph → Interaction |
| P2 | Meta-Analysis on Transitions | 元认知升级 |
| P3 | Cognitive Dynamics Model | v7 远景 |
