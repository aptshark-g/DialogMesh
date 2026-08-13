# 蓝图系统（core/agent/blueprint/）接线调查报告

调查日期：2026-08-13
调查方法：以实际代码 import 关系为准（grep 全仓 `core.agent.blueprint.*` 引用 + 逐处阅读调用上下文），`docs/only/blueprint/` 下文档仅作背景参考。

## 1. 概述

蓝图系统是 DialogMesh 的「任务规划 → DAG 执行 → 学习闭环」子系统：把用户输入构建成 `BlueprintDAG`（节点=认知链/工具链），经 StateMachine 或 BlueprintExecutor 执行，执行结果经 LearningBridge / MetaFeedback 回流为可复用模板与策略权重。

- 规模：`core/agent/blueprint/` 下 19 个非测试 `.py` 文件，共约 **5301 行**；自带 `tests/` 子目录 20 个测试文件约 2811 行。
- 生产入口：`core/agent/api/v3_session_api.py`（v6_app 挂载的主会话 API）、`core/agent/runtime/engine.py`（CognitiveRuntimeEngine 白盒初始化）、`core/agent/event/statemachine.py`（DAG 执行）、`core/agent/llm/task_runner.py` / `tool_loop.py`（v2 执行层）、`core/agent/cli/`（blueprint/decider 子命令）、`core/agent/api/stubs_api.py`（任务执行端点）。

## 2. 模块接线状态总表

状态定义：**已连接**=生产运行路径实际引用；**条件接入**=懒加载/try-except/特定策略或端点触发才生效；**仅测试**=只有测试引用；**孤立**=无人引用。

| 模块 | 功能一句话 | 状态 | 被谁引用（生产） |
|---|---|---|---|
| `__init__.py` (21行) | 包级 re-export（models/skill_registry/llm_dag_builder/engine/meta_feedback/executor/decider） | 已连接（间接） | 任何 `core.agent.blueprint.X` import 都会先执行它（`__init__.py:12-21`）；直接 `from core.agent.blueprint import ...` 仅 tests/test_blueprint_e2e.py:8 |
| `models.py` (137) | BlueprintDAG/Node/Edge/ExecutionAudit 数据结构 | 已连接 | engine/executor/decider 等全部内部模块 + stubs_api.py:235 + task_runner.py:277 + statemachine 测试等 |
| `engine.py` (363) | BlueprintEngine — 按策略构建 DAG | 已连接 | v3_session_api.py:353,686；kernel/dispatch.py:1740；cli/commands/blueprint_cmd.py:7 |
| `skill_registry.py` (432) | 内置/习得 DAG 模板注册与匹配 | 已连接 | engine.py:22、learning_bridge.py:32、meta_feedback.py:22、skill_lifecycle.py:26 |
| `llm_dag_builder.py` (380) | LLM 驱动的 DAG 构建器 | 条件接入 | engine.py:23,177 总是实例化，但只在 HYBRID/LLM_DRIVEN 策略下真正调用（默认 TEMPLATE）；外部直接 import 仅测试 |
| `executor.py` (1190) | BlueprintExecutor — 混合模式 DAG 执行器 | 条件接入 | 仅 decider.py:28 函数内懒 import；生产可达路径只有 stubs_api 的 `POST /task/{sid}/execute`（见 §3.4）。v3_session_api.py:343-345 注释明确其已降级为「校验/回放工具」 |
| `decider.py` (64) | Decider — executor 的薄门面 | 条件接入 | stubs_api.py:234（execute_task 端点，函数内 import）；orchestrator/agent_native.py:384（`process_dag`，但该方法全仓无生产调用方） |
| `protection.py` (251) | 高风险链/执行保护规则 | 已连接（间接） | executor.py:28、intervention.py:26；蓝图外直接引用仅 tests |
| `intervention.py` (195) | 三层介入分级路由（approve/reject） | 已连接 | runtime/engine.py:764（白盒装配）；task_runner.py:102；executor.py:131（懒） |
| `decision_event.py` (180) | 决策变更事件总线（EventLog/Journal 双写） | 已连接 | runtime/engine.py:726；task_runner.py:97（默认内存总线） |
| `permission_engine.py` (237) | 工具权限门（风险分级/shell 链阻断） | 已连接 | statemachine.py:316（tool 节点门）；tool_loop.py:81；v3_common/gates.py:356,372（懒）；decider.py:41,57（懒） |
| `learning_bridge.py` (343) | 学习桥：成功 DAG 沉淀 + 蒸馏原料收集 | 已连接 | runtime/engine.py:779；v3_session_api.py:420 经 `learn_from_execution`；task_runner.py:260（有 trace_store 时） |
| `skill_lifecycle.py` (165) | LEARNED_TEMPLATES 活性状态机 | 已连接 | runtime/engine.py:807（try/except 内，挂到 bridge 的 registry） |
| `heuristic_distiller.py` (381) | 二阶抽象蒸馏器（trace→启发式） | 已连接 | runtime/engine.py:788（嵌套 try，attach 到 LearningBridge）；内部依赖 heuristic_inventory.py:21 |
| `heuristic_inventory.py` (278) | 启发式库存储 | 已连接 | runtime/engine.py:789；heuristic_distiller.py:21 |
| `meta_feedback.py` (263) | 执行复盘回流（ExecutionAudit→策略权重降级） | 已连接 | runtime/engine.py:823；check_degradations 由 engine.py:1041 `_run_meta_consume`（engine.py:2018 触发）调用 |
| `tracer.py` (96) | PipelineTracer — 管线迹写 data/pipeline_traces.jsonl | 已连接 | v3_session_api.py:354 import、:463 `PipelineTracer.record(...)` |
| `code_request.py` (23) | `is_code_request` 编码类请求判定 | 条件接入 | v3_session_api.py:509 — 仅当判定为编码请求才进入 TaskRunner 工具循环分支 |
| `automation.py` (302) | 定时自动化任务（Scheduler/Store，GAP-2） | **仅测试** | 全仓唯一引用：core/agent/blueprint/tests/test_automation.py:17。无任何生产 import |

## 3. 已连接链路的调用链

### 3.1 主会话链路（API → 建图 → 执行 → 学习）

```
FastAPI v6_app (core/agent/api/v6_app.py:36 include v3_session_router)
└─ v3_session_api.py 会话处理
   ├─ Phase 3.5: from core.agent.blueprint.engine import BlueprintEngine   (v3_session_api.py:353)
   │    engine = BlueprintEngine(decision_bus=_dbus, registry=_shared_registry)  (:369)
   │    — registry 与 runtime engine 的 learning_bridge 共享（:361-368）
   ├─ dag → StateMachine.run_dag(dag, context={decision_bus, meta_feedback, ...})  (:399-407)
   │    └─ event/statemachine.py tool 节点分支:
   │         from core.agent.blueprint.permission_engine import PermissionEngine  (statemachine.py:316)
   ├─ 学习注入: _eng.learn_from_execution(dag, ...)  (v3_session_api.py:420)
   │    └─ runtime/engine.py:834 → LearningBridge.learn_from_execution
   ├─ PipelineTracer.record(...)  (v3_session_api.py:463 → tracer.py → data/pipeline_traces.jsonl)
   └─ Phase 5 兜底: BlueprintEngine().build(...)  (v3_session_api.py:686-688)
```

### 3.2 编码请求执行链路（v2 执行层）

```
v3_session_api.py:509  from core.agent.blueprint.code_request import is_code_request
  if is_code_request(req.content):
    └─ llm/task_runner.py TaskRunner (:513 import)
         ├─ DecisionEventBus() 默认内存总线        (task_runner.py:97)
         ├─ InterventionRouter(decision_bus=...)   (task_runner.py:102)
         ├─ _writeback: ExecutionTrace → trace_store (task_runner.py:260, learning_bridge)
         ├─ _writeback: ExecutionAudit → MetaFeedback.consume (task_runner.py:277, models)
         └─ tool_loop._execute_tool_call:
              from core.agent.blueprint.permission_engine import PermissionEngine  (tool_loop.py:81)
```

### 3.3 Runtime 引擎白盒装配（元认知/学习闭环底座）

`runtime/engine.py:_init_whitebox()`（__init__ :262 与 :962 两处调用），全部 try/except 懒装配：

- :726 `DecisionEventBus`（event_log/journal 双写，每轮 attach 刷新）
- :764 `InterventionRouter`
- :779 `LearningBridge` → :788-789 `HeuristicDistiller` + `HeuristicInventory`（attach 到 bridge）→ :807 `SkillLifecycle`（挂到 bridge.registry）
- :823 `MetaFeedback`；:1041 `_run_meta_consume` 调 `check_degradations()`，:2018 触发

入口：`core/agent/cli/engine.py:50 get_engine()` → :89 `CognitiveRuntimeEngine()`；v3_session_api 经 `get_engine()` 取同一引擎（v3_session_api.py:355-357）。

### 3.4 任务执行端点（executor 唯一生产可达路径）

```
v6_app.py:44 include stubs_router
└─ stubs_api.py:227 POST /task/{sid}/execute
     from core.agent.blueprint.decider import Decider        (stubs_api.py:234)
     from core.agent.blueprint.models import BlueprintDAG... (stubs_api.py:235)
     decider.execute(dag)  →  decider.py:28 懒 import BlueprintExecutor(gate_resolver=权限门)
```

注意：`v3_session_api.py:343-345` 注释明确「B2/G1 后 BlueprintExecutor 不再是主执行器，StateMachine 经注册的 phase handler 消费 DAG；executor 保留为校验/回放工具」。

### 3.5 CLI 链路

- `cli/commands/__init__.py:4,15` 注册 `blueprint_cmd.register_cmds` → 提供 `dm blueprint show/build/validate/export/build-hybrid/build-llm/history` 与 `dm decider show/chains/execute`（blueprint_cmd.py:85-105）。
- `cli/entry.py:1153-1162` 分发 `blueprint`/`decider` 命令到 blueprint_cmd 的 cmd 函数。
- `cli/entry.py:1179-1194` `bp`/`dc` 别名 → p9_cmd.py:307+ 的细粒度命令 → `kernel_blueprint_*`（kernel/dispatch.py:1738-1769，函数内懒 import BlueprintEngine）。

### 3.6 门控链路（permission_engine 的另一生产入口）

`v3_common/gates.py:_default_permission_resolver()`（:354-380，函数内懒 import permission_engine）→ `OrchestrationGate` → `DualTrackOrchestrator`，被 `core/agent/service/agent_service.py:31` 与 `async_agent_service.py:35` 引用。

## 4. 未连接 / 仅测试 / 孤立模块

- **`automation.py`（302 行，仅测试）**：定时自动化调度实体（GAP-2 设计，对标 OpenWorker scheduler）。全仓唯一 import 是 `core/agent/blueprint/tests/test_automation.py:17`；无 API/CLI/runtime 任何接线，属于「实现了但从未接入」的模块。
- **`llm_dag_builder.py`（条件接入）**：BlueprintEngine 总是实例化它（engine.py:177），但仅 HYBRID/LLM_DRIVEN 策略才真正走 LLM 建图；默认 TEMPLATE 策略下是死重。蓝图外的直接 import 只有 tests/test_blueprint_v2.py:116。
- **`decider.py` + `executor.py`（条件接入）**：生产唯一可达路径是 stubs_api 的 `POST /task/{sid}/execute`；`agent_native.process_dag()`（agent_native.py:374-386）import 了 Decider 但全仓无任何调用方（grep `process_dag` 仅定义处与两处注释），是半成品接线。
- **孤立模块**：无。除 automation 外所有模块都至少有一条生产引用链。

## 5. 模块间内部依赖与备注

### 内部依赖图（→ 表示 import）

```
models            ←（叶，被几乎所有模块依赖）
skill_registry    → models
llm_dag_builder   → models
engine            → models, skill_registry, llm_dag_builder
meta_feedback     → models, skill_registry
executor          → models, protection; 懒: intervention(:131)
protection        → models
intervention      → decision_event, protection
decision_event    ←（叶）
decider           → models; 懒: executor(:28), permission_engine(:41,57)
learning_bridge   → skill_registry; 懒: models(:300,311)
skill_lifecycle   → skill_registry
heuristic_distiller → heuristic_inventory
heuristic_inventory ←（叶）
permission_engine ←（叶）
tracer / code_request / automation ←（叶，无内部依赖）
__init__          → models, skill_registry, llm_dag_builder, engine, meta_feedback, executor, decider
```

- **无循环依赖**：所有内部 import 均单向指向叶模块；懒 import（decider→executor、executor→intervention）也不构成环。
- **`__init__.py` eager-import 7 个子模块**（:12-21）：任何 `from core.agent.blueprint.engine import ...` 都会先执行包 `__init__`，即 engine/executor/meta_feedback/decider 等总是被实际加载——「条件接入」指的是*功能是否被调用*，不是*模块是否被加载*。
- **生产侧 import 几乎全是函数内懒 import + try/except 降级**（runtime/engine、v3_session_api、dispatch、stubs_api、task_runner、tool_loop、statemachine、gates 均如此），import 失败仅 `logger.debug` 后静默跳过——蓝图功能失效时不会有显式报错。

### 死代码 / 坏接线迹象

1. **CLI `dm blueprint` 分发必崩**：`entry.py:1155` 从 blueprint_cmd import `cmd_blueprint_analyze`/`cmd_blueprint_template_list`/`cmd_blueprint_clear`，但这三个函数不存在（blueprint_cmd.py:85-99 的 `register_cmds` 注册了 `analyze`/`template-list`/`clear`/`diff`/`optimize` 子命令解析器却没有对应 cmd 函数）。已实测：`from core.agent.cli.commands.blueprint_cmd import cmd_blueprint_analyze` 抛 `ImportError`。即任何 `dm blueprint <子命令>` 走到 entry.py:1153 分支都会 ImportError。
2. **`agent_native.process_dag()` 无调用方**（agent_native.py:374）：Decider 的第二条「生产」引用实际是死端。
3. **同名类撞车**：`v3_common/orchestrator.py:140` 自定义了一个 `BlueprintExecutor`（被 v3_common/gates.py:31 import），与 `core.agent.blueprint.executor.BlueprintExecutor` 无关——读 gates.py 时极易误判为蓝图执行器已被门控链路使用。
4. **`blueprint_cmd.py` 的 show/validate/export/history 用固定字符串建 DAG**（:13/:25/:31/:57），属演示性质，非真实会话数据。

### 数据产物

- `data/blueprint_dags/`（8 个 JSON）：executor 执行时的 DAG 快照（executor.py:501 `Path("data")/"blueprint_dags"`），内容形如 `{"request_id","strategy","nodes","edges"}`。
- `data/pipeline_traces.jsonl`：PipelineTracer 写入（tracer.py:20）。

## 6. 结论

- 19 个模块中：**14 个已连接**生产链路（models、engine、skill_registry、protection、intervention、decision_event、permission_engine、learning_bridge、skill_lifecycle、heuristic_distiller、heuristic_inventory、meta_feedback、tracer、__init__）；**4 个条件接入**（executor、decider、llm_dag_builder、code_request——分别依赖特定端点/策略/请求类型才触发）；**1 个仅测试**（automation）；**0 个完全孤立**。
- 主链路是「v3_session_api → BlueprintEngine 建图 → StateMachine 执行 → LearningBridge/MetaFeedback 回流」，元认知底座由 runtime engine `_init_whitebox` 统一装配。
- 主要问题：① `automation.py`（302 行）完全未接线；② `dm blueprint` CLI 分发存在必现 ImportError（entry.py:1155）；③ executor/decider 只剩一个任务执行端点可达，`process_dag` 是死端；④ 生产侧普遍 try/except 静默降级，蓝图失效不可观测。
