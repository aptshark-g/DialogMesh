# DialogMesh v6 — 深度评估 & 下一轮实施计划

> 2026-07-29 · 概念覆盖→生产深度差距分析

---

## 一、评估方法论

概念覆盖 ≠ 生产就绪。以下评估按三层：
- **L1 骨架** (概念实现，能跑) — 当前状态
- **L2 肌肉** (深度实现，可靠) — 下一轮目标
- **L3 骨骼** (生产级，高可用) — 远期目标

---

## 二、八大组件深度差距

### 2.1 SubprocessRunner (进程隔离)

| 层级 | 能力 | 状态 |
|:----:|------|:----:|
| L1 | subprocess.Popen, stdin/stdout JSON | ✅ |
| L2 | 进程池复用, 健康检查, 崩溃自动重启 | ❌ |
| L2 | 资源限制 (memory/time per subprocess) | ❌ |
| L2 | 优雅关闭 (graceful shutdown) | ❌ |
| L3 | 跨进程共享内存 IPC | ❌ |
| L3 | 进程级 cgroups 隔离 | ❌ |

**下一轮: 进程池 + 健康监控 + 自动重启 (~200行)**

### 2.2 DeciderScheduler (CFS调度)

| 层级 | 能力 | 状态 |
|:----:|------|:----:|
| L1 | P0-P3 + vruntime排序 + 线程抢占 | ✅ |
| L2 | 跨会话公平 (non-work-conserving) | ❌ |
| L2 | I/O等待补偿 (休眠进程醒来时优先) | ❌ |
| L2 | 饥饿预防 (最低vruntime保障) | ❌ |
| L3 | deadline调度 (实时任务SLA) | ❌ |
| L3 | 多核并行 (process pool per priority) | ❌ |

**下一轮: I/O补偿 + 饥饿预防 (~150行)**

### 2.3 EventBus + NATS

| 层级 | 能力 | 状态 |
|:----:|------|:----:|
| L1 | 内存EventBus + 6订阅者 | ✅ |
| L1 | NATS bridge (可选依赖) | ✅ |
| L2 | NATS实际集成测试 | ❌ |
| L2 | at-least-once投递 + 消息重放 | ❌ |
| L2 | Subject通配符路由 (* / > 匹配) | ❌ |
| L3 | NATS集群 + JetStream持久化 | ❌ |
| L3 | 死信队列 + 背压降级策略 | ❌ |

**下一轮: NATS集成测试 + subject通配符 (~100行)**

### 2.4 StorageLayer

| 层级 | 能力 | 状态 |
|:----:|------|:----:|
| L1 | Hot/Warm/Cold + TTL+SQLite+JSON | ✅ |
| L2 | 查询优化 (索引, 预编译语句) | ❌ |
| L2 | 迁移支持 (schema migration) | ❌ |
| L2 | 备份/恢复 | ❌ |
| L2 | ChromaDB实际向量查询集成 | ❌ |
| L3 | 读写分离 (read replicas) | ❌ |
| L3 | WAL checkpoint管理 | ❌ |

**下一轮: 索引 + ChromaDB集成 (~150行)**

### 2.5 PipelineTracer

| 层级 | 能力 | 状态 |
|:----:|------|:----:|
| L1 | auto-record + SSE streaming | ✅ |
| L2 | 全链路trace_id传播 (跨子系统) | ❌ |
| L2 | Span层级 (parent→child关系) | ❌ |
| L2 | 采样策略 (全量/比例/错误优先) | ❌ |
| L3 | OpenTelemetry导出 (Jaeger/Prometheus) | ❌ |
| L3 | 保留策略 + 自动压缩 | ❌ |

**下一轮: 全链路传播 + Span树 (~200行)**

### 2.6 HotReloader

| 层级 | 能力 | 状态 |
|:----:|------|:----:|
| L1 | importlib.reload单模块 | ✅ |
| L2 | 依赖追踪 (级联重载) | ❌ |
| L2 | 状态迁移 (保留内存状态) | ❌ |
| L2 | 原子替换 (swap后旧实例才销毁) | ❌ |
| L3 | 热加载回滚 (失败自动恢复) | ❌ |

**下一轮: 依赖追踪 + 状态迁移 (~150行)**

### 2.7 TokenBucket (RateGuard)

| 层级 | 能力 | 状态 |
|:----:|------|:----:|
| L1 | 9阶段独立限流 | ✅ |
| L2 | 级联故障检测 (1个阶段慢→上游限流) | ❌ |
| L2 | 自适应速率 (根据成功率自动调整) | ❌ |
| L2 | 全局限流 (跨引擎实例) | ❌ |
| L3 | 断路保护 (CircuitBreaker) | ❌ |

**下一轮: 级联检测 + 自适应 (~180行)**

### 2.8 CapabilityGuard

| 层级 | 能力 | 状态 |
|:----:|------|:----:|
| L1 | 静态allow/deny + 10子系统 | ✅ |
| L2 | 操作审计日志 (每次deny记录) | ❌ |
| L2 | 动态提权 (临时grant) | ❌ |
| L2 | 继承/角色权限 (role-based) | ❌ |
| L3 | 文件沙箱集成 (DESIGN_FILESANDBOX) | ❌ |

**下一轮: 审计日志 + 角色权限 (~120行)**

---

## 三、超越八大组件 — 架构级差距

### 3.1 State Machine Engine (当前: 0%)

LangGraph的核心竞争力:
- StateGraph带类型状态迁移 — 我们没有
- conditional_edges动态路由 — 我们没有
- Send API fan-out并行 — 我们没有
- interrupt() HITL暂停 — 我们没有
- Thread级checkpoint — 我们没有

**我们的DAG只建不跑。BlueprintEngine.build()输出DAG但执行层是串行的。**

### 3.2 Multi-Agent Coordination (当前: 10%)

7-Tree设计是并行的但实际没有任何协调协议:
- 无leader选举
- 无任务委托
- 无共识机制
- 无agent间通信协议

每个树独立运行，互不知道对方状态。

### 3.3 Streaming/Real-time (当前: 20%)

- SSE仅用于trace，不用于LLM响应
- 无WebSocket双向通信
- 前端轮询v6端点(2s间隔)而非事件驱动
- LLM响应是完整返回而非token-by-token流式

### 3.4 Testing Gap (当前: 15%)

- 71 tests全是unit/mock
- 无integration test (真实LLM调用)
- 无performance benchmark
- 无fault injection
- 无chaos testing
- 无E2E test

### 3.5 API Completeness (当前: 60%)

v3_session_api的send_message绕过我们新做的EventBus+Scheduler+Storage管线。两套管线并存：
- v3_session_api: AgentOrchestrator直接调Gateway
- engine.on_event: 我们新做的EventBus→Scheduler→Subscribers→Storage

这两个管线没有统一。

---

## 四、下一轮实施优先级 (按ROI排序)

| 优先级 | 项目 | 工作量 | ROI |
|:------:|------|:------:|:---:|
| P0 | 统一双管线 (v3_api走EventBus) | 2h | 🔴 当前最大浪费 |
| P1 | PipelineTracer全链路传播 | 2h | 🟡 调试必备 |
| P2 | State Machine Engine | 4h | 🟡 架构核心 |
| P3 | 级联检测 + 自适应限流 | 2h | 🟢 生产必须 |
| P4 | NATS实际集成测试 | 2h | 🟢 性能提升 |
| P5 | ChromaDB向量查询集成 | 1.5h | 🟢 语义检索 |
| P6 | SubprocessRunner进程池 | 1.5h | 🟢 隔离性 |
| P7 | HotReloader依赖追踪 | 1.5h | 🟢 运维效率 |
| P8 | CapabilityGuard审计日志 | 1h | 🟢 安全合规 |
| P9 | Streaming LLM token-by-token | 2h | 🟡 用户体验 |
| P10 | E2E + Integration测试 | 3h | 🟡 质量保障 |

**总计: ~22h (约3个工作日)**

---

## 五、建议实施顺序

```
第1天 (8h):
  Morning:  P0 统一双管线 (最关键的架构修复)
  Afternoon: P1 PipelineTracer全链路 + P2 State Machine骨架

第2天 (8h):
  Morning:  P3 级联检测 + P5 ChromaDB
  Afternoon: P4 NATS测试 + P6 SubprocessPool

第3天 (6h):
  Morning:  P9 Streaming + P7 HotReload依赖追踪
  Afternoon: P8 审计日志 + P10 E2E测试框架
```
