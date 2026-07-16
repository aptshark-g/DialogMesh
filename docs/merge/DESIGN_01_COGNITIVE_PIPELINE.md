# 认知管线设计

> **本文档合并自以下源头文档**（原文件保留于 `docs/v3.0/` 不删除）：
> - `DESIGN_COGNITIVE_RUNTIME.md` — 四路径调度架构、触发时机、失败策略
> - `DESIGN_COGNITIVE_SCHEDULER.md` — Task/Worker/Policy 调度器设计
> - `DESIGN_OBSERVATION_COMPILER.md` — Observation Bundle、五层认知模型、Pipeline 阶段
> - `DESIGN_HYPOTHESIS_ENGINE.md` — Match/Vote/Decay/Resolve、Belief Vector、Knowledge 冻结
> - `DESIGN_V4_KNOWLEDGE_REFINEMENT.md` — 五层架构、Observation Pool、Hypothesis Pool
> - `DESIGN_MULTI_TIER_PIPELINE.md` — 精度-算力谱系、UpgradePolicy、FeedbackLoop

---

## 1. 总览：五层认知模型 + 四路径调度

> 源自 `DESIGN_V4_KNOWLEDGE_REFINEMENT.md` §1 + `DESIGN_COGNITIVE_RUNTIME.md` §3

DialogMesh 的认知管线由两个正交维度定义：**五层认知模型**（数据怎么流动）和**四路径调度**（数据什么时候流动）。

### 1.1 五层认知模型

```
Layer 0: Reality（现实）     — 世界发生了客观事实（鼠标、对话、Git Commit）
Layer 1: Observation（观察） — 把 Event 投影到多个认知域
Layer 2: Interpretation（解释）— 同域内产生多种候选解释，互相竞争
Layer 3: Hypothesis（假设）  — 跨域证据融合，共识收敛
Layer 4: Knowledge（知识）   — 置信度超阈值 → 冻结为持久知识
```

对应的数据流：

```
Event IR → ObservationCompiler → ObservationPool
  → HypothesisEngine (Match+Vote+Decay+Resolve) → KnowledgeNode
  → SkillDistiller → Skill
```

### 1.2 四路径调度

| 路径 | 触发 | 延迟预算 | 并发模型 | 失败策略 |
|:---|:---|:---|:---|:---|
| Fast | 每次用户输入 | <50ms | 同步，阻塞回复 | 降级到旧管线 |
| Async | Fast Path 产出的 Event | <5s | 异步，不阻塞回复 | 重试 3 次，然后丢弃 |
| Slow | Checkpoint（N Events 或 T 时间） | 分钟级 | 后台线程 | 永久保留，下次重试 |
| Deep | 阈值触发（N 次同类 Pattern） | 小时/天级 | 独立 worker | 标记 pending，人工审查 |

### 1.3 五个核心设计原则

> 源自 `DESIGN_COGNITIVE_RUNTIME.md` §2

1. Event IR 不持久化。Event 是运行时中间语言，类比 HTTP Request。持久化的是 Observation 及其下游产物。
2. 新旧管线并行。旧管线（PCR → Planner → LLM）负责回复用户，新管线（Event → Observation → Knowledge）负责知识沉淀。
3. 所有模块通过 Runtime 调度，不互相直接调用。Module A 不 import Module B。
4. 每个模块有明确的路径归属（Fast/Async/Slow/Deep），不跨路径调用。
5. 路径之间通过 UnifiedGraphStore 和 Observation Pool 交换数据——不通过直接函数调用。

---

## 2. Cognitive Scheduler

> 源自 `DESIGN_COGNITIVE_SCHEDULER.md`

### 2.1 定位

Cognitive Scheduler 不是 Executor，不是 Worker Pool。它决定"谁、什么时候、跑多久、以什么优先级"。不负责思考——只负责调度思考的时机。

三层结构：

```
Cognitive Scheduler (调度层)
    ├── Policy (Fast/Async/Slow/Deep)
    ├── Queue + Dispatcher
    └── Monitor

Cognitive Pipeline (认知流水线)
    Event → Observation → Hypothesis → Knowledge → Skill

Context Engine (内容层)
    提供"处理什么内容"
```

### 2.2 Task 抽象

Worker 不应该知道自己在跑 Observation Compiler 还是 Hypothesis Engine。Worker 只知道 `Task.execute()`。

```python
class Task(ABC):
    task_id: str
    priority: int = 0            # 越高越优先
    status: str = "pending"      # pending | running | done | failed | cancelled
    max_retries: int = 3
    timeout_ms: int = 30000

    @abstractmethod
    def execute(self) -> Any: ...
```

四类 Task：

| Task | 对应模块 | Policy 路径 | 典型耗时 |
|:---|:---|:---|:---|
| `ObservationTask` | Observation Compiler | Async | 5-50ms |
| `HypothesisTask` | Hypothesis Engine (Match+Vote) | Async/Slow | 10-500ms |
| `KnowledgeTask` | Hypothesis Engine (Decay+Resolve) | Slow | 100ms-2s |
| `SkillTask` | DistillationEngine + Evaluation | Deep | 1-10s |

### 2.3 Policy

```python
class SchedulerPolicy(ABC):
    def select_task(self, queue: List[Task]) -> Optional[Task]: ...
    def assign_worker(self, task: Task, pool: WorkerPool) -> Optional[Worker]: ...
    def should_delay(self, task: Task) -> bool: ...
    def should_merge(self, a: Task, b: Task) -> bool: ...
```

默认实现 `PriorityFIFOPolicy`：优先级高者先出，同优先级 FIFO。

Policy 与 MultiTierPipeline 的关系：MultiTierPipeline 的 rule→embedding→LLM 级联是执行层的精度策略，不是调度策略。Policy 决定"Observation 队列太长了，暂停 Deep，把 Worker 分配给 Async"。两层互不干扰。

### 2.4 PathAwareScheduler

> 源自代码 `core/agent/v4/cognitive_scheduler/path_scheduler.py`

实际实现中，Scheduler 升级为 `PathAwareScheduler`，每个路径有独立的状态机：

```
idle → running → (backlogged | idle)
```

- `ConfigDrivenTriggerPolicy` 从 runtime.yaml 读取触发条件
- `EventCounter` 在 Event 累积达到阈值（默认 50）时自动触发 Slow Path
- Deep Path 在 Slow Path 成功后评估：pattern_count ≥ 5 且 success_rate ≥ 0.9 时触发

### 2.5 参数

| 参数 | 默认值 | 说明 |
|:---|:---|:---|
| `scheduler.default_workers` | 4 | Worker Pool 大小 |
| `scheduler.tick_interval_ms` | 100 | 调度循环间隔 |
| `scheduler.max_task_timeout_ms` | 30000 | Task 默认超时 |
| `scheduler.queue_max_size` | 1000 | 队列最大容量 |

---

## 3. Observation Compiler

> 源自 `DESIGN_OBSERVATION_COMPILER.md`

### 3.1 定位：投影而非解析

Observation Compiler 不是 Parser。它是从"事实"到"解释"的投影层。把统一 Event IR（白光）投射到多个认知域（光谱），生成每域独立的候选解释。

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

关键设计原则：
- **多 Perspective 同时成立** — 工程、行为、对话域各有自己的 Observation，不互斥
- **同域内多 Interpretation 竞争** — 工程域内部"调整布局" vs "优化依赖"互相竞争
- **Observation 永远不淘汰** — 不作置信度判断，不删候选
- **Partial OK** — 部分域完成即可发布，后台继续补充

### 3.2 ObservationBundle 架构

Bundle 与 Event 是 1:1 关系，内含多个 DomainObservation（按认知域独立），每个 DomainObservation 内含多个 Interpretation（同域内竞争）。

### 3.3 域定义

| 域 | 键 | 视角 | 下游消费者 |
|:---|:---|:---|:---|
| Engineering | `"engineering"` | 工程结构发生了什么变化？ | 工程链、Context Compiler(E) |
| Behavior | `"behavior"` | 用户做了什么操作？ | 行为链、UserProfile |
| Dialogue | `"dialogue"` | 对话中传达了哪些语义？ | 对话树、L1/L2 Summary |
| Memory | `"memory"` | 哪些信息值得长期记住？ | Memory Compiler |
| User | `"user"` | 反映了用户的什么偏好/风格？ | UserProfile |
| Causal | `"causal"` | 事件之间存在因果关联吗？ | 因果链 |

### 3.4 Pipeline 阶段

```
Event IR
  │
  ▼
Stage 0: Normalizer        — 归一化字段、时间戳、引用
  │
  ▼
Stage 1: Projector         — 基于 EventIR.kind 路由到各认知域
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

Event Kind 路由表：

| Event Kind | 目标域 |
|:---|:---|
| `dialog.message` | dialogue, memory, user |
| `ui.drag` | engineering, behavior, memory |
| `tool.call` | engineering, behavior, causal |
| `git.commit` | engineering, memory |

### 3.5 Surface Relation vs Semantic Relation

| | Surface（Parser 提取） | Semantic（Hypothesis 推断） |
|:---|:---|:---|
| 来源 | 文本中显式出现的词 | 需要推理才能得出 |
| 示例 | before, after, inside | depends_on, implements, causes |
| 产生时机 | Parser 阶段 | Hypothesis Engine 阶段 |

Observation 层只保存 Surface Relation。Semantic Relation 留给 Hypothesis Engine。

### 3.6 Partial Observation：快速路径

```
Time 0ms:   Event 到达
Time 5ms:   Normalize 完成
Time 15ms:  DialogueInterpreter 完成 → Partial Bundle v1 发布
            ↑ 前端拿到结果，继续交互
Time 50ms:  EngineeringInterpreter 完成 → Bundle v2（追加）
Time 80ms:  BehaviorInterpreter 完成 → Bundle complete
Time 200ms+: Hypothesis Engine 在后台消费完整 Bundle
```

### 3.7 Interpretation Generator

独立于 Parser 和 ActionResolver。同一组 {action, objects, relations} 可以产生完全不同的解释，取决于行为历史、工程图状态和用户画像。

生成策略：

| 策略 | 来源 | 示例 |
|:---|:---|:---|
| Action-driven | from action | request_change → "user requests modification" |
| Object-driven | from objects | [RateLimiter, Auth] → "focusing on middleware security" |
| Context-driven | from history/graph | 3 recent reorders → "continuously optimizing" |
| Uncertainty-driven | low-confidence signals | → "exploratory operation" |

约束：Generator 不淘汰 Interpretation，Hypothesis Engine 才淘汰。

---

## 4. Hypothesis Engine

> 源自 `DESIGN_HYPOTHESIS_ENGINE.md` + `DESIGN_V4_KNOWLEDGE_REFINEMENT.md` §4-6

### 4.1 定位：共识形成而非参数更新

Hypothesis Engine 不是"计算置信度"的系统。它是"共识形成"系统。多个认知域从各自视角共同验证同一组假设，在交汇点形成共识。

```
Event
  → Interpretation A, B, C, ... （多解释并存）
  → 不同认知链独立给每个 Interpretation 投 Support/Conflict/Neutral
  → Interpretation 之间传播支持关系（supports/explains/derived_from）
  → 网络整体重新平衡 → 形成跨域共识
  → 最稳定的共识冻结为 Knowledge
```

核心区别：不是一条路径越来越确定，而是多个认知域从不同视角共同验证。

### 4.2 四个 Primitive

```
Evidence 到达
  │
  ▼
Match:  这条 Evidence 能影响哪些 Hypothesis？按 Object/Topic/Domain/Time 匹配
  │
  ▼
Vote:   匹配到的每个 Hypothesis，Evidence 投一票（Support | Conflict | Neutral）
  │     票型是离散的，不是连续值。计票结果积累在 BeliefState 中
  │
  ▼
Decay:  时间衰减。EffectiveSupport = Support × e^(-λ × age)
  │     半衰期默认 7 天
  │
  ▼
Resolve: 扫描所有 Hypothesis，判定状态
        冻结为 Knowledge？合并到更强 Hypothesis？标记为 stale？
```

### 4.3 Belief Vector（7 维存储）

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

### 4.4 belief_score（每次按需导出）

```python
def compute_belief_score(bs: BeliefState, params: dict) -> float:
    support_ratio = bs.support / max(1, bs.support + bs.conflict)
    score = (
        support_ratio * 0.35      # weight_support
        + bs.stability * 0.25     # weight_stability
        + bs.coverage * 0.20      # weight_coverage
        + bs.recency * 0.10       # weight_recency
        + min(1.0, bs.entropy) * 0.10  # weight_entropy
    )
    return score
```

权重可配置，算法可替换。`belief_score` 是函数不是字段。

### 4.5 Hypothesis Graph

Hypothesis 之间有三种关系边：

| 边类型 | 语义 | 传播权重 |
|:---|:---|:---|
| `supports` | H_A 成立增加 H_B 成立概率 | 0.30 |
| `explains` | H_A 是 H_B 的原因/背景 | 0.15 |
| `derived_from` | H_A 从 H_B 演化而来 | 0.10 |

Belief Propagation：当一个 Hypothesis 获得新 Support，通过 `supports` 边向被支持的 Hypothesis 传播一部分信念。

### 4.6 Knowledge 冻结条件

5 维 AND 判定，全部满足才冻结：

| 条件 | 参数 | 默认值 |
|:---|:---|:---|
| 最低支撑度 | `hypothesis.min_support` | 8 |
| 最大冲突度 | `hypothesis.max_conflict` | 3 |
| 最低稳定性 | `hypothesis.min_stability` | 0.70 |
| 最低覆盖度 | `hypothesis.min_coverage` | 0.40 |
| 最低共识度 | `hypothesis.min_consensus_domains` | 2 |

冻结不可逆。Hypothesis 标记为 `frozen`，不再参与竞争。

### 4.7 ReasonSession

ReasonSession 是一次推理的 trace 记录——从 Evidence 到达到 Knowledge 冻结的完整投票过程。append-only，用于审计和 replay。

---

## 5. 路径间数据流

> 源自 `DESIGN_COGNITIVE_RUNTIME.md` §8

```
用户输入
  │
  ▼
Adapter → Event IR
  │                   (Fast Path, <50ms)
  +─────► DomainSelector → BudgetAllocator → ContextAssembler → LLM → 回复用户
  │
  │                   (Async Path, <5s, 并行)
  +─────► Observation Compiler → Observation Pool
            │
            +──► Behavior Analyzer → BehaviorGraph
            +──► Engineering Analyzer → EngineeringGraph
            +──► Profile Analyzer → UserProfile
            │
            │         (Slow Path, Checkpoint 触发)
            +──► Memory Compiler → PersistentGraph
                     │
                     +──► HypothesisEngine (Decay+Resolve) → Knowledge
                     +──► GraphTierManager → tier migration
                     │
                     │    (Deep Path, 阈值触发)
                     +──► Skill Distiller → Skill Layer
```

关键：路径之间通过 UnifiedGraphStore 和 Observation Pool 交换数据——不通过直接函数调用。

### 5.1 Bayesian Optimizer 反馈闭环

> 源自代码 `core/agent/v4/optimizer/optimizer.py`

Slow Path 每个 checkpoint 运行 Bayesian Optimizer：

- 收集 FeedbackSignal（用户隐式反馈：接受/纠正）
- 计算 composite_reward
- 用 Incremental GP（Sherman-Morrison 增量更新）建议下一组参数
- 优化对象：min_support、community_resolution、compiler_max_nodes 等
- Acquisition Function: EI (Expected Improvement)

### 5.2 Deep Path 触发评估

Slow Path 成功后评估 Deep Path 触发条件：
- `pattern_count >= 5`（成功模式数量）
- `success_rate >= 0.9`

条件满足时自动触发 Skill Distiller。

---

## 6. Multi-Tier Precision Pipeline

> 源自 `DESIGN_MULTI_TIER_PIPELINE.md`

### 6.1 精度-算力谱系

不是快/慢二元。是多层递进——用可配置的算力预算换取递增的精度。

| 谱系位置 | 算力 | 精度 | 示例 |
|:---|:---|:---|:---|
| L0: 零算力 | 0ms | ~70% | 缓存命中、预计算索引 |
| L1: 符号规则 | <5ms | ~85% | 词典匹配、正则、关键词 |
| L2: 统计模型 | ~30ms | ~92% | spaCy、Tree-sitter、embedding |
| L3: 小模型 | ~200ms | ~95% | 本地小 LLM (Ollama 3B) |
| L4: 大模型 | ~500ms | ~98% | 全量 LLM |
| L5: 人工 | 无限 | 100% | 人工审核 |

### 6.2 Pipeline 编排

```python
for each tier:
    result = tier.process(input, context_with_prev_hints)
    if result.confidence >= tier.threshold:
        return result
    context.set(tier_hint, result)  # 下层收到上层的种子
return last_result
```

每层的 context 包含前面所有层的输出作为提示。下层不需要从零开始。

### 6.3 UpgradePolicy

| 策略 | 逻辑 | 适用场景 |
|:---|:---|:---|
| ThresholdBased | confidence < threshold → 升级 | 默认 |
| AdaptiveThreshold | 根据 correction_rate 动态调整 | 长期自优化 |
| BudgetAware | 根据剩余时间预算决定 | 时间敏感 |

### 6.4 修正反馈闭环

```
Tier N+1 纠正了 Tier N 的结果:
  → feedback.record_correction(tier=N, correction={...})
  → feedback.apply():
       将修正写回 Tier N 的本地规则/缓存
       Tier N 的 correction_count += 1
  如果 Tier N 的 correction_rate > 阈值:
      触发规则更新 + 生成 Observation
```

### 6.5 全系统映射

| 模块 | 谱系配置 |
|:---|:---|
| TieredParser | L1(规则) + L2(spaCy) + L4(LLM) |
| CodeWorldAdapter | L0(Tree-sitter) + L2(AST) + L3(LSP) |
| IntentParser | L1(规则分类) + L4(LLM消歧) |
| NegativeKB | L1(关键词) + L2(语义) |

### 6.6 TierHeatBridge

MultiTierPipeline（执行层精度）与 GraphTierManager（存储层分层）之间的桥接：

- MultiTierPipeline 的 pass_rate / correction_rate → 影响数据热度
- GraphTierManager 的 GC 触发"哪些数据需要升级/降级"
- TierHeatBridge 将 Pipeline 的热度信号传递给 GC

---

## 7. 实现状态

> 源自代码 `core/agent/v4/` 实际检查

### 7.1 已实现

| 组件 | 文件 | 状态 |
|------|------|------|
| `CognitiveRuntimeEngine` | `runtime/engine.py` (576行) | ✅ 四路径编排、状态机、checkpoint 定时器 |
| `EventBus` | `event_ir.py` (120行) | ✅ 线程安全环形缓冲 |
| `PathAwareScheduler` | `cognitive_scheduler/path_scheduler.py` | ✅ 路径状态机 + 优先级调度 |
| `ConfigDrivenTriggerPolicy` | `cognitive_scheduler/path_trigger_policy.py` | ✅ 配置驱动触发 |
| `ObservationBuilder` | `observation_compiler/builder.py` | ✅ Bundle 组装 |
| `HypothesisPipeline` | `hypothesis_engine/pipeline.py` | ✅ Match+Vote+Decay+Resolve |
| `BayesianOptimizer` | `optimizer/optimizer.py` (255行) | ✅ 增量 GP + EI |
| `MultiTierPipeline` | `tiered/pipeline.py` (137行) | ✅ 级联升级 |

### 7.2 待补齐

| 缺口 | 说明 | 优先级 |
|------|------|--------|
| LLM 接线 | `start()` 不调 `_init_llm_provider()`，`on_event()` 不调 `_call_llm()` | 🚨 P0 |
| ObservationCompiler 接入 Async Path | 验证 adapter 是否真正实例化 | ✅ 已验证 |
| HypothesisEngine 接入 Slow Path | Checkpoint 时从 Pool 取数据 → submit，已接入四路径调度 | ✅ 已接入 |
| Knowledge 持久化 | KnowledgeNode 写入 UnifiedStore，Persistent Graph 已可用 | ⚠️ 待验证 |

---

> 本文档定义认知管线的数据流和调度契约。具体的数据结构定义见代码 `core/agent/v4/`。
