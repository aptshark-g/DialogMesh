# 执行层设计文档全面精读（第二轮）

> 日期: 2026-08-03 | 精读对象（8 篇，1885 行）:
> `BUSINESS_CHAIN_STATE_MACHINE.md`（80）+ `DESIGN_GLOBAL_STATE_MACHINE.md`（226）+
> `DESIGN_EXECUTION_LAYER.md`（280）+ `DESIGN_RUNTIME_KERNEL.md`（130）+
> `FLOW_EXECUTION_INTERNAL.md`（164）+ `FLOW_EXECUTION_OVERALL.md`（248）+
> `v3.0/DESIGN_COGNITIVE_RUNTIME.md`（318）+ `v3.0/DESIGN_STATE_EVOLUTION_SYSTEM.md`（439）
> 配套: `AUDIT_ENTRY_20260803.md`（一轮盘点）+ `DEEP_AUDIT_20260803.md`（实锤验证）
> 本文档 = 设计全貌凝练 + 设计↔代码对照 + 待讨论点。

---

## 一、StateMachine 业务链精读（BUSINESS_CHAIN_STATE_MACHINE.md，80 行）

### 1.1 设计核心

```
动机: 旧链间直接 push = 广播风暴（6 链连锁指数级放大）
方案: Decider 串行化 —— 36 条 push 路径 → 6 条 Tick 序列

Command → Event → State 三阶段:
  用户/LLM/系统 → decide(cmd, state) → 1 Event → evolve → new State → 下一 Tick

事件类型: MESSAGE_RECEIVED → PCR_COMPUTED → INTENT_PARSED → PLAN_GENERATED
  → CONTEXT_COMPILED → REPLY_GENERATED → PROFILE_UPDATED → BEHAVIOR_RECORDED
  → META_REVIEWED → ABC_EVALUATED → MIND_LEARNED

StateSnapshot（10 字段）: pcr_expectation / intent_category / plan_task_count /
  context_entries / profile_trust / behavior_actions / meta_signals /
  abc_rules_fired / mind_relations / tick

代码: v4/state/global_decider.py（180 行）
```

### 1.2 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| GlobalDecider（decide/evolve）| `state/global_decider.py:68`（12 EventType + Command/Event/StateSnapshot）| ✅ 类实现 |
| 防风暴（单 Event 原则）| decide() 每次返回 1 Event | ✅ |
| **on_event 集成**（业务链 §三: engine.on_event 调 _decider.evolve）| runtime/engine.py 无 `_decider` 使用（rg 未见）| ❌ 未接线 |
| **StateSnapshot 10 字段** | global_decider.StateSnapshot 字段待核对 | ⚠️ |

> 关键: GlobalDecider 类存在但 **engine 从未调用它**（与 StateMachine DeciderStateMachine
> 并存，两个"决策器"都未成为主路径）。

---

## 二、全局状态机精读（DESIGN_GLOBAL_STATE_MACHINE.md，226 行）

### 2.1 设计核心

```
参考: Temporal Workflow+Activity / Event Sourcing+Decider / Flink Checkpoint / LangGraph

广播风暴诊断: 链间直接 push 无协调者无反压
防风暴三板斧:
  ① 单 Event 原则（每 Tick 只 1 个 Event）
  ② 反压（Event Queue > 10 → 丢弃低优先级）
  ③ 增量 Checkpoint（只持久化变化分片，参考 Flink）

Event Sourcing 三阶段:
  Command（意图）→ Decider 验证（冲突/权限/预算）→ Event（不可变日志）→ evolve → State（投影）
  优势: 可重放 / 可从任何 Event 重建 / 元认知可复盘

状态分片（Flink KeyedState 映射）: 按 discourse_block_id 分片，互不干扰

生命周期状态机:
  active(Fast <50ms) → paused(5min) → cooling(Async, 粘合度悬崖) → cold(Slow, Checkpoint)
  → frozen(Deep, 压缩) → archived(7d) → active(部分复活)

路径调度（Temporal 映射）:
  Fast→无 Activity | Async→Activity{retry=2,timeout=10s} |
  Slow→Activity{retry=1,timeout=60s} | Deep→Child Workflow
```

### 2.2 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| GlobalDecider | `state/global_decider.py`（decide/evolve/_map_command_to_event）| ✅ 类实现 |
| Event Sourcing | `api/api_event_log.py` EventLog（关联链 Phase 6 用）| ✅ 部分 |
| 状态分片 | 待核对（ShardedState 类？）| ⚠️ |
| 反压机制 | 待核对 | ⚠️ |
| 生命周期状态机 | `v4/cognitive_scheduler/models.py` PathStateMachine（idle→running→backlogged）| ⚠️ 另一套 |
| **engine 接线** | `_decider` 未被 runtime/engine 调用 | ❌ |

> 结论: 全局状态机设计 = 防广播风暴 + Event Sourcing 的正确方向，但 GlobalDecider
> 与 DeciderStateMachine（event/statemachine.py）双决策器并存且都未真正成为主路径——
> 执行层核心待拍板（X 系列 + 本模块新增）。

---

## 三、执行层精读（DESIGN_EXECUTION_LAYER.md，280 行）

### 3.1 七棵树并行模型

```
DiscourseBlockTree（基类: 节点/分支/摘要/归档）→ 7 子类:
  DiscourseTree(对话) / ExecutionTree(任务分解+子Agent, 最活跃) /
  ConstraintTree(工程约束, 轻量) / AssociationTree(实体关系, 辅助) /
  BehaviorTree(用户偏好+PlanGate 学习, 协同) / MetaTree(元认知仲裁, 拍板) /
  ProfileTree(OCEAN 演化, 极轻)

查询驱动通信（不是通知）:
  需要信息 → 主动 query（多头注意力 Q 向量类比）
  活跃节点直接读 / 归档节点 LLM 决策是否回档 /
  未找到 → 双方案并行（新子Agent 探索 + 持久化层 L5 搜索）→ LLM 去重
  等待不阻塞: 目标完成标记 ready，下 Tick 重新 query

树的动态生长:
  正向: 自顶向下分解（根→LLM 评估→子Agent ≤4K）
  反向: 回退插入（MetaTree 发现冲突/遗漏/环境变化 → 决策节点插入新分支）
  任意位置: 元认知判断"先验证" → 插入验证节点

子Agent 派生: LLM 元认知综合判断（complexity/context_size/阈值 8K-16K/subtasks/
  tools/constraint_violations/behavior_hints）| 可选: 单触发/纯 LLM/关闭
Memory Node: 上下文>阈值 → 语义切块 → 只读降级 → L5（XML+Federation）
ReAct 重试闭环: 明确错误→自动修正(Max3) / 模糊→降温度 / 信息不足→派生检测 Agent

归约策略（重要性倒置）: 合并次数 ∝ 1/重要性
  高价值(1次): 安全/架构/偏好/约束冲突 → 直接 LLM 归约
  中价值(2次): 代码修改/配置 → 结构化提取→压缩→LLM
  低价值(3次): 报告/日志 → 摘要丢弃细节
外部工具归一化: OpenClaw/Codex/MCP → ExecutionResult{source,status,output,artifacts}

实施序列: AgentTreeManager(Phase1) → Memory Node+查询驱动(2) → 动态生长(3) →
  StructuredSynthesizer(4) → 端到端(5)
```

### 3.2 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| 七棵树 | `execution/tree_manager.py`（AgentTree + 7 子类: Discourse/Execution/Constraint/Association/Behavior/Meta/Profile）| ✅ 类实现 |
| 查询驱动 | `execution/tree_manager.py:321` global_query | ✅ |
| 回退插入/动态生长 | `execution/closure.py` NodeLifecycle/CausalTracer（回档）| ✅ 部分 |
| ReAct 重试闭环 | 行为链 ReActRetryEngine | ✅ |
| 归约/StructuredSynthesizer | 待核对 | ⚠️ |
| 外部工具归一化 | 待核对（adapter/openclaw.py?）| ⚠️ |
| **端到端接线** | tree_manager 仅被 bootstrap_v6/orchestrator agent_native 引用（A 路径），CLI 主路径未挂 | ⚠️ |

> 印证: 设计自述"复用已实现 + 待建 AgentTreeManager"——AgentTreeManager 已在
> execution/tree_manager.py 实现（含 7 树），但归属 agent_native A 路径。

---

## 四、Runtime Kernel 精读（DESIGN_RUNTIME_KERNEL.md，130 行）

### 4.1 设计核心

```
目标: 从"蓝图好但执行弱" → "内核级 Agent OS"（对标 Linux Kernel + Erlang BEAM + LangGraph）

领域成熟度自评:
  状态机 50%（DAG 有 schema 无执行）/ 消息总线 20%（EventBus 没接）/
  任务调度 10%（无调度器）/ 可观测性 5%（PipelineTracer 没接）/
  持久化 40%（JSON 直写）/ 模块热加载 30%
结论: "缺的不是想法，是基础设施落地。把已选的方案（NATS/SQLite/ChromaDB）真正接上。"

四大组件:
  调度器（BlueprintEngine v2）: DAG → Decider 调度 → EventBus 并行
    P0 REALTIME(<10ms) / P1 INTERACTIVE(<100ms) / P2 BATCH(<1s) / P3 IDLE(后台)
  消息总线（NATS）: EventType→JSON schema / 订阅注册 / 并行执行 / 背压
  存储抽象（StorageLayer）: HotStore(内存) / WarmStore(SQLite+WAL) / ColdStore(JSON/ChromaDB)
  可观测性: 每条消息 trace_id 贯穿 → Prometheus + JSON trace

不自研决策: NATS(总线) / SQLite+ChromaDB(存储) / OpenTelemetry(可观测) —
  自研仅调度器+状态机（7-tree 模型不兼容 LangGraph）
实施路径: 4 周（EventBus 接线 → 调度升级 → 存储统一 → 可观测生产化）
```

### 4.2 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| 调度器（BlueprintEngine v2）| `blueprint/engine.py` + `event/statemachine.py`（Decider 半实现）| ⚠️ |
| 消息总线（NATS）| `event/nats_bridge.py` HybridEventBus | ⚠️ **P0: 无限重连阻塞启动** |
| 存储抽象（StorageLayer）| `event/storage.py`（Hot/Warm/Cold 三件套）| ✅ 类实现（非孤儿，见持久化勘误）|
| 可观测性（trace_id）| `event/tracer.py` PipelineTracer + `observability/` | ⚠️ 双套并存 |
| 任务调度（P0-P3 优先层）| 无对应实现 | ❌ |
| **EventBus 接线**（10 链→publish）| on_event 仍串行（on_event_sm 半状态机）| ❌ |

> 印证: Runtime Kernel 自评"消息总线 20%/调度 10%/可观测 5%"完全准确——
> 这正是执行层 DEEP_AUDIT 的 P0-1/P0-2 实锤（NATS 未真正接上 + on_event 递归）。

---

## 五、执行业务流精读（FLOW_EXECUTION_INTERNAL.md 164 + FLOW_EXECUTION_OVERALL.md 248）

### 5.1 内部闭环（ExecutionEngine + PlanGate）

```
单次执行: LLM Plan → PlanGate.create_checkpoint（逐步骤风险评估:
  first_use→requires_review / confidence<0.6→requires_review）
  → 前端审批（批准/修改参数/拒绝）→ ExecutionEngine.execute_batch（read/edit/bash/write）
  → 归约

异常路径: 约束拦截(BLOCKED) / 超时(TIMEOUT 不阻塞) / 用户拒绝(回到 LLM 重规划) /
  DRY_RUN（约束检查+工具验证不产生副作用）

行为学习闭环: 用户审批→PlanGate.record_approval_pattern→BehaviorGraphBridge.
  record_observation→下次同类操作不再 requires_review（除非违反约束/置信低）
  用户拒绝→CorrectionJournal.record→漂移检测→参数 shift（更保守）

状态机: PlanGate{CREATED→PENDING_REVIEW→APPROVED→EXECUTING→COMPLETED|REJECTED|ADJUSTED}
  Execution step{PENDING→RUNNING→SUCCESS|FAILED|BLOCKED|TIMEOUT} + stop_on_error 配置
```

### 5.2 整体业务流（七棵树协同端到端）

```
流一: 子Agent 派生（LLM 元认知综合判断: complexity/context/thresholds/tools/constraints/
  behavior_hints/confidence → {action:"split", sub_agents[]}）
流二: 子树并行执行 + 查询驱动（pointer→约束/偏好；query→活跃节点/双方案/L5）
流三: MetaTree 归约（重要性评估→合并次数→归约→产出 learning_points）
流四: 归档+回档+ReAct 重试（达标归档 / 明确错误重试 Max3 / 模糊降温度 /
  信息不足派生检测 Agent；回档=REOPENED 保留原节点不可变）
流五: 跨树冲突裁决（RelationSubstrate 映射发现→MetaTree 裁决: 查 Behavior/Profile→
  notify PlanGate→用户批准→Behavior 例外+Constraint 白名单）+ 外部工具融合
  （OpenCode/Codex 归一化→LLM 去重融合→AssociationTree 写入）

端到端时序示例: 8.2s 总耗时（含 5s 用户审批）
```

### 5.3 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| ExecutionEngine 7 工具 | `execution/engine.py`（bash/read/write/edit/glob/grep/image）| ✅ |
| PlanGate | `blueprint/` PlanGate（蓝图审计已覆盖）| ✅ |
| 约束拦截 | `execution/permissions.py` + `tree_manager.py` ConstraintTree | ✅ |
| DRY_RUN/超时 | `execution/engine.py`（timeout/trunc）| ✅ 部分 |
| 行为学习闭环 | `behavior/` + CorrectionJournal | ✅ |
| 子Agent 派生/并行/归约 | `execution/tree_manager.py` spawn_sub_agent + `execution/pipeline.py` | ✅ 类实现 |
| 回档/ReAct | `execution/closure.py` + 行为链 ReActRetryEngine | ✅ |
| 外部工具归一化 | `adapter/openclaw.py`（rg 已见）| ⚠️ 待核对 |
| **主路径接线** | 以上全部挂 agent_native A 路径 / bootstrap_v6；CLI 主路径（start_engine→runtime）未挂 | ⚠️ |

> 结论: 执行层业务流（PlanGate/七棵树/子Agent/归约/回档）的组件**几乎全部已实现**，
> 但集中在 agent_native（A 路径）；CLI/API 主路径（B 路径 runtime/engine）未使用它们——
> 与执行层 DEEP_AUDIT"execution/ 未进 CLI 主路径"一致。

---

## 六、认知运行时精读（DESIGN_COGNITIVE_RUNTIME.md，318 行，v2.0）

### 6.1 设计核心

```
v1.0→v2.0 修订:
  12 状态线性 Pipeline → CognitiveScheduler 优先级调度（真实推理是 Retrieve⇄Reason⇄Reflect 循环）
  Workspace Stack → WorkspaceGraph（并行子任务；Stack=单 child 特例）
  Observer 包含 Workspace → Observer=CPU, Workspace=Process（OS 类比）
  +ExecutionTrace（trace→replay→debug→meta-learn）

CognitiveScheduler: next() 按 workspace 状态动态生成任务
  （INIT→LOAD / LOADED→PERCEIVE / conf<0.3→RETRIEVE 或 EXPAND /
  单假设→EXPAND / 无推理→REASON / 无反思→REFLECT / conf>0.7→COMMIT / DONE→DESTROY）
  任务类型: PERCEIVE/RETRIEVE/EXPAND/REASON/REFLECT/VERIFY/COMMIT

OS 类比表: CPU=Observer / Process=Workspace / Scheduler=CognitiveScheduler /
  Context Switch=切 perspective / Syscall=Commit / Core Dump=ExecutionTrace /
  fork=push_workspace / wait=merge_results

ExecutionTrace: replay（重放验证一致性）/ debug_path（回溯诊断）/ summary
```

### 6.2 代码对照（实锤）

| 设计 | 代码 | 状态 |
|---|---|:--:|
| CognitiveScheduler | `v4/cognitive_scheduler/`（1,659L 完整认知调度系统）| ✅ 类实现 |
| WorkspaceGraph | `v4/cognitive/workspace.py`（CognitiveWorkspace/WorkspaceGraph）| ✅ |
| ExecutionTrace | `v4/cognitive/workspace.py:109` + `state/execution_trace.py:17` ExecutionTraceV3 | ✅ |
| Observer | `v4/cognitive_scheduler/models.py` Worker/WorkerPool/PathStateMachine | ⚠️ 近似 |
| run 主循环 | `v4/cognitive/runtime.py:18` run_cognitive_loop | ⚠️ 调用方待确认 |

> 结论: v2.0 认知运行时组件（Scheduler/WorkspaceGraph/Trace）均有类实现，
> 但生产主路径未接入（与 B1 状态演化/MetaConsumer 未接线同型）。

---

## 七、执行层设计精读完成度（8/8，含元认知 B1 交叉）

| # | 文档 | 核心结论 |
|---|--:|---|
| 1 | BUSINESS_CHAIN_STATE_MACHINE | Decider 串行化防广播风暴；GlobalDecider 类有但 engine 未调用 |
| 2 | DESIGN_GLOBAL_STATE_MACHINE | Command→Event→State + 三板斧；双决策器并存未成主路径 |
| 3 | DESIGN_EXECUTION_LAYER | 七棵树/查询驱动/子Agent/归约——组件几乎全实现，挂 A 路径 |
| 4 | DESIGN_RUNTIME_KERNEL | 内核级 OS 定位；自评基础设施 5-50% 落地——实锤准确 |
| 5 | FLOW_EXECUTION_INTERNAL | PlanGate 内部闭环 + 行为学习——组件已实现 |
| 6 | FLOW_EXECUTION_OVERALL | 七棵树端到端流程——A 路径可用，B 路径未挂 |
| 7 | DESIGN_COGNITIVE_RUNTIME | CognitiveScheduler/WorkspaceGraph/Trace——类实现未接主路径 |
| 8 | DESIGN_STATE_EVOLUTION_SYSTEM | （元认知 B1 已精读）Mind/ExecutionTraceV3 类齐引擎未接线 |

> 执行层两轮审计完成（AUDIT_ENTRY + DEEP_AUDIT + DESIGN_FULL_READ 七节）。
> 核心结论: **执行层"想法完整、组件齐备、但双路径分裂（A 挂了 B 没挂）+ 2 个 P0
> （NATS 无限重连 / on_event 递归）+ 双决策器并存**。
