# Blueprint 编排 — LLM 动态构建执行图

> 2026-07-26 · 基于前沿研究 + DialogMesh 现有架构

---

## 一、核心理念

**LLM 是图的构建者，不是图的执行者。**

```
❌ 硬编码线性管道:
  user_input → PCR → Intent → Context → LLM → reply
  10 链调用顺序写死在 agent_native.py

✅ LLM 动态构建 DAG:
  user_input → PCR(意图分析) → LLM 选 Blueprint → 动态构建有向图
  图节点 = 链/模块调用, 边 = 数据依赖
  确定性引擎执行, LLM 在关键节点介入(条件路由/决策分叉)
```

**设计哲学类比**: Linux kernel `make menuconfig`——内核模块成千上万, 但不是全部编译。根据目标(硬件架构/功能需求)选模块, 构建依赖图, 编译。

---

## 二、前沿验证

| 方案 | 核心模式 | 关键引用 |
|------|---------|---------|
| **LangGraph** | StateGraph + Supervisor Pattern + interrupt() | arXiv 2607.19297 |
| **BatchDAG** | LLM 生成类型化 DAG → 确定性引擎执行 | arXiv 2607.18241 |
| **CrewAI** | @start() + @listen() 事件驱动隐式 DAG | CrewAI Flow |
| **Hermes Agent** | ReAct 循环 + Skills + PlanGate | Nous Research |

**共同结论**: LLM 负责"建什么图", 运行时负责"怎么跑图"。

---

## 三、DialogMesh 现有资产

### 3.1 已设计未接的模块

| 模块 | 代码 | 状态 |
|------|------|:----:|
| **Blueprint Engine** (5策略) | `planning/blueprint.py` | ⚠️ 只有 TEMPLATE |
| **SkillRegistry** (意图→蓝图) | `planning/blueprint.py` | ⚠️ 5 个内置技能 |
| **EventBus** (NATS pub/sub) | `event/event_bus.py` | ❌ 10 链仍是线性调用 |
| **7-Tree 并行** | `execution/tree_manager.py` | ❌ 树存在, 没接管线 |
| **PlanGate** (人工审核) | `planning/checkpoint.py` | ❌ 代码有, API 无 |
| **Subgraph Compiler** | `compiler/` | ❌ 176L, 零接入 |
| **Decider 状态机** | `state/` | ❌ 替代 agent_native 的设计 |
| **ReactRetryEngine** (5策略) | `execution/closure.py` | ⚠️ 有代码, 没走管线 |

### 3.2 当前实际跑的

```
v3_session_api.send_message()
  → AgentOrchestrator.process()  (线性硬编码 9 阶段)
  → GET /v6/profile              (stub 画像)
  → POST switch /chat/completions (LLM 直接调用)
  → Phase5: LLM 生成 task_graph  (plan → JSON 数组)
```

**问题**: 
- 10 条链是串行的, 不是 EventBus 并行
- LLM 只被用来做最后一步回复, 没参与图构建
- task_graph 有 schema 但执行层没接

---

## 四、目标架构

```
                    ┌─────────────────────────────────┐
                    │        Blueprint Engine          │
                    │  SkillRegistry.match(intent)     │
                    │  → 选 Blueprint (模板)           │
                    │  → LLM override (加/删/改节点)    │
                    │  → 编译为 DAG (有向无环图)         │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │        Decider (EventBus)        │
                    │  每个 Tick: 检查依赖→发射Task    │
                    │  链 = subscriber, 消费事件        │
                    │  00 PCR ──→ 观察                 │
                    │  01 Discourse ──→ 对话结构         │
                    │  02 Context ──→ 上下文组装         │
                    │  03 Intent ──→ 意图拆分           │
                    │  ...                             │
                    │  所有结果 → EventBus →           │
                    │  Subgraph Compiler → LLM 回复     │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │     PlanGate (人工审核点)         │
                    │  interrupt() → 前端展示          │
                    │  用户 approve/adjust/reject      │
                    │  → CorrectionJournal → 学习      │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │     Execution Engine             │
                    │  7-Tree 并行执行                 │
                    │  Sandbox / Permissions / Diff   │
                    │  ReAct 重试 (AUTO_FIX/TEMP/...) │
                    └─────────────────────────────────┘
```

---

## 五、蓝图类型 (5 策略, Blueprint Engine 已有)

| 策略 | 说明 | 适用场景 |
|------|------|---------|
| **RULE_BASED** | 纯规则, 不用 LLM | 已知路径(如"查天气") |
| **TEMPLATE** | 固定模板 + 参数化 | 常见任务(代码审查/搜索) |
| **HYBRID** (默认) | 模板 floor + LLM ceiling | 通用对话→图 |
| **LLM_DRIVEN** | LLM 全权构建图 | 新领域/复杂推理 |
| **RECOVERY** | 失败重试→替换子图 | 执行中异常 |

**当前**: 只用了 TEMPLATE(agent_native 硬编码)。HYBRID/LLM_DRIVEN 未实现。

---

## 六、最小闭环路径 (本周可做)

```
当前起点:
  v3_session_api → agent_native(线性) → switch LLM

Step 1: LLM 选蓝图
  SkillRegistry.match(intent) → 选择 Blueprint 类型
  意图=代码分析 → TEMPLATE:coding_analysis
  意图=通用对话 → HYBRID

Step 2: LLM 构建 DAG
  Blueprint → LLM 加/删节点 → 输出 DAG JSON
  如: [PCR]→[Intent]→[Context→Subgraph]→[LLM回复]

Step 3: EventBus 执行
  Decider 逐 tick 发射 → 各链消费 → 结果汇聚

Step 4: PlanGate 审核
  高风险节点 → checkpoint → 前端展示 → 用户确认
```

---

## 七、与前沿的差距

| 维度 | LangGraph | BatchDAG | DialogMesh 现有 | 差距 |
|------|:---:|:---:|:---:|------|
| 图构造 | ✅ LLM conditional_edges | ✅ LLM 全图 | ⚠️ Blueprint(5策略) | 没让 LLM 建图 |
| 图执行 | ✅ Pregel superstep | ✅ 确定性 DAG 引擎 | ❌ 线性管道 | 需接 EventBus |
| 状态管理 | ✅ TypedDict channels | ✅ 类型化 DAG 边 | ✅ EventLog | 已覆盖 |
| 人机协作 | ✅ interrupt() | ❌ | ✅ PlanGate | 需接 API |
| 并行执行 | ✅ fan-out/fan-in | ✅ 并行 DAG | ⚠️ 7-Tree | 需接 EventBus |
| 子图嵌套 | ✅ SubGraph 编译 | ✅ DAG 递归 | ⚠️ Subgraph Compiler | 需接入 |
| 持久化 | ✅ CheckpointSaver | ✅ | ✅ SHA256 链 | 已覆盖 |

---

## 八、实施优先级

```
P0 (本周): LLM 选 Blueprint + 构建 DAG → EventBus 执行最短路
P1: PlanGate → 前端 task_graph 展示 + 编辑 + 回传
P2: 7-Tree 并行 → Execution Engine (sandbox/permissions/diff)
P3: Subgraph Compiler → 编译上下文子图 → LLM 注入
```
