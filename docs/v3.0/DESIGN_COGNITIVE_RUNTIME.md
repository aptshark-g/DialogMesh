# Cognitive Runtime：v4 运行时调度层

> 定义 v4 所有模块的触发时机、执行优先级、并发模型和资源预算。
> Cognitive Runtime 不产生数据——它决定数据在什么时刻、经过什么处理阶段。

> 版本: v1.0 | 日期: 2026-07-11

---

## 目录

1. 定位：为什么需要 Runtime
2. 核心设计决策：五个原则
3. 四路径架构
4. Fast Path（每轮，<50ms）
5. Async Path（后台，<5s）
6. Slow Path（Checkpoint，分钟级）
7. Deep Path（小时/天级）
8. 路径间的数据流
9. 与现有模块的关系

## 1. 定位：为什么需要 Runtime

v4 设计文档定义了 20+ 模块——ContextCompiler、MemoryCompiler、BeliefUpdate、
GraphTierManager、DomainSelector、SkillDistiller……但从未定义这些模块的运行时调度契约。

每个模块都知道自己做什么——但不知道什么时候做、以什么优先级做、做不完怎么办。

Cognitive Runtime 是这些问题的统一答案。它不是新模块——它是一个调度文档，
定义所有模块的触发条件、执行顺序、超时策略和资源预算。

类比：如果 v4 的模块就像 Linux 的各个子系统（内存管理、文件系统、网络栈），
Cognitive Runtime 就是 Linux 的调度器（scheduler）——它不产生数据，
它决定 CPU 时间片如何分配、进程何时被唤醒、中断如何处理。

## 2. 核心设计决策：五个原则

1. Event IR 不持久化。Event 是运行时中间语言，类比 CPU 寄存器或 HTTP Request。
   持久化的是 Observation 及其下游产物。Event 最多保留 24h WAL 用于审计回放。

2. Event IR 在 PCR 前面，不是替代。PCR 是 Event Consumer（消费 dialog.message）。
   新类型 Event（ui.drag、config.change）有各自的 Consumer，PCR 不改。

3. 新旧管线并行。旧管线（PCR → Planner → LLM）继续负责回复用户。
   新管线（Event → Observation → Knowledge）负责知识沉淀。
   等新管线成熟到能产出更好的 Context IR，再切流。

4. 所有模块通过 Runtime 调度，不互相直接调用。Module A 不 import Module B。
   Runtime 从统一的 Event Chain 读取数据，按路径分配执行。

5. 每个模块有明确的路径归属（Fast/Async/Slow/Deep），不跨路径调用。
   一个模块不能同时被 Fast Path 和 Slow Path 使用——如果需要，拆成两个子模块。

## 3. 四路径架构

`
用户输入
  |
Fast Path (<50ms，同步)
  Adapter -> Event IR -> DomainSelector -> BudgetAllocator -> ContextSerializer -> LLM
  |  （并行）
Async Path (<5s，后台)
  Observation Pipeline -> Behavior/Engineering Analyzer
  |
Slow Path (Checkpoint，分钟级)
  MemoryCompiler -> BeliefUpdate -> GraphTierManager
  |
Deep Path (小时/天级)
  Skill Distiller
`

| 路径 | 触发 | 延迟预算 | 并发模型 | 失败策略 |
|:---|:---|:---|:---|:---|
| Fast | 每次用户输入 | <50ms | 同步，阻塞回复 | 降级到旧管线 |
| Async | Fast Path 产出的 Event | <5s | 异步，不阻塞回复 | 重试 3 次，然后丢弃 |
| Slow | Checkpoint（N Events 或 T 时间） | 分钟级 | 后台线程 | 永久保留在 Event Log，下次重试 |
| Deep | 阈值触发（N 次同类 Pattern） | 小时/天级 | 独立 worker | 标记为 pending，人工审查 |

## 4. Fast Path（每轮，<50ms）

触发：用户消息到达。同步执行——必须在此时间内完成，否则降级到旧管线。

`
Adapter（Input -> Event IR）         <5ms
  -> DomainSelector.select(intents)   <5ms
  -> BudgetAllocator.allocate(...)    <5ms
  -> ContextSerializer.serialize(ir)  <5ms
  -> LLM（实际推理）                  ＜剩余时间
`

模块分配：

| 模块 | 路径 | 输入 | 输出 | 超时 |
|:---|:---|:---|:---|:---|
| Adapter | Fast | 原始输入（文本/点击/拖拽） | Event IR | 5ms |
| DomainSelector | Fast | IntentEstimate[] | DomainSelection | 5ms |
| BudgetAllocator | Fast | DomainWeights + Entries | selected entries | 5ms |
| ContextSerializer | Fast | CrossDomainContextIR | Prompt string | 5ms |

降级策略：任何一个模块超时 -> 跳过新管线 -> 使用旧管线（扁平历史+system prompt）。

## 5. Async Path（后台，<5s）

触发：Fast Path 产出的每个 Event。异步执行——不阻塞用户回复。

`
Observation Compiler：Event -> Observation（intent提取、实体识别、快速解析，<2s）
  -> Behavior Analyzer：Observation -> 行为模式更新（<1s）
  -> Engineering Analyzer：Observation -> 约束检查 + Pattern匹配（<1s）
  -> 写入 Observation Pool
`

模块分配：

| 模块 | 路径 | 输入 | 输出 | 超时 |
|:---|:---|:---|:---|:---|
| Observation Compiler | Async | Event IR | Observation | 2s |
| Behavior Analyzer | Async | Observation[] | Hypothesis[] | 1s |
| Engineering Analyzer | Async | Observation[] | Hypothesis[] | 1s |

失败策略：Event 保留在 24h WAL 中，下次 Checkpoint 时重试。连续 3 次失败标记为 dead letter。

## 6. Slow Path（Checkpoint，分钟级）

触发（满足任一）：Event 累积 >= 50、时间 >= 30 分钟、会话结束、用户触发。

`
Memory Compiler：Observation Pool -> Knowledge（冲突检测+合并+去重+冷热分层）
  -> Belief Update Engine：Hypothesis -> 证据更新+置信度传播
  -> GraphTierManager.run_gc()：Hot->Warm->Cold->Archive 分层迁移
  -> Summary Builder：L1（节点级）+ L2（话题级）摘要生成
`

模块分配：

| 模块 | 路径 | 输入 | 输出 | 超时 |
|:---|:---|:---|:---|:---|
| Memory Compiler | Slow | Observation[] | Knowledge Graph delta | 60s |
| Belief Update | Slow | Hypothesis[] | Updated confidences | 30s |
| GraphTierManager | Slow | UnifiedGraphStore | tier migration | 10s |
| Summary Builder | Slow | Knowledge Graph | L1/L2 summaries | 30s |

失败策略：Observation 永久保留在 Observation Pool，下次 Checkpoint 时重试。

## 7. Deep Path（小时/天级）

触发：阈值——同一 Pattern 被使用 N 次（默认 5 次）且成功率 > 90%。

`
Skill Distiller：Pattern[] -> Skill（经验模板蒸馏）
  -> Candidate Skill（confidence 30%）-> 人工或自动审查 -> Verified Skill
`

| 模块 | 路径 | 输入 | 输出 | 超时 |
|:---|:---|:---|:---|:---|
| Skill Distiller | Deep | Pattern[] + usage stats | Candidate Skill | 60s |

失败策略：标记为 pending，等待更多使用数据后重试。不自动降级。


## 8. 路径间的数据流

`
用户输入
  |
  v
Adapter -> Event IR
  |                   (Fast Path)
  +-----> PCR -> TopicTree -> LLM -> 回复用户
  |
  |                   (Async Path，并行)
  +-----> Observation Compiler -> Observation Pool
            |
            +--> Behavior Analyzer -> BehaviorGraph
            +--> Engineering Analyzer -> EngineeringGraph
            +--> Profile Analyzer -> UserProfile
            |
            |         (Slow Path，Checkpoint触发)
            +--> Memory Compiler -> PersistentGraph
                     |
                     +--> Belief Update -> Hypothesis confidence
                     +--> GraphTierManager -> tier migration
                     |
                     |    (Deep Path，阈值触发)
                     +--> Skill Distiller -> Skill Layer
`

关键：路径之间通过 UnifiedGraphStore 和 Observation Pool 交换数据——不通过直接函数调用。


## 9. 与现有模块的关系

| 现有模块 | 路径归属 | 变化 |
|:---|:---|:---|
| IntentParser (PCR) | Fast（旧管线） | 不变——保持现在的工作方式 |
| TopicTree | Fast（旧管线） | 不变 |
| DomainSelector | Fast（新管线） | 已有，纳入 Runtime 调度 |
| BudgetAllocator | Fast（新管线） | 已有 |
| ContextSerializer | Fast（新管线） | 已有 |
| Observation Compiler | Async | 需新建 |
| Behavior Analyzer | Async | 复用 BehaviorGraph 的 consume 逻辑 |
| Engineering Analyzer | Async | 复用 ConstraintEngine |
| Memory Compiler | Slow | 已有 consolidation.py + cold_indexer.py 可合并 |
| Belief Update Engine | Slow | 需新建 |
| GraphTierManager | Slow | 已有 |
| Skill Distiller | Deep | 需新建 |

---

> Cognitive Runtime 不是新模块——它是调度文档，
> 定义 v4 所有模块的运行时契约：什么时刻启动、到什么时间必须完成、
> 超时或失败时该怎么做。
