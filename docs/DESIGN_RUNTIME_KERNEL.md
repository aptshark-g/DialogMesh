# DialogMesh Runtime Kernel — 架构设计

> v1.0 | 2026-07-29
> 目标: 从 "蓝图好但执行弱" → "内核级 Agent OS"
> 对标: Linux Kernel + Erlang BEAM + LangGraph

---

## 一、领域成熟度

**这个领域非常成熟。** Agent 编排的工程模式已被充分验证：

| 成熟部分 | 现有方案 | 我们的对齐度 |
|----------|---------|:---------:|
| 状态机 | LangGraph StateGraph, XState | 50% — DAG有schema无执行 |
| 消息总线 | NATS, RabbitMQ, Kafka | 20% — EventBus设计在文档里没接 |
| 任务调度 | Celery, Temporal, Prefect | 10% — 无调度器 |
| 可观测性 | OpenTelemetry, LangSmith | 5% — PipelineTracer没接 |
| 持久化 | SQLite+WAL, Redis, Postgres | 40% — JSON文件直写 |
| 模块热加载 | Linux kmod, Erlang hot code swap | 30% — 注册表有拓扑但无热重载 |

**结论：缺的不是想法，是基础设施落地。我们不需要重新发明这些——需要的是把已选的方案（NATS/SQLite/ChromaDB）真正接上。**

---

## 二、Linux Kernel 模式映射

Linux 内核的每个核心概念在 DialogMesh 中都有天然映射：

```
Linux Kernel                DialogMesh Runtime
─────────────────────────────────────────────────
Process (task_struct)   →   Subsystem (37个)
Scheduler (CFS)         →   BlueprintEngine + Decider
IPC (pipe/signal/shm)   →   EventBus (NATS pub/sub)
VFS (virtual filesystem)→   StorageLayer (JSON/SQLite/ChromaDB)
Syscall (stable ABI)    →   CLI commands (237个，DM协议)
kmod (模块加载)          →   SubsystemRegistry
Watchdog                →   HealthCheck + PipelineTracer
cgroups (资源限制)       →   TokenBudget + RateLimiter
SELinux (安全)          →   CapabilityModel + Sandbox
```

**核心洞察：Linux 不是"设计"出来的，是 30 年迭代出来的。我们不需要一步到 Linux 强度，需要的是一个可迭代的内核架构框架。**

---

## 三、Runtime Kernel 四大组件

### 3.1 调度器 (Scheduler) — BlueprintEngine v2

```
当前: BlueprintEngine.build() → DAG → 串行执行
目标: BlueprintEngine.build() → DAG → Decider调度 → EventBus并行 → 结果汇聚

优先级层:
  P0 (REALTIME)  — PCR路由, 安全约束检查 (<10ms)
  P1 (INTERACTIVE)— 意图解析, 上下文编译 (<100ms)
  P2 (BATCH)     — discourse树, 行为图, 关联链 (<1s)
  P3 (IDLE)      — OCEAN, cold压缩, meta审计 (后台)
```

**实施：Decider状态机的 Tick 机制已存在（`_decider._tick`），只需将其从"记录"升级为"调度"。**

### 3.2 消息总线 (EventBus) — NATS 接入

```
当前: on_event 中 10 条链串行调用
目标: EventBus 发布事件 → 各子系统订阅 → 并行处理 → 结果回写

关键升级:
  1. 事件定义标准化 (EventType enum → JSON schema)
  2. 订阅注册 (每个子系统声明自己关心的事件)
  3. 并行执行 (同一 tick 内，无依赖的 handler 并发)
  4. 背压处理 (队列满 → 降级 → 告警)
```

**实施：NATS 已在 DESIGN_EVENTBUS_V2.md 中选定。只需将 `on_event` 中的链式调用改为 `event_bus.publish()`。**

### 3.3 存储抽象 (StorageLayer)

```
当前: 每个端点自己 open("data/xxx.json")
问题: 无事务、无查询、路径散落、跨进程不一致

目标:
  StorageLayer
  ├─ HotStore  (内存 dict)        — 当前会话状态
  ├─ WarmStore (SQLite+WAL)       — 行为边、关联链、事件日志
  └─ ColdStore (JSON/ChromaDB)    — discourse摘要、语义对象、历史
```

**实施：SQLite 已有（EventLogDB），ChromaDB 已在设计文档。只需统一接口。**

### 3.4 可观测性 (Observability)

```
当前: PipelineTracer 类存在但未接入
目标: 每条消息一个 trace_id，贯穿所有子系统

trace_id → PCR路由(5ms) → Intent解析(45ms) → LLM调用(15s)
         → Discourse树更新(2ms) → Behavior边记录(1ms)
         → OCEAN分析(5ms) → 持久化(3ms)

输出: Prometheus metrics + JSON trace log
```

---

## 四、不自研的决策

| 组件 | 自研? | 理由 |
|------|:----:|------|
| 消息总线 | ❌ 用 NATS | 成熟、高性能、已有设计文档 |
| 持久化 | ❌ 用 SQLite+ChromaDB | SQLite 已有 WAL，ChromaDB 是向量标准 |
| 调度器 | ✅ 自研 | LangGraph/CrewAI 的调度和我们的 7-tree 模型不兼容 |
| 状态机 | ✅ 自研 | Blueprint DAG + Decider Tick 是独特设计 |
| 可观测性 | ❌ 用 OpenTelemetry | 标准化、生态好 |
| 安全 | ⚠️ 混合 | Gateway 用现有，内部沙箱自研 |

**核心原则：基础设施用成熟方案，业务编排自研。这是 Linux 的成功模式——内核自研，驱动接口标准化。**

---

## 五、实施路径 (4周)

```
Phase 1 (本周): EventBus 接线
  → on_event 中 10 链 → EventBus.publish() + 订阅
  → 验证: 一条消息触发多个 handler 并行执行

Phase 2 (下周): 调度器升级
  → Decider Tick → 优先层 + 超时 + 重试
  → 验证: P0 约束检查在 10ms 内完成

Phase 3 (第3周): 存储抽象 + 持久化统一
  → SQLite 统一存储层 + ChromaDB 向量查询
  → 验证: 跨进程读写一致

Phase 4 (第4周): 可观测性 + 生产化
  → PipelineTracer → OpenTelemetry → 指标面板
  → 验证: 每条消息可完整追踪
```

---

## 六、与 LangGraph 的差异定位

LangGraph 做的是**通用 Agent 编排**。我们做的是**认知 Agent OS**。

| | LangGraph | DialogMesh Runtime |
|---|---|---|
| 定位 | Agent 框架 | 认知操作系统 |
| 核心 | StateGraph 状态机 | 7-Tree + Blueprint DAG |
| 用户画像 | 无内置 | OCEAN + MBTI 嵌入式分析 |
| 对话理解 | 无内置 | DiscourseBlockTree + EDUs |
| 工具生态 | LangChain 工具 | ToolRegistry 3级自主 |
| 部署 | Python library | Gateway + Backend + CLI |
| 目标用户 | AI 工程师 | 需要深度认知追踪的用户 |

**我们的差异化不是"更好"，是"更垂直"——深挖对话认知分析而非通用编排。**

---

## 七、Linix 对标诚实评估

| Linux Kernel 特性 | 我们能达到吗 | 需要多久 |
|---|---|---|
| 进程隔离 | ✅ 可以 (subprocess) | 1-2月 |
| CFS 调度 | ✅ 可以 (Decider) | 2-3周 |
| IPC 完整性 | ✅ 可以 (NATS) | 1周 |
| VFS 抽象 | ✅ 可以 (StorageLayer) | 2周 |
| Syscall ABI | ⚠️ 部分 (CLI 需版本化) | 1月 |
| kmod 热加载 | ⚠️ 需要进程重启 | 2月 |
| cgroups | ✅ 可以 (RateLimiter) | 1周 |
| SELinux | ⚠️ 需要沙箱升级 | 2月 |

**结论：能达到 Linux 60-70% 的架构强度，但需要 2-3 个月系统化推进，不是一周的事。**
