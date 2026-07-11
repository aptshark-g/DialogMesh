# DESIGN_OBSERVATION_COMPILER.md — Observation Compiler 设计规范

> 版本: v1.0 | 日期: 2026-07-11
>  
> Observation Compiler 不是 Parser。它是 v4 认知模型中从"事实"到"解释"的投影层。
> 它把统一 Event IR 投射到多个认知域，生成每域独立的候选解释，
> 供 Hypothesis Engine 竞争收敛。

---

## 目录

1. [定位：为什么不叫 Parser](#1-定位为什么不叫-parser)
2. [认知模型：五层递进](#2-认知模型五层递进)
3. [ObservationBundle 架构](#3-observationbundle-架构)
4. [Schema 定义](#4-schema-定义)
5. [Pipeline 阶段](#5-pipeline-阶段)
6. [Partial Observation：快速路径](#6-partial-observation快速路径)
7. [Observation Pool 生命周期](#7-observation-pool-生命周期)
8. [集成面：与现有 v4 模块的关系](#8-集成面与现有-v4-模块的关系)
9. [实现计划](#9-实现计划)

---

## 1. 定位：为什么不叫 Parser

### 1.1 传统 Parser 的局限

传统 NLU Parser 做的是：
```
raw_text → intent + entities + slots
```

这在纯对话场景下够用，但 DialogMesh v4 的事件源是**多模态的**：

- 对话消息
- UI 操作（拖拽、点击、展开/折叠）
- 代码变更（Git commit、IDE edit）
- 工具调用（Agent tool output）
- 配置变更
- 系统事件

其中很多事件根本没有语言文本，也就没有"intent"。用户拖一条边——intent 是什么？不存在。存在的是 `action: drag, target: node42`。

### 1.2 Observation Compiler 的真正职责

Observation Compiler 做的是**投影（Projection）**：

```
统一的 Event IR（白光）
       │
       ▼
   棱镜（Compiler）
       │
    ┌──┼──┬──┬──┐
    ▼  ▼  ▼  ▼  ▼
   工程 行为 对话 记忆 画像  （光谱）
```

一束白光通过棱镜分成多个光谱。每个光谱是同一事件在不同认知维度的呈现，各自完整，各自独立。

没有哪个光谱比另一个更"正确"。

### 1.3 关键设计原则

| 原则 | 含义 |
|:---|:---|
| **多 Perspective 同时成立** | 工程、行为、对话、记忆域各有自己的 Observation，不互斥 |
| **同域内多 Interpretation 竞争** | 工程域内部"调整布局"vs"优化依赖"vs"修改规范"互相竞争 |
| **Observation 永远不淘汰** | 不作置信度判断，不删候选 |
| **Interpretation 稍后竞争** | 由 Hypothesis Engine 负责收敛 |
| **Partial OK** | 部分域完成即可发布，后台继续补充 |

---

## 2. 认知模型：五层递进

```
Layer 0: Reality（现实）
        世界发生了客观事实。
        鼠标移动、点击、一句话、Git Commit、Tool 输出。
        没有解释。只有发生。

Layer 1: Observation（各域感知）
        把 Event 投影到不同认知域。
        工程域看到"Pipeline Changed"，行为域看到"User dragged node"。
        多个域同时成立，不互斥。

Layer 2: Interpretation（同域候选）
        同一域内产生多种可能解释。
        工程域："调整布局" or "优化依赖" or "修改规范"。
        行为域："主动编排" or "探索性操作" or "误操作"。

Layer 3: Hypothesis（跨域竞争收敛）
        所有域的 Interpretation 进入竞争。
        Bayesian Update / Belief Propagation。
        跨域证据融合。

Layer 4: Knowledge（稳定认知）
        confidence > threshold → 冻结为 Knowledge。
        之后可以 Skill / Constraint / Pattern / Preference。
```

对应的数据流：

```
Reality（世界事件）
    │
    ▼
Event IR（统一格式，不持久化）
    │
    ▼
ObservationBundle（1:1 with Event）
    ├── EngineeringObservation  →  [Interp_A, Interp_B, Interp_C]
    ├── BehaviorObservation    →  [Interp_A, Interp_B]
    ├── DialogueObservation    →  [Interp_A, Interp_B, Interp_C, Interp_D]
    ├── MemoryObservation      →  [Interp_A]
    └── UserObservation        →  [Interp_A, Interp_B]
    │
    ▼
Hypothesis Engine（竞争收敛）
    │
    ▼
Knowledge（冻结）
```

### 2.1 与传统 DMN/ECN 的对应

| 阶段 | 认知功能 | 对应脑区模型 |
|:---|:---|:---|
| Observation + Interpretation | 生成大量候选解释 | DMN（默认模式网络）——发散 |
| Hypothesis Engine | 竞争、收敛、择优 | ECN（执行控制网络）——收束 |

但注意：发散的不是"信息"，而是**解释空间**。信息没有增加，增加的只是对同一事件的不同理解方式。

---

## 3. ObservationBundle 架构

### 3.1 为什么要有 Bundle？

如果 Observation 是扁平的 1:1（一个 Event 产生一个 Observation，内含所有域混合在一起），则下游每个链都需要自己做域分类。

如果 Observation 是 1:N（一个 Event 产生 N 个 Observation），则丢失了"这些 Observation 来自同一事件"的关联。

**Bundle 解决了这个两难**：

```
Event (id="evt_001")
    │
    ▼
ObservationBundle (bundle_id="bun_001", event_id="evt_001")
    ├── DomainObservation (domain="engineering")
    ├── DomainObservation (domain="behavior")
    ├── DomainObservation (domain="dialogue")
    ├── DomainObservation (domain="memory")
    └── DomainObservation (domain="user")
```

- Bundle 与 Event 是 **1:1** 关系
- Bundle 内含多个 **DomainObservation**，按认知域独立
- 每个 DomainObservation 内含多个 **Interpretation**，同域内竞争

### 3.2 域定义

| 域 | 键 | 视角 | 下游消费者 |
|:---|:---|:---|:---|
| Engineering | `"engineering"` | 工程结构发生了什么变化？ | 工程链、Context Compiler(E) |
| Behavior | `"behavior"` | 用户做了什么操作？ | 行为链、UserProfile |
| Dialogue | `"dialogue"` | 对话中传达了哪些语义？ | 对话树、L1/L2 Summary |
| Memory | `"memory"` | 哪些信息值得长期记住？ | Memory Compiler |
| User | `"user"` | 反映了用户的什么偏好/风格？ | UserProfile |
| Causal | `"causal"` | 事件之间存在因果关联吗？ | 因果链、Do-Calculus |

### 3.3 Perspective vs Interpretation 的区别

这是整个设计里最重要的概念区分：

| | Perspective（跨域） | Interpretation（同域内） |
|:---|:---|:---|
| 关系 | 共存（不互斥） | 竞争（互斥或半互斥） |
| 数量 | 每个 Event 每个域最多 1 个 DomainObservation | 每个 DomainObservation 可以有 N 个 Interpretation |
| 淘汰机制 | 不淘汰 | Hypothesis Engine 负责淘汰 |
| 示例 | "Pipeline Changed" AND "User Dragged Node" 同时为真 | "调整布局" vs "优化性能" 竞争 |

---

## 4. Schema 定义

### 4.1 EventIR（已有，仅引用）

```python
@dataclass
class EventIR:
    id: str                    # 唯一标识
    kind: str                  # dialog.message | ui.drag | ui.click | ...
    payload: dict              # 动态内容（文本、坐标、节点 ID 等）
    refs: dict                 # 引用（conversation_id, user_id, session_id）
    metadata: dict             # 元数据（time, source, confidence）
    timestamp: float           # 事件发生时间
```

### 4.2 ObservationBundle

```python
@dataclass
class ObservationBundle:
    bundle_id: str                          # 唯一标识
    event_id: str                           # 关联的 Event
    created_at: float                       # 创建时间戳
    domain_observations: dict[str, DomainObservation]  # key = domain name
    status: str = "partial"                 # partial | complete | stale
```

### 4.3 DomainObservation (per domain)

```python
@dataclass
class DomainObservation:
    domain: str                     # "engineering" | "behavior" | "dialogue" | ...
    observation_id: str             # 唯一标识
    event_id: str                   # 关联的 Event
    summary: str                    # 人类可读摘要："User dragged RateLimiter before Auth"
    actions: list[str]              # ["drag", "reorder"]
    objects: list[str]              # ["RateLimiter", "Auth"]
    relations: list[dict]           # [{"type": "before", "from": "X", "to": "Y"}]
    interpretations: list[Interpretation]  # 同域内的候选解释列表
    evidence_sources: list[str]     # 指向 Evidence.evidence_id 列表
    status: str = "partial"         # partial | complete | stable
    meta: dict = field(default_factory=dict)  # 域特定扩展字段
```

`DomainObservation` 是**不跨域竞争**的。工程域 Observation 和行为域 Observation 同时为真，各有各的 `interpretations`。

### 4.4 Interpretation (per domain, per candidate)

```python
@dataclass
class Interpretation:
    interpretation_id: str          # 唯一标识
    domain_observation_id: str      # 所属的 DomainObservation
    summary: str                    # "User is reordering middleware pipeline"
    hypothesis: str                 # 解释性陈述："为了优化请求处理顺序"
    evidence_refs: list[str]        # 指向支撑此解释的 Evidence.evidence_id
    # 注意：Interpretation 没有 confidence 字段，证据竞争由 Hypothesis Engine 完成
    competing_with: list[str]       # 同域内互斥的 Interpretation ID
    status: str = "active"          # active | confirmed | dismissed | stale
    version: int = 1                # 版本号（Hypothesis Engine 每次更新递增）
```

关键约束：

- **`competing_with`** 显式声明互斥关系。不声明的视为可共存
- **`evidence_refs`** 由 Compiler 填充，指向具体的 Evidence 记录，Compiler 不判断可信度
- **`status`** 只有 Hypothesis Engine 可以改（`confirmed` / `dismissed`）

### 4.5 Observation Event（Observation 产生的事件）

当 ObservationBundle 内某个域完成或产生新的 Interpretation 时，发布内部事件：

```python
@dataclass
class ObservationEvent:
    kind: str                       # domain_observation_created | interpretation_added | bundle_complete
    bundle_id: str
    domain: str | None
    observation_id: str | None
    interpretation_id: str | None
    timestamp: float
```

这允许下游模块（行为链、工程链、ContextCompiler）订阅特定域的 Observation 更新事件，而非轮询 Observation Pool。

---

## 5. Pipeline 阶段

Observation Compiler 是一个**可分段提前退出**的流水线：

```
Event IR
    │
    ▼
Stage 0: Normalizer           — 归一化字段、时间戳、引用
    │
    ▼
Stage 1: Projector            — 分发到各认知域（Engineering/Behavior/Dialogue/...）
    │
    ▼
Stage 2: Per-Domain Interpreter  — 每个域独立生成 Interpretation 列表
    │  ├── EngineeringInterpreter
    │  ├── BehaviorInterpreter
    │  ├── DialogueInterpreter
    │  ├── MemoryInterpreter
    │  └── UserInterpreter
    │
    ▼
Stage 3: Observation Builder  — 组装 Bundle + 写入 Observation Pool
```

### 5.1 Normalizer

**职责**：标准化 Event 字段，统一时间格式，解析引用链。

- 时间戳：统一为 UTC float
- 引用解析：`refs.conversation_id` → 查找关联会话
- Payload 扁平化：嵌套结构展平为 `flat_payload`
- 输入：`EventIR`
- 输出：`NormalizedEvent`

### 5.2 Projector

**职责**：决定 Event 需要分发到哪些域。

决策逻辑——基于 `EventIR.kind` 的路由表：

| Event Kind | 目标域 |
|:---|:---|
| `dialog.message` | dialogue, memory, user |
| `ui.click` | behavior, memory |
| `ui.drag` | engineering, behavior, memory |
| `ui.drop` | engineering, behavior, task |
| `tool.call` | engineering, behavior, causal |
| `config.change` | engineering, memory |
| `api.call` | engineering, causal |
| `git.commit` | engineering, memory |

非匹配的事件进入 `memory` 默认域。

### 5.3 Per-Domain Interpreter

每个域有独立的轻量解释器，以 Action/Object/Relation 三元组为基础生成候选 Interpretation。

**输入**：`NormalizedEvent` + `domain`  
**输出**：`list[Interpretation]`

#### EngineeringInterpreter

从 UI 操作、Git commit、tool call 中抽取工程含义：

```
Event: ui.drag(node=RateLimiter, target=Auth, position=before)

Action: reorder
Objects: [RateLimiter, Auth]
Relations: [{type: "before", from: RateLimiter, to: Auth}]

Interpretations:
  A: "调整中间件顺序"          (see evidence_refs)
  B: "优化请求处理性能"        (see evidence_refs)
  C: "遵循工程规范重排"        (see evidence_refs)
```

#### BehaviorInterpreter

从 UI 操作序列中抽取行为模式：

```
Event: ui.drag + history context (最近 3 次都是 drag)

Action: drag
Objects: [RateLimiter, Auth]

Interpretations:
  A: "手动编排节点"            (see evidence_refs)
  B: "探索性操作"              (see evidence_refs)
  C: "整理布局"                (see evidence_refs)
```

#### DialogueInterpreter

从对话文本中抽取语义（可复用已有的 SyntacticDecomposer + TieredParser）：

```
Event: dialog.message(text="帮我把 RateLimiter 放在 Auth 前面")

Action: reorder
Objects: [RateLimiter, Auth]
Relations: [{type: "before", from: RateLimiter, to: Auth}]

Interpretations:
  A: "请求修改 Pipeline 顺序"  (see evidence_refs)
  B: "测试 RateLimiter 效果"   (see evidence_refs)
```

**关键设计**：DialogueInterpreter 复用已有的 `TieredParser`（rule → spaCy → LLM 三级），但输出格式从 `intent + slots` 改为 `actions + objects + relations + interpretations`。

### 5.4 Observation Builder

**职责**：将各域的结果组装成 `ObservationBundle`，写入 Observation Pool，发布 `ObservationEvent`。

```
输入：NormalizedEvent + {domain: [Interpretation, ...]}
输出：ObservationBundle + ObservationEvent[]
```

Builder 不需要等所有域完成。某个域先完成就可以**先发布 Partial Bundle**——这就是快速路径的基础。

---

## 6. Partial Observation：快速路径

### 6.1 核心思想

Observation Compiler 不需要等所有域完成才返回。前端需要快速响应，后台继续深入解析。

```
Time 0ms:  Event 到达
Time 5ms:  Normalize 完成
Time 8ms:  Project 完成，Dialogue 域可以立即开始
Time 15ms: DialogueInterpreter 完成 → Partial Bundle v1 发布
           ↑ 前端拿到结果，继续交互
Time 50ms: EngineeringInterpreter 完成 → Partial Bundle v2（追加 engineering）
Time 80ms: BehaviorInterpreter 完成 → Bundle complete
Time 200ms+: Hypothesis Engine 在后台消费完整 Bundle
```

### 6.2 Bundle 版本化

每次追加域完成时，Bundle 版本号递增。下游订阅者可以通过 `ObservationEvent` 感知增量更新。

```python
Bundle v1 (t=15ms):  {dialogue: [...], status: "partial"}
Bundle v2 (t=50ms):  {dialogue: [...], engineering: [...], status: "partial"}
Bundle v3 (t=80ms):  {dialogue: [...], engineering: [...], behavior: [...], status: "complete"}
```

### 6.3 与 MultiTierPipeline 的关系

Per-domain Interpreter 内部可以使用已有的 MultiTierPipeline：

```
DomainInterpreter
  ├── Tier 0: rule-based pattern matching (fast, ~5ms)
  ├── Tier 1: domain-specific heuristics (~20ms)
  └── Tier 2: LLM-based interpretation (~200ms)

Tier 0 完成 → 立即发布 Partial Observation
Tier 1+2 完成 → 补充更多 Interpretations
```

---

## 7. Observation Pool 生命周期

### 7.1 存储策略

ObservationBundle 暂时**不进入 UnifiedGraphStore 的 Hot/Warm/Cold/Archive 分层**。原因：

- Observation 是运行时中间产物，不是长期知识
- 大部分 Observation 的 Interpretations 在 Hypothesis Engine 竞争完成后就不再需要
- 归档后的 Observation 只有审计价值

存储选择：

| 阶段 | 存储 | TTL |
|:---|:---|:---|
| 活跃（Bundle status = partial/complete） | 内存池 + 可选 Redis | 与 Session 同生命周期 |
| 已消费（Hypothesis Engine 处理完毕） | SQLite（压缩后） | 24h（仅审计） |
| 已确认（Interpretation → Knowledge） | UnifiedGraphStore Knowledge 节点 | 永久 |

### 7.2 Observation Pool 接口

```python
class ObservationPool:
    def put(bundle: ObservationBundle) -> None
    def get(bundle_id: str) -> ObservationBundle | None
    def get_by_event(event_id: str) -> list[ObservationBundle]
    def get_by_domain(domain: str, since: float) -> list[ObservationBundle]
    def mark_consumed(bundle_id: str) -> None
    def evict_old(max_age_sec: float) -> int
    def subscribe(callback: Callable[[ObservationEvent], None]) -> None
```

### 7.3 到 Hypothesis Engine 的触发条件

ObservationBundle 变为 `complete` 时自动通知 Hypothesis Engine。此外也支持：

- **数量触发**：同一域积累了 N 个 Bundle（默认 5）
- **时间触发**：距上次 Hypothesis Engine 运行超过 T 秒（默认 60s）
- **手动触发**：Context Compiler 请求时按需触发

触发参数纳入 ParameterRegistry：
- `obs.hypothesis.min_support` (default: 5) ? ?????
- `obs.hypothesis.max_conflict` (default: 3) ? ?????
- `obs.hypothesis.min_stability` (default: 0.70) ? ?????
- `obs.hypothesis.min_coverage` (default: 0.30) ? ?????
- `obs.hypothesis.min_recency` (default: 0.40) ? ?????

---

## 8. 集成面：与现有 v4 模块的关系

### 8.1 已有模块（不修改）

| 模块 | 关系 |
|:---|:---|
| Event IR + EventBus | Observation Compiler 的输入源 |
| MultiTierPipeline | Per-domain Interpreter 内部使用 |
| 8 个 Tiered Wrapper | TieredParser 被 DialogueInterpreter 复用 |
| UnifiedGraphStore | Knowledge 节点的最终存储（不直接存 Observation） |
| ParameterRegistry | 所有阈值统一管理 |

### 8.2 新建模块

| 模块 | 依赖 |
|:---|:---|
| Observation Compiler | Event IR, MultiTierPipeline, ParameterRegistry |
| Observation Pool | 独立（内存 + 可选持久化） |
| Observation Event | 独立（简单 dataclass） |
| Per-domain Interpreters (5) | 各自域的知识库/规则 |

### 8.3 依赖 Observation Compiler 的下游模块

| 下游模块 | 依赖方式 |
|:---|:---|
| Hypothesis Engine | 消费 complete Bundle，做跨域竞争 |
| 工程链 | 订阅 domain="engineering" 的 ObservationEvent |
| 行为链 | 订阅 domain="behavior" 的 ObservationEvent |
| 对话树 | 订阅 domain="dialogue" 的 ObservationEvent |
| ContextCompiler | 按需查询 Observation Pool |

---

## 9. 实现计划

| Phase | 内容 | 估时 | 依赖 |
|:---|:---|:---|:---|
| Phase 1 | ObservationBundle + DomainObservation + Interpretation + ObservationEvent Schema | 小 | 无 |
| Phase 2 | Normalizer + Projector + Observation Builder + Observation Pool | 中 | Phase 1 |
| Phase 3 | DialogueInterpreter（复用 TieredParser） | 中 | Phase 2, TieredParser |
| Phase 4 | EngineeringInterpreter + BehaviorInterpreter | 中 | Phase 2 |
| Phase 5 | MemoryInterpreter + UserInterpreter | 小 | Phase 2 |
| Phase 6 | Observation Pool 持久化 + GC + 监控 | 中 | Phase 2 |
| Phase 7 | Hypothesis Engine（独立模块，本设计文档的后续） | 大 | Phase 2-6 |

### 9.1 可并行的工作

- Phase 1-2 必须先于 3-7
- Phase 3-5（各域 Interpreter）可并行
- Phase 6 可与 Phase 3-5 并行
- Phase 7 需要等 Phase 2-6 完成

---

> Observation Compiler 不是"给 Event 加语义"。它做的是：
> 把统一 Event 投影到多个认知域，每个域独立生成候选解释，
> 供 Hypothesis Engine 在后续阶段竞争收敛。
>
> 它是 v4 认知模型从"事实"到"解释"的桥梁层。
