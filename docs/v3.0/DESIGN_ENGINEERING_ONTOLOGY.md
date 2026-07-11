# Engineering Ontology v1 — 工程本体定义

> 定义工程链中所有节点类型、来源分类、生命周期和边规则。
> 这是工程链的元层——它不存储数据，它定义数据可以是什么。

> 版本: v1.0 | 日期: 2026-07-10

---

## 目录

1. 为什么需要本体层
2. 节点类型定义
3. 来源分类（Source Classification）
4. 生命周期（Lifecycle State Machine）
5. 边规则（Edge Permission Matrix）
6. 白盒化设计：用户可修改的接口
7. 操作记忆与学习闭环
8. 与 Belief Update Engine 的统一

## 1. 为什么需要本体层

工程链定义了七类节点。但系统怎么知道 Every Provider needs Metrics
是 Constraint 而不是 Rule？Plugin Architecture 是 Pattern 而不是 Decision？

目前靠人判断。如果系统不知道类型之间的区别，它就不能：
自动分类候选知识，验证边是否合法，推测新知识类型。

本体层回答：什么类型的事物可以存在？怎么产生？怎么演化？怎么连接？

## 2. 节点类型定义

| 类型 | 回答的问题 | 关键判别属性 |
|:---|:---|:---|
| Constraint | 什么必须成立？ | 强制性。有 evidence 列表。违反会产生 AntiPattern 事件。 |
| Rule | 什么在什么前面？ | 顺序性。描述 pipeline 位置，不是依赖关系。 |
| Pattern | 怎么做这类东西？ | 可复用性。有 template 结构。从重复实例中蒸馏。 |
| AntiPattern | 什么绝对不能连？ | 禁止性。使用负边。有 correct_path。 |
| Decision | 为什么选这个？ | 追溯性。有 tradeoff + benefit + context。不可自动生成。 |
| QualityAttribute | 改这个代价多大？ | 量化性。每个关联模块有 impact_score。 |
| Module | 系统里有什么？ | 事实性。有 status。唯一可以直接注册/卸载的类型。 |
| Skill | 怎么做（缓存版）？ | 执行性。从 Pattern 蒸馏，可缓存可丢弃。 |

## 3. 来源分类

每个节点有 source 字段，决定初始置信度和升级路径：

| source | 含义 | 谁写入 | 初始 confidence | 可升级到 |
|:---|:---|:---|:---|:---|
| manual | 用户显式定义 | 用户通过接口添加 | 0.90 | verified (经使用验证) |
| derived | Analyzer 从数据中推断 | Engineering Analyzer | 0.40 | verified (经使用验证) |
| learned | LLM 从 Observations 中提取的候选 | LLM Hypothesis Generator | 0.30 | derived -> verified |
| verified | 经实际使用验证（至少 N 次匹配且无用户纠正） | Analyzer | 0.85 | core |
| core | 系统默认，不可删除 | 系统预置 | 1.00 | (不可变) |

只有 manual 和 core 可以直接进入 Graph。derived 和 learned 必须先进入 Hypothesis Pool。

## 4. 生命周期

不是所有节点类型都有生命周期。只有那些可以从数据中蒸馏的类型才有：

| 类型 | 有生命周期？ | 状态路径 |
|:---|:---|:---|
| Constraint | 是 | candidate -> derived -> verified -> deprecated |
| Pattern | 是 | candidate -> suggested -> verified -> deprecated |
| Skill | 是 | draft -> verified -> core -> deprecated |
| Rule | 是 | derived -> verified -> deprecated |
| Decision | 否 | 只有 manual 和 verified（不可自动生成） |
| QualityAttribute | 否 | 只随关联 Module 变化，无独立生命周期 |
| AntiPattern | 否 | 只 manual 和 core（禁止 LLM 自动创建 AntiPattern） |
| Module | 否 | 注册/卸载，无蒸馏路径 |

关键约束：LLM 不应拥有自动创建 AntiPattern 或 Decision 的能力。
这些需要人工判断——前者因为误判代价高，后者因为需要追溯性。

## 5. 边规则（Edge Permission Matrix）

不是所有节点对之间都能连边。本体层定义哪些连接合法：

| from / to | Module | Constraint | Pattern | Rule | Decision | Quality | AntiPattern | Skill |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| Module | depends_on | implements | implements | follows | NI | improves(NI) | violates | generated_by |
| Constraint | requires | NI | NI | NI | NI | NI | NI | NI |
| Pattern | derived_from | NI | extends | NI | NI | NI | NI | generates |
| Rule | NI | NI | NI | precedes | NI | NI | NI | NI |
| Decision | influences | justifies | NI | NI | supersedes | NI | NI | NI |
| Quality | NI | NI | NI | NI | NI | NI | NI | NI |
| AntiPattern | NI | NI | NI | NI | NI | NI | related_to | NI |
| Skill | NI | NI | instantiates | NI | NI | NI | NI | NI |

NI = Not Implemented (不允许连接)。

核心原则：
- Constraint 只能连接到 Module（检查谁满足/违反约束）
- Pattern 只能从 Module 有 implements 边，Pattern 之间可以 extends
- AntiPattern 只能从 Module 有 violates 边——禁止 LLM 创建 AntiPattern
- Decision 可以 justifies Constraint（解释约束的来源）

## 6. 白盒化：用户可修改的接口

工程本体不是写死的代码——它是一组可供用户查看、编辑、扩展的元数据。
这是整个 DialogMesh 系统中用户操作最频繁的层。

### 6.1 用户可修改的内容

| 可修改对象 | 操作 | 记录为 |
|:---|:---|:---|
| 边规则 | 添加新允许边类型 (如 Pattern->Decision 的 influences 边) | USER_EDIT |
| 生命周期状态 | 添加新状态 (如在 candidate 和 verified 之间加 challenged) | USER_EDIT |
| 节点类型 | 添加新类型 (如添加 Convention 类型) | USER_EDIT |
| source 分类 | 调整初始 confidence 值 | USER_EDIT |

### 6.2 修改接口设计

所有修改通过统一的 OntologyEditor 接口：

`
OntologyEditor.add_edge_rule(from=Pattern, to=Decision, edge_type=influences)
OntologyEditor.add_lifecycle_state(Constraint, challenged, before=verified)
OntologyEditor.add_node_type(Convention, discriminator=规范性约定)
OntologyEditor.set_source_confidence(learned, new_value=0.35)
`

每次修改产生一条 EngineeringChain Event (source=User)，进入 Event Log。
修改后的本体立即生效——不需要重启。

### 6.3 最小保护

核心本体（core 标记的 node types, edge rules, lifecycle states）不可删除，
不可降级。用户只能扩展核心本体，不能破坏它。

## 7. 操作记忆与学习闭环

用户修改本体的操作不是一次性的——进入系统学习管线：

USER_EDIT -> Event Log -> Observation Pool -> Engineering Analyzer -> 多次出现 -> Pattern detected -> 
候选本体升级: 新边从 user-defined 提升为 suggested。

操作记忆存储为 OntologyEditEvent：
turn_number, user_id, target(edge_rule/lifecycle/node_type/source_conf),
action(add/modify/remove), before, after, reason。

同一修改在多个会话中累积到阈值(默认3次)，系统主动提示提升。
本体从人定义演化到系统辅助定义——本体自己也在学习。

## 8. 与 Belief Update Engine 的统一

本体元素遵循 source + confidence 体系：

| 本体元素 | source | 初始 confidence | 升级路径 |
|:---|:---|:---|:---|
| 用户添加的边规则 | manual | 0.90 | N会话使用->verified |
| Analyzer发现的候选 | derived | 0.40 | 人工确认->manual |
| LLM建议的新类型 | learned | 0.20 | 人工审查->manual |
| 系统核心规则 | core | 1.00 | 不可变 |

复用 AdaptiveParameter 机制——锚点 + 区间 + reward_signal。

---

> 本体层定义了工程世界可以有什么，以及它们之间可以怎么连接。
> 它是工程链的宪法——不是条文本身，但决定了什么条文可以存在。

## 9. 三层架构：两张图

工程链内部其实混合了两类东西——把它们拆开：

`
Layer 1: Artifact Graph（工程对象图）
  节点: Artifact (Module, API, Config, Workflow, ...)
  边: depends_on, contains, references
  回答: 系统里有什么？它们怎么关联？

Layer 2: Knowledge Graph（工程知识图）
  节点: Constraint, Pattern, Decision, Quality, Skill
  边: requires, implements, improves, violates
  回答: 什么东西应该成立？什么东西不应该做？

Layer 3: Reasoning Engine（约束推理引擎）
  输入: Artifact Graph + Knowledge Graph + 用户操作
  输出: 受影响的约束、推荐的模式、检测到的违规
`

Context Compiler 的 E 域只需要查询 Reasoning Engine 的输出。
两张图的存储可以共用 PersistentGraph，但语义空间是分离的。

---

## 10. 开发顺序

依赖链路决定了实现顺序：

`
Ontology (类型定义)
  -> Artifact Type System (Provider/Middleware/Controller/...)
    -> Artifact Graph (注册/查询模块)
      -> Knowledge Graph (手动 Constraint + Pattern)
        -> Constraint Engine (类型匹配 + 禁止边)
          -> Context Compiler E域
            -> Pattern Distiller (Pattern自动蒸馏 — v4.5+)
              -> Skill Layer
`

第一批可实现的：Ontology + Type System + Artifact Graph + 手动 Knowledge Graph + Constraint Engine。
Pattern 蒸馏和 Skill 自动生成放到后续版本。

## 1.4 根问题：模块类型是谁定义的？

当前设计默认 Module 属于某个类型（Provider、Middleware、Controller...），
但系统怎么知道一个新模块是什么类型？如果系统不知道，
Every Provider needs Metrics 这条约束就找不到目标。

解决方案：不是让系统猜——是建立一个 Artifact 类型树 + 约束绑定到类型。

## 2.1 Artifact 类型树

Module 只是 Artifact 的一种。完整的工程对象层次：

`
Artifact
  Module
    Provider
    Middleware
    Controller
    Service
    Repository
    Tool
  Config
  API
  Pipeline
  Workflow
  Database
  Repository (VCS)
  Directory
`

类型之间的关系：
- Provider is_a Module is_a Artifact（继承）
- Middleware is_a Module is_a Artifact
- Constraint 绑定到类型，不绑定到个体

Constraint Every Provider needs Metrics 绑定到 ArtifactType=Provider，
不是绑定到 OpenAIProvider。任何 is_a Provider 的 Artifact 自动匹配此约束。

## 2.2 类型推断策略

模块注册时确定类型。三层 fallback：

1. 显式标注（优先）：注册时声明 artifact_type=Provider
2. 结构推断（fallback）：模块实现了 PluginPattern -> 推断为 Plugin 类型
3. LLM 推断（兜底）：从模块名和代码推断类型 -> Hypothesis Pool -> manual 确认

类型推断的结果有置信度，存储为 Module.type_confidence。

## 2.3 类型与约束的绑定

约束不再绑定到个体 Module，而是绑定到 ArtifactType：

`
Constraint: Every Provider needs Metrics
  binds_to: ArtifactType.Provider  # 不是个体，是类型
  evidence: [OpenAIProvider(v), ClaudeProvider(v)]

Constraint: Every Middleware must be before Auth
  binds_to: ArtifactType.Middleware
  applies_to_pipeline: Gateway
`

当新模块注册时，Constraint Engine：
1. 查模块的 ArtifactType
2. 查所有 binds_to 匹配的约束
3. 返回 applicable constraints -> Context Compiler E 域
