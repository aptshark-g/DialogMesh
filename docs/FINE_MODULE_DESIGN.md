# DialogMesh — 细颗粒模块设计 (完整版)

> 2026-07-24 · 7模块 × 相变映射 × 组件清单 × 数据流 × 交叉连接

---

## 一、Perception (感知模块)

### 1.1 组件清单 (7个子组件)

| 组件 | 代码 | 行数 | 状态 | 相变位置 |
|------|------|:---:|:---:|----------|
| **PCR Router** | pcr/ (29f, 10,415L) | ✅ | Observe: 结构特征→3D坐标 |
| **Grammar Tagger** | pcr/grammar_tagger.py | 146L | ✅ | Observe: Stanza S/V/O/NEG标记 |
| **NoiseSpan** | — | 0L | ❌ 仅设计 | Observe: 7种噪声×char级 |
| **Segmenter** | discourse_block_tree/segmenter.py | 85L | ✅ | Observe: EDUs切分 |
| **MultiIntent Splitter** | intent/multi_intent_splitter.py | 117L | ✅ | Observe: LLM-first拆分 |
| **DualTrack** | intent/dual_track.py | 155L | ✅ 未接入 | Observe: 热+冷双轨 |
| **MultiPerspective** | intent/multi_perspective.py | 210L | ✅ 未接入 | Interpret: 4视角DeepSeek |

### 1.2 内部数据流

```
用户文本
  │
  ├── PCR (结构特征) → Route(zone, x, y, z)
  ├── Grammar Tagger (S/V/O/NEG/...) → 语法标签
  ├── NoiseSpan (TYPO/AMBIGUOUS/INJECTION/...) → 噪声标记
  ├── Segmenter → EDUs (话语单元)
  ├── MultiIntent → [intent_1, intent_2, ...]
  ├── DualTrack → 热路径结果 + 冷路径候选
  └── MultiPerspective → 4个DeepSeek实例并发分析
        │
        ▼
    FusionContext (Perception汇总)
```

### 1.3 向 Assembly 输出

```
{
  route:        {zone, x, y, z},
  edus:         [EDU, ...],
  intents:      [{text, confidence}, ...],
  noise_spans:  [{type, start, end}, ...],
  grammar_tags: [{token, tag}, ...],
  perspectives: [{source, analysis, confidence}, ...]
}
```

### 1.4 交叉模块连接

- **→ Assembly**: 所有输出作为上下文编译的输入
- **→ Memory**: PCR route 作为 Transition 写入 EventLog
- **→ Orchestration**: Route 的复杂度 → Blueprint 选择依据
- **→ Meta**: MultiPerspective 分歧 → AmbiguityBridge → 信念桥接

### 1.5 现有代码缺口

- NoiseSpan: 设计完整 (DESIGN_NOISESPAN, 269L), 代码零
- DualTrack: 代码存在 (155L), 未接入
- MultiPerspective: 代码存在 (210L), 未接入

---

## 二、Assembly (组装模块)

### 2.1 组件清单 (6个子组件)

| 组件 | 代码 | 行数 | 状态 | 相变位置 |
|------|------|:---:|:---:|----------|
| **ContextAssembler** | context/assembler.py | 373L | ❌ 未接入 | Interpret: 6源聚合 |
| **SubgraphCompiler** | v4/cognitive/subgraph_compiler.py | 176L | ❌ 未接入 | Interpret: 双视角编译 |
| **BudgetAllocator** | context/budget_allocator.py | 217L | ❌ 未接入 | Interpret: 三层预算 |
| **Pruner** | context/pruner.py | 303L | ❌ 未接入 | Interpret: 溢出裁剪 |
| **TopicTree** | topic_tree/manager_v2.py | 1,091L | ❌ 未接入 | Observe→Interpret: 话题路由 |
| **DiscourseBlockTree** | discourse_block_tree/ (17f, 2,035L) | ✅ | Observe: 块生命周期管理 |

### 2.2 内部数据流

```
Perception输出 + 历史数据
  │
  ├── DiscourseBlockTree → 活跃块 + 祖先 + 摘要
  ├── TopicTree → 当前分支 + 距离衰减L1/L2/L3/Lroot
  ├── ContextAssembler → 6源读取 → CrossDomainContextIR
  │    源: Discourse + Topic + Behavior + Association + Profile + Engineering
  ├── BudgetAllocator → 三层预算分配
  │    domain级(60%) + entity级(25%) + turn级(15%)
  ├── SubgraphCompiler → compile_dialogue() + compile_meta()
  │    对话视角: D(40)+B(15)+A(25)+P(10)+E(10)
  │    元认知视角: M(15)+V(25)+E(30)+I(15)+P(10)+Q(5)
  └── Pruner → 4轮trim + 3步landing
       ▼
  CompiledSubgraph (注入LLM的最终上下文)
```

### 2.3 向 LLM (Runtime) 输出

```
{
  dialogue_subgraph: str,    // 对话视角 → LLM 回复生成
  meta_subgraph: str,        // 元认知视角 → Meta 审核
  token_usage: {total, budget, trimmed},
  sources: [{domain, entity_count, priority}, ...]
}
```

### 2.4 二选一决策

当前 **context/** (5,418L, 19文件) 和 **context_manager/** (2,560L, 5文件) 两套管线功能重叠。

| 维度 | context/ | context_manager/ |
|------|----------|------------------|
| 架构 | ContextSource抽象 + 多源聚合 | DiscourseManager + 语义索引 |
| 预算 | BudgetAllocator(三层) | 无独立预算 |
| 剪枝 | Pruner(4轮trim) | 无 |
| 加工 | CrossDomainContextIR | ContextLayer(系统注入) |
| 多源 | 6源(含SemanticWorld) | 3源(Disourse+Semantic+Conversation) |

**建议**: 选 context/ (功能更全, 有预算+剪枝), context_manager/ 的 DiscourseManager(1,988L) 可作 discourse_tree 的上游。

### 2.5 现有代码缺口

- 全部6个组件代码存在但未接入 — 这是最大 gap
- 需决定 context/ 还是 context_manager/

---

## 三、Cognition (认知模块)

### 3.1 组件清单 (7个子组件)

| 组件 | 代码 | 行数 | 状态 | 相变位置 |
|------|------|:---:|:---:|----------|
| **LLM RelationExtractor** | compiler/llm_relation_extractor.py | 203L | ✅ 未接入 | Interpret: 开放谓词+聚类 |
| **Association Funnel** | association/ (19f, 2,253L) | ✅ 部分接入 | Interpret: L1→L4漏斗 |
| **Belief Accumulator** | association/l2_5_belief.py | 285L | ✅ | Converge: 贝叶斯+7D |
| **L4 Temporal** | association/l4_temporal.py | 240L | ✅ | Converge: T-BN+JS漂移 |
| **Hypothesis Engine** | v4/ + hypothesis/ | 742L | ❌ 闲置 | Interpret→Converge: 投票+衰减 |
| **Behavior Model** | behavior/ (16f, 1,728L) | ✅ 部分接入 | Converge→Evolve: 自适应阈值 |
| **Engineering Chain** | engineering/ (15f, 812L) | ⚠️ 基础 | Interpret: 约束推理 |

### 3.2 内部数据流

```
Assembly输出 → 
  │
  ├── Relation Extractor (LLM-native)
  │     LLM提取开放谓词 → embedding聚类 → 归一化
  │     "validates_output_of" + "validates_integrity_of" → "validates" 族
  │
  ├── Association Funnel (5层)
  │     L1(句法) → L1.5(补全) → L2(语义) → L2.5(信念) → L3(语用) → L4(时序)
  │     每层: f(规则) ──conf不足──→ f(LLM)
  │
  ├── Belief Accumulator
  │     7维Belief: origin/trace/support/conflict/independence/stability/recency
  │     投票→锁定→结晶化
  │
  ├── Hypothesis Engine (闲置)
  │     Match→Vote→Decay→Resolve→Knowledge freeze
  │
  ├── Behavior Model
  │     4层决策树: conf>0.85(统计) → 0.4-0.7(LLM) → <0.3(询问用户)
  │     ε-greedy + EMA自适阈值
  │
  └── Engineering Chain
        tree-sitter解析 → 约束推理 → 反模式检测
```

### 3.3 向 Meta 输出

```
{
  relations: [{source, predicate, target, confidence, evidence}, ...],
  beliefs: {intent, 7d_vector, locked?},
  temporal: {predictions, drift},
  behaviors: {patterns, anomalies},
  constraints: {violations, anti_patterns}
}
```

### 3.4 现有代码缺口

- LLM RelationExtractor: 代码存在, L2未替换硬编码分类
- Hypothesis Engine: 完全闲置
- Engineering: 仅MCP桥接, 约束推理未实现
- Association L5(因果): 设计存在, 代码闲置

---

## 四、Meta (元认知模块)

### 4.1 组件清单 (5个子组件)

| 组件 | 代码 | 行数 | 状态 | 相变位置 |
|------|------|:---:|:---:|----------|
| **Meta Subscriber** | meta/meta_subscriber.py | 63L | ✅ | Evolve: 冷路径, 订阅8事件 |
| **MetaCognition** | v4/cognitive/metacognition.py | 328L | 🔗 | Evolve: 审查+回顾+自审 |
| **CorrectionJournal** | v4/cognitive/correction_journal.py | 156L | 🔗 | Evolve: 用户修正+漂移 |
| **Dynamics** | v4/cognitive/dynamics.py | 172L | 🔗 | Evolve: 惯性/注意力/情绪 |
| **VersionControl** | v4/cognitive/version_control.py | 202L | ❌ 未接入 | Evolve: Git不可变日志 |

### 4.2 内部数据流

```
├── 冷路径: EventBus订阅 → Meta Subscriber._on_event()
│     每5 tick扫描: 8种事件 → 权重分析
│
├── 热路径: MetacognitiveTrigger → MetaCognition
│     7条规则触发: error_rate/high_entropy/drift/...
│     submit() → scan() → retrospect() → self_audit()
│
├── CorrectionJournal: 用户每次修正 → record()
│     check_drift() → 漂移超过阈值 → 触发LLM review
│
├── Dynamics: tick() → compute_all()
│     cognitive_inertia + behavior_inertia + trust + emotion + attention
│
└── VersionControl: 所有修改 → commit() + snapshot
      diff() → rollback_to()
```

### 4.3 冷→热回写

```
Meta Subscriber 产出 → 
  │
  ├── META_REVIEWED   → Profile 重新校准 (drift → recalibrate)
  ├── ANOMALY_DETECTED → Intent 重解析 (anomaly → re-parse)
  └── CORRECTION       → 所有消费模块参数更新

Association Subscriber 产出 →
  ├── hidden_relation  → Context 追加
  ├── causal_chain     → LLM 推理增强
  └── temporal_pattern → Behavior 模式学习
```

### 4.4 现有代码缺口

- 桥接已接但空数据运行 (13/13模块加载, 方法对齐, 无生产数据)
- Meta Subscriber 代码完备, 缺 agent_native 的 EventLog.append()
- Cold→Hot 回写: 设计完整, 代码零

---

## 五、Memory (存储模块)

全模块完成 ✅ — 无需细颗粒展开。

- 6组件: Persistence(Rust+Python) + FederationIndex + RAG+Graph + XML Cards + Compression Router
- 全部已接入/可接入

---

## 六、Orchestration (编排模块)

### 6.1 组件清单 (5个子组件)

| 组件 | 代码 | 行数 | 状态 |
|------|------|:---:|:---:|
| **Blueprint System** | — | 0L | ❌ 仅设计 |
| **Decider/State** | state/ (6f, 914L) | ⚠️ 闲置 |
| **Planner** | planner/ (28f, 7,908L) | ⚠️ 仅 llm_planner(66L) |
| **CognitiveScheduler** | v4/cognitive_scheduler/ (9f, 1,659L) | ❌ 闲置 |
| **ToolRegistry** | tool_registry/ (10f, 3,442L) | ❌ 闲置 |

### 6.2 核心缺口

- Blueprint: 设计完整 (5种), 代码零 — **P0 缺口**
- Decider: 代码存在, 未替代 agent_native
- Planner: 完整系统 (7,908L), 只用了薄封装 (66L)

---

## 七、Runtime (运行模块)

全模块完成 ✅ — 无需细颗粒展开。

- API(40+端点) + Gateway(Go, :8080) + LLMProviders(DeepSeek+6实例) + Security + Config
- 缺口: 6个专用LLM实例闲置

---

## 八、交叉映射表 (粗→细, 模块间数据流)

| 产出模块 | 产出 | 消费模块 | 用途 |
|----------|------|----------|------|
| Perception | Route(zone,x,y,z) | Assembly | 域选择偏置 |
| Perception | EDUs | Assembly | 块组织 |
| Perception | Intents | Cognition | 意图→漏斗输入 |
| Perception | NoiseSpan | Assembly | 可信度加权 |
| Assembly | Subgraph(对话) | Runtime | LLM 回复上下文 |
| Assembly | Subgraph(元认知) | Meta | 审核上下文 |
| Cognition | Relations | Meta | 关联审核 |
| Cognition | Beliefs | Assembly | 信念偏置 |
| Cognition | Behaviors | Meta | 行为审核 |
| Meta | MetaDecision | Perception | 重解析/重校准 |
| Meta | Cold→Hot | Assembly | 隐藏关系/因果追加 |
| Memory | — | All | 读写接口 |
| Orchestration | Blueprint | All | 执行约束 |
