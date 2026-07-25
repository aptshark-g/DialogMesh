# DialogMesh — 粗颗粒模块架构设计

> 2026-07-24 · 230篇设计凝练后的模块重组 · 7大模块 × 3层部署

---

## 一、7 大模块 ≠ 10 条链

10 条链是设计文档的组织方式。糅合后 7 个粗颗粒模块：

```
10 链                    7 模块                   覆盖的相变

00 PCR          ──┐
01 Discourse     ─┤ 
03 Intent        ─┼── 1. Perception         Observe (原始→结构化)
                    │
02 Context       ──┤
10 Subgraph      ─┼── 2. Assembly            Interpret (多源→编译上下文)
                    │
06 Association  ──┐
05 Behavior      ─┤
07 Engineering   ─┼── 3. Cognition           Interpret + Converge
                    │                          (漏斗过滤→共识)
08 Profile       ──┤
04 MetaP + 09 Meta─┼── 4. Meta               Evolve (Transition→反思→回写)

持久化 + 记忆 + 联邦 ── 5. Memory             存储层 (Entity/Relation/State持久化)

蓝图 + 调度 + 编排   ── 6. Orchestration      调度层 (Blueprint选择+Decider串行)

用户 + 画像 + 模型   ── 7. Runtime            运行层 (API/LLMProvider/Config/Security)
```

---

## 二、模块详解

### 1. Perception — 感知

```
职责: Observe 相变。原始输入 → 结构化感知。

包含:
  PCR          — 结构特征(S/V/O/问号数/复杂度) → 坐标路由
  NoiseSpan    — 7种噪声类型 × char级标记
  Segmenter    — LCseg/TextTiling → EDUs
  MultiIntent  — LLM-first 多意图拆分
  DualTrack    — 热路径+冷路径双轨
  Entities     — 实体提取(jieba+nomic)

输入: 用户原始文本
输出: Route(zone,x,y,z) + EDUs + Intents + Entities + NoiseSpan
现有代码: ✅ PCR V2, MultiIntent, Segmenter, GrammarTagger
缺口: NoiseSpan(设计存在, 代码零), DualTrack(代码存在, 未接入)
```

### 2. Assembly — 组装

```
职责: Interpret 相变(后半段)。结构化感知 + 所有域数据 → 编译子图 → LLM上下文。

包含:
  ContextAssembler   — 6源读取 + 域选择 + 预算分配
  SubgraphCompiler   — 双视角编译(对话/元认知) + 六域令牌分配
  BudgetAllocator    — 三层预算 (domain/entity/turn)
  Pruner             — 4轮trim + 3步landing
  TopicTree          — 话题树 + 距离衰减摘要

输入: Perception输出 + Discourse + Behavior + Association + Profile
输出: 编译后的子图 (对话视角 + 元认知视角)
现有代码: ✅ context/(5,418L) + context_manager/(2,560L) + subgraph_compiler(176L)
缺口: 全未接入。二选一 context/ 或 context_manager/。
```

### 3. Cognition — 认知

```
职责: Interpret(前半段) + Converge 相变。假设生成→竞争→共识。

包含:
  RelationExtractor — LLM-native 关系提取 + 聚类归一化
  AssociationFunnel — L1(句法) → L1.5(补全) → L2(语义) → L2.5(信念) → L3(语用) → L4(时序)
  HypothesisEngine  — Match+Vote+Decay+Resolve → 7维Belief
  BehaviorPatterns  — 4层决策树 + ε-greedy + 自适应阈值
  EngineeringChain  — 约束推理 + 递归地图

输入: Assembly输出 + 历史数据
输出: Relations + Beliefs + Patterns + Constraints
现有代码: ✅ association/(L1-L4), behavior/(models+collab), llm_relation_extractor
缺口: HypothesisEngine闲置, Engineering约束推理未实现, L5因果闲置
```

### 4. Meta — 元认知

```
职责: Evolve 相变 + 冷路径微服务。

包含:
  MetaSubscriber    — 冷路径: 订阅8种事件, 每5 tick审核
  MetaCognition     — 审查优先级 + 回顾 + 自审
  CorrectionJournal — 用户修正日志 + 漂移检测
  DynamicsComputer  — 认知动态计算 (惯性/注意力/情绪/信任)
  VersionControl    — Git风格不可变日志
  AssocSubscriber   — 冷路径: 订阅6种事件, 异步关联发现

输入: Transition序列 (从EventLog读取)
输出: MetaDecision → 修正回写 (Intent重解析, Profile重新校准)
      Cold→Hot回写 (hidden_relation→Context, causal→LLM增强)
现有代码: ✅ meta_subscriber(63L), metacognition(328L), dynamics(172L)
缺口: agent_native不publish到EventLog → Subscriber收不到事件
```

### 5. Memory — 存储

```
职责: 数据核 (Entity/Relation/State/Transition) 的持久化。

包含:
  Persistence     — Rust+Python双轨, LSM Store, SHA256链, JVM-GC
  FederationIndex — 6源联邦锚点索引 (Rust+Python)
  RAG + Graph     — 向量锚点 + 2-hop图扩展
  XML Cards       — 6种记忆卡 (person/preference/fact/event/plan/heuristic)
  Compression     — P×I 信息论路由 (高频压缩, 低频高价值 RAG)

输入: 所有模块的读写请求
输出: 持久化的 Entity/Relation/State + 检索结果
现有代码: ✅ 全模块完成
缺口: 无
```

### 6. Orchestration — 编排

```
职责: 调度层。Blueprint选择 + Decider串行 + 模块调度。

包含:
  BlueprintSystem  — 5种预定义蓝图, 约束模板, 动态选择
  DeciderState     — Command→Event→State 三阶段, 防广播风暴
  CognitiveScheduler — 优先级调度, Queue→Scheduler→Worker→Policy
  Planner          — Skill生命周期 (蒸馏/匹配/执行/验证)
  ToolRegistry     — 工具注册/发现/权限/执行

输入: Perception输出 + 当前State
输出: 选中的Blueprint + 调度决策
现有代码: ✅ planner(7,908L), tool_registry(3,442L), state/(914L)
缺口: Blueprint系统代码零, agent_native未替换为Decider
```

### 7. Runtime — 运行

```
职责: 平台层。API + LLM Provider + 配置 + 安全。

包含:
  API              — REST(v4/v6) + WebSocket, 40+端点
  Gateway          — Go后端 (:8080), 9厂商Provider管理
  LLM Providers    — DeepSeek直连 + 6个专用LLM实例
  Config           — discourse/prompt/Runtime配置
  Security         — 输入消毒 + 幻觉检测 + 偏误检测 + SchemaGuard

输入: HTTP请求
输出: LLM响应
现有代码: ✅ api/, service/, llm_providers/, config/, security/
缺口: 6个LLM实例闲置(仅用DeepSeek)
```

---

## 三、7 模块之间的数据流

```
用户输入
    │
    ▼
┌──────────┐      ┌──────────┐      ┌──────────┐
│Perception│ ───→ │ Assembly │ ───→ │ LLM      │
│ Observe  │      │ Interpret│      │ Runtime  │
└────┬─────┘      └────┬─────┘      └──────────┘
     │                  │
     │          ┌───────┴───────┐
     │          ▼               ▼
     │   ┌──────────┐    ┌──────────┐
     │   │Cognition │    │  Memory  │
     │   │Interpret │    │ 存储/检索 │
     │   │ Converge │    └────┬─────┘
     │   └────┬─────┘         │
     │        │               │
     │        ▼               │
     │   ┌──────────┐         │
     │   │   Meta   │◄────────┘  ← Transition流
     │   │  Evolve  │
     │   └────┬─────┘
     │        │ 修正回写
     └────────┘

所有模块通过 EventLog → EventBus 连接 (冷路径异步)
编排层 (Orchestration) 调度所有模块的执行顺序
```

---

## 四、模块 vs 10链 映射表

| 模块 | 覆盖的链 | 模块角色 |
|------|---------|----------|
| Perception | 00, 01, 03 | 感知层: 原始→结构化 |
| Assembly | 02, 10 | 组装层: 编译子图→LLM上下文 |
| Cognition | 05, 06, 07, 08 | 认知层: 假设→共识 + 画像 |
| Meta | 04, 09 | 反思层: Transition→修正 |
| Memory | — | 存储层: 4对象持久化 |
| Orchestration | 1.5 | 调度层: Blueprint+Decider |
| Runtime | — | 平台层: API+LLM+Config |

---

## 五、实施路线

```
Phase 1: 先跑通端到端 (本周)
  Perception + Assembly → LLM回答
  仅需接: Context + Subgraph (代码已有)

Phase 2: 冷路径激活 (本周)
  agent_native 加 EventLog.append()
  Meta Subscriber 自动消费

Phase 3: 认知层接入 (下周)
  Cognition 模块: Association + Behavior + Hypothesis

Phase 4: 编排层 (下下周)
  Blueprint 系统 + Decider 替代 agent_native
```
