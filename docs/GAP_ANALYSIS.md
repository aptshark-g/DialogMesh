# DialogMesh v6 — 设计 vs 落地 差距分析

> 2026-07-24 · 基于 ARCHITECTURE_CONDENSED.md 的 10 链体检表

---

## 一、每个相变的实际状态

```
                           设计状态          代码状态          接入状态
四对象:
  Entity                   ✅ DESIGN_SPEC §1   ✅ 多模块实现       ✅ 分散在各链
  Relation                 ✅ RelationSubstrate ✅ V3(LLM-native)   ⚠️ 部分接入
  State                    ✅ State Evolution  ✅ OCEAN/belief      ⚠️ 各自维护, 无统一对象
  Transition               ✅ 留痕信念         ✅ EventLog          ❌ 未作为一等公民使用

四相变:
  Observe (Entity→Observation)  ✅ 6域Projector  ✅ observation/    ❌ 未接入EventBus
  Interpret (Obs→Hypothesis)    ✅ HypothesisEng ✅ hypothesis/     ❌ 闲置
  Converge  (Hyp→Consensus)     ✅ 投票/衰减机制 ✅ belief_map      ✅ 桥接已接(空数据)
  Evolve    (Cons→Transition)   ✅ 回写+学习     ✅ dynamics        ✅ 桥接已接(空数据)
```

---

## 二、10 链条目状态

| 链 | 设计 | 代码 | 接入 | 缺口 |
|----|:---:|:---:|:---:|------|
| 00 PCR | ✅ | ✅ | ✅ | 无 Converge/Evolve—路由无状态, 合理 |
| 01 Discourse | ✅ | ✅ | ✅ | Segmenter+Cohesion+Tree 全通 |
| 02 Context | ✅ | ✅ | ❌ | context/(5,418L)+context_manager/(2,560L) 两套都没接 |
| 03 Intent | ✅ | ✅ | ⚠️ | MultiIntent已接, DualTrack+MultiPerspective闲置 |
| 04 MetaP | ✅ | ✅ | ✅ | EventLog+SHA256, 10链可写 |
| 05 Behavior | ✅ | ✅ | ⚠️ | 基础接, 发现/审核/吸收三阶段未闭环 |
| 06 Association | ✅ | ✅ | ⚠️ | L1-L4已接, L2(LLM-native)未替, L5因果闲置 |
| 07 Engineering | ✅ | ⚠️ | ❌ | 仅MCP桥接, ENGINEERING规格(7类节点+约束推理)完全未实现 |
| 08 Profile | ✅ | ✅ | 🔗 | 桥已接, OCEAN/BFI/Dynamics可用, 空数据 |
| 09 Meta | ✅ | ✅ | 🔗 | 桥已接, 7规则Trigger+MetaCognition可用, 空数据 |
| 10 Subgraph | ✅ | ✅ | ❌ | compiler代码存在(176L), 从未接入管线 |

符号: ✅ 完成 ⚠️ 部分 🔗 桥接好空跑 ❌ 未接入

---

## 三、按严重度分组

### A. 阻塞性的 — 不改就没法跑

```
EventBus 未接入
  → agent_native 走线性管线, 不是 10 链并行
  → 广播风暴风险 (36条push路径)
  → Decider 状态机设计存在, 代码 state/ 存在, 未替代 agent_native

Blueprint 未实现
  → 编排器没有调度能力
  → agent_native 硬编码了蓝图1 (固定流程)
  → 5种蓝图全未用
```

### B. 代码存在但闲置 — 改了就能跑

```
Context     两套 ~8,000L 从未调
Planner     7,908L, llm_planner 只用了66L
Observation 1,355L(23文件) 闲置
Hypothesis  742L 闲置
World       1,182L 闲置
ToolRegistry 3,442L 闲置
State       GlobalDecider+ExecutionTrace 闲置
Runtime     3,519L engine, 当前未用
CognitiveCompiler 1,444L 闲置
```

### C. 设计存在代码零 — 按蓝图建

```
ENGINEERING 27篇 22,800L — 完整施工蓝图
  优先级: DATA_MODEL(数据契约) → INTEGRATION(组件依赖) → COGNITIVE_COMPILER(认知编译)
```

### D. 设计完整, 做完了

```
Persistence     Rust+Python双轨, GC+LSM
L5 Memory       RAG+联邦索引+XML Cards
PCR V2          3D路由+LLM协同
MultiIntent     LLM-first拆分
L4 Temporal     T-BN+JS漂移
V4 Cognitive    13/13桥接加载
```

---

## 四、最快闭环路径

```
当前: 用户输入 → agent_native(线性管道) → LLM回答
                                 ↑ 只有PCR+Intent+L4+Behavior

最小闭环 (本周可完成):
  用户输入
    → agent_native 替换为 Decider(EventBus)
    → Context 接入 (二选一: context/ 或 context_manager/)
    → Subgraph コンパイラ接入
    → LLM 拿到编译后的子图上下文
    → Meta 异步读取 Transition
    → 下一次 Tick 的 Observe 参数被 Meta 修正

最小闭环只需接 3 个闲置模块: EventBus + Context + Subgraph
```
