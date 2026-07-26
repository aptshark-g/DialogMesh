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

---

## 九、谁负责 Blueprint？Meta LLM 的分层角色

### 热路径: Blueprint 的选择者不是 Meta

```
用户输入 → SkillRegistry.match(intent) → 选 Blueprint 策略
         → TEMPLATE / HYBRID / LLM_DRIVEN
         → LLM 调整节点 → 编译为 DAG
```

SkillRegistry 在热路径上——它是**快速模式匹配**（模板+意图），不是 LLM 推理。
决策粒度: 一次请求内完成，延迟预算 <500ms。

### 冷路径: Meta LLM 负责"学"，不负责"跑"

```
每次执行完成 → EventLog 写入
              → Meta 异步消费:
                  - 审计: 本次 DAG 路径是否最优？
                  - 对比: HYBRID vs TEMPLATE 本次谁更好？
                  - 修正: CorrectionJournal → 下次选策略的权重调整
                  - 学习: 新出现意图 → 建议新增 Blueprint 模板
```

Meta 是**异步的第二大脑**——
- 不阻塞请求
- 通过 EventBus 订阅执行结果
- 输出: 影响**下一次 Tick**的策略选择，不是当前请求

### Blueprint 生命周期

```
[SkillRegistry] → 匹配 Blueprint  ← Meta 调整权重
      ↓
[LLM override]  → 调整节点        ← Meta 审计质量
      ↓
[EventBus 执行]  → DAG 跑完
      ↓
[EventLog]       → 持久化
      ↓
[Meta 异步审计]   → 学习 + 修正
      ↓
[下次请求]       → 策略更优
```

---

## 十、执行模式矩阵 — 三个决策粒度

### Level 1: 模板执行 `RULE_BASED / TEMPLATE`

```
LLM 零介入 — 确定性跑模板
适用: 查天气、代码搜索、已知路径
优势: 极快, 零幻觉
风险: 覆盖窄, 新场景 fallback 到 Level 2
```

### Level 2: 单步路由 `HYBRID`（默认）

```
LLM 在分叉点介入: "下一步去哪？"
不建全图 — 每次只决定一步
适用: 复杂分析、多步推理
模式 = LangGraph conditional_edges
优势: LLM 做最小决策单元, 不循环
风险: 局部最优 ≠ 全局最优
```

### Level 3: 全图构建 `LLM_DRIVEN`

```
LLM 建完整 DAG → PlanGate 人工审核 → 执行
适用: 探索性任务、因果推理、新领域
模式 = BatchDAG
优势: 全局视角, 主动性
风险: 迭代多、死循环、质量不可控 ← 见 §十一
```

---

## 十一、高度放权模式 — 主动性的代价

> 为基础讨论，单独展开。关联: L5 因果链设计。

### 现状: 行业为什么都是最小闭环

| 问题 | 具体表现 |
|------|---------|
| **迭代多** | LLM 无限制探索 → 10+ 轮 → 延迟爆炸 |
| **死循环** | 无终止条件 → 同一模式反复 |
| **低效果** | 探索宽但没深度 → 不如模板 |
| **质量漂移** | 每一步自指 → 离初始目标越来越远 |

### 前沿解法对比

| 方案 | 解法 |
|------|------|
| **BatchDAG** | LLM 只建图(一次性), 确定性引擎执行, 不循环 |
| **LangGraph** | conditional_edges 单步决策, 不建全图 |
| **Hermes** | PlanGate 每高风险步骤 checkpoint |
| **CrewAI** | @listen() 事件驱动, agent 只响应不主动 |

**共同结论**: 限制 LLM 的自由度 = 提升可靠性。

### DialogMesh 的定位:

**LLM_DRIVEN 不是默认模式——它是"特殊模式, 人工审核准入"。**

```
LLM_DRIVEN 触发条件(任一):
  - 意图置信度 >0.8 且 策略历史成功率高
  - 因果推理任务 (L5 Causal)
  - 用户手动切换模式

执行保护:
  - PlanGate: 建图后 → 人工审核 → 才执行
  - Budget Gate: 节点数上限 (默认 7)
  - Loop Detector: 重访已执行节点 3 次 → 强制 checkpoint
  - Quality Gate: 执行后 Meta 评分 → 低于阈值 → 降级到 HYBRID
```

### 与 L5 因果层的关系

因果推理的难点不是算概率——是**决定"要探索哪种因果路径"**。
LLM_DRIVEN 在此场景的必要性:
- 因果假设空间爆炸 → 模板覆盖不了
- LLM 主动提出假设 → 建 DAG 验证
- 人类审核假设(不是审核图) → 降低 LLM 的规划负担

这是后续讨论。——标注: §十一 待展开

---

## 十二、三层范式 — 设计→工程→执行

> Agent 认知循环对标人类工程范式。每个阶段独立, 通过结构化契约传递信息。

### 范式映射

```
人类工作方式:                    Agent 执行模式:

设计文档                         发散 + 收束 + 学习
  ├── 发散: 无约束探索               ├── LLM (T=0.8, 无上下文)
  │   - 研究文献/方案                 │   - 提出假设/方案
  │   - 并行多路径                   │   - 给推导和原因
  ├── 收束: 约束过滤                 ├── LLM (T=0.1, 完整上下文)
  │   - 对照约束检查                 │   - 过滤/融合
  │   - 选出可行路径                 │   - 输出: 设计结论
  └── 学习: 外部信息摄入             └── 文献/源码检索
      - 前沿论文                        - arxiv 搜索
      - 开源实现                        - 源码分析
      - 成熟方案                        - 模式提取

工程文档                         约束 + 施工方案
  ├── 约束: 设计→施工翻译           ├── ConstraintTree 检查
  │   - 资源/安全/工期              │   - 7类节点 × 约束推理
  └── 方案: 可执行步骤              └── → 编译为 DAG

实际解决                         确定性执行
  └── 按方案施工                    └── EventBus 跑图
      - 不来回改设计                    - 不循环
      - 一次到位                       - ReAct 重试(3次上限)
```

### 发散+收束 方案对比

| 方案 | 出处 | 模式 | 适用 |
|------|------|------|------|
| **掩盖约束法** | DialogMesh 已有 | 发散LLM 不给上下文 → 收束LLM 给完整上下文 | 设计阶段, 避免上下文锁死 |
| Tree of Thoughts | Yao 2023 | BFS/DFS → 评估 → 回溯 | 多路径探索 |
| Reflexion | Shinn 2023 | 执行→失败→LLM反思→重试 | 学习阶段自我改进 |
| Graph of Thoughts | Besta 2024 | 思维图任意拓扑 → 聚合 | 复杂推理 |
| STILL-ALIVE | arXiv 2024 | LLM 自主文献搜索→假设→验证 | 科学发现循环 |
| DSPy | Stanford 2024 | 程序化调用→自动优化→编译 | Prompt 自动调优 |

### 学习阶段的输入源

```
学习 = Agent 自主获取 + 评估信息质量

来源:
  1. arXiv / 学术论文     → 理论前沿
  2. 开源项目源码          → 实现参考 (NATS/pingora/Git 模式提取)
  3. 成熟框架文档          → 工程验证 (LangGraph/Hermes/CrewAI)
  4. 自身 EventLog         → 历史经验 (什么策略对什么意图有效)
  5. 用户修正历史           → 偏好学习 (CorrectionJournal)

评估:
  - 来源权威性 → 权重
  - 与当前任务相关性 → 优先级
  - 时效性 → 衰减
```

### 工程文档 — 约束层

```
设计输出 → ConstraintTree 检查:
  - 安全约束: 不可逆操作？文件系统边界？
  - 资源约束: 节点数 ≤ 7, 总 token ≤ 预算
  - 依赖约束: 拓扑排序, 无环检查
  - 权限约束: Capability check (reduce-only原则)

→ 编译为执行 DAG
→ 确定性跑, 不回头改设计
```

---

## 十三、成本与质量控制 — 自治化的驾驭

> 不是 token 限制。是控制迭代次数和层级深度。
> 当人不选择时, Profile + Behavior + Meta 代替人做驾驭决策。

### 控制维度 — 用户可调, 但不是调 token

```
可调参数 (用户视角):
  ┌─────────────────────────────────┐
  │ 控制面板                         │
  │                                  │
  │ 探索深度:  [1] [2] [3] [4] [5]   │  ← 发散 LLM 的搜索广度
  │ 验证严格度: [宽松] [标准] [严格]  │  ← 收束阶段的过滤强度
  │ 学习广度:  [关] [核心] [全面]     │  ← 外部信息摄入范围
  │ 决策模式:  [自动] [半自动] [手动] │  ← 人工介入频率
  │                                  │
  │ 默认: 深度2 / 标准 / 核心 / 自动  │
  └─────────────────────────────────┘

底层含义 (映射到架构):
  探索深度 → 发散 LLM 并行分支数 (1-5)
  验证严格度 → 收束 LLM 的 confidence threshold
  学习广度 → arxiv/源码/框架 搜索的 source count
  决策模式 → PlanGate checkpoint 频率
```

### 当人不选择时 — Profile + Behavior + Meta 代替人类

```
                    ┌──────────┐
                    │  用户    │ ← 显式选择 (优先)
                    └────┬─────┘
                         │ 未选择
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   ┌─────────┐    ┌───────────┐    ┌──────────┐
   │ Profile │    │ Behavior  │    │   Meta   │
   │ 画像    │    │ 行为链    │    │ 元认知   │
   └────┬────┘    └─────┬─────┘    └────┬─────┘
        │               │               │
        ▼               ▼               ▼
   探索深度偏好    历史成功率      质量评分趋势
   O: 开放→深    上次 HYBRID    本次 vs 历史
   C: 谨慎→浅    ＞ TEMPLATE    如降级 → 自动调参
   N: 焦虑→严

加权融合 → 生成代理决策:
  - 探索深度: 2 (OCEAN加权)
  - 验证严格度: 标准 (BFI C维度高 → 偏严)
  - 学习广度: 核心 (Meta 评估: 当前领域文献少 → 扩展)
```

### 自调节闭环

```
每次执行 → EventLog
         → Meta 异步评分:
             本次 DAG 质量 vs 历史基线
             如果连续 3 次低于基线:
               → 自动降级: LLM_DRIVEN → HYBRID
               → 自动缩量: 深度 3 → 深度 2
               → 通知用户 (不阻塞)
             如果连续 5 次高于基线:
               → 信任度提升 → 深度可放宽到 3
               → 减少 PlanGate checkpoint 频率
```

### 为什么不是调 token？

| 调 token | 调迭代/层级 | 
|---------|-----------|
| LLM 不可控 (再少 token 也可能跑偏) | 结构性约束 (分支数 = 确定性) |
| 用户不理解 (token = ?) | 用户理解 (深度 2 → 3) |
| 只影响单次调用 | 影响整个图结构和执行策略 |
