# DialogMesh 系统设计总纲

> **本文档合并自以下源头文档**（原文件保留于 `docs/v3.0/` 不删除）：
> - `DESIGN_V4_CONTEXT_ENGINEERING.md` — v4 核心主张、十个洞察、双 Compiler 架构
> - `DESIGN_FULL_CONCEPT.md` — 分层架构、数据契约、PCR/IntentParser 概念
> - `ARCHITECTURE_INDEX.md` — 原始文档索引
> - `THOUGHT_IMPRINT.md` — 设计哲学、关键决策记录
> - `DESIGN_INTERACTION_MODEL.md` — Event Layer + Multi-Projection
> - `DESIGN_COMPETITOR_ABSORPTION.md` — 竞品对比精华
> - `implementation_assessment.md` — 实现状态评估

---

## 1. 系统定位

DialogMesh 是一个**认知增强型对话系统**，核心设计哲学：

> "对话不是一问一答，而是基于用户认知模型的持续推断与自适应。"

更进一步的 v4 主张：

> **整个系统真正应该优化的不是"AI 怎么记住更多"，而是"进入 Transformer 之前的 Context 怎么构建"。**

当前范式：全部历史 → LLM → 回答。这假设 LLM 既是记忆者也是推理者。但 Transformer 是一个推理引擎——它不该同时兼任数据库、摘要器、冲突仲裁器和上下文调度器。

| 旧定义 | 新定义 |
|:-------|:-------|
| Memory Engineering | Context Engineering |
| 怎么记住更多 | 怎么搞清楚当前该想什么 |
| 评估标准：覆盖率 | 评估标准：信息密度 |
| 优化目标：更大的上下文窗口 | 优化目标：更好的 Context IR |

**目标**：对标并超越 Codex/Claude Code 等编码 Agent。DialogMesh 不自己当 coding agent，而是做 OpenClaw 等执行层的**上下文大脑**——用 World Model 预编译代码结构，用 Context IR 替代裸 prompt。

---

## 2. 十个核心洞察

> 源自 `DESIGN_V4_CONTEXT_ENGINEERING.md` §2

### 2.1 Memory 不是文档，而是关系（Typed Edge）

文本是表象。真正承载工程信息的是节点之间的类型化关系。

```
Gateway ──depends──▶ Provider
Provider ──creates──▶ Monitor
Provider ──updates──▶ Metrics
```

Memory = Graph + Typed Edge。边的类型承载了比节点文本更稠密的信息。

### 2.2 记忆不是知识，而是推理轨迹（Reasoning Graph）

节点不只是概念节点，更关键的是推导边：`A ──reason──▶ B ──reason──▶ C`。图的主干应该是推理边，推论节点只是副产品。

### 2.3 Context Compiler：不是全文，是子图

```
Persistent Graph (50000 nodes)
  ↓ Context Compiler
Task Subgraph (500 tokens)
  ↓ Serialize
Transformer-ready Context
```

### 2.4 Transformer 只吃 Token 序列

Transformer 内部没有树、没有图、没有分层结构。只有位置编码 + 注意力权重。**序列化策略 = Context Engineering 的核心技术**。

### 2.5 真正可优化的不是 Transformer，而是它前面的层

```
Prompt Engineering → Memory Engineering → Context Engineering
```

优化对象的前移：从"怎么问"到"给什么信息"再到"怎么组织信息"。

### 2.6 Context IR（中间表示）

```
编译器：源代码 → AST → SSA → IR → CPU 指令
Context：Memory → Reason Graph → Context IR → Token → Transformer
```

Context IR 不是 Graph 本身，而是为当前任务定制的、最优的信息组织方式。Graph 是 IR 的原料，不是 IR 本身。

### 2.7 Event Log：Lazy Merge

借鉴 Spark 懒求值、数据库 WAL、Git commit。每次行为 → 追加一条 Event → 不更新 Memory。Checkpoint 触发 → 批量 Merge → Graph Rewrite → Summary → Persistent。

### 2.8 Memory Compiler：维护记忆的专用编译器

LLM 不应该维护 Memory。LLM 应该只负责推理。Events → Merge → Conflict Resolution → Graph Rewrite → Summary → Persistent。它是一个非实时、批处理、可规则化的编译器。

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

持久化的不应该是"当前最终状态"，而是：`Base State + Patch1 + Patch2 + Patch3 + ...`。每次追加 O(1)、可回放撤销审计、Merge 冲突延迟到 Checkpoint。

---

## 3. 架构分层全景

> 源自 `DESIGN_FULL_CONCEPT.md` §1.2，融合 v4 双 Compiler 架构

```
┌──────────────────────────────────────────────────────────────────────┐
│ 用户接口层 (WebSocket / REST / CLI / TUI)                            │
├──────────────────────────────────────────────────────────────────────┤
│ API + Event Log 层                                                    │
│  • HTTP API  • SQLite WAL  • Crash Recovery                          │
├──────────────────────────────────────────────────────────────────────┤
│ Cognitive Runtime（运行时调度层）                                      │
│  • 四路径调度 (Fast/Async/Slow/Deep)  • PathAwareScheduler           │
│  • BayesianOptimizer  • EventCounter  • 状态机                        │
├──────────────────────────────────────────────────────────────────────┤
│ 认知管线 (Cognitive Pipeline)                                          │
│  Event IR → ObservationCompiler → ObservationPool                     │
│  → HypothesisEngine → KnowledgeNode → SkillDistiller                  │
├──────────────────────────────────────────────────────────────────────┤
│ 上下文层 (Context Engine)                                              │
│  • ContextCompiler: 子图裁剪 + IR 生成                                │
│  • DomainSelector + BudgetAllocator + ContextAssembler               │
│  • CrossDomainContextIR → to_prompt() → LLM                          │
├──────────────────────────────────────────────────────────────────────┤
│ 记忆与存储层                                                           │
│  • Persistent Graph (Property Graph + Typed Edge + Patch Chain)      │
│  • UnifiedGraphStore (Hot/Warm/Cold/Archive 分层)                    │
│  • HybridIndex (语义 + 关键词双通路)  • Milvus/SQLite 向量存储        │
├──────────────────────────────────────────────────────────────────────┤
│ 世界模型层 (World Model)                                               │
│  • StructuralWorldGraph  • ReferenceUnit  • 多类型边                  │
│  • Community Detection  • Backbone Coloring                           │
│  • CodeWorldAdapter (tree-sitter)  • Engineering Chain               │
├──────────────────────────────────────────────────────────────────────┤
│ 输入层                                                                 │
│  • PCR (噪声检测 + 期望推断 + 画像快照)                                │
│  • TieredParser (规则→spaCy→LLM)  • TieredActionResolver             │
│  • MultiTierPipeline (精度-算力谱系)                                   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. 核心数据契约

> 源自 `DESIGN_FULL_CONCEPT.md` §1.3 + `DESIGN_V4_CONTEXT_ENGINEERING.md` §4

### 4.1 EventIR

> 源自 `DESIGN_V4_KNOWLEDGE_REFINEMENT.md` §2 + 代码 `core/agent/v4/event_ir.py`

Event IR 是运行时中间语言，类比 CPU 寄存器或 HTTP Request。**不持久化**（最多 24h WAL 用于审计回放）。

```python
@dataclass
class EventIR:
    id: str                    # 唯一标识
    kind: str                  # dialog.message | ui.drag | config.change | api.call | git.commit
    payload: dict              # 完全动态，不预设 schema
    refs: dict                 # conversation_id, user_id, session_id, engineering_node
    metadata: dict             # time, source, confidence
    timestamp: float
```

设计约束：kind 固定几个大类，payload 完全开放。不预设标签体系——维护可成长的 Vocabulary（Core / Candidate / Unknown 三级）。

### 4.2 ObservationBundle

> 源自 `DESIGN_OBSERVATION_COMPILER.md` §3-4

Bundle 与 Event 是 1:1 关系，内含多个 DomainObservation（按认知域独立），每个 DomainObservation 内含多个 Interpretation（同域内竞争）。

```
Event (id="evt_001")
  → ObservationBundle (bundle_id="bun_001", event_id="evt_001")
      ├── DomainObservation (domain="engineering") → [Interp_A, Interp_B, Interp_C]
      ├── DomainObservation (domain="behavior")    → [Interp_A, Interp_B]
      ├── DomainObservation (domain="dialogue")    → [Interp_A, Interp_B, Interp_C]
      └── DomainObservation (domain="memory")      → [Interp_A]
```

### 4.3 HypothesisNode → KnowledgeNode

> 源自 `DESIGN_HYPOTHESIS_ENGINE.md` §7

```python
@dataclass
class HypothesisNode:
    hypothesis_id: str
    interpretation_ref: str         # 关联的 Interpretation ID
    domain: str
    statement: str                  # "用户正在开发 Gateway"
    objects: list[str]
    belief_state: BeliefState       # 7维：support/conflict/novelty/stability/coverage/recency/entropy
    status: str = "active"          # active | merged | frozen | stale

@dataclass
class KnowledgeNode:
    knowledge_id: str
    hypothesis_ref: str             # 冻结来源
    statement: str
    domain: str
    belief_score: float             # 冻结时的 belief_score
    frozen_at: float
```

### 4.4 CrossDomainContextIR

> 源自 `DESIGN_CROSS_DOMAIN_CONTEXT.md` §7

```python
@dataclass
class CrossDomainContextIR:
    intent_category: str            # task | query | correction | discussion | casual | topic_switch
    domain_allocation: list[DomainAllocation]  # 域 + 角色 + 预算百分比
    entries: list[IREntry]          # 实际内容条目
    total_estimated_tokens: int
    compile_strategy: str           # primary_deep | balanced | summary_fallback

@dataclass
class IREntry:
    domain: str                     # E/C/P/B/K
    type: str                       # MODULE | TOPIC | ACTION | CONCEPT | PATTERN
    content: str
    cross_refs: list[CrossRef]      # 跨域指针
    source_events: list[str]
    confidence: float
    estimated_tokens: int
```

### 4.5 StructuralWorldGraph

> 源自 `DESIGN_SEMANTIC_WORLD_MODEL.md` §7

```python
@dataclass
class StructuralWorldGraph:
    graph_id: str
    world: str                      # code | cad | unity | dom | db
    units: Dict[str, ReferenceUnit] # unit_id -> ReferenceUnit
    edges: List[StructuralEdge]     # 多类型边
    communities: Dict[str, List[str]]  # 社区检测结果
    backbone: Dict[str, float]      # unit_id -> backbone_score
```

---

## 5. 数据流全景

> 源自 `DESIGN_V4_CONTEXT_ENGINEERING.md` §6 + `DESIGN_COGNITIVE_RUNTIME.md` §8

### 5.1 一次 Request 的完整路径

```
用户消息 "优化 Gateway 的缓存策略"
  │
  ├─(1)► Adapter → EventIR
  ├─(2)► Async Path: ObservationCompiler → ObservationPool
  ├─(3)► Fast Path: DomainSelector → BudgetAllocator → ContextAssembler
  │       ├─ 从 Persistent Graph 取锚点附近子图
  │       ├─ 发现推理路径 + 约束 + 行为历史
  │       ├─ 生成 CrossDomainContextIR (≤500 tokens)
  │       └─ to_prompt() → 序列化注入 Prompt
  ├─(4)► Transformer 推理 → 回答
  └─(5)► 回答追加为 Event → 回到(2)
```

### 5.2 Checkpoint 路径（Slow Path）

```
触发（Event≥50 或 时间≥30min 或 会话结束）
  → MemoryCompiler 批处理
      ├─ 合并节点、融合边
      ├─ 冲突检测与解决（规则为主，LLM 仲裁）
      ├─ 重算 importance + activation
      ├─ GraphTierManager: Hot→Warm→Cold→Archive 分层迁移
      ├─ HypothesisEngine: Decay + Resolve → Knowledge 冻结
      └─ 写入 PersistentGraph + 生成 L1/L2 Summary
```

### 5.3 Deep Path（蒸馏）

```
触发（同一 Pattern 使用 N≥5 次且成功率>90%）
  → SkillDistiller: Pattern[] → Candidate Skill (confidence 30%)
  → 人工或自动审查 → Verified Skill → Core Skill
```

---

## 6. 设计哲学与关键决策

> 源自 `THOUGHT_IMPRINT.md`

### 6.1 五条核心哲学

1. **因果不是发现出来的，是投射出来的** — `structural_prior` 永远不输出 1.0，以"约束稳定性"而非"因果必然性"表达
2. **结构因果补充统计因果，不是替代** — 统计因果处理常见模式，结构因果提供冷启动方向
3. **LLM 不做约束消解，LLM 只做粗切割** — LLM 做语义角色标注，规则做约束消解
4. **纠错即训练** — 用户纠正的惩罚是预测命中的两倍（-0.20 vs +0.10）
5. **先信任规则，后信任自身经验** — δ 从 0.05 开始动态上调，不固定

### 6.2 核心设计决策

1. 行为链/因果链/关联链三链在 TopicTreeNode 中并行，不在独立的行为树上
2. BehaviorGraph 是独立的图引擎（存权重），TopicTreeNode 是行为链的拓扑索引
3. 因果基地离线跑，在线只读——所有 Heavy 操作只在会话间隙执行
4. 融合器不是一次性融合，是分阶段（10ms→80ms→150ms）——系统在 10ms 就有可用输出
5. 负知识库有三次熔断——用户坚持 3 次后系统学习新上下文规则
6. do-calculus 只做验证（后门准则），不做发现

### 6.3 放弃过的方案

| 放弃的方案 | 原因 | 替代方案 |
|-----------|------|---------|
| 全量 World Model（状态推演） | LLM 成本爆炸 | Skill 元数据 + 历史统计 |
| NeSyS logit 层约束 | 约束编译复杂，多 token 失效 | 流式结构化输出增量验证 |
| 完整全局工作空间（Baars） | 过度设计 | 融合器加简化 workspace（100 行） |
| 因果基地实时推理 | 不可行，50-500ms | 离线预计算 + 在线只读缓存 |
| 噪声自适应上线即用 | 无真实数据 | Phase 1 统一 noise_level=0.5 |

**核心模式**："理论正确但工程太重 → 做轻量版"。几乎在所有"理论深度"和"工程可行性"的交叉点上，都选择了先落地、再深化。

---

## 7. 交互模型：Event Layer + Multi-Projection

> 源自 `DESIGN_INTERACTION_MODEL.md`

### 7.1 三层架构

```
                Event Log (唯一事实源)
                      |
               Event Processor
                      |
        ┌─────────────┼─────────────┐
        |             |             |
  Conversation    Operation    Engineering
   Projection     Projection    Projection
   (对话树视图)   (操作树视图)   (工程图视图)
        |             |             |
        └─────────────┼─────────────┘
                      |
               Cognitive Layer
        (Memory / Planning / Behavior)
```

### 7.2 核心原则

- **统一协议，不统一表现形式** — 不同模态通过 Adapter 转化为统一 Event，不同 Projection 各自解释
- **Event 不包含推断结果** — TopicSwitch、ConstraintUpdate 是 Projection 层的推断产物
- **链是注解层，不是嵌入层** — 行为链/因果链/工程链是对树边的注解，不是边的属性
- **双轨制** — Event Log（时序事实轨，不可变）+ Projection（语义结构轨，可重组）

---

## 8. 竞品对比

> 源自 `DESIGN_COMPETITOR_ABSORPTION.md` 精华 + `implementation_assessment.md` §4.2

### 8.1 与现有系统对比

| 文献/系统 | 核心方法 | DialogMesh 的差异 |
|-----------|----------|-------------------|
| ChatGPT/Claude | 未公开，推测为轮级滑动窗口 | 话语块压缩 + Context IR 编译，大幅降低 token 消耗 |
| Codex/Claude Code | 被动堆叠文件内容到 prompt | World Model 预编译代码结构，主动裁剪子图 |
| 王梦秋（DPTM） | 轮级树 + 注意力 | 话语块替代轮次作为最小单元，粒度更灵活 |
| 陈书宏（SRoT） | 基于 RST 的浅层对话结构 | 增加了粘合度量化和渐进式压缩 |
| MemWalker | 代码知识图谱 | 我们做 Structural World Model，代码只是第一视图 |

### 8.2 对标 Codex 的核心差异点

Codex/Claude Code 的弱点：**上下文是被动堆叠的**——把文件内容塞进 prompt，靠 LLM 自己理解。

DialogMesh 的优势：**主动编译上下文**——用 World Model 做子图裁剪，只给 LLM 最相关的结构化信息。这个差异必须用实验数据证明。

---

## 9. 当前实现状态与已知缺口

> 源自 `implementation_assessment.md`

### 9.1 代码资产

| 维度 | 数值 |
|------|------|
| 核心代码（非测试） | ~78,800 行 Python |
| 其中 v4 | ~13,900 行 |
| 测试代码 | ~24,400 行（117 文件） |
| 设计文档 | 107 篇，~65,700 行 |
| 提交历史 | 150 commits，13 天，单人开发 |

### 9.2 已实现且扎实的部分

| 组件 | 评价 |
|------|------|
| `CognitiveRuntimeEngine` | 真正的编排器：路径状态机、事件计数器、checkpoint 定时器 |
| `EventBus` | 线程安全环形缓冲，背压保护 |
| `BayesianOptimizer` | 真实实现：增量 GP + EI acquisition |
| `MultiTierPipeline` | 干净的级联升级模式 |
| `ContextAssembler` | 多源聚合 + HybridIndex + 分层向量存储 |
| `HypothesisPipeline` | 观察→假设→知识队列，匹配投票+衰减解决 |
| `CLI/API/TUI` | 完整的 CLI + REST API + Textual TUI |

### 9.3 关键缺口

| 缺口 | 严重程度 | 说明 |
|------|----------|------|
| **LLM 接线** | ✅ 已修复 | `start()` 调 `_init_llm_provider()`，`on_event()` 调 `_call_llm()` |
| **端到端** | ✅ 已修复 |   可连接 DeepSeek API 正常多轮对话 |
| **PerspectivePlanner** | ✅ 已实现 | intent → strategy → domain 三层决策，4 种策略自动检测 |
| **ViewManager** | ✅ 已实现 | 持久相机 + SemanticPath 层级导航 + zoom_in/out |
| **6+ stub 未实现** | 🟡 改善 | ContentIndex/SubgraphCompiler 替代 3 个 stub，剩 3 个 |
| **四代代码并存** | 🔴 严重 | v3.0 (26K行) + v3.2 (8K行) + v4 (14K行) + legacy (30K行) |
| **测试环境** | ⚠️ 部分修复 | Python 3.14 venv 可跑 95 tests，discourse_models 问题仍存在 |
| **无基线对比** | 🟡 中等 | 无法回答"Context IR 是否比裸 prompt 更好" |

### 9.4 迭代路线

> 源自 `DESIGN_V4_CONTEXT_ENGINEERING.md` §8，结合当前实际状态调整

| Phase | 目标 | 验收标准 |
|-------|------|----------|
| Phase 0 | 端到端跑通 | `dialogmesh chat "你好"` 返回真实 LLM 回复 |
| Phase 1 | 上下文引擎生效 | 20轮对话 token ≤ 裸对话 60%，LLM-as-judge 评分 ≥ 裸对话 |
| Phase 2 | OpenClaw 对接 | OpenClaw + DialogMesh 完成代码任务，token 降 30%+ |
| Phase 3 | Multi-Layer Memory | Hot/Working → Engineering → Long-term 三层 + ColdIndexer 回升 |
| Phase 4 | 评估体系 | 信息密度、任务相关性、推理完整性、上下文浪费率 |

---

## 10. 后续文档导航

| 文档 | 内容 | 源头 |
|------|------|------|
| `DESIGN_01_COGNITIVE_PIPELINE.md` | 四路径调度 + Observation + Hypothesis + Knowledge + Skill | 6 篇合并 |
| `DESIGN_02_CONTEXT_AND_MEMORY.md` | Context Compiler + World Model + 持久化 + 工程链 | 7 篇合并 |
| `DESIGN_03_INPUT_AND_SKILL.md` | PCR + TieredParser + ActionResolver + Skill Layer + DIL | 5 篇合并 |
| `DESIGN_04_INTERFACE.md` | REST API + CLI + TUI + EventLog | 5 篇合并 |
| `ARCHIVE_INDEX.md` | ~70 篇历史文档归档索引 | — |

---

> 本文档是 DialogMesh 的设计总纲。每个核心概念在后续文档中有更详细的规格定义。
> 设计文档只写"做什么"和"为什么"，不写"怎么做"——"怎么做"看代码。
