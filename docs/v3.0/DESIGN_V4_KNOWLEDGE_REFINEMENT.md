# DialogMesh v4: 知识精炼与信念维护

> 定义 Observation Pool, Knowledge Refinement, Hypothesis Pool, Belief Update Engine, Skill Layer 五层架构。
> 回答 V4 的核心问题：知识不是输入时产生的，而是在系统不断解释观察事实的过程中逐渐形成的。

> 版本: v1.0 | 日期: 2026-07-10

---

## 目录

1. 架构总览：五层替代三层
2. Event IR：统一事件中间表示
3. Observation Pool：快速写入，暂不解释
4. Knowledge Refinement：多解析器竞争解释
5. Hypothesis Pool：贝叶斯信念更新
6. Belief Update Engine：增量真值维护
7. Skill Layer：经验蒸馏
8. 设计原则
9. 与现有模块的关系

## 1. 架构总览：五层替代三层

### 1.1 之前的假设

v4 初始设计隐含了一个假设：知识在输入时产生。
Event IR -> Knowledge Layer -> Context Compiler -> LLM。

这个假设的问题：不是所有信息都能立即分类。用户说工程越来越复杂，
它既是工程链的、也是行为链的、也是用户画像的——没有唯一归属。

### 1.2 新的五层架构

`
用户输入
  |
Event IR（统一事件中间层，不持久化）
  |
Observation Pool（观察池，快速写入，暂不解释）
  |  （异步）
Knowledge Refinement（多解析器竞争解释）
  |
Hypothesis Pool（候选假设竞争池，贝叶斯信念更新）
  |
Persistent Knowledge（最终持久化）
  |
Skill Layer（蒸馏出的长期经验模板）
`

| 层 | 职责 | 时间尺度 | 速度要求 |
|:---|:---|:---|:---|
| Event IR | 统一表达交互，动态 payload | 实时 | 极快 |
| Observation Pool | 暂存原始观察，不分类 | 实时写入 | 快 |
| Knowledge Refinement | 多个 Analyzer 竞争解释 | 后台异步 | 可慢 |
| Hypothesis Pool | 贝叶斯迭代逼近真相 | 持续更新 | 慢 |
| Skill Layer | 蒸馏长期经验 | 月/季度 | 不紧急 |

## 2. Event IR：统一事件中间表示

### 2.1 定位

Event IR 是系统的中间语言，不是数据库。类比 LLVM IR：
C++/Rust -> LLVM IR -> ARM/x86，IR 不会被拿去当数据库用。

它只负责表达发生了什么和涉及了什么。知识属于领域模型。

### 2.2 数据结构

固定字段极简，payload 完全动态：

`
Event {
  id: UUID
  kind: dialog.message | ui.drag | config.change | api.call
  payload: dict   # 完全动态，不预设 schema
  refs: { conversation_id, user_id, engineering_node, ... }
  metadata: { time, confidence, source }
}
`

kind 固定几个大类，payload 完全开放——因为 LLM 天然动态。
今天 payload 里有 requirement，明天可能有 ui_layout，后天可能有 emotion。
不限制。

### 2.3 Vocabulary 替代 Schema

不预设标签体系。维护一个可成长的 Vocabulary：

- Core Vocabulary: constraint, monitor, dependency, intent, emotion（稳定标签）
- Candidate Vocabulary: risk_level, hesitation（LLM 新创建的标签，待人工批准）
- Unknown Tag Pool: 临时存放，不被任何 Analyzer 消费，等待未来升级

LLM 产生新标签 -> 进入 Candidate -> 人工批准或自动批准(高频+高置信) -> 加入 Core。
系统可以成长，而不是一开始被 schema 锁死。

## 3. Observation Pool：快速写入，暂不解释

### 3.1 为什么需要

核心矛盾：不是所有信息都能立即分类。用户说最近这个项目越来越顺手了——
工程链、行为链、用户画像都可以从中提取信息，但没有唯一归属。

如果要求每条输入必须立刻决定属于哪条链，系统马上就僵住了。

### 3.2 设计

Observation 就是原始事件日志。先存，不急着解释。

`
Observation {
  id: UUID
  event_id: UUID       # 来源 Event
  raw_text: str         # 原始内容
  parsed_intent: str    # 快速解析（几十毫秒完成）
  status: raw | quick_parsed | deep_parsed
  consumer_marks: {     # 记录哪些 Analyzer 已经消费过
    behavior: claimed
    engineering: unclaimed
    emotion: claimed
  }
}
`

### 3.3 两条流水线

快速回复：Observation -> 直接参与上下文 -> 回复用户（不等精炼完成）
后台精炼：Observation -> 多个 Analyzer 慢慢消费 -> 产生 Hypothesis

这是 Pull 不是 Push。没有中央调度器决定这条信息属于谁。
Behavior Analyzer 自己来挑，Engineering Analyzer 自己来挑。
同一条 Observation 可以被多个 Analyzer 同时消费——类似 Kafka 的多 Consumer。

### 3.4 Observation 永远不删

因为 Analyzer 会升级。今天的 Analyzer 只能识别行为，明天的 LLM 突然能识别价值观。
如果 Observation 被删了，永远没机会重新解释。

## 4. Knowledge Refinement：多解析器竞争解释

### 4.1 不是分类，是竞争解释权

传统的想法：Dispatcher 决定一条信息属于哪个领域模型。

新的想法：多个 Analyzer 同时消费同一条 Observation，各自生成解释（Hypothesis），
互相竞争置信度。没有一个先验的正确分类。

### 4.2 角色分工

| 角色 | 职责 | 工具 |
|:---|:---|:---|
| LLM (Hypothesis Generator) | 生成候选解释，提出可能性 | 自然语言理解 |
| Rule Engine + Statistics | 积累证据，更新置信度 | 规则/统计/图传播 |
| Knowledge Engine | 决定什么时候置信度够高，可以提升为 Knowledge | 阈值判定 |

LLM 只出现在 Hypothesis 生成阶段。后续几千、几万次信念更新全是算法。
这不是让 LLM 做全部——是把 LLM 放在概率图模型的前端。

### 4.3 流程

`
Observation -> LLM: 生成候选解释
   H1: 学习能力提高 (confidence=0.42)
   H2: 任务变简单 (confidence=0.31)
   H3: AI 参与更多 (confidence=0.27)
       |
新 Observation -> Evidence Accumulator: 更新置信度
   用户开始解释底层架构 -> H1 confidence: 0.42 -> 0.71
   用户开始提出优化方案 -> H1 confidence: 0.71 -> 0.91
       |
超过阈值(0.85) -> 提升为 Knowledge -> 写入 Persistent Graph
`

## 5. Hypothesis Pool：贝叶斯信念更新

### 5.1 为什么需要 Hypothesis

Observation 不能直接推出 Knowledge。Observation 只是证据，真实状态是 Hidden Variable。

Observation: 修改速度提高。可能的解释：能力提高、任务简单、AI 参与更多、状态好。
所有这些都解释得通。直接挑一个是危险的。

### 5.2 Hypothesis 数据结构

`
Hypothesis {
  id: UUID
  statement: str
  confidence: float       # 当前置信度 0-1
  supporting_evidence: [EventID]
  counter_evidence: [EventID]
  generated_by: analyzer_name
  last_updated: timestamp
  tier: hot | warm | cold | archive
}
`

### 5.3 证据积累（纯算法，不用 LLM）

每次新 Observation 到达 -> 检查受影响 Hypothesis -> 更新置信度。

支持证据权重：每条支持性 Observation 按证据强度加分。
反驳证据权重：每条反驳性 Observation 减分。
时间衰减：长时间无新证据 -> confidence 自然下降。

### 5.4 冷却分层

| 层 | 时间范围 | 更新频率 | 存储数量 |
|:---|:---|:---|:---|
| Hot | 最近 1 天 | 每次 Observation | ~1000 |
| Warm | 最近 1 月 | 每小时一批 | ~5000 |
| Cold | 半年以内 | 每周一批 | ~100000 |
| Archive | 半年以上 | 基本冻结 | 无限 |

## 6. Belief Update Engine：增量真值维护

### 6.1 核心问题

如果每来一条新 Observation 就全局重算所有 Hypothesis，
一年后 Observation 百万条、Hypothesis 几十万条，复杂度必然爆炸。

### 6.2 解法：影响变更集

借鉴 Git 的思路：只重新计算受影响的 Hypothesis，不是全部重算。

`
Observation -> Change Set（影响图）
  只影响: Engineering, Behavior, Project
  不影响: Emotion, Preference, Skill
       |
沿影响边传播（Graph Propagation）
  只更新受影响节点的置信度
`

### 6.3 理论基础

Truth Maintenance System (TMS): 维护依赖图。一个事实变了，只重新推导依赖它的结论。
Incremental View Maintenance: 数据库新增一行，不重新扫 100GB，只更新受影响的行。
Belief Propagation: 概率图模型中沿边传播置信度更新。

### 6.4 分层更新策略

| 层 | 更新策略 |
|:---|:---|
| Hot | 实时全量传播 |
| Warm | 批量传播 |
| Cold | 仅节点自身衰减 |
| Archive | 不解冻（除非重大新证据） |

## 7. Skill Layer：经验蒸馏

### 7.1 定位

Skill 不是手工写的 prompt，是从 Observation 中蒸馏出的稳定经验模板。

类比：AlphaGo 不保存 100 万盘棋，保存的是 Policy。

Observation 每天变，Knowledge 每周变，Skill 每月变一次。

### 7.2 Skill 数据结构

`
Skill {
  name: str
  prerequisite: [node_types]
  preferred_order: [step_types]
  required_constraints: [constraint_rules]
  common_failures: [failure_patterns]
  references: [related_skills, parent_project_patterns]
  lifecycle: draft | verified | core | deprecated
  confidence: float
  usage_count: int
  success_rate: float
}
`

### 7.3 Adaptive Skill

同一个 Gateway Skill，对不同用户、不同项目，动态重组：

新用户: 通用 Gateway 模板。
资深用户: 自动加入监控、热更新、测试链路（基于行为链学到）。

Skill = 通用经验 x 用户画像 x 当前工程上下文。

### 7.4 生命周期

Draft (30%) -> Verified (10次使用, 95%成功率) -> Core (系统默认启用) -> Deprecated (技术过时)

## 8. 设计原则

1. IR 不应承载知识，只应承载事件。知识属于领域模型，IR 是知识流动的语言。

2. 知识不是输入时产生的。用户在输入时产生的只是观察事实。
   真正的知识是多个 Analyzer 在不同时间赋予这些事实意义的结果。

3. 持久化事实 + 可重复解释机制，而非一次性结论。
   Observation 永远不删——未来的分析器可能发现今天分析器看不到的东西。

4. 不是分类，是竞争解释权。没有先验的正确分类。
   多个 Analyzer 对同一 Observation 的解释都可以成立。

5. LLM 生成假设，算法积累证据。LLM 只在 Hypothesis Generation 阶段调用。
   后续信念更新全是纯算法。

6. 增量计算，不是全量重算。借鉴 Git/TMS/增量视图维护的思想。

7. Vocabulary 成长，而非 Schema 锁定。标签体系随时间演化。

8. Observation -> Knowledge -> Skill -> Planning -> Execution。
   从具体到抽象，五层递进蒸馏。

## 9. 与现有模块的关系

| v4 新模块 | 依赖的现有模块 | 新增代码估计 |
|:---|:---|:---|
| Event IR | 无（新基础设施） | ~150 行 |
| Observation Pool | Event IR, session_recorder | ~200 行 |
| Knowledge Refinement | BehaviorGraph, CausalSubstrate, EngineeringGraph | ~300 行 |
| Hypothesis Pool | Knowledge Layer (PersistentGraph) | ~250 行 |
| Belief Update Engine | ColdIndexer（冷却分层复用）, AdaptiveParameter | ~300 行 |
| Skill Layer | Consolidation, ColdIndexer | ~250 行 |

总计估计: ~1,450 行新增代码，分布在 6 个新模块。

---

> 这份设计定义了 DialogMesh v4 的知识精炼与信念维护体系。
> 核心转变：从信息分类系统转变为持续生成、竞争、验证解释的系统。
> 知识不是输入时产生的，而是在不断解释观察事实的过程中逐渐形成的。
