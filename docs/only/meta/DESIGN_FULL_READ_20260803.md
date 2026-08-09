# 元认知设计文档全面精读（第二轮）

> 日期: 2026-08-03 | 精读对象（2 篇，754 行）:
> `docs/BUSINESS_CHAIN_09_METACOGNITION.md`（业务链第九章，309 行）+
> `docs/DESIGN_METACOGNITION_RUNTIME.md`（运行时元认知 Workflow Graph Loop，445 行）
> 配套: `AUDIT_ENTRY_20260803.md`（一轮盘点）+ `DEEP_AUDIT_20260803.md`（实锤验证）
> 本文档 = 设计全貌凝练 + 设计↔代码对照 + 待讨论点。

---

## 一、设计全貌（两份文档合并凝练）

### 1.1 定位（业务链第九章）

```
元认知 = 第二大脑。第一大脑 = 算法+业务（对话树/行为链/关联链/工程链/画像）。
第二大脑 = 反思、审核、回溯。
核心机制:
  ① Git 式不可变版本控制（所有可修改数据 commit 化，可回滚/可追溯/可审计）
  ② 审核队列（被动接收各链推送 + 主动拉取扫描）
  ③ 复盘引擎（修改前后运行数据对比 → verdict/recommendation）
  ④ 自我复盘（元认知审计自己的操作历史 → 调审核阈值）
  ⑤ 双模式决策（紧急收敛 <5s / 从容多视角跨 Slow Path）
  ⑥ 预留外部能力（web_search/env_validate/literature/data_query/code_execute）
```

### 1.2 版本控制覆盖范围（设计 §2.2）

```
对话树节点 / 关联链边权重 / 工程链约束 / 画像 OCEAN / 参数注册表 /
ABC 规则 / 惯性模式 / 元认知自身决策 —— 全部 per-entity 版本化
VersionedState = {commit_id, parent_id, timestamp, author, operation,
                  target, before, after, diff, reason, verification}
```

### 1.3 审核队列（设计 §3）

```
被动推送: 行为链候选模式 / 关联链 L1.5 冲突 / 画像漂移 / 工程链新约束 / 参数自适应
主动拉取（每 Slow Path checkpoint 5 轮）: 低置信度边(conf<0.4) / 长期未触发预测(7天) /
  违反约束模块 / stale 标注 / 久未验证惯性模式(>30轮)
优先级: 紧急(风险操作/用户修正/漂移>0.25/断路器OPEN) vs 从容(候选/低置信度/参数/衰减)
```

### 1.4 复盘引擎（设计 §4）

```
复盘 = 修改前 N 轮指标 × 修改后 N 轮指标 × diff
输出 RetrospectionReport: {target, change, metrics_before/after, delta,
  verdict(effective/neutral/harmful/inconclusive), confidence,
  recommendation(keep/rollback/adjust/investigate), rollback_id}
```

### 1.5 自我复盘（设计 §5）

```
每 Slow Path: 检查自己最近 N 条决策的 accuracy / user_override_rate / side_effect_rate
accuracy<0.7 → 更保守 + 分析原因；user_override_rate>0.3 → 调整审核标准
```

### 1.6 双模式决策（设计 §6）

```
紧急收敛（风险/修正/漂移>0.25/断路器）: 单次 LLM <5s → 立即执行 → 标记 rapid_decision 事后审查
从容多视角（候选/低置信度/参数）: 多视角证据（设计/工程/行为/对话 4 视角）→
  多轮 LLM 迭代（独立分析→交叉验证→综合判定）→ 歧义给用户（凝练问题+选项）→ 不回复则 pending
```

### 1.7 运行时双环结构（DESIGN_METACOGNITION_RUNTIME）

```
小环（热路径, 节点内）: Think → Act → SelfCheck → Correct → Retry（≤3 次）
  修正对象 = 当前节点产出（先验: 大多数错误局部性）
  Correct 手段: 参数调整 / 上下文扩展 / 温度降低 / 策略切换
  复用 ReActRetryEngine 5 策略（AUTO_FIX/TEMPERATURE_DROP/EXPAND_CONTEXT/SPAWN_DETECTOR/ESCALATE）

大环（冷路径, MetaTree 5 tick 审计）:
  归档节点审计（跨树冲突/下游失败溯源/用户后行为暗示/长期失败模式）
  回档流程: ARCHIVED→REOPENED → 上下文重载 → 修正提示 → 重入小环 → 新版本归档(X_v1→X_v2)
  Transition 记录（高价值低概率）→ L5 Memory → 所有模块学习

逆向因果追溯: 节点失败 → 检查 depends_on 上游 → 上溯一阶 → 标记 causal_trace 边 →
  小环修上游 / 大环审计回档

死循环保护:
  小环 3 次重试失败 → BLOCKED → CascadeDetector → root_cause 回档
  子树 3 节点 blocked → DEGRADED
  回档循环 >2 次 → persistent_failure → USER_TRIAGE（强制用户介入）

User-In-Loop（对标 LangGraph interrupts）:
  触发: LLM 自触发（低置信度/异常模式/高风险/需要决策）+ 用户主动（中断按钮）+ 规则触发（约束违规/首次高风险/3次失败）
  干预: 批准/调整/重推理/跳过/终止 → Transition 记录 → BehaviorTree/ParameterRegistry 学习
  vs PlanGate: PlanGate=执行前全局审批；UserInLoop=执行中单步干预（互补）

完整节点状态机:
  PENDING → ACTIVE → THINKING → ACTING → SELF_CHECK →(pass) COMPLETED → ARCHIVED
                              ↑        │
                              └ Correct ← fail
  BLOCKED ← COMPLETED(blocked)   ARCHIVED →(reopen) REOPENED → BLOCKED(persistent) → USER_TRIAGE
```

### 1.8 对标表（设计 §九）

```
独有优势: 跨节点因果追溯 / 冷路径事后审计 / 死循环检测+自动剥离 /
归档回档+版本链 / 多树约束冲突消解 / 执行中用户干预 / LLM 自触发暂停
（ReAct/Reflexion/ToT/LATS/LangGraph 均缺其中多项）
```

---

## 二、设计 ↔ 代码对照（实锤）

### 2.1 已实现（代码侧）

| 设计要素 | 代码位置 | 状态 |
|---|---|:--:|
| Git 式版本控制 | `v4/cognitive/version_control.py`（Commit/VersionStore/GlobalVersionControl）| ✅ |
| 审核队列（submit/scan/process_queue）| `v4/cognitive/metacognition.py:97-163` | ✅ 实现 |
| 双模式决策（rapid/deliberate）| `v4/cognitive/metacognition.py:165-213`（_rapid_review/_deliberate_review）| ✅ 实现 |
| 复盘（retrospect）| `metacognition.py:215-249` → RetrospectionReport | ✅ 实现 |
| 自我复盘（self_audit/verify_past_decision）| `metacognition.py:250-280` | ✅ 实现 |
| 小环（NodeLifecycle/ReActor）| `execution/closure.py:23-34 / 234-301` | ✅ 实现 |
| 逆向因果追溯（CausalTracer）| `execution/closure.py:73-129` | ✅ 实现 |
| User-In-Loop | `execution/closure.py:165-232`（UserIntervention/UserInLoop）| ✅ 实现 |
| 级联检测 | `event/closure.py:214` CascadeDetector | ✅ |
| 死循环（ReActRetryEngine 5 策略）| 行为链/执行层 | ✅（关联链审计已验）|

### 2.2 未实现 / 断链（实锤）

| 设计要素 | 现状 | 根因 |
|---|---|---|
| 全链路接线 | 4 个静默失效（M1-M4）| post_decision 零调用 / MetaSubscriber 从未订阅 / _meta_consumer+_trace_v3 恒 None / handler 输出不传下游 |
| 外部能力接口 | 无 MetaCognitionCapabilities 类 | web_search 等分散在 tool_registry（permission.py），未按设计封装 |
| 主动拉取扫描（5 类）| scan(engine) 存在但参数断裂 | handle_meta 里 ctx 无意图数据 → scan 输入错误 |
| 自我复盘闭环 | self_audit 实现但无触发方 | 仅 CLI p10 诊断入口 |
| 版本控制全链消费 | version_control 仅被 metacognition 用 | 各链（画像/行为/关联）未接 GlobalVersionControl |
| Transition→L5 Memory→全模块学习 | 无 L5 消费证据 | 设计 §八 未落地 |

---

## 三、待讨论点（元认知，供全局拍板池）

1. **四职责落点**: A10 协同/学习/裁决/复盘 —— 目前 v4 MetaCognition 只覆盖"裁决+复盘"，
   "协同"在 FeedbackBridge（断）、“学习”在 v6 MetaConsumer（死代码）→ 三套归一方案。
2. **元认知写路径修复优先级**: M5（post_decision/订阅/_meta_consumer/_trace_v3）是否
   列为 P0 施工（与执行层 X1-X8 联动）。
3. **版本控制全局化**: GlobalVersionControl 是否升级为各链统一版本底座（A17 一致性公理）。
4. **外部能力接口**: 设计预留的 5 个接口是否对接 tool_registry（A21 安全护栏约束）。
5. **User-In-Loop 归属**: execution/closure.py 的 UserInLoop 与蓝图 §7 PlanGate 的边界
   （设计已区分: 执行前 vs 执行中）→ 需确认执行层/蓝图审计结论。
6. **主动扫描周期**: 设计"每 Slow Path 5 轮" vs 实际 `_turn_counter % 5` 死代码 ——
   扫描时机的真实载体（StateMachine META handler？CognitiveLoop？）。

---

## 四、元认知相关设计文档完整清单（分类，找齐）

> 方法: 全库关键词扫描（元认知/复盘/审核队列/第二大脑/自我复盘 + 机制关键词），
> 排除架构综述/审计类（ARCHITECTURE_*、*_AUDIT、FINAL_AUDIT 等仅提及层面）。

### A. 元认知本体（2 篇）✅ 已精读
| 文档 | 行数 | 主题 |
|---|--:|---|
| `docs/BUSINESS_CHAIN_09_METACOGNITION.md` | 309 | 第二大脑: 版本控制/审核队列/复盘/自我复盘/双模式决策/外部接口 |
| `docs/DESIGN_METACOGNITION_RUNTIME.md` | 445 | 运行时双环: 小环热路径/大环冷路径/逆向因果/死循环/User-In-Loop/状态机 |

### B. 机制底座（强相关，元认知运行所需的机制）⏳ 待逐批精读
| # | 文档 | 行数 | 与元认知的关系 |
|---|---|--:|---|
| B1 | `docs/v3.0/DESIGN_STATE_EVOLUTION_SYSTEM.md` | 439 | 状态演化 = 元认知观察的状态底座（trace_v3 对应）|
| B2 | `docs/v3.0/ENGINEERING_OBSERVABILITY.md` | 773 | 可观测性 = 元认知数据源（指标/轨迹）|
| B3 | `docs/v3.0/DESIGN_HYPOTHESIS_ENGINE.md` | 363 | 假设引擎 = 元认知学习闭环（生成→验证→沉淀）|
| B4 | `docs/v5/DESIGN_L5_LONG_TERM_MEMORY.md` | 150 | L5 长期记忆 = 元认知输出落点（Transition→L5）|
| B5 | `docs/v5/DESIGN_COLD_HOT_FEEDBACK.md` | 114 | 冷热反馈 = 元认知写路径（慢→快）|
| B6 | `docs/v5/DESIGN_DERIVATION_COMPRESSION.md` | 145 | 推导压缩 = 发散/收束（逆向动力系统）|
| B7 | `docs/v5/DESIGN_DERIVATION_COMPRESSION_V2.md` | 110 | 推导压缩 V2 |
| B8 | `docs/v5/DESIGN_TRACEABILITY.md` | 75 | 可追溯性（A17 一致性）|
| B9 | `docs/v3.0/RFC_PARAMETER_REGISTRY.md` | 267 | 参数注册表 = 元认知调参对象 |

### C. 哲学/公理（wise 目录）
| # | 文档 | 主题 |
|---|---|---|
| C1 | `docs/only/wise/PARADIGM.md` | A10 元认知四职责 + A16/A17/A18 相关公理 |
| C2 | `docs/only/wise/BEHAVIOR_CHAIN_DIGEST_20260801.md` | 行为链↔元认知联动（预测/奖励/裁决）|

### D. 跨模块交集（元认知为其中一部分）
| # | 文档 | 行数 | 交集点 |
|---|---|--:|---|
| D1 | `docs/BUSINESS_CHAIN_STATE_MACHINE.md` | 80 | META 阶段归属（执行层审计已覆盖）|
| D2 | `docs/BUSINESS_CHAIN_05_BEHAVIOR.md` | 224 | 行为链反馈→元认知（已审计）|
| D3 | `docs/DESIGN_SYSTEM_SCHEDULER.md` | 322 | 元认知周期调度（Slow Path checkpoint）|
| D4 | `docs/v5/DESIGN_V4_COGNITIVE_INTEGRATION.md` | 92 | v4 认知集成（元认知位置）|

**阅读计划**: B1-B9 逐批精读 → 记录追加至本文档 §五+；C 类引用 PARADIGM 已有结论；
D 类由对应模块审计覆盖（状态机=执行层，行为=行为链），仅交叉引用。

---

## 五、B1 精读: 状态演化系统（DESIGN_STATE_EVOLUTION_SYSTEM.md，439 行）

### 5.1 设计核心

```
问题诊断: v4 四空间各自维护状态（ConceptGraph/BehaviorGraph/CausalPlanner/
ExecutionTrace/Reflection/Prediction）——同一根因: 缺少统一状态对象与状态演化语义。
核心对象: Mind（长期心智，跨对话持久化认知结构）
闭环: Mind → Observer → Workspace → ExecutionTrace → Reflection → Mind Update → (下次)

Mind 结构: attention_prior / prediction_prior / preference_model / thinking_style /
  learned_strategies / common_mistakes / reflection_history / relation_prior / behavior_prior
Mind 更新: 增量（EMA 注意力先验 / 策略权重 0.9:0.1 / 错误频率累积 / 保留最近 100 条反思）

统一关系图 RelationGraph: "只有一种图，边的类型决定语义"
  RelationType: CONTAINS/DEPENDS_ON/IMPLEMENTS/DEFINES（结构）| SEMANTIC/ANALOGOUS/EVOLVES_TO（语义）
  | CAUSAL/CONTRADICTS/SUPPORTS（因果逻辑）| BEHAVIOR/ATTENTION/PREDICT（行为）
  迁移: ConceptGraph→CONTAINS 等 / RelationSubstrate→SEMANTIC 等 /
        BehaviorGraph→BEHAVIOR / CausalPlanner→CAUSAL(conf≥0.7) 子集
  RelationEdge: {source, target, type, confidence, evidence, created_at, last_activated, activation_count}

ExecutionTrace v2 = WorkspaceSnapshot 序列（注意力分布/活跃假设/置信度分布/关系激活/冲突/对象快照）
  delta(from,to) / replay(from_idx) / diff(trace_b)
  能力表: 哪步提升置信度 / 哪条关系最有效 / 为何拒绝假设 / 中途重放 / 两次推理对比

范式转变: "组织知识的系统" → "演化认知的系统"
  v4: Document/Concept/Knowledge + 三套并行图 + 函数调用追踪 + 无学习 + 每次从零开始
  v5: State/Transition/Mind + 统一 RelationGraph + 状态快照序列 + Mind 增量更新 + 跨对话演化
```

### 5.2 代码对照（实锤修正）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| ExecutionTrace v2 | `state/execution_trace.py:17` ExecutionTraceV3（snapshot/record_transition/meta_analyze/diff）| ✅ **类完整实现** |
| Mind | `v4/cognitive/mind.py:19` Mind（learn/initialize_workspace/load/save）| ✅ 类实现 |
| Workspace | `v4/cognitive/workspace.py` CognitiveWorkspace/WorkspaceGraph/ExecutionTrace | ✅ 类实现 |
| RelationGraph | `storage/relation_graph.py:152` RelationGraph + `state/interaction_graph.py` | ✅ 类实现 |
| StateObject/StateDelta | `state/state_object.py`（Transition/TransitionReason）| ✅ 类实现 |
| GlobalDecider | `state/global_decider.py:68`（decide/evolve）| ✅ 类实现 |
| **闭环接线** | `runtime/engine.py:180` `_trace_v3 = None`（唯一赋值）| ❌ **类齐但从未实例化** |
| **MetaConsumer 接线** | `runtime/engine.py:1218` 依赖 `_meta_consumer`（无赋值）| ❌ 同上 |

> **重要修正（DEEP_AUDIT M3）**: 不是「死代码」——`ExecutionTraceV3` 与 `MetaConsumer`
> 类均完整实现；断点是 **engine 从未创建实例**（`_trace_v3`/`_meta_consumer` 恒 None）。
> 修复方向 = 在 `runtime/engine.py` start() 处接线实例化，非重写。

### 5.3 待讨论点（联动执行层/元认知）

1. `GlobalDecider`（state/global_decider.py）与 `event/statemachine.py` DeciderStateMachine
   是否应归一（两个"决策器"并存）。
2. 统一 RelationGraph 迁移（设计 Phase A: 三套图 → 统一图）未实施——ConceptGraph/
   BehaviorGraph/CausalPlanner 仍各自维护（与关联链/子图/行为链审计联动）。
3. Mind 类（v4/cognitive/mind.py）与画像 OCEAN/inertia_graph 的边界（谁承载"长期心智"）。

---

## 六、B2 精读: 可观测性（ENGINEERING_OBSERVABILITY.md，773 行）

### 6.1 设计核心

```
定位: 可观测性系统 = 多层 LLM 认知架构的"诊断基础设施"（元认知的数据源）。
原则: "预期无休止的猜测，不如多加监视模块。"
六大组件:
  MetricsCollector（指标收集: 延迟/成功率/Token/幻觉率/意图准确率, 聚合 avg/sum/p95/p99, 10000 点截断）
  StructuredLogger（JSON 日志: Console/File/SQLite 三 handler, llm_call/hallucination_detected 专用方法）
  TraceManager（端到端追踪: trace_id + span 树, get_slow_traces）
  HealthChecker（Provider 级 + 系统级, is_degraded: 健康 Provider <50%）
  DiagnosticsEngine（错误自动分类: timeout/rate_limit/auth/hallucination/context_overflow, 诊断报告 Markdown）
  Dashboard（6 个 LLM 专属面板）

指标定义（15 个）: llm_latency_ms / llm_success_rate / llm_token_usage /
  llm_hallucination_rate / llm_cognitive_load / llm_intent_accuracy /
  llm_planning_efficiency / llm_validation_rate / llm_reflection_insight /
  llm_answer_relevance / routing_hop_count / context_compression_rate /
  ct_node_count / ct_edge_count / ct_conflict_count

6 个 LLM 专属面板（告警阈值）:
  PCR-LLM 模糊度>0.7 / Intent-LLM 准确率<0.85 / Planning-LLM 达成率<0.8 /
  Meta-Cognitive-LLM 通过率<0.9 / Reflective-LLM 洞察质量<0.7 / Answer-LLM 相关性<0.8

集成方式: Provider.generate_native_async 注入指标记录（llm_name/provider/cognitive_mode 标签）
```

### 6.2 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| observability 全套 | `observability/`（10 文件: alert/dashboard/logger/metrics/models/store/telemetry/tracer/metacognitive_trigger/trigger_wiring）| ✅ 包完整 |
| Telemetry 接线 | `orchestrator/bootstrap.py:41` + `orchestrator/orchestrator.py:65` | ✅ 真接线 |
| Metrics 消费 | `engineering_bridges.py:349,357` | ✅ |
| 测试 | `observability/tests/test_telemetry.py` | ✅ 存在 |
| 双套 Tracer/Metrics | `observability/tracer.py` + `event/tracer.py`（PipelineTracer/MetricsCollector）| ⚠️ 两套并存 |
| MetacognitiveTriggerEngine 挂载 | `observability/metacognitive_trigger.py` + trigger_wiring | ⚠️ wiring 函数存在，生产挂载待确认（meta 审计 M9）|

> **修正（meta AUDIT_ENTRY §2.5）**: observability/ 包整体有真实消费（orchestrator Telemetry +
> engineering_bridges Metrics）；MetacognitiveTriggerEngine 是否挂载需单独确认，非整个包孤儿。

### 6.3 待讨论点

1. 两套 Tracer/Metrics（observability/ vs event/tracer.py）归一（与执行层/LLM 回复侧审计联动）。
2. 设计 15 个指标的落地覆盖度（哪些在 observability/metrics.py 真实采集）。
3. 告警阈值 → 元认知触发（MetacognitiveTriggerEngine 对接 DiagnosticsEngine 快照）。

---

## 七、B3 精读: 假设共识引擎（DESIGN_HYPOTHESIS_ENGINE.md，363 行）

### 7.1 设计核心

```
定位: 不是"计算置信度"的系统，是"共识形成"系统。
核心区别: 不是一条路径越来越确定，而是多个认知域从各自视角共同验证同一组假设。

关键设计原则:
  Belief 不存现算（存原始计数，belief_score 每次按需计算，算法可换）
  竞争不标注动态算（共享 Object+Topic+冲突 Statement → 自动竞争池）
  Evidence 不直接更新置信度（只投 Support/Conflict/Neutral 离散票）
  置信度 = 共识度（belief_score = f(support, conflict, stability, coverage, entropy)）
  Knowledge 冻结不可逆（冻结后不再参与竞争）

四个 Primitive:
  Match: Evidence 按 Object/Topic/Domain 匹配受影响的 Hypothesis
  Vote: 每 Hypothesis 投 Support/Conflict/Neutral（离散）
  Decay: 时间衰减（TimeWeight = e^(-λ×age)，半衰期 7 天）
  Resolve: 冻结/合并/stale 判定

Hypothesis Graph 三边: supports(0.3) / explains(0.15) / derived_from(0.1) → Belief Propagation
BeliefState 7 维: support/conflict/novelty/stability/coverage/recency/entropy
Knowledge 冻结 5 维 AND: min_support=8 / max_conflict=3 / min_stability=0.70 /
  min_coverage=0.40 / min_consensus_domains=2（至少 2 个独立认知域支持）
共识质量 = 支持域数量 / 总认知域数量（非 Support 绝对数）

调度: ObservationBundle complete → Match+Vote；Decay+Resolve 60s 周期；
  ContextCompiler 查询时按需重算 belief_score
集成面: Observation Compiler（输入）/ NodeAnnotationStore（消费）/ UnifiedGraphStore（存储）/
  ParameterRegistry（权重）/ TierHeatBridge（热提升）/ ContextCompiler（上下文）/ 各链（投票源）

ReasonSession: 共识会话记录（candidates/votes/merged/winner/knowledge_ref，append-only 可重放）
```

### 7.2 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| 真实现 | `core/agent/hypothesis/`（5 文件: models/match_vote/decay_resolve/pipeline/session_manager）| ✅ 类实现 |
| 接线 | `cognition/hub.py` CognitionHub（ingest_relations/converge）→ `orchestrator/bootstrap_v6.py:54,122` + `agent_native.py:35`（A 路径）| ✅ 真接线 |
| 测试 | `core/agent/hypothesis/tests/`（4 文件）| ✅ |
| **误导壳** | `v4/hypothesis_engine/__init__.py`（相对导入 .models/.match_vote 等，目录内只有 __init__.py）| ❌ 导入即炸（迁移残留）|
| BeliefAccumulator | `association/l2_5_belief.py` + `v4/cognitive/belief_map.py`（RecursiveMap 是工程地图，非假设引擎）| ⚠️ 关联链体系，另起炉灶 |

> **新实锤（与 v4/skill_layer 同型）**: `v4/hypothesis_engine/` 是迁移壳，
> 引用不存在的相对模块 → `import core.agent.v4.hypothesis_engine` 即 ModuleNotFoundError。
> 真实现与真接线在 `core/agent/hypothesis/` + `cognition/hub.py`。

### 7.3 待讨论点

1. 假设引擎（共识形成）与关联链 L2.5 BeliefAccumulator 的关系（两套信念体系并存）。
2. `v4/hypothesis_engine/` 壳去留（同 v4/skill_layer 壳——全局"v4 壳清理"）。
3. 设计集成面（TierHeatBridge/ContextCompiler 消费）实际落地情况（待核查）。

---

## 八、B4 精读: L5 长期记忆（DESIGN_L5_LONG_TERM_MEMORY.md，150 行）

### 8.1 设计核心

```
核心哲思: 记忆不是"存什么"，是"什么时候用什么方式取"。
三层分治:
  高频平庸 → 压缩成规则（DerivationCompressor）
  低频高价值 → RAG 原样保留（密码/密钥/罕见 bug）
  思考过程 → 启发凝练（元认知专属持久化）

信息论二维决策矩阵（P=频率, I=价值）:
  P高+I高 → 压缩成规则+快速索引    P高+I低 → 强压缩/丢弃
  P低+I高 → RAG 原样保留（关键）   P低+I低 → 仅索引
信息价值 = 0.3×entity_rarity + 0.35×intent_novelty + 0.35×action_deviation

图+RAG 两层检索（锚点定位）:
  Step1: embedding → 最近邻 → 定位 EntityNode（锚点）
  Step2: 图扩散（water-wave）→ 2 跳内召回"实际发生过关系"的实体+证据链
  优势: 2 跳内召回的是因果相关而非语义近似（vs 纯 RAG）

规则验证闭环: 聚类→归纳规则→逆推验证→失败→多视角调整
  （结构/语义/时序/反例 4 视角，与 MultiPerspectiveAnalyzer 同构复用）

启发式凝练（元认知专属持久化）:
  HeuristicChain = 条件 + 反例 + 验证路径 + 置信度（"系统怎么想的"）

五区存储: Hot（dict）/ Working（DiscourseBlockTree SQLite）/ Archived（RAG VectorDB）/
  Compressed（DerivationCompressor JSON）/ Meta-Cognitive（HeuristicChain，设计指 Rust）
检索优先级: Working → Archived(RAG+图扩散) → Compressed(规则) → Meta-Cognitive(启发链)
```

### 8.2 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| DerivationCompressor + HeuristicChain | `cognitive/derivation_compressor.py:37,67`（发散→收敛→启发链）| ✅ 类实现 |
| 信息价值计算 | `compiler/three_paradigm_context.py:73` `_information_value` | ✅ |
| XML Memory Cards | `memory/xml_cards.py`（information_value 字段）| ✅ |
| RAG 层（HNSW/Faiss/Milvus）| `persistence/`（hnsw/faiss/milvus）| ✅（依赖见持久化审计）|
| 图扩散 | `v4/cognitive/subgraph_compiler.py`（多锚点+边优先扩展）| ✅（子图审计已验）|
| **RAG→锚点→图扩散→上下文 连接** | 待确认（子图/上下文审计联动）| ⚠️ |
| **Meta-Cognitive Memory（Rust）** | `persistence/rust_bridge.py`（探测壳）| ❌ 未实现 |

### 8.3 待讨论点

1. L5 五区存储与持久化审计 6 套体系的对应（Hot/Working/Archived/Compressed 归属）。
2. 启发链（元认知持久记忆）的生产/消费接线（与 B1 Mind、B3 假设引擎的关系）。

---

## 九、B5 精读: Cold→Hot 三层回写（DESIGN_COLD_HOT_FEEDBACK.md，114 行）

### 9.1 设计核心

```
核心哲学（非修正原则）: 多面决策，不是对错判断。
  传统 React: 请求→尝试→判断对错→重来→给出（阻断当前回答）
  DialogMesh: 请求→多视角竞争→给最优回答→Meta 异步审视→修正未来（不阻断）
  不二值: 不是对/错，是置信度在哪个区间；修正不是重试，是调整下次 Tick 参数

三层通道:
  Layer1 确定信号→同步修正: hallucination>0.7 | bias>0.8 | confidence<0.1
    → MetaDecision 附加 CorrectionMark（不覆盖已给回答）→ 下次 Tick PCR 被告知
  Layer2 证据积累→异步裁决: confidence 0.3-0.6 | MultiPerspective 分歧
    → Belief Accumulator 跨 Tick 收敛 → 阈值触发 action（auto_correct/ask_user/llm_decide）
  Layer3 模式漂移→参数调整: OCEAN 惯性变化>0.15 | BehaviorPattern 持续异常
    → 不直接修正 → 调整 Blueprint 参数（OCEAN 权重/ε-greedy ε/蓝图偏置）

MetaDecision 契约: {tick, confidence, urgent_correction, belief_update, parameter_shift}
```

### 9.2 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| MetaDecision | `meta/feedback_bridge.py:19`（tick/confidence/urgent/belief/parameter_shift）| ✅ 契约一致 |
| CorrectionJournal | `v4/cognitive/correction_journal.py:28` | ✅ |
| Dynamics | `v4/cognitive/dynamics.py:16` DynamicsComputer | ✅ |
| CognitionHub | `cognition/hub.py`（bootstrap_v6 接线）| ✅ |
| **Layer1 数据流** | post_decision 零调用（DEEP_AUDIT M1）| ❌ 生产端断 |
| **Layer3 BlueprintSelector.adjust()** | 待确认（蓝图审计）| ⚠️ |

> **修正（设计 §五 断言"✅ 直接施工"）**: 设计认为 Layer1-3 可直接施工且基础已备；
> 实际 Layer1 的 MetaDecision 生产→agent_native 消费链**断在 post_decision 零调用**（M1）。

### 9.3 待讨论点

1. Layer1 写路径接线（谁产 MetaDecision、谁 post_decision）——元认知施工首要事项。
2. Layer2/3 与行为链（rewarder/DPO）、蓝图（BlueprintSelector）的边界。

---

## 十、B6 精读: 约束驱动推导压缩（DESIGN_DERIVATION_COMPRESSION.md，145 行）

### 10.1 设计核心（哲学基座）

```
哲学内核: 同一信号（低概率信息），不同约束 → 相反结论
  卡尔曼滤波: 低概率=低权重（丢弃）← 约束: 正态分布, 追求准确性（自动化控制）
  信息论:     低概率=高价值（放大）← 约束: log分布, 追求信息价值（通信/密码学）
  结论: 不是"低概率"本身，是"约束框架"决定它的意义
       约束内 → 互化；约束间 → 不可直接比较，需转换层

压缩 ≠ 聚类:
  聚类压缩（错误）: "延迟飙升"+"监控缺失" → 主题"系统问题" → 丢失因果推导链
  推导链压缩（正确）: 提取状态转移(a→b→c) → 归纳规则 → 压缩规则集 → 逆推验证

四步压缩算法:
  Extract: L2 实体图 + L2.5 信念轨迹 → state_t → state_{t+1} 转移对
  Induce: 模式归纳（entity_pair+relation→intent_shift / stability drop→drift / 簇>3→topic_lock）
  Compress: 规则集（每条 <200 tokens 覆盖数百轮）
  Verify: 新对话逆推 → 匹配+0.01 / 不匹配-0.05 / <0.3 移除

子图↔LLM 混合格式（A8 表达形式哲学的具体化）:
  高结构/确定性 → XML（实体+关系+置信）
  中结构/量化 → JSON（信念分布+转移概率）
  低结构/模糊 → 自然语言（推理/元认知建议）
  格式选择规则（非硬编码）: entity_count>5+conf>0.8 → XML /
    quantitative_distribution_present → JSON / ambiguous → NL

核心公式: 压缩率<5% / 逆推覆盖率>80% / 新鲜度=1-(last_fired/turn)
核心哲学: "压缩不是让信息变小——是让信息的约束结构显式化"
```

### 10.2 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| 四步算法（extract/diverge/converge/heuristic）| `cognitive/derivation_compressor.py:89-232` | ✅ 完整实现 |
| HeuristicChain（含反例/测试/新鲜度）| `derivation_compressor.py:37-65` | ✅ |
| 消费: intent dual_track 冷路径 | `intent/dual_track.py:34,122-124`（cold→hot 优化）| ✅ 真接线 |
| 消费: 触发器 | `observability/trigger_wiring.py:35`（belief_entropy→compressor）| ✅ |
| 消费: 锚点源 | `memory/federated_index.py:186`（HeuristicChain 池作锚点源）| ✅ |
| 消费: XML cards | `memory/xml_cards.py:177`（思维模式卡）| ✅ |

> 修正（此前"发散收束只是理念"的隐含假设）: 推导压缩**已实现且接入
> intent 冷路径/触发器/记忆锚点**——B6/B7 是本项目落地最好的元认知机制之一。

---

## 十一、B7 精读: 发散→收敛启发链（DESIGN_DERIVATION_COMPRESSION_V2.md，110 行）

### 11.1 设计核心（B6 的修正版）

```
为什么规则归纳是过拟合: 从有限采样归纳确定性规则 = LSTM 窗口拟合
  （"if causes_chain && conf>0.7 → 诊断"换场景即失效）

正确路径 = 发散→筛选→启发链（类比神经网络训练）:
  Diverge: LLM 无上下文猜测（temperature=0.8, no system prompt, K=3-5）
    → 产生发散性假设（含预训练海量知识，可错误但覆盖广）
  Converge: LLM 有上下文筛选（temperature=0.1, full context）
    → 验证猜测（对齐证据保留 / 无证据驳回，含拒绝理由）
  Heuristic Chain: 模式描述 + 适用条件 + 反例 + 推理路径
    → 有包容性/泛化/保留推导/可逆推

压缩质量度量: 不是"规则匹配率"（验证过拟合），是"启发覆盖率" 60-80%
  （100% = 过拟合；覆盖率下降 → 重新发散 → 新启发链替代）

实现流程（每 N=5 轮）: 提取推导链 → 发散 K 猜测 → 收敛筛选 → 启发链 → 入池替换低覆盖率旧启发
元认知角色: 监测覆盖率 / 触发重新压缩 / 新旧启发冲突裁决
```

### 11.2 代码对照

```
与 B6 共用 `cognitive/derivation_compressor.py`（diverge:120 / converge:146 / heuristic:187）✅
`HeuristicChain.record_test/is_stale/freshness`（50-62）→ 覆盖率生命周期机制 ✅
元认知裁决（覆盖率<阈值触发重压）→ 待确认（MetaCognition 未接 compressor）
```

### 11.3 待讨论点

1. 启发覆盖率监控（元认知角色）的接线：MetaCognition 是否应消费 HeuristicChain 池。
2. B6（规则归纳）vs B7（发散收敛）在实现中的关系——代码同时保留 extract/induce 路径
   与 diverge/converge 路径，实际默认走哪条（dual_track 调用细节第二轮代码深读确认）。

---

## 十二、B8 精读: 历史设计点追踪（DESIGN_TRACEABILITY.md，75 行）

### 12.1 文档性质

```
非独立设计，是"设计点吸收/等效/遗漏追踪表"（2026-07-22，对照全部 BUSINESS_CHAIN + DESIGN）。
元认知相关条目:
  ✅ Meta subscriber — 8 事件订阅（已实现）
  ⚠️ Mind — 代码存在（长期心智/Attention Prior）
  ❌ Cold→Hot 回写 — Meta→Intent, Assoc→Context 未实现
  ⚠️ Hypothesis Engine — 7 维信念/解释生态（当时标记闲置）
  ⚠️ Slow Path checkpoint — 框架存在未触发业务
  ⚠️ ABC Framework — learn_from_feedback 空壳
  ❌ Parameter Registry — v3_2→un_use（当时标记未用）
```

### 12.2 与 2026-08-03 现状的差异（重要：旧表已过时）

```
Hypothesis Engine: B8 标记"闲置" → 现已接入 cognition/hub（bootstrap_v6 真接线，见 §七）
Parameter Registry: B8 标记"v3_2→un_use" → 现已实现在 compiler/parameter_registry.py
  （被 dpo_learner/scheduler/pipeline_api/behavior_cmd 真消费，见 §十三）
Cold→Hot 回写: B8 标记"未实现" → 仍成立（post_decision 零调用，DEEP_AUDIT M1）
Mind: 类存在，引擎未接线（§五 5.2）
```

> 结论: B8 作为"当时快照"仍有参考价值（哪些设计点曾被认为未实现），
> 但须以 2026-08-03 审计为准（多点在 B 类精读中已更新状态）。

---

## 十三、B9 精读: 参数注册表（RFC_PARAMETER_REGISTRY.md，267 行）

### 13.1 设计核心

```
动机: 全系统 50+ 参数散落 22 模块硬编码；统一管理锚点-区间-自适应范式。

AdaptiveParameter 统一接口:
  {name, anchor, interval[min,max], step, current, min_samples,
   reward_signal(绑定信号函数), last_adjusted, cooldown_sec, tier(hot/warm/cold)}
更新逻辑: samples>=min_samples and cooldown passed →
  信号改善+step / 恶化-step / clamp 到区间；每次调整写 Event Log 审计轨迹

全局策略切换: quality_first / balanced / cost_first / provider_default
  切换时参数线性过渡（非瞬时突变）
参数自身热冷分层: Hot(实时,1min冷却) / Warm(每小时,10min) / Cold(每天,1h)

参数全景（50+）: TopicTree 5 / LLM 熔断 4 / 安全 5 / 可观测 2 / 编排 3 /
  Tool 1 / Gate+PCR 3 / Onboarding 3 / 约束编译器 2 / BehaviorGraph 7 /
  Predictor+Rewarder 6 / FoA+do-calculus 4 / 嵌入 2 / 合并+持久化+元认知 3 /
  v4 新模块 25（Hypothesis/Belief/Refinement/Skill/EventIR/ObsPool/ContextCompiler/SubgraphPrune）
  元认知参数: metacognition_token_threshold=10000（meta_insight_density 信号）
```

### 13.2 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| ParamDef（observe/adapt）| `compiler/parameter_registry.py:20-57` | ✅ |
| ParameterRegistry（get/set/observe/adapt_all/switch_strategy）| `parameter_registry.py:59-203` | ✅ |
| 策略切换 | `parameter_registry.py:190` switch_strategy | ✅ |
| 消费者 | `behavior/dpo_learner.py:31` + `behavior/scheduler.py:22` + `api/pipeline_api.py` + `cli/commands/behavior_cmd.py:109` + `execution/closure.py:173` + `monitor/p1_gaps.py:142` | ✅ 真消费 |
| CRUD API | `api/pipeline_api.py`（v6 Pipeline Parameters API）| ✅ |
| 测试 | `compiler/tests/test_parameter_registry.py` | ✅ |

> 修正（B8 表 §三"Parameter Registry v3_2→un_use 未实现"）: 现已实现在
> `compiler/parameter_registry.py` 且被 A18 相关模块（dpo/scheduler）真消费。

### 13.3 待讨论点

1. RFC 50+ 参数 vs 实际注册参数的数量/覆盖度（哪些模块仍未接入注册表）。
2. 参数自适应（A18）与元认知（参数复盘/回滚）的接口——RFC 说"每次调整写 Event Log
   审计轨迹"，是否接 GlobalVersionControl（§五）与 MetaCognition.retrospect。

---

## 十四、B 类精读完成度（9/9）

| # | 文档 | 核心结论 |
|---|--:|---|
| B1 | 状态演化 | ExecutionTraceV3/Mind/RelationGraph 类齐，引擎未接线（M3 修正）|
| B2 | 可观测性 | observability/ 包实现+接线；MetacognitiveTrigger 挂载待确认 |
| B3 | 假设引擎 | core/agent/hypothesis/ 真实现+cognition/hub 真接线；v4 壳导入即炸 |
| B4 | L5 长期记忆 | DerivationCompressor/信息价值/XML cards 实现；RAG→图连接待确认 |
| B5 | 冷热反馈 | MetaDecision 契约齐；Layer1 断在 post_decision（M1）|
| B6 | 推导压缩 | 四步算法完整实现 + intent 冷路径/触发器/锚点消费 ✅ |
| B7 | 发散收敛 | 与 B6 同实现；启发覆盖率生命周期机制在 |
| B8 | 可追溯性 | 旧快照表，多条目已被 2026-08-03 审计更新 |
| B9 | 参数注册表 | ParameterRegistry 实现 + A18 模块真消费（修正 B8 的"未用"）|

> 元认知模块两轮审计全部完成（第一轮 AUDIT_ENTRY + 深层次复核 DEEP_AUDIT +
> 第二轮设计精读 DESIGN_FULL_READ 十四节）。下一模块: 规划（8 篇设计文档）。
