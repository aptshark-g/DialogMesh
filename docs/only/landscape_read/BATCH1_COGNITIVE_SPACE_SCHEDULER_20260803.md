# 未对应设计文档批量精读 · 批 1 — 认知空间 / 认知系统 / 调度器

> 日期: 2026-08-03 | 批次: 1/8 | 状态: 已读完（6 文档全文精读）
> 定位: 把 DOCS_LANDSCAPE_MAPPING A 类真缺口按批读完，冲突只记录不拍板（哲学统一）。

---

## 1. DESIGN_COGNITIVE_WORKSPACE.md（v3.0, 310 行）— 四空间模型 / 认知工作区

**核心命题**: 系统缺失的不是 RAG/Context/子模块，而是让 LLM 推理时"有地方想"的
内部认知空间。

**四空间模型**:
```
Document Space（物理组织: 文件/代码/对话记录）
  → Concept Space（语义组织: SemanticObject / RelationSubstrate / SemanticPath）
  → Knowledge Space（冻结事实: Belief / Frozen Facts / Causal Rules）
  → Cognitive Space（当前思考: Perspective / Reasoning Tree / Reflection Queue / Hypothesis Pool）
前三个回答"知识如何组织"；第四个回答"推理时内部状态如何演化"。
```

**CognitiveWorkspace 数据结构**: current_perspective/horizon/attention（观察者状态）、
active_objects/relations（工作记忆）、reasoning_tree/candidate_answers（推理）、
hypotheses/conflicts（假设池）、confidence/pending_questions/reflection_log（自我监控）、
token_budget_remaining/reasoning_depth（预算）。

**生命周期**: 一次 LLM 推理 = 一个 Workspace 实例；PerspectivePlanner.plan → ObjectRuntime
→ RelationSubstrate → HypothesisEngine → LLM → MetaCognition.reflect → 可序列化到
Knowledge Space（冰冻）。Workspace 不替代其他空间，是"当前关注窗口"。

**四棵树的重新定义**（关键）:
```
Conversation Tree → Document Space（DiscourseBlockTree）
Topic Tree        → Concept Space（TopicTreeManager）
Semantic Tree     → Concept Space（ObjectRuntime.render）
Reasoning Tree    → Cognitive Space（MetaCognition.build_tree）  ← 新增归属
```

**解决 4 个 P1**: 元认知有反思对象 / ToT 有归属 / 因果链记认知因果（Observation→
Hypothesis→CounterEvidence→Revision→Belief）/ Meta Loop = Workspace 状态转换。

**冲突登记（暂不裁决）**:
- 与现有"对话树是树图/内存组块"哲学: 本文档把四树按空间归属切分，但对话树审计
  已确立"树图一体 + 组块抽象"。归属边界待哲学统一（子图/对话树/思考树三者的空间划分）。
- 与 LLM 认知层审计（cognitive_tree 65KB 已实现）: 本文档的 reasoning_tree 概念
  在 cognitive_tree 中已有实现，但"CognitiveWorkspace 容器"未实现 → 实现缺口。

---

## 2. DESIGN_COGNITIVE_SCHEDULER.md（v3.0, 441 行）— 认知调度器（Cognitive OS）

**定位**: 不是 Executor/Worker Pool；是决定"谁、什么时候、跑多久、以什么优先级"的
调度层。类比操作系统进程调度器。

**问题**: 各模块自管调度（HypothesisPipeline.start_background / DecayResolveEngine 周期
decay / GraphTierManager 周期 GC / DistillationEngine 按需 / MultiTierPipeline 内部级联）
互不感知，没有统一"现在应该先跑什么"的决策层。

**三条线**: Cognitive Scheduler（调度层: Policy/Queue/Dispatcher/Monitor/Advisor）→
Cognitive Pipeline（认知流水线: Event→Observation→Hypothesis→Knowledge→Skill）→
Context Engine（内容层）。

**Task 抽象**: 四类任务（ObservationTask Fast/Async 5-50ms / HypothesisTask Async/Slow
10-500ms / KnowledgeTask Slow/Deep 100ms-2s / SkillTask Deep 1-10s）。Worker 不知道
自己在跑什么，只执行 Task.execute()。

**Policy（快慢系统的归宿）**: MultiTierPipeline 是"执行层精度策略"，Policy 是"调度策略"
（负载/优先级）——两层互不干扰。SchedulerPolicy 接口: select_task/assign_worker/
should_delay/should_merge。

**冲突登记（暂不裁决）**:
- 与执行层审计 X 系列（双决策器并存 / StateMachine 半实现）: 本文档主张"调度器替代
  线性 StateMachine"，与 v5 DESIGN_GLOBAL_STATE_MACHINE 和 DECIDER 体系存在三套候选
  （GlobalDecider / DeciderStateMachine / CognitiveScheduler）。归一方向待哲学统一。
- 与蓝图 EventBus 体系: 调度器 + EventBus 的关系未定义（调度是编排的一种实现？）。

---

## 3. DESIGN_COGNITIVE_SYSTEM_V5.md / _CN.md（v3.0, 223 行 ×2）— 从检索系统到认知系统

**核心洞察**: v5 主张"模拟替代预测"。
```
v4 预测: 话题转移统计（需历史，冷启动无用）
v5 模拟: LLM 构造用户认知态，站在其中推理（心智理论，第一轮即可用）
  输出: "我会问 X、Y、Z，置信度 0.82"
  学习: 自监督（匹配→奖励 +0.09~0.15 / 未匹配→惩罚 -0.05）+ 元学习（学哪种模拟策略有效）
```

**模拟引擎循环**: 第 N 轮回答后构建用户认知态 → LLM 生成"用户最可能问的 3 个问题"+置信度
→ 第 N+1 轮 BGE 语义相似度评估（>0.6 部分匹配）→ 策略权重更新（模拟/话题转移/缺口填补）。

**认知轨迹（BehaviorGraph → ExecutionTrace）**: 行为图只记表面（Q1→A1→Q2→A2），
认知轨迹记录内部过程（观察/假设/拒绝/冲突/置信度演化），支持重放/半途重放/对比/元学习。

**关系图作为统一本体**: 三套关系系统（ConceptGraph 边 / RelationSubstrate 类型化边 /
CausalChain 因果边）→ 统一 Relation 模型（causal/contains/depends_on/defines/implements/
evolves_to/contradicts/analogous_to/uses）。核心洞察: **因果只是关系的一种**。

**四空间 → 认知本体**: 存在什么（SemanticObject）/ 如何关联（RelationGraph）/ 推理时如何
演化（Workspace+Runtime+Trace）/ 什么提交为长期知识（KnowledgeSpace）。

**冲突登记（暂不裁决）**:
- "模拟替代预测"与行为链预测器（predictor）现存实现的关系: 行为链审计已完成 DPO/预测，
  本文档的模拟引擎是另一条路线 → 并存 or 归一的裁决留给哲学层（行为链=记忆组块方向 vs
  v5=心智理论模拟方向）。
- 统一关系模型与关联链 L2.5/RelationSubstrate 现状: 关联链已实现分层漏斗，本文档主张
  平面统一本体 → 颗粒度哲学（分层 vs 平面）待统一。

---

## 4. DESIGN_COGNITIVE_RUNTIME.md（v3.0, 384 行）— 认知运行时 v2.0

**v1→v2 变化**: StateMachine → CognitiveScheduler / Stack → WorkspaceGraph / +ExecutionTrace
/ +OS 类比。前置 = COGNITIVE_WORKSPACE。

**CognitiveTask**: 7 类（LOAD/PERCEIVE/RETRIEVE/EXPAND/REASON/REFLECT/VERIFY/COMMIT/
DESTROY），priority 0-1，dependency 列表，reason 字段（可追踪）。

**CognitiveScheduler.next()**: 由 workspace 状态驱动生成任务（非固定 A→B→C→D）:
```
ws.state==INIT → LOAD / LOADED → PERCEIVE
confidence<0.3 → RETRIEVE（无关系）or EXPAND（需深挖）
单假设 → EXPAND（需替代）
无 reasoning_tree → REASON / 无反思 → REFLECT
confidence>0.7 且有多假设 → COMMIT
```

**WorkspaceGraph**（替代 Stack）: 有向图，支持递归 + 并行；can_merge 依赖检查 +
merge_results 子假设合并（加权/vote/concat）。Stack 只是单 child 特例。

**OS 类比**: Observer=CPU（唯一实例）/ Workspace=Process / WorkspaceGraph=Address Space /
Scheduler=OS Scheduler / Context Switch=切 perspective / Syscall=Commit to Knowledge /
Core Dump=ExecutionTrace / fork=push_workspace / wait=merge_results。

**ExecutionTrace**: TraceStep（state/observer_snapshot/workspace_snapshot/decision/
llm_input_tokens/llm_output/latency/parent_step）；三个用途: replay 验证一致性 /
debug_path 回溯诊断 / 多 session 聚合元学习。

**实现计划**: R1-R6 共 ~360 行，0 接口破坏（Observer+Workspace+Graph / Task+Scheduler /
Trace / Commit Protocol / 现有模块接入 / run() 主循环包 engine.on_event）。

**冲突登记（暂不裁决）**:
- Observer"永远只有一个实例"vs 蓝图多 agent/联邦/并行设计 → 单 Observer 是否成为瓶颈。
- 与 v4 simulation_engine.py（已实现）的关系: v4/cognitive/simulation_engine 已存在，
  本文档是更完整的运行时蓝图 → 实现缺口（simulation_engine 103 行壳 vs 设计 360 行）。

---

## 5. DESIGN_MULTI_TIER_PIPELINE.md（v3.0, 281 行）— 算力-精度可编排谱系

**核心命题**: 不是快/慢二元，是多层递进——用可配置算力预算换递增精度；每层输出作为
下一层种子输入，每层修正回流前层。

**谱系**: L0 缓存/索引(0ms,~70%) → L1 符号规则(<5ms,~85%) → L2 统计模型(~30ms,~92%)
→ L3 小模型(~200ms,~95%) → L4 大模型(~500ms,~98%) → L5 人工(100%)。
每个模块可选 Tier 组合（TieredParser L1+L2+L4 / CodeContextGraph L0+L2+L4 / NegativeKB L1+L3）。

**Pipeline 编排**: 逐层执行，confidence >= tier.threshold 则返回；否则 context 携带前层
hint 传给下层（下层不从零开始）。

**UpgradePolicy**: ThresholdBased（默认）/ AdaptiveThreshold（按 correction_rate 动态调整）
/ BudgetAware（按剩余预算）。可自定义联合条件。

**FeedbackLoop**（快慢系统最缺的一环）: Tier N+1 纠正 Tier N → record_correction →
apply 写回 Tier N 本地规则/缓存 → correction_count++ → correction_rate 超阈值触发规则
更新 + 生成 Observation（pattern_detected=systematic_errors）。

**全系统映射建议**: TieredParser / CodeContextGraph / BehaviorGraph 更新 / CausalSubstrate /
UserProfile 更新 / NegativeKB / IntentParser 七模块适合套用。

**冲突登记（暂不裁决）**:
- 与 tiered/ 包现状: 审计已确认 tiered 活跃（discourse_block_tree A 路径 + extraction_blueprint
  + runtime p3），但本文档主张的"通用 Pipeline + FeedbackLoop 闭环"未落地 → 半实现。
- 与 A16 快慢通道 / 蓝图编排: 本文档是"模块内谱系"，蓝图是"模块间编排"——两层关系
  与 COGNITIVE_SCHEDULER 的"精度策略 vs 调度策略"划分一致 → 待统一为编排哲学。

---

## 批 1 汇总（冲突登记清单，待哲学统一）

| # | 冲突点 | 涉及文档/审计 |
|---|--------|--------------|
| B1-1 | 四树空间归属（conversation/topic/semantic/reasoning）vs 树图一体哲学 | WORKSPACE vs 对话树审计 |
| B1-2 | 三套调度候选（GlobalDecider/DeciderStateMachine/CognitiveScheduler）归一 | SCHEDULER vs 执行层 X 系列 |
| B1-3 | 调度器 vs EventBus（编排实现关系）| SCHEDULER vs 蓝图审计 |
| B1-4 | 模拟引擎（心智理论）vs 行为链预测器（统计+DPO）| V5 vs 行为链审计 |
| B1-5 | 统一关系本体 vs 关联链分层漏斗 | V5 vs 关联链审计 |
| B1-6 | 单 Observer 实例 vs 多 agent/联邦 | RUNTIME vs 蓝图 |
| B1-7 | 模块内谱系（MultiTier）vs 模块间编排（蓝图）| MULTI_TIER vs 蓝图 |
| B1-8 | CognitiveWorkspace 容器未实现（设计存在，实现缺）| WORKSPACE vs LLM 认知层审计 |

