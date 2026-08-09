# P0 施工前置：耦合关联盘点 — 2026-08-02

> 目的: P0 施工前摸清蓝图系统与周边模块的完整耦合关系（谁依赖它、它依赖谁、哪些断了、哪些要新建接线），据此规划任务顺序，避免施工时破坏现有功能。
> **状态（2026-08-02）**: 本审计已完成使命。P0 施工完成，见 `P0_RETRO_20260802.md`（设计 vs 实现对照）+ `P0_TASK_PLAN_20260802.md`（完成状态）。后续工作转向 P1。
> 方法: AST 全量 import 分析 + 接口签名核查 + 运行时探针（此前审计已实测）。

---

## 一、蓝图包外部消费者（3 个生产 + 1 个 CLI）

| 消费者 | 用法 | 施工影响 |
--------|------|---------|
| `core/agent/api/v3_session_api.py` | L163-174 Phase 3.5: `BlueprintEngine()` → `engine.build()` → `orch.process_dag()` → Decider；L165/193 `PipelineTracer`；L281-308 Phase 5 fallback 也建 `BlueprintEngine()` | **两处 BlueprintEngine 实例化都要动**；Phase 3.5 是生产唯一执行路径 |
| `core/agent/orchestrator/agent_native.py` | L374-385 `process_dag(dag)` → `Decider()` → `decider.execute()` | **Decider 唯一入口**；改造执行器时同步 |
| `core/agent/cli/commands/blueprint_cmd.py` | 全文件：`_build_dag()` → `BlueprintEngine()`；decider 命令读的是 GlobalDecider/StateMachine（**连错对象**） | P1 修命令对象；P0 不阻塞 |
| `core/agent/blueprint/__init__.py` | 包导出（含 Decider） | 保持导出兼容 |

## 二、蓝图依赖的外部模块（含函数内惰性 import）

| 依赖 | 用途 | 现状 |
------|------|------|
| `core.agent.orchestrator.agent_native` | 执行器 `_get_orchestrator()` 惰性构造 AgentOrchestrator | ✅ 可导入；但无参构造核心链全 None（P0 改造点） |
| `core.agent.learning.ingestion` | `learn()` 阶段 IngestionPipeline | ✅ 存在；离线 4 路网络失败被吞 |
| `core.agent.learning.credibility` | MetaFeedback.update_source_credibility | ✅ 存在；死代码 |

**关键结论**: 蓝图对链组件（PCR/Subgraph/Intent/Profile）目前**零耦合**——执行器直调它们 = 新增接线，不破坏现有代码。

## 三、蓝图内部耦合

```
decider.py → executor.py（抓私有 handler）+ models
engine.py → llm_dag_builder + models + skill_registry
executor.py → models
meta_feedback.py → models + skill_registry
skill_registry.py → models
llm_dag_builder.py → models
```

→ 依赖树清晰：models 是根，executor 是叶子（被 decider 引用）。施工改 executor 时注意 decider 引用其私有 handler（`ex._handle_*`）——**decider/executor 双实现重复**要一并处理。

## 四、链组件接口核查（执行器直调的候选）

| 组件 | 接口 | 可用性 |
------|------|--------|
| `core/agent/pcr_router_v2.py` `PCRRouterV2` | `route(cls, text, history=None, subgraph_prior=None) -> PCRResult`（classmethod！） | ✅ 完整：返回 PCRResult（x/y/z/zone/labels/structural/cognitive_level/execution_mode/prompt_style） |
| `core/agent/v4/cognitive/subgraph_compiler.py` `SubgraphCompiler` | `__init__(engine=None, budget=2000)`; `compile_dialogue(intent, ...)`; `compile_meta(...)`; `pull_prior(domain_scope)`; `expand_from_graph(query, max_nodes)` | ✅ 完整（v4 已施工，40 测试绿） |
| `core/agent/intent/dual_track.py` `DualTrackIntentPipeline` | `process(text, profile=None, ...)` | ✅ 存在（hot/cold 双轨） |
| `core/agent/v3_common/intent_parser.py` | **DEPRECATED shim**: `IntentParser = None`（un_use 导入失败时） | ⚠️ **不可用**——registry L284 还注册它！施工别用它 |
| `core/agent/planner/skill_registry.py` | v3.0 技能注册中心（SkillTemplate CRUD） | ⚠️ **与蓝图 SkillRegistry 完全不同的东西**，命名冲突但无代码耦合 |
| `core/agent/cli/registry.py` | `pcr_router` 注册用 `_pcr_factory()` → `PCRRouterV2()`；37 子系统注入模式（`_instances["engine"]`） | ✅ 现成注入模板 |

## 五、命名冲突与陷阱（施工注意）

1. **两个 SkillRegistry**: 蓝图 `blueprint/skill_registry.py` vs `planner/skill_registry.py`（v3.0）——改蓝图时**只动 blueprint 的**，别混淆；
2. **三个 Decider**: 蓝图 `blueprint/decider.py`（DAG 执行）/ `state/global_decider.py`（状态机）/ `event/statemachine.py`（阶段路由）——CLI `dm decider` 命令连的是后两个，**P1 要修命令对象**；
3. **两套 EventBus**: `event/event_bus.py`（API bootstrap 用，asyncio）/ `events/event_bus.py`（CLI registry 用，ring buffer）——P0 执行器若发事件，先定用哪套（建议 EventLog 起步，事件后置）；
4. **DEPRECATED Intent shim**: `v3_common/intent_parser.py` 是 shim（`IntentParser = None`），但 `cli/registry.py L284` 仍注册——P0 若走"registry 注入"，**别注入这个**，改注入 DualTrack 或 PCR V2 结果；
5. **PCRRouterV2.route 是 classmethod**——执行器直调 `PCRRouterV2.route(text)` 即可，无需实例化（但 `cli/registry.py` 的 factory 是 `PCRRouterV2()` 实例化——实例也能调 classmethod，无冲突）。

## 六、对 P0 施工的含义

1. **改动面收敛**: 生产消费方只有 `v3_session_api.py`（2 处）+ `agent_native.process_dag`（1 处）——执行器改造的同步面很小；
2. **链组件接线是新增不是修改**: 蓝图现在对 PCR/Subgraph/DualTrack 零耦合，直调它们不需要动这些组件的现有代码；
3. **不要动 DEPRECATED shim**: 执行器 intent 段直调 DualTrack 或读 PCRResult，别碰 `v3_common/intent_parser.py`；
4. **decider/executor 重复**: 施工时统一执行器（留 Decider 作入口，executor 逻辑内联或反向引用），注意 `decider.py` 引用 `ex._handle_*` 私有方法；
5. **EventLog 起步**: P0 的事件段先用 EventLog 全量记录（git 式），真事件广播后置——避免 P0 就背上两套 EventBus 的选择负担。
