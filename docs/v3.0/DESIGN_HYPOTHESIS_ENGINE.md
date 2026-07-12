# DESIGN_HYPOTHESIS_ENGINE.md — 假设共识引擎

> 版本: v1.0 | 日期: 2026-07-12
>
> Hypothesis Engine 不是"计算置信度"的系统。它是"共识形成"系统。
> 它维护一个不断演化、竞争、合并、传播的解释网络，
> 每个 Hypothesis 从多个认知链收集独立验证信号，形成跨域共识。

---

## 目录

1. [定位：共识形成而非参数更新](#1-定位共识形成而非参数更新)
2. [核心概念：解释生态 + 共识累积](#2-核心概念解释生态-共识累积)
3. [四个 Primitive：Match → Vote → Decay → Resolve](#3-四个-primitive)
4. [Hypothesis Graph：假设之间的传播网络](#4-hypothesis-graph假设之间的传播网络)
5. [Belief Vector 与 belief_score](#5-belief-vector-与-belief_score)
6. [Knowledge 冻结条件](#6-knowledge-冻结条件)
7. [Schema 定义](#7-schema-定义)
8. [调度与消费周期](#8-调度与消费周期)
9. [集成面：与现有 v4 模块的关系](#9-集成面与现有-v4-模块的关系)
10. [实现计划](#10-实现计划)

---

## 1. 定位：共识形成而非参数更新

### 1.1 控制模型 vs 共识模型

控制系统的思维：Evidence → confidence += 0.1 → 达到阈值 → Knowledge。整个系统只有一条线。

共识模型的思维：

```
Event
   │
   ▼
Interpretation A， Interpretation B， Interpretation C， ...  （多解释并存）
   │
   ▼
不同认知链独立给每个 Interpretation 投 Support/Conflict/Neutral
   │
   ▼
Interpretation 之间传播支持关系（supports/explains/derived_from）
   │
   ▼
网络整体重新平衡 → 形成跨域共识
   │
   ▼
最稳定的共识冻结为 Knowledge
```

**核心区别**：不是一条路径越来越确定，而是多个认知域从各自视角共同验证同一组假设，在交汇点形成共识。

### 1.2 关键设计原则

| 原则 | 含义 |
|:---|:---|
| **Belief 不存，现算** | BeliefState 存原始计数，belief_score 每次计算导出，算法可换 |
| **竞争不标注，动态算** | 共享 Object + Topic + 冲突的 Statement → 自动竞争池，不人工维护 |
| **Evidence 不直接更新置信度** | Evidence 只投票 (Support/Conflict/Neutral)，不产生浮点数 |
| **置信度 = 共识度** | belief_score = f(support， conflict， stability， coverage， entropy) |
| **Knowledge 冻结不可逆** | 一旦冻结，不再参与竞争；竞争都在 Hypothesis 层 |

---

## 2. 核心概念：解释生态 + 共识累积

### 2.1 解释生态（Interpretation Ecosystem）

Observation Compiler 产出的每个 Interpretation 进入 Hypothesis Engine 后成为 **Hypothesis 节点**。Hypothesis Engine 不淘汰——只调整状态。

```
Interpretation "用户正在开发 Gateway"
    │ 进入 Hypothesis Engine
    ▼
Hypothesis {
    id: "H_001",
    statement: "用户正在开发 Gateway",
    belief_state: { support: 5, conflict: 1， ... }，
    edges: [
        { type: "supported_by",  target: "E_042" }，  // Evidence 引用
        { type: "explains",      target: "H_005" }，  // H_001 解释了 H_005
        { type: "derived_from",  target: "H_003" }，  // H_001 从 H_003 推导
    ],
}
```

### 2.2 共识累积（Consensus Accumulation）

共识不是"足够多的 Evidence 投了 Support"。共识是 **多个独立认知域从不同角度同时支持同一个 Hypothesis**。

```
H_001 "用户正在开发 Gateway" 得到:
  行为链:  Support (连续 5 次编辑 Gateway 节点)
  工程链:  Support (Gateway 模块的工程图正在扩展)
  对话树:  Neutral  (用户最近没提 Gateway)
  记忆:    Support (3 周前用户提到要开发 Gateway)

→ 3/4 认知域独立支持 → 共识高
```

**共识质量** = 支持域数量 / 总认知域数量，非 Support 的绝对数量。

---

## 3. 四个 Primitive

```
Evidence 到达
    │
    ▼
┌──────────────────────────────────────────────────────┐
│ Match: 这条 Evidence 能影响哪些 Hypothesis？           │
│   按 Object/Topic/Domain/Time 匹配                    │
│   不匹配的 Hypothesis 不受影响                          │
├──────────────────────────────────────────────────────┤
│ Vote: 匹配到的每个 Hypothesis，Evidence 投一票         │
│   票型: Support | Conflict | Neutral                   │
│   票数累计到 BeliefState.{support/conflict}            │
├──────────────────────────────────────────────────────┤
│ Decay: 时间衰减                                       │
│   Support 存在时间越久，有效值越衰减                     │
│   EffectiveSupport = Support × TimeWeight              │
│   TimeWeight = e^(-λ × age)                           │
├──────────────────────────────────────────────────────┤
│ Resolve: 扫描所有 Hypothesis，判定状态                   │
│   是否升级为 Knowledge？是否合并到更强 Hypothesis？      │
│   是否标记为 stale？                                   │
└──────────────────────────────────────────────────────┘
```

### 3.1 Match 策略

```python
def match(evidence: Evidence， hypotheses: List[Hypothesis]) -> List[Hypothesis]:
    matched = []
    for h in hypotheses:
        if h.status == "frozen":  # Knowledge 不再参与
            continue
        # 按 Object 匹配
        if evidence.objects and any(o in h.objects for o in evidence.objects):
            matched.append(h)
        # 按 Topic 匹配
        elif evidence.topic and evidence.topic == h.topic:
            matched.append(h)
        # 按 Domain 匹配
        elif evidence.domain == h.domain:
            matched.append(h)
    return matched
```

### 3.2 Vote 策略

```python
def vote(evidence: Evidence， hypothesis: Hypothesis) -> str:
    # Support: 证据直接支撑 hypothesis 的 statement
    if evidence.description in hypothesis.supporting_patterns:
        return "support"

    # Conflict: 证据与 hypothesis 的 statement 冲突
    if any(c in evidence.description for c in hypothesis.conflicting_patterns):
        return "conflict"

    # Neutral: 证据不直接相关
    return "neutral"
```

**Vote 是离散的 (Support/Conflict/Neutral)，不是连续值 (+0.1/-0.2)。**
计票结果积累在 `BeliefState.support` 和 `BeliefState.conflict` 中。

### 3.3 Decay 策略

```python
def decay(belief: BeliefState， now: float， half_life_days: float = 7.0) -> BeliefState:
    age_days = (now - belief.last_update) / 86400.0
    decay_factor = 2.0 ** (-age_days / half_life_days)
    belief.support = int(belief.support * decay_factor)
    belief.conflict = int(belief.conflict * decay_factor)
    belief.recency = max(0.0, belief.recency - age_days * 0.1)
    return belief
```

### 3.4 Resolve 策略

Resolve 在每个周期末尾运行。对每个 Hypothesis：
- 满足 Knowledge 冻结条件 → 写 Knowledge 节点，标记 Hypothesis 为 `frozen`
- belief_score 持续下降且 coverage 极低 → 标记 `stale`
- 两个 Hypothesis 的 statement 高度重叠 → 合并（保留更强的，标记 `merged_into`）

---

## 4. Hypothesis Graph

Hypothesis 之间有三种关系边：

| 边类型 | 语义 | 示例 |
|:---|:---|:---|
| `supports` | H_A 成立增加了 H_B 成立的概率 | "开发 Gateway" → supports → "熟悉中间件架构" |
| `explains` | H_A 是 H_B 的原因/背景 | "修 Bug" → explains → "频繁修改 Logger" |
| `derived_from` | H_A 从 H_B 演化而来 | "开发高级 Gateway" ← derived_from ← "开发 Gateway" |

边的权重影响 Belief Propagation：当一个 Hypothesis 获得新 Support，它通过 `supports` 边向被支持的 Hypothesis 传播一部分信念。

### 4.1 Belief Propagation

```
Evidence → H_001 (support+1)
    │
    ├─0.3─→ H_002  (间接增强)
    │
    └─0.1─→ H_003  (弱增强)
```

传播因子从 ParameterRegistry 读取，默认值:
- `hypothesis.bp_support_weight`: 0.3  (Support 通过 supports 边的传播系数)
- `hypothesis.bp_explain_weight`: 0.15 (通过 explains 边的传播系数)
- `hypothesis.bp_derived_weight`: 0.1  (通过 derived_from 边的传播系数)

### 4.2 动态竞争池

不标注 `competing_with`。两个 Hypothesis 自动进入竞争池，当：
- `Object` 相同
- `Topic` 相同
- `Statement` 语义冲突

竞争池内的 Hypothesis 共享同一个 Evidence 的 Vote。冲突的 Hypothesis 之间的 Vote 会相互削弱——"已经有一条解释拿到了 Support，冲突的解释就需要更高的 Support 才能升级"。

---

## 5. Belief Vector 与 belief_score

### 5.1 BeliefState（存储，7 维）

```python
BeliefState:
    support: int        # 累积 Support 票数
    conflict: int       # 累积 Conflict 票数
    novelty: float      # 与已有 Knowledge 的重叠度 (0=完全已知, 1=全新)
    stability: float    # 连续未变更比例 (0-1)
    coverage: float     # 所有可能证据源中已覆盖比例
    recency: float      # 最近 T 时间内 Evidence 占比
    entropy: float      # 证据源分散度 (越高=来源越分散, 共识越强)
```

### 5.2 belief_score（计算，每次按需导出）

```python
def compute_belief_score(bs: BeliefState, params: dict) -> float:
    support_ratio = bs.support / max(1, bs.support + bs.conflict)
    weights = {
        "support": params.get("weight_support", 0.35),
        "stability": params.get("weight_stability", 0.25),
        "coverage": params.get("weight_coverage", 0.20),
        "recency": params.get("weight_recency", 0.10),
        "entropy": params.get("weight_entropy", 0.10),
    }
    score = (
        support_ratio * weights["support"]
        + bs.stability * weights["stability"]
        + bs.coverage * weights["coverage"]
        + bs.recency * weights["recency"]
        + min(1.0, bs.entropy) * weights["entropy"]
    )
    return score
```

**关键**：权重可配置，算法可替换。`belief_score` 是函数不是字段。

### 5.3 权重纳入 ParameterRegistry

所有权重参数进入统一注册表：
- `hypothesis.weight_support` (default: 0.35)
- `hypothesis.weight_stability` (default: 0.25)
- `hypothesis.weight_coverage` (default: 0.20)
- `hypothesis.weight_recency` (default: 0.10)
- `hypothesis.weight_entropy` (default: 0.10)
- `hypothesis.bp_support_weight` (default: 0.3)
- `hypothesis.bp_explain_weight` (default: 0.15)
- `hypothesis.bp_derived_weight` (default: 0.1)
- `hypothesis.decay_half_life_days` (default: 7.0)

---

## 6. Knowledge 冻结条件

5 维 AND 判定，全部满足才冻结：

| 条件 | 参数 | 默认值 |
|:---|:---|:---|
| 最低支撑度 | `hypothesis.min_support` | 8 |
| 最大冲突度 | `hypothesis.max_conflict` | 3 |
| 最低稳定性 | `hypothesis.min_stability` | 0.70 |
| 最低覆盖度 | `hypothesis.min_coverage` | 0.40 |
| 最低共识度 | `hypothesis.min_consensus_domains` | 2 |

**共识度**: 至少 N 个独立认知域对该 Hypothesis 有 Support 票（非 Neutral）。

冻结产物：`KnowledgeNode`，包含冻结时的 `belief_state` 快照和 `belief_score`。Hypothesis 节点状态标记为 `frozen`，不再参与后续竞争。

---

## 7. Schema 定义

### 7.1 HypothesisNode

```python
@dataclass
class HypothesisNode:
    hypothesis_id: str              # 唯一标识
    interpretation_ref: str         # 关联的 Interpretation ID
    domain: str                     # 所属认知域
    statement: str                  # "用户正在开发 Gateway"
    objects: list[str]              # ["Gateway"， "Logger"]
    topic: str = ""                 # "current_goal" | "learning" | "exploration"
    belief_state: BeliefState = field(default_factory=BeliefState)
    domain_signals: dict[str， str] = field(default_factory=dict)  # domain -> vote
    edges: list[HypothesisEdge] = field(default_factory=list)
    status: str = "active"          # active | merged | frozen | stale
    merged_into: str | None = None  # 合并目标的 hypothesis_id
    created_at: float = field(default_factory=time.time)
    last_vote_at: float = 0.0

    def belief_score(self， params: dict = None) -> float:
        return compute_belief_score(self.belief_state， params or {})
```

### 7.2 HypothesisEdge

```python
@dataclass
class HypothesisEdge:
    type: str                       # "supports" | "explains" | "derived_from"
    source_id: str                  # 源 Hypothesis ID
    target_id: str                  # 目标 Hypothesis ID
    weight: float = 0.3             # 传播权重
    created_at: float = field(default_factory=time.time)
```

### 7.3 KnowledgeNode

```python
@dataclass
class KnowledgeNode:
    knowledge_id: str
    hypothesis_ref: str             # 冻结来源的 hypothesis_id
    statement: str
    domain: str
    belief_score: float             # 冻结时的 belief_score
    belief_snapshot: BeliefState    # 冻结时的 BeliefState
    frozen_at: float
```

### 7.4 VoteRecord

```python
@dataclass
class VoteRecord:
    evidence_id: str
    hypothesis_id: str
    vote: str                       # "support" | "conflict" | "neutral"
    domain: str                     # 投票来源域
    timestamp: float
```

---

## 8. 调度与消费周期

```
Cognitive Runtime (Async Path)
    │
    ▼
ObservationBundle complete → 通知 Hypothesis Engine
    │
    ▼
Match: 新 Evidence 匹配到受影响的 Hypothesis
    │
    ▼
Vote: 投票 Support/Conflict/Neutral
    │
    ▼
Belief Propagation: 传播到 supports/explains/derived_from 邻居
    │
    ▼ (周期末尾)
Decay: 时间衰减所有活跃 Hypothesis
    │
    ▼
Resolve: 冻结、合并、淘汰
    │
    ▼
Knowledge 写入 UGS 图
```

**消费触发**：ObservationBundle complete 事件自动触发 Match+Vote。Decay+Resolve 按时间周期（默认 60s）。ContextCompiler 查询时按需触发 belief_score 的重新计算。

---

## 9. 集成面

| 模块 | 关系 |
|:---|:---|
| Observation Compiler | 输入: ObservationBundle + Evidence → 触发 Match |
| NodeAnnotationStore | 消费: Hypothesis 节点的标注查询 |
| UnifiedGraphStore | Knowledge 节点存储 + Hypothesis Graph 持久化 |
| ParameterRegistry | 所有权重 + 阈值参数统一管理 |
| TierHeatBridge | 热 Hypothesis (频繁被 Vote) → 提升图存储层级 |
| ContextCompiler | 查询: "当前最高共识 Hypothesis" → 编译为 LLM 上下文 |
| Behavior/Engineering/Dialogue Chain | 各域独立 Vote 的来源 |

---

## 10. 实现计划

| Phase | 内容 | 依赖 |
|:---|:---|:---|
| Phase 1 | HypothesisNode + HypothesisEdge + VoteRecord Schema | Observation Compiler models |
| Phase 2 | Match + Vote primitive | Phase 1 |
| Phase 3 | Decay + Resolve + KnowledgeNode 冻结 | Phase 2 |
| Phase 4 | Hypothesis Graph + Belief Propagation | Phase 1 |
| Phase 5 | 消费调度 (ObservationBundle → Match+Vote 触发) | Phase 2, Observation Compiler |
| Phase 6 | ParameterRegistry 权重 + 阈值参数 | ParameterRegistry |
| Phase 7 | ContextCompiler 集成 | Phase 2-5, ContextCompiler |

---

> Hypothesis Engine 不是"计算置信度"的系统。
> 它是"共识形成"系统：多个认知域从各自视角共同验证同一组假设，
> 在交汇点形成共识，将最稳定的共识冻结为 Knowledge。
