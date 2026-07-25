# DialogMesh — 架构凝练 (v6 Final)

> 2026-07-24 · 从 230 篇设计文档提取 · 宪法 + 体检表 + 地图

---

## 一、数据核：四对象

```
             结构轴                        时间轴
       (世界是类型化图)                (历史是事件流)

         Entity ──relation── Entity     State ──transition── State
           │                          │
           │                          │
       "现在是什么"                "曾经是什么、变成了什么"

图 = 现在的物化视图
日志 = 过去的不可变记录
两者互为推导：日志 replay → 重建图, 图 snapshot → 归档日志起点
```

| 对象 | 是什么 | 例子 |
|------|--------|------|
| **Entity** | 世界里的任何东西 | User, Document, Tool, Concept, Code, DiscourseBlock |
| **Relation** | Entity之间的类型化连接 | structural/behavioral/temporal/causal, 带 evidence 链 |
| **State** | 某个时间点的快照 | OCEAN 10维, belief 7维, confidence, heat, attention |
| **Transition** | State A → State B 的完整记录 | evidence + mechanism + confidence + timestamp |

**对照 DESIGN_SPECIFICATION 的四态模型**: Entity/Relation/State/Transition 是**存储视角**的结构。Information→Event→Observation→Knowledge 是**数据流视角**的四态。两套体系互补——前者描述"存什么"，后者描述"怎么流"。一句融合：`Observation = Entity + State 的快照`, `Knowledge = Relation + Transition 的凝结`。

---

## 二、计算核：四相变

```
一个认知 Tick:

  Observe             Interpret           Converge             Evolve
  ──────────────────► ──────────────────► ──────────────────► ──────────────────►
  Entity              Observation         Hypothesis           Consensus            Transition
  (原始世界)          (结构化感知)         (竞争解释)            (共识)               (新历史)

  每个相变内部 = 同一机制:
    f(规则, <10ms) ──conf不足──► f(嵌入, ~5ms) ──conf不足──► f(LLM, ~200ms)
```

| 相变 | 输入 → 输出 | 做什么 | 证据在哪 |
|------|-----------|--------|----------|
| **Observe** | Entity → Observation | 原始世界→结构化感知 (棱镜投影, 多域) | Observation Compiler §11.3 |
| **Interpret** | Observation → Hypothesis | 单视角→多解释竞争 (假设生成, 漏斗过滤) | Hypothesis Engine §11.3 |
| **Converge** | Hypothesis → Consensus | 多→一 (投票/衰减/冻结, 7维Belief) | Hypothesis Engine §11.3 |
| **Evolve** | Consensus → Transition | 知识→历史 (回写State, 追加Transition, 学习) | Cognitive Runtime §11.1 |

**Meta 闭环**: Evolve 产生的 Transition 被 Meta 异步读取 → 分析模式 → 修正下一次 Tick 的 Observe/Interpret 参数。

---

## 三、三条信念

### ① 留痕 — 一切行为皆 Transition

```
每个 Observe/Interpret/Converge/Evolve 调用 = 一次行为
每次行为 → 追加 Transition (不可变, SHA256链)
Meta 不分析 State — 只分析 Transition 序列

  例: Confidence 0.3 → 0.7 → 0.82
      重要的不是 0.82, 而是为什么从 0.3 变成 0.82
      Transition 记录了: evidence + mechanism + source
```

### ② 投影 — Context = 编译产物, 不是拼接

```
LLM 不直面数据池。只看编译出的视角:

  对话树子图 (生成回复):
    D域(对话):40% + B域(行为):15% + A域(关联):25% + P域(画像):10% + E域(工程):10%

  元认知子图 (审核):
    M域(操作):15% + V域(版本):25% + E域(证据):30% + I域(惯性):15% + P域(画像):10% + Q域(问题):5%

  Context = 相同数据池 × 不同视角 × 不同预算 = 子图
```

### ③ 多元化 — 蓝图调度 = 质量选择, 非成本约束

```
不是: "怎么少调LLM" (省钱)
而是: "怎么选择正确的蓝图" (质量)

5 种预定义蓝图, 编排器按需选择:
  蓝图1: 规则直连 (0次LLM)      — 确定性场景
  蓝图2: LLM+规则协同 (1次LLM)   — 分类/消歧
  蓝图3: LLM多步推理 (2-5次LLM)  — 复杂任务
  蓝图4: 联邦并行 (多次LLM)      — 跨域检索
  蓝图5: 用户交互 (LLM暂停)      — 歧义消解

选择权在编排系统, 不在成本函数。
```

---

## 四、体检表：10 链 × 4 相变 (空格即设计声明)

| 链 | Observe | Interpret | Converge | Evolve |
|----|---------|-----------|----------|--------|
| **00 PCR** | ✅ 结构特征 | ✅ 坐标路由 | — 路由无状态, 合理 | — 路由无状态 |
| **01 Discourse** | ✅ Segmenter | ✅ Cohesion量化 | ✅ 话题树分组 | ✅ 摘要回写 |
| **02 Context** | ✅ 多源读取 | ✅ 预算+裁剪 | ✅ 子图组装 | ⚠️ Context不持久化 |
| **03 Intent** | ✅ 原始文本 | ✅ Tier0→Tier2 | ✅ 5信号贝叶斯 | ✅ 分布回写画像 |
| **04 MetaP** | ✅ EventLog追加 | ✅ SHA256验证 | — 日志本身即共识 | ✅ Snapshot+Replay |
| **05 Behavior** | ✅ 行为边读取 | ✅ 贝叶斯→LLM | ✅ 发现+审核 | ✅ 自适应阈值 |
| **06 Association** | ✅ 句法依存 | ✅ L1→L5漏斗 | ✅ 信念累积 | ✅ L4时序+因果 |
| **07 Engineering** | ✅ tree-sitter解析 | ✅ 约束推理 | ⚠️ 约束匹配 | ⚠️ 约束演化 |
| **08 Profile** | ✅ OCEAN+BFI | — 信号直接进State | ✅ 多视角证实 | ✅ EMA聚合+惯性图 |
| **09 Meta** | ✅ Transition日志 | ✅ 权重分析 | ✅ 共识判定 | ✅ 修正回写 |
| **10 Subgraph** | ✅ 共享数据 | ✅ 双视角投影 | ✅ 六域预算 | ⚠️ 不独立持久化 |

符号: ✅ 已设计+已实现 | ⚠️ 已设计+代码存在+未接入 | — 声明不具备 (设计决策)

---

## 五、蓝图调度

```
编排器 (Orchestrator)
  │
  ├── 评估当前 State (用户画像/信念/上下文复杂度)
  ├── 选择 Blueprint (约束模板)
  │     Blueprint { max_llm_calls, min_confidence, hot_path_first, fallback }
  ├── 按 Blueprint 约束调度 4 相变
  │     每个相变内部: f(规则) → f(嵌入) → f(LLM), conf 不足时升级
  ├── Evolve: 回写 State + 追加 Transition
  └── Meta 异步读取 Transition → 修正参数
```

**关键**: 蓝图不是"固定流程"——是"约束模板"。LLM 在约束内自由操作。编排器不预设路径, 根据 State 动态选择蓝图。

---

## 六、地图：概念 → 设计文档出处

| 概念 | 出处 |
|------|------|
| 四对象 (Entity/Relation/State/Transition) | DESIGN_SPECIFICATION §1 + State Evolution §13.7 |
| 相变 (Observe/Interpret/Converge/Evolve) | Cognitive Pipeline §11.1 + Hypothesis Engine §11.3 |
| 投影/子图 | BUSINESS_CHAIN_10_SUBGRAPH + DESIGN_00_OVERVIEW §2.3 |
| 蓝图系统 | BUSINESS_CHAIN_1.5_PLANNING + DESIGN_FULL_CONCEPT §1.5 |
| 置信度门控 | 10 条 BUSINESS_CHAIN 每条双速通道 |
| 留痕/Transition | State Evolution §13.7 + ThOUGHT_IMPRINT |
| ENGINEERING 断层 | 27 篇 ENGINEERING_*.md, 全部标注"工程待实现" |
| 实现率量化 | IMPLEMENTATION_REALITY + COMPLETENESS_AUDIT + DESIGN_VS_IMPL_AUDIT |

---

## 附录：ENGINEERING 断层 (P0 清单)

```
27 篇 ENGINEERING 施工蓝图, 22,800 行, 全部"工程待实现":

  核心系统:
    ENGINEERING_DATA_MODEL (1,621L) — 全系统数据模型
    ENGINEERING_INTEGRATION (745L)   — 组件依赖/启动顺序/部署
    ENGINEERING_MULTILAYER_LLM (1,724L) — 认知双工架构

  编译器:
    ENGINEERING_COGNITIVE_COMPILER (995L) — 5 层认知模型
    ENGINEERING_COGNITIVE_PROFILE_V2 (2,034L) — 认知画像

  持久化:
    ENGINEERING_PERSISTENCE (1,320L) — 分层存储 (Hot/Warm/Cold)
    ENGINEERING_CONTEXT_MANAGER (879L) — 上下文管理
    ENGINEERING_TOOL_REGISTRY (1,216L) — 工具注册/发现/执行

  其余 19 篇:
    PCR/IntentParser/Planner/ServiceLayer/Observability/
    BehaviorGraph/BehaviorEmbedding/Predictor/Rewarder/
    Compiler/CausalSubstrate/FoA/L1Summary/DoCalculus/
    Fusion/NegativeKB/TopicTree
```
