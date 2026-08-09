# 执行层（StateMachine + Runtime + Execution）全面审计 — 第一轮（代码现状盘点）

> 日期: 2026-08-03 | 范围: `core/agent/event/`（StateMachine 宿主 14 文件）+
> `core/agent/runtime/engine.py`（64.8KB CognitiveRuntimeEngine）+
> `core/agent/execution/`（9 文件，工具执行引擎）+
> 关联: `core/agent/events/`（旧 EventBus，与 `event/` 并存）
> 结论先行: **执行层是三套体系并存的宿主层** —— ① `event/statemachine.py` 8 阶段
> DeciderStateMachine（有 3 个阶段无 handler: PLANNING/CONTEXT/LLM，且 DONE/IDLE 注册缺失）；
> ② `runtime/engine.py` 是 v6 主宿主（真接线 49+ 子系统）；③ `execution/` 工具执行引擎
> 挂在 orchestrator/bootstrap_v6（A 路径），CLI 主路径通过 `start_engine` 走 runtime/engine。
> **测试实锤: `event/tests/test_pluggable.py` 卡死（NATSBridge 无服务器无限重连）,
> `test_e2e.py` 卡死（start_engine 全链路）——执行层测试不绿且有两处环境/设计缺陷。**

---

## 一、文件清单与体量

### 1.1 `core/agent/event/`（StateMachine 宿主，14 源码 + 4 测试）
| 文件 | 体量 | 定位 |
|---|--:|---|
| `statemachine.py` | 7.4KB | PipelinePhase(12) + STATE_TRANSITIONS + DeciderStateMachine |
| `handlers.py` | 14.9KB | register_all_handlers（8 个阶段 handler 注册）|
| `event_bus.py` | 9.6KB | Event + Subscription + EventBus（pub/sub）|
| `subscribers.py` | 8.7KB | 7 个 Subscriber + wire_subscribers |
| `closure.py` | 16.2KB | SubprocessRunner/HotReloader/RateGuard/CascadeDetector/CapabilityGuard |
| `cognitive_loop.py` | 9.6KB | BehaviorLearner/MetaReviewer/CognitiveLoop |
| `production.py` | 10.7KB | SLAWatchdog/CircuitBreaker/ParallelDispatcher/GracefulShutdown |
| `tracer.py` | 15.2KB | PipelineTracer/TraceStore/MetricsCollector |
| `scheduler.py` | 8.7KB | EventScheduler（被动 tick + 定时器）|
| `storage.py` | 13.3KB | HotStore/WarmStore/ColdStore/StorageLayer（孤儿，见持久化审计）|
| `pluggable.py` | 12.8KB | ChromaBridge/NATSBridge/OTelBridge（⚠️ NATS 无限重连）|
| `nats_bridge.py` | 7.1KB | HybridEventBus（NATS 混合）|
| `redis_otel.py` | 8.3KB | Redis/OTel 集成 |
| `discourse_gaps.py` | 6.9KB | TopicBacktracker/FormatRouter |

### 1.2 `core/agent/runtime/`（v6 主宿主）
| 文件 | 体量 | 定位 |
|---|--:|---|
| `engine.py` | 64.8KB | **CognitiveRuntimeEngine（主宿主，49+ 子系统）** |
| `adapter.py` | 6.3KB | RuntimeAdapter/RuntimeContext/AdapterResult |
| `config.py` | 3.8KB | RuntimeConfig/PathConfig/load_runtime_config |
| `async_dispatch.py` | 3.0KB | 异步分发 |
| `event_log_adapter.py` | 5.1KB | 事件日志适配 |
| `p1_resolver.py` / `p3_resolver.py` | 5.5+5.9KB | 解析器 |

### 1.3 `core/agent/execution/`（工具执行引擎）
| 文件 | 体量 | 定位 |
|---|--:|---|
| `engine.py` | 12.0KB | ExecutionEngine（bash/read/write/edit/glob/grep/image）|
| `pipeline.py` | 18.3KB | ExecutionPipeline（任务链）|
| `tree_manager.py` | 13.2KB | 8 类 AgentTree（Discourse/Execution/Constraint/Association/Behavior/Meta/Profile）|
| `closure.py` | 11.9KB | NodeLifecycle/CausalTracer/UserInLoop/ReActor |
| `permissions.py` | 21.9KB | PermissionEnforcer（安全/护栏）|
| `sandbox.py` | 16.1KB | FileSandbox |
| `semantic_diff.py` | 17.8KB | SemanticDiffer |
| `server.py` | 5.7KB | 执行服务 |
| `normalizer.py` | 8.5KB | 归一化 |

---

## 二、StateMachine 现状（实锤）

### 2.1 阶段与转移
```
PipelinePhase: IDLE → PCR → INTENT → PLANNING → CONTEXT → LLM → DISCOURSE →
               BEHAVIOR → META → PROFILE → PERSIST → ASSOCIATION(补丁) → DONE
STATE_TRANSITIONS 主表: PCR/INTENT/PLANNING/CONTEXT/LLM/DISCOURSE/BEHAVIOR/META/PROFILE/PERSIST
handlers.py:311-314 运行时补丁: META→ASSOCIATION→PROFILE（把 ASSOCIATION 塞进主流程）
```

### 2.2 handler 注册缺口（实锤）
```
register_all_handlers 注册了 8 个: PCR/INTENT/DISCOURSE/BEHAVIOR/META/PROFILE/PERSIST/ASSOCIATION
**缺: PLANNING / CONTEXT / LLM 三个阶段无 handler**（与上下文审计 C4/C5 一致：
状态机 PLANNING/CONTEXT/LLM 三 phase 无 handler）
→ 跑 run_pipeline 时这 3 个阶段直接落 DEFAULT（无操作）
```

### 2.3 Decider 决策逻辑（浅）
```
decide(): 仅查 result.error/skip + confidence<0.3（pass 占位）→ 实质只走 normal 转移
设计声明（docstring）的 4 项决策能力（跑哪些链/升级/跳过/checkpoint）→ 只实现 1/4
```

### 2.4 生产接线
```
cli/engine.py:274-277   _engine._state_machine = DeciderStateMachine() + register_all_handlers
cli/pool.py:50-54       每 engine 独立 StateMachine
api/v3_session_api.py:259-269   StateMachine unified post-LLM pipeline（sm_results）
runtime/engine.py:648-658       on_event_sm（新路径入口；无 StateMachine 时回退 on_event）
```

---

## 三、Runtime Engine 现状（v6 主宿主）

### 3.1 子系统清单（engine.py 初始化）
```
_behavior_brain（248）/ _association_components（298）/ _association_service（355）/
_profile_runtime（573）/ _meta_consumer（1218 每 5 轮）/ _trace_v3（ExecutionTraceV3）/
_causal_planner（152）/ _perspective_planner（140）/ _planner（224 延迟）/_state_machine（未在此文件创建）
```

### 3.2 已知缺陷（此前审计实锤 + 本轮确认）
```
- _compile_context 幽灵调用（上下文审计 C4: 方法不存在）
- _on_event_continue 死代码（793-1253，约 460 行；on_event_sm 是新路径但旧路径未删）
- PLANNING/CONTEXT/LLM handler 缺失（见 §2.2）
- 新旧双路径并存: on_event（旧串行）vs on_event_sm（新状态机）
```

### 3.3 测试
```
runtime/tests/test_behavior_causal_integration.py  ✅ 14 passed
```

---

## 四、Execution 工具引擎现状

### 4.1 生产接线
```
orchestrator/bootstrap_v6.py:196-239   AgentTreeManager + ExecutionEngine + ExecutionPipeline +
                                       FileSandbox + PermissionEnforcer + SemanticDiffer + ReActor
orchestrator/agent_native.py:364-366   延迟导入（A 路径）
execution/server.py:31                  ExecutionEngine + ExecutionBridge
```
→ CLI 主路径（start_engine → runtime/engine）**不挂 execution/**；
execution/ 主要服务 agent_native（orchestrator A 路径）与 server。

### 4.2 与 StateMachine 的关系
```
execution/closure.py 的 UserInLoop 依赖 plan_gate + behavior_tree + parameter_registry
tree_manager 的 MetaTree = 元认知仲裁/审计轨迹/综合（与 meta 模块接口待核查）
→ 第二轮需确认 execution/ 是否被 v6 runtime 调用，还是仅 agent_native 专用
```

---

## 五、测试现状（实锤）

```
event/tests/test_storage.py        ✅ 21 passed
event/tests/test_subscribers.py    ✅ 8 passed
event/tests/test_scheduler.py      ✅ 14 passed
event/tests/test_pluggable.py      ❌ 卡死（NATSBridge 无服务器无限重连，已探针实锤 60s+）
event/tests/test_e2e.py            ❌ 卡死（start_engine 全链路启动后无法结束）
runtime/tests                       ✅ 14 passed
```

**test_pluggable 卡死根因（探针实证）:**
```
NATSBridge.connect() → nats 客户端对 127.0.0.1:4222 无限重试（每次 8s 超时）
→ asyncio.run 永不返回。nats aio client 的 _select_next_server 循环无最大重试。
→ 生产路径若 HybridEventBus/NATSBridge 被误接会无限阻塞 —— P0 级防御缺口。
```

**test_e2e 卡死根因（待确认）:** `start_engine(provider_type="mock")` 启动后
（子系统 49+）测试主体执行完毕，但进程不退出 —— 疑似后台线程/atexit 钩子未清理。

---

## 六、实锤线索汇总（第一轮）

1. **StateMachine 是「半实现宿主」**: 12 阶段定义完整，但 3 阶段无 handler、
   Decider 决策 4 项只实现 1 项、ASSOCIATION 靠运行时补丁塞入。
2. **双 EventBus 并存**: `events/event_bus.py`（旧，meta_subscriber 用）
   vs `event/event_bus.py`（新，handlers/closure 用）——同型分裂问题。
3. **新旧流水线双路径**: `on_event`（旧串行 ~460 行死代码）vs `on_event_sm`（新状态机）。
4. **execution/ 与 event/ 存在职责重叠**: 两者都有 closure（event/closure.py vs execution/closure.py）、
   都有树/权限/沙箱概念——第二轮需确认边界。
5. **NATSBridge 无限重连 = P0 防御缺陷**（test_pluggable 卡死实证）。
6. **test_e2e 进程不退出** = 全链路启动/清理缺陷（第二轮深挖）。
7. **runtime/engine.py 64.8KB 巨型文件** = 宿主承担过多职责（与 topic_tree manager_v2 44.8KB
   同型巨文件问题）。

---

## 七、待第二轮确认清单

- [ ] 设计文档: `BUSINESS_CHAIN_STATE_MACHINE.md` + `DESIGN_GLOBAL_STATE_MACHINE.md` +
  `DESIGN_EXECUTION_LAYER.md` + `DESIGN_RUNTIME_KERNEL.md` + `FLOW_EXECUTION_INTERNAL.md` +
  `FLOW_EXECUTION_OVERALL.md` + `v3.0/DESIGN_COGNITIVE_RUNTIME.md` +
  `v3.0/DESIGN_STATE_EVOLUTION_SYSTEM.md` 精读
- [ ] on_event（旧）vs on_event_sm（新）双路径完整对照
- [ ] _compile_context 幽灵调用 + PLANNING/CONTEXT/LLM handler 缺失的修复面
- [ ] execution/ vs event/ 职责边界（closure/tree/permissions 重叠）
- [ ] NATSBridge 无限重连修复方案
- [ ] test_e2e 进程不退出根因（后台线程/atexit）
- [ ] StateMachine ↔ 10 链的完整映射（哪些链走状态机、哪些走 subscribers）
- [ ] runtime/engine 拆分建议（64.8KB 巨文件）

---

## 八、勘误（深层次复核后）

> 见 `docs/only/execution/DEEP_AUDIT_20260803.md`。修正 2 处:
> ① `test_e2e`/`test_pluggable` 卡死根因 = NATS 无限重连（生产 P0-1），非「进程不退出」；
> ② `on_event` 不是旧串行——它是 `on_event_sm` 的 wrapper（旧串行在 `_on_event_continue`，
> 460 行零调用方死代码）。新实锤 P0-2: 纯 runtime engine `on_event` 无限递归
> （无 `_state_machine` 时 on_event ↔ on_event_sm 互调）。
