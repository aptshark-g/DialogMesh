# DialogMesh v4: Context Engineering

> **状态**: 设计草案  
> **日期**: 2026-07-09  
> **从**: Memory Engineering → Context Engineering  
> **核心主张**: 整个系统真正应该优化的不是"AI 怎么记住更多"，而是"进入 Transformer 之前的 Context 怎么构建"。

---

## 目录

1. 问题定义：为什么 AI 越跑越笨
2. 十个洞察
3. 核心架构：双 Compiler + Event Log
4. 组件规格
5. 与现有 v3.0/v3.2 的关系
6. 数据流全景
7. 待解决问题

---

## 一、问题定义

### 1.1 观察现象

AI Agent 在长周期工程任务中表现出系统性退化：
- 新功能不会延续旧规范
- 做新模块不知道已有设计
- Memory 越来越长，效果越来越差
- Prompt 越来越复杂，边际收益递减
- 每次都重新理解整个工程上下文

### 1.2 问题本质

这不是"记忆容量不足"的问题。是**信息和推理之间的耦合方式错了**。

当前范式：全部历史 → LLM → 回答

这个流程假设 LLM 既是记忆者也是推理者。但实际上 Transformer 是一个推理引擎——它不该同时兼任数据库、摘要器、冲突仲裁器和上下文调度器。

### 1.3 重新定义问题

| 旧定义 | 新定义 |
|:-------|:-------|
| Memory Engineering | Context Engineering |
| 怎么记住更多 | 怎么搞清楚当前该想什么 |
| 评估标准：覆盖率 | 评估标准：信息密度 |
| 优化目标：更大的上下文窗口 | 优化目标：更好的 Context IR |

---

## 二、十个洞察

### 2.1 Memory 不是文档，而是关系（Typed Edge）

文本是表象。真正承载工程信息的是**节点之间的类型化关系**。

`
Gateway ──depends──▶ Provider
Provider ──creates──▶ Monitor
Provider ──updates──▶ Metrics
`

**结论**: Memory = Graph + Typed Edge。边的类型承载了比节点文本更稠密的信息。

### 2.2 记忆不是知识，而是推理轨迹（Reasoning Graph）

节点不只是概念节点，更关键的是**推导边**。

`
A ──reason──▶ B ──reason──▶ C
`

**结论**: 图的主干应该是推理边（Reason Edges），推论节点只是副产品。

### 2.3 Context Compiler：不是全文，是子图

`
Persistent Graph (50000 nodes)
  ↓ Context Compiler
Task Subgraph (500 tokens)
  ↓ Serialize
Transformer-ready Context
`

### 2.4 Transformer 只吃 Token 序列

`
Graph → Serialization → Token Sequence → Embedding → Attention
`

Transformer 内部没有树、没有图、没有分层结构。只有位置编码 + 注意力权重。**序列化策略 = Context Engineering 的核心技术**。

### 2.5 真正可优化的不是 Transformer，而是它前面的层

`
Prompt Engineering → Memory Engineering → Context Engineering
`

优化对象的前移：从"怎么问"到"给什么信息"再到"怎么组织信息"。

### 2.6 Context IR（中间表示）

**这是本架构中最核心的新概念。**

`
编译器：源代码 → AST → SSA → IR → CPU 指令
Context：Memory → Reason Graph → Context IR → Token → Transformer
`

Context IR 不是 Graph 本身，而是**为当前任务定制的、最优的信息组织方式**。

**关键原则**: Graph 是 IR 的原料，不是 IR 本身。

### 2.7 Event Log：Lazy Merge

当前系统的最大性能瓶颈是**增量图更新**——每一次行为变化都触发图重写。

**解决方案**: 借鉴 Spark 懒求值、数据库 WAL、Git commit。

`
每次行为 → 追加一条 Event → 不更新 Memory
Checkpoint 触发 → 批量 Merge → Graph Rewrite → Summary → Persistent
`

Checkpoint 触发条件：任务完成、CPU 空闲、固定时间窗口、会话边界、用户显式归档。

### 2.8 Memory Compiler：维护记忆的专用编译器

LLM 不应该维护 Memory。LLM 应该只负责推理。

`
Events → Merge → Conflict Resolution → Graph Rewrite → Summary → Persistent
`

它是一个**非实时、批处理、可规则化**的编译器。

### 2.9 双 Compiler 分工

| | Memory Compiler | Context Compiler |
|:--|:--|:--|
| 触发 | Checkpoint（懒） | 每次 Query（实时） |
| 输入 | Event Log | Persistent Graph + 当前任务 |
| 输出 | 更新后的 Persistent Graph | Context IR |
| 优化目标 | 图的一致性和信息保真 | Token 预算内的最大相关性 |
| 实现 | 规则为主 + LLM 冲突仲裁 | LLM + 子图算法 |
| 类比 | Git 的 commit | Git 的 checkout |

### 2.10 Memory 不是状态，而是 Patch Chain

持久化的不应该是"当前最终状态"，而是：

`
Base State + Patch1 + Patch2 + Patch3 + ...
`

Memory Compiler 在 Checkpoint 时 apply 所有 patch，生成新的 base state。

**好处**: 每次追加 O(1)、可回放撤销审计、Merge 冲突延迟到 Checkpoint。

---

## 三、核心架构

### 3.1 架构全景

`
                           ┌──────────────────────┐
                    │    用户行为           │
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │   Behavior Chain     │  ← v3.2 BehaviorGraph
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │    Event Log          │  ★ 追加式，不实时更新
                    └──────────┬───────────┘
                               │
              ┌────────────────┴────────────────┐
              ▼                                 ▼
   ┌──────────────────────┐        ┌──────────────────────┐
   │  Memory Compiler     │        │  Context Compiler    │
   │  (后台·懒求值)        │        │  (实时·按 Query)     │
   │  Event→Merge→Conflict│        │  Graph→Subgraph→IR   │
   │  →Rewrite→Persist    │        │                      │
   └──────────┬───────────┘        └──────────┬───────────┘
              ▼                                 ▼
   ┌──────────────────────┐        ┌──────────────────────┐
   │  Persistent Graph    │◄───────│  Context IR          │
   │  Property Graph      │ 检索    │  ≤500 tokens         │
   │  + Typed Edge        │        │  结构化序列化         │
   │  + Patch Chain       │        └──────────┬───────────┘
   └──────────────────────┘                   ▼
                                    ┌──────────────────────┐
                                    │    Transformer        │
                                    └──────────────────────┘
`

### 3.2 分层职责

| 层 | 职责 | 频率 | 延迟容忍 | 并发模型 |
|:---|:-----|:-----|:---------|:---------|
| Behavior Chain | 捕获行为结构化表示 | 每轮 | 低延迟 | 同步 |
| Event Log | 追加原始事件 | 每轮 | 低延迟 | 同步，O(1) |
| Memory Compiler | 批量合并，更新图 | Checkpoint | 高延迟容忍 | 异步 |
| Persistent Graph | 长期存储 | 查询时 | 低延迟（读） | 读写分离 |
| Context Compiler | 生成 Context IR | 每轮 | 低延迟 | 同步，预算受限 |
| Context IR | 序列化上下文 | 每轮 | — | — |
| Transformer | 推理 | 每轮 | — | — |

---

## 四、组件规格

### 4.1 Event Log

`
Event {
  id: UUID
  timestamp: DateTime
  type: "behavior" | "correction" | "topic_switch" | "profile_update" | "checkpoint"
  payload: Dict
  session_id: UUID
  turn_number: int
}
`

设计约束：只追加不删改、每条独立、可中断恢复、存储用 SQLite/JSONL。

### 4.2 Persistent Graph

`
Node {
  id: UUID
  type: "topic" | "concept" | "action" | "constraint" | "entity"
  text: str
  embedding: vector(384)
  activation_count: int      # 电容模型
  importance_score: float    # Memory Compiler 计算
  source_events: [UUID]
}

Edge {
  id: UUID
  source: UUID
  target: UUID
  type: "depends" | "creates" | "updates" | "constrains" | "reason" | "corrects" | "extends"
  weight: float              # α/β/γ/δ 四因子
  activation_count: int
  confidence: float
  source_events: [UUID]
}
`

关键属性：Property Graph、Typed Edge、跨会话持久化、Patch Chain 存储。

### 4.3 Memory Compiler

`
process(checkpoint_events: [Event]) -> MergePlan

步骤:
1. 冲突检测：同节点的多个 patch 有没有矛盾
2. 冲突解决：
   - 确定性冲突 → 规则引擎
   - 模糊冲突 → 轻量 LLM 仲裁
   - 高置信度冲突 → 保留两个版本，标记分叉
3. 节点合并：embedding 去重
4. 边融合：同类型同方向加权合并
5. 重要性重算：activation_count + 结构位置 + 推理参与度
6. ColdIndexer 更新：低重要性下沉，回升策略
7. Summary 生成：L1 节点级 / L2 话题级
`

触发条件（满足任一）：Event 数≥N、时间≥T、会话结束、用户触发、系统空闲。

### 4.4 Context Compiler

`
compile(query, persistent_graph, user_profile) -> ContextIR

步骤:
1. 话题定位 (TopicBoundaryDetector)
2. 子图裁剪：锚点出发 k 跳水波扩展
   - 沿 typed edge 按类型权重扩展
   - 沿 reason 边高优先级
   - 沿 depends 边次优先级
   - 相关性过滤 + 激活计数过滤
3. 信息选择：在 500 token 预算内最大化推理路径+约束+行为链+画像
4. Context IR 生成：结构化序列化
5. 验证：每个 token 是否必要，超预算降级到摘要模式
`

### 4.5 Context IR 格式

`
ContextIR {
  sections: [
    { type: "topic",       tokens: 80,  confidence: 0.95 },
    { type: "reasoning",   tokens: 200, confidence: 0.88 },
    { type: "constraints", tokens: 100, confidence: 0.92 },
    { type: "history",     tokens: 80,  confidence: 0.99 },
    { type: "profile",     tokens: 40,  confidence: 0.85 }
  ]
  total_tokens: 500
  strategy: "greedy_ilp" | "summary_fallback"
  compile_time_ms: 45
}
`

---

## 五、与现有代码的关系

### 5.1 映射表

| v4 组件 | v3.0/v3.2 对应 | 状态 |
|:--------|:---------------|:-----|
| Event Log | session_recorder, monitor 事件流 | 已有雏形，需强化 |
| Memory Compiler | consolidation, cold_indexer, BehaviorGraph 更新, adaptive_threshold | 分散模块 → 合并 |
| Persistent Graph | persistence/graph_store, cold_indexer, BehaviorGraph, CognitiveProfile | 已有，转 Patch Chain |
| Context Compiler | TopicBoundaryDetector, cognitive_compiler, l2_summary, fusion, compressor | 分散模块 → 合并 |
| Context IR | **全新** | 从零设计 |

### 5.2 整合策略

- **保留**: BehaviorGraph, CognitiveProfile, TopicBoundaryDetector, ColdIndexer, Persistence Layer
- **合并到 Memory Compiler**: consolidation, cold_indexer, adaptive_threshold, negative_kb
- **合并到 Context Compiler**: cognitive_compiler, l2_summary, fusion, compressor, compiler(v3.2)
- **降级**: do_calculus, FoA, L1Summary 变为子模块
- **废弃**: 所有冗余的独立管理器类

---

## 六、数据流

### 6.1 一次 Request 的完整路径

`
用户消息 "优化 Gateway 的缓存策略"
  │
  ├─(1)► BehaviorChain 捕获
  ├─(2)► EventLog 追加
  ├─(3)► TopicBoundaryDetector 定位当前话题
  ├─(4)► ContextCompiler.compile()
  │       ├─ 取锚点附近 2 跳子图
  │       ├─ 发现推理路径 + 约束 + 行为历史
  │       ├─ 生成 ContextIR (470 tokens)
  │       └─ 序列化注入 Prompt
  ├─(5)► Transformer 推理 → 回答
  └─(6)► 回答追加为 Event → 回到(2)
`

### 6.2 Checkpoint 路径

`
触发 → MemoryCompiler 批处理
  ├─ 合并节点、融合边
  ├─ 冲突检测与解决
  ├─ 重算 importance + activation
  ├─ ColdIndexer 下沉/回升
  └─ 写入 PersistentGraph + 生成 Summary
`

---

## 七、待解决问题

### 7.1 Graph 数据模型 (P0)

- DAG vs 允许环：允许环但裁剪时做 DAG 转化
- HyperEdge：暂用二元边 + group_id
- 节点 identity：embedding 去重 + LLM 仲裁

### 7.2 Context Compiler 的子图裁剪算法 (P0)

在 token 预算 C 内选最大信息价值的子图 S → NP-hard，需 ILP 近似或启发式。

### 7.3 Memory Rewrite 冲突解决 (P1)

- 确定性冲突 → 规则引擎
- 模糊冲突 → LLM 仲裁
- 高置信度矛盾 → 保留双版本
- 顺序冲突 → last-write-wins

### 7.4 Multi-Layer Memory (P1)

| 层 | 大小 | 延迟 | 内容 |
|:---|:-----|:-----|:-----|
| Working | ~10 nodes | <5ms | 当前会话活跃节点 |
| Engineering | ~1000 nodes | <50ms | 当前项目图(内存) |
| Long-term | ∞ | <500ms | 持久化图+冷索引 |

晋升/降级规则：基于 activation_count 连续阈值。

### 7.5 LLM 参与程度 (P2)

推荐 90% 规则 + 10% LLM（仅冲突仲裁、节点去重）。

### 7.6 评估标准 (P1)

- 信息密度：每 token 的平均信息增益
- 任务相关性：IR 覆盖任务需求信息的比例
- 推理完整性：推理路径无遗漏
- 上下文浪费率：attention 中被忽略的 token 比例

---

## 八、迭代路线

- **Phase 0**: 设计定稿，确定 Graph 模型和 IR 格式
- **Phase 1**: Event Log 实现 + 迁移现有入口
- **Phase 2**: Memory Compiler（merge + conflict + rewrite）
- **Phase 3**: Context Compiler（子图裁剪 + IR 生成）
- **Phase 4**: Multi-Layer Memory + ColdIndexer 回升
- **Phase 5**: 评估体系 + 基准测试

---

> **核心主张**: 把 Transformer 当推理引擎用，不把它当数据库用。多花的每一分算力都放在 Context 的编译质量上，而不是 Memory 的存储体量上。
