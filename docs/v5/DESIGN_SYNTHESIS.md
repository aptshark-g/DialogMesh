# DialogMesh v6 — 设计全貌合成 (从13篇核心设计提取)

> 2026-07-24 · 读完: 10条BLINE链设计 + 3条v5专项设计 + HYBRID_ARCHITECTURE + INFO_THEORETIC_COMPRESSION

---

## 一、核心公式

```
Agent = 编排系统(Everything is Behavior)

不是: Agent = LLM + 上下文 + 工具  (这是LLM视角)
而是: Agent = 行为网络                    (这是系统视角)

每个操作 = 一次行为(Behavior)
  LLM → call(规则)    = 行为
  规则 → trigger(LLM)   = 行为
  用户 → edit(节点)     = 行为
  算法 → notify(LLM)    = 行为
```

## 二、10条链 × 双速通道

每条链独立消费事件、独立决策——不是线性管道。

| 链 | 快路径(<10ms) | 慢路径(LLM) | 决策门控 |
|----|--------------|-------------|----------|
| 00 PCR | 结构特征(S/V/O/问号数) | LLM分类 | conf<0.6→LLM |
| 01 对话树 | LCseg+BM25 | LLM块分割 | cohesion |
| 02 上下文 | DomainSelector+BudgetAllocator | LLM压缩 | token预算 |
| 03 意图 | Tier0结构+Tier1 BGE/SVO | Tier2 LLM few-shot | conf<0.6→LLM |
| 04 元认知持久 | EventLog追加 | Snapshot+Replay | — |
| 05 行为 | 贝叶斯+频率 | LLM推理 | conf 0.4-0.7→LLM |
| 06 关联 | L1句法+L1.5补全 | L2-L5 LLM | 每层可选LLM |
| 07 工程 | tree-sitter解析 | 约束推理 | 约束匹配 |
| 08 画像 | TrackA(动力学)+TrackB(标签) | LLM分析师 | 漂移>阈值→LLM |
| 09 元认知 | 规则触发器(7条) | LLM审查+回顾 | 冷却期控制 |
| 10 子图 | 对话树子图(窄深) | 元认知子图(宽浅) | 双视角 |

## 三、统一的共享数据层

所有链读同一数据池，不同视角解释：

```
共享数据层:
  对话树     ← 链01写入, 链02/03/05/06/10读取
  行为链     ← 链05写入, 链06/08/09/10读取
  关联链     ← 链06写入, 链03/05/09/10读取
  工程链     ← 链07写入, 链10读取
  用户画像   ← 链08写入, 链00/02/03/05读取
  元认知日志 ← 链09写入, 链08/10读取
  版本控制   ← 链09写入, 全部读取
```

## 四、蓝图系统——编排器的核心

```
蓝图 = 约束模板 (不是固定流程)

Blueprint {
  "max_llm_calls": 3,
  "min_confidence": 0.7,
  "hot_path_first": true,
  "allowed_callers": ["LLM", "user"],
  "fallback": "blueprint_3"
}

5种预定义蓝图:
  蓝图1: 规则直连 (0次LLM)       — 会员号查询、简单事实
  蓝图2: LLM+规则协同 (1次LLM)    — 意图分类、实体消歧
  蓝图3: LLM多步推理 (2-5次LLM)   — 复杂分解、多意图
  蓝图4: 联邦并行 (多次LLM并行)   — 跨域检索、多视角决策
  蓝图5: 用户交互 (LLM暂停)       — 歧义消解、关键决策
```

## 五、子图——跨链通信织物

```
子图 = 相同数据池 × 不同视角 × 不同预算分配

对话树子图 (生成回复):
  D域(对话):40% + B域(行为):15% + A域(关联):25% + P域(画像):10% + E域(工程):10%

元认知子图 (审核):
  M域(操作历史):15% + V域(版本diff):25% + E域(多链证据):30% + I域(惯性):15% + P域(画像):10% + Q域(问题):5%

子图编译器:
  compile_dialogue() → 对话视角 → LLM回复
  compile_meta()     → 元认知视角 → LLM审核
```

## 六、状态机——Decider模式

```
Command → Decider → Event → State → evolve → 下一Tick

不是: 链间直接push (广播风暴)
而是: Decider串行化 → Tick 1(PCR) → Tick 2(Intent) → Tick 3(Plan) → ...
```

## 七、信息论内核

```
温度(时间轴) ⟂ 距离(空间轴) ⟂ 信息价值(稀缺轴)

压缩 ≠ 聚类:
  聚类 ❌: BGE聚类→主题群→摘要 → 丢失因果推导链
  推导 ✅: 状态转移(a→b→c)→规则归纳→可逆推
  
同一信号, 不同约束 → 相反结论:
  卡尔曼滤波: 低概率=低权重 (追求准确性)
  信息论:     低概率=高价值 (追求信息量)
```

## 八、Agent-Native设计对标

| 范式 | 来源 | DialogMesh应用 |
|------|------|----------------|
| ReAct | Yao 2022 | 拆分→验证→修正循环 |
| Plan-Execute | Wang 2023 | 意图拆分=Plan阶段 |
| Reflexion | Shinn 2023 | 分歧→收敛=Reflexion |
| Multi-Agent Debate | Du 2023 | 5链=5个LLM视角 |
| Tool-Augmented | OpenAI/Anthropic | LLM是协调者,工具是执行者 |

## 九、新增发现 (从7篇补充设计)

### 9.1 多信号意图 (DESIGN_MULTI_SIGNAL_INTENT)
```
5路弱信号 → 贝叶斯融合:
  S1: SVO向量距离 (cos(S_vec, O_vec))
  S2: 主题峰度 (kurtosis)
  S3: 用户状态 (OCEAN+DMN)
  S4: 时间加权 (recency+习惯曲线)
  S5: 画像后验 (历史意图分布)

→ 替代当前单LLM意图分类
```

### 9.2 3D路由矩阵 (DESIGN_V3.2_ROUTING_MATRIX)
```
语义距离(X) × 句法复杂度(Y) × 用户偏置(Z)
  STC (Syntactic Terrain Complexity): nesting_depth + info_density + clauses
  替代当前PCR V2的纯nomic embedding X轴
```

### 9.3 NoiseSpan (DESIGN_NOISESPAN)
```
7种噪声类型 × char级标记:
  TYPO | AMBIGUOUS_ANAPHORA | JARGON_ABUSE | UNRELATED_FLUFF | 
  LOGICAL_LEAP | PROMPT_INJECTION | CONTEXT_BREAK
→ 替代全局 noise_level: float
```

### 9.4 Topic Tree 距离衰减 (DESIGN_TOPIC_TREE_GRANULARITY)
```
4层摘要: L1(near,200t) → L2(mid,100t) → L3(far,50t) → Lroot(global,30t)
effective_distance = tree_distance / max(1, heat)
```

### 9.5 TRACEABILITY 完整缺口
```
已吸收: 28个设计点 ✅
等效替代: 14个 ⚡
未实现: 17个 (Subgraph跨链, Engineering约束推理, TopicTree分支切换,
               Planner蒸馏, NoiseSpan, CognitiveCompiler, ObservationCompiler,
               HypothesisEngine, SemanticWorld, SkillLayer, ABC完整,
               Cold→Hot回写, DeepPath蒸馏, SoftConfig, Workspace,
               Observer, ExecutionTrace, PerspectivePlanner)
```

### 9.6 ALIGNMENT 验证——EventBus曾工作
```
EventBus: 13 subscribers, 0 dropped, 96/96 tests ✅
→ 证明冷路径(EventSourcing)设计可行
→ 但当前agent_native未接EventBus, 走了线性管线
```

## 十、设计 vs 实现差距总表

| 设计存在, 代码完备, 未接线 | 设计存在, 代码零 | 设计存在, 改为等效方案 |
|---------------------------|-----------------|---------------------|
| SubgraphCompiler(176L) | Subgraph跨链通信 | PCR离散→3D连续 |
| Engineering(812L) | Engineering约束推理 | Intent规则→LLM协同 |
| Planner(7,908L) | Planner蒸馏 | 关键词→结构特征 |
| cognitive_compiler(1,444L) | NoiseSpan | Emotion词表→BGE向量 |
| observation(1,355L) | TopicTree分支切换 | NRC-VAD→BGE优先 |
| hypothesis(742L) | TopicTree双层摘要 | |
| world(1,182L) | CognitiveWorkspace | |
| tool_registry(3,442L) | Observer | |
| state(914L) | ExecutionTrace | |
| runtime/engine(3,519L) | PerspectivePlanner | |
| ABC系统(480L) | Do-Calculus因果 | |
| service(3,680L) | Cold→Hot回写 | |
| context_manager(2,560L) | DeepPath蒸馏 | |

---

> 已读: 26篇设计 (10链 + AI Agent Book Ch3 + 7篇v5 + 2篇对齐核查 + 6篇v3.0)
> 待读: ~95篇 v3.0, 6篇 merge, ~80篇其他

---

## 十一、v3.0 设计文档新发现 (6篇刚读完)

### 11.1 Cognitive Runtime — OS类比

```
Observer = CPU (调度资源)
Workspace = Process (执行任务)
ExecutionTrace = strace (trace→replay→debug→meta-learn)
CognitiveScheduler = 优先级调度, 替代线性Pipeline
7种认知任务: PERCEIVE|RETRIEVE|EXPAND|REASON|REFLECT|VERIFY|COMMIT
```

### 11.2 Cognitive Workspace — 四空间模型

```
External World → Perceptual Space → Cognitive Space → Semantic Space → Action Space

核心洞见: "系统缺失的不是RAG/Context——而是LLM推理过程中无处可'想'的内部认知空间"
→ Cognitive Space 是 Hypothesis + Reasoning + Belief 的容器
```

### 11.3 Hypothesis Engine — 共识形成

```
不是"计算置信度", 是"共识形成":
  Multiple Interpretations → Vote → Decay → Resolve → Knowledge freeze

Belief Vector 7维: origin/trace/support/conflict/independence/stability/recency
冻结条件: belief_score > θ_freeze AND consensus_ratio > θ_consensus
```

### 11.4 Cognitive Scheduler — 调度与执行分离

```
三条线: Queue → Scheduler → Worker → Policy
Policy 决定: "哪个任务先跑, 跑多久, 以什么优先级"
当前问题: 6个模块各有自己的调度(HypothesisPipeline/DecayResolve/GraphTier/Distillation/…)
→ 互不感知, 无统一决策层
```

### 11.5 Competitor Absorption — 5竞品吸收

```
来源: MemWalker / Hermes-Agent / M-FLOW / MRAgent / VeritasGraph
吸收点:
  P0: 来源追溯独立层 (VeritasGraph+M-FLOW) — 每个结论标注source_events
  P0: 指代消解前置 (MRAgent) — 新能力
  P1: 冲突检测+版本追踪 — 设计存在,未独立
  P1: Pipeline Trace结构化输出 — 新能力
  P2: Cone Graph动态检索深度 — 设计可增强
  P2: 因果发现自动化管线 — 新能力
```

### 11.6 Graph Fallback — 大规模检索策略

```
Anchor-First, Graph-Second:
  Tier1: LSH bucket → Tier2: HNSW → Tier3: BFS → Tier4: BGE precise

已有代码未接入: lsh_index(114L) + hnsw_index(396L) + hybrid_index(196L) + faiss_store(205L)
→ O(N) → O(log N + k×branch^depth)
```

### 11.7 FULL_CONCEPT — 完整系统规格 (1,548L, 77KB)

```
设计哲学: "对话不是一问一答, 而是基于用户认知模型的持续推断与自适应"
四原则: 认知优先 / 正交解耦 / 渐进抽象 / 自适应演进

Layer 0-3架构 + 认知画像v2 + 记忆系统 + 可观测性 + 完整数据流生命周期
→ 这是整个DialogMesh的宪法级文档
```


## 十二、v3.0 设计文档 (第二批次, 6篇刚读完)

### 12.1 Design Overview (merge/DESIGN_00) — 10个核心洞察

```
Memory ≠ 文本, Memory = 类型化边 (Typed Edge)
知识 ≠ 概念节点, 知识 = 推理轨迹 (Reasoning Graph)
Context ≠ 全文拼接, Context = 子图编译 (Subgraph Compilation)
Semantic Object ≠ Node, Node = 世界的入口, 不是终点
Retrieval ≠ 找相关文本, Retrieval = 世界视图渲染 (World View)
```

### 12.2 Multilayer LLM Cognitive (1,077L, 63KB) — 认知双工

```
v2: 算法为主, LLM为仆 (主从式)
v3: 算法 = LLM的神经加速层 (认知双工)

双树架构:
  Discourse Tree (外部对话树) — 用户可见, 人机交互
  Cognitive Tree (LLM心智树) — 10种节点+8种边, LLM内部推理空间

三层LLM: 专业LLM(6实例) → 穿透LLM(回答) → 审视LLM(元认知)
```

### 12.3 Observation Compiler (629L, 23KB) — 投影层

```
不是Parser — 是投影层 (Projection Layer):
  Event IR (白光) → Observation Compiler (棱镜) → 多域Observation (光谱)

五层递进: Event → Normalize → Interpret → Project → Bundle
6个DomainAdapter: Dialogue/Engineering/Behavior/Document/User/Memory
```

### 12.4 Semantic World Model — 从RAG到世界运行时

```
范式转变: RAG(文本→Chunk→Embedding→Top-K) → World Runtime(构建世界→对象化→关系化→多尺度观察→编译)

LLM不直接面对信息碎片, 通过可缩放世界接口观察
Node ≠ Object — Node是子图入口
Context ≠ 拼接 — Context = 世界视图 (World View)
```

### 12.5 TieredActionResolver — 共享分类内核

```
所有分类场景共享同一内核: f(domain_context, input) → ranked_candidates
消费者: DialogueInterpreter / EngineeringInterpreter / BehaviorInterpreter 
       / IntentParser / NegativeKB / Projector
三级: Rule(fast) → Embedding(mid) → LLM(slow)
```

### 12.6 Unified Graph Store — 通用图持久化

```
替代 per-domain 存储: 一张 graph_nodes 表, domain-tagged
5域: T(Topic) / E(Engineering) / B(Behavior) / K(Knowledge) / P(Profile)
JVM GC分层: Hot/Warm/Cold/Archive, 自动迁移
```
