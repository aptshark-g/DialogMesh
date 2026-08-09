# Blueprint 实现专项审计 — 运行时行为验证（2026-08-02）

> 审计对象: `core/agent/blueprint/` + `core/agent/orchestrator/` + `core/agent/api/v3_session_api.py` 的**具体实现行为**（非设计对照）。
> **状态（2026-08-02）**: 本审计已完成使命。P0 施工完成，见 `P0_RETRO_20260802.md`（设计 vs 实现对照）+ `P0_TASK_PLAN_20260802.md`（完成状态）。后续工作转向 P1。
> 方法: 探针脚本逐条实测（`.venv` Python 3.13），全部可复现。探针脚本见 `docs/only/blueprint/probes/`。
> 结论: 本轮实测把"综合分析"里的推断全部坐实 + 新增 6 个运行时行为发现（RECOVERY strategy 覆盖、未知链死代码、生产意图恒空、同 Tick 顺序敏感、空串匹配 bug、degradation 无副作用）。

---

## 一、运行时实测结果总表

| # | 探针 | 实测结果 | 级别 |
|---|------|---------|------|
| 1 | `AgentOrchestrator()` 无参构造 | 87ms 构造；**pcr/intent/l4/behavior/engineering/llm/discourse 全 None** | 根因 |
| 2 | 首次 `process()` | **12.9s**（其中 12.46s 在 `UnifiedContext.assemble` 模型冷加载）；返回 keys 无 route/intents/plan | P0-3 |
| 3 | 热路径 `process()` | 7ms（模型加载后） | — |
| 4 | `bootstrap()` | 141ms；支撑模块全加载（compass/context/event_log/event_bus/reactor/sandbox/permission/semantic_diff）但核心六链全 None | 根因 |
| 5 | `process()` 返回 | `keys=['text','session','compass','context','cognition','latency_ms']` — **无 route/intents/plan** | P0-4 |
| 6 | `ModelService` | 读 `C:\Users\APTShark\.config\memorygraph\discourse.yaml` WinError 5（权限被拒）→ fallback direct encoder | 独立 bug |
| 7 | converge 非数字 confidence | `float("high")` → **ValueError 冒泡崩溃**（engine.build 无 try） | P1-9 ✅ |
| 8 | converge `required="false"` 字符串 | `bool("false")=True` → 边必选被当可选的反面 | P2-19 ✅ |
| 9 | 约束边界（8节点/环/无llm/未知data_key） | 全部正确拒绝 ✅ | — |
| 10 | 缓存 key 碰撞 | `hash("分析任务")%10000 == hash("分析任务1927")%10000`，`d1 is d2 == True`（不同文本共享对象） | P1-11 ✅ |
| 11 | HYBRID override add 悬空依赖 | `ghost→subgraph_x` 边 → **全局模板永久损坏，validate 永远失败 → 所有后续任务规划请求永久 RECOVERY** | P0-1 灾难变体 ✅ |
| 12 | RECOVERY strategy 覆盖 | 约束回退后 `dag.strategy` 被覆盖为请求策略（HYBRID），**结构是 RECOVERY 但声称 HYBRID**，rationale 仍写"最小保底DAG" | P1-22 新增 ✅ |
| 13 | 未知链 fallback | `BlueprintNode` 构造期拒绝未知 chain → **decider L100-102 fallback 是死代码** | P2-21 修正 ✅ |
| 14 | 生产意图链条 | orchestrator 从不设 intents → v3_session_api intent 恒"通用对话" → **生产中只有 general_chat 模板被选** | P0-4 延伸 ✅ |
| 15 | 同 Tick 依赖顺序 | 节点按定义顺序执行；**依赖节点定义在后 → 前面的被跳过**（tick0 只剩 'a'），下游 c 也连锁跳过 | P1-23 新增 ✅ |
| 16 | `match("")` 空串 | 空串是任何串子串 → `match("")` 返回 **code_analysis TEMPLATE**（本应 general_chat） | P1-24 新增 ✅ |
| 17 | 权重演化 | 3 次低分→weight 0；2 次高分→0.4（恢复） | P1-5 确认 |
| 18 | `check_degradations` | 3 次低分触发 degrade action ✅，但 **registry 权重零变化（无副作用）** | P1-10 确认 ✅ |
| 19 | `learn()` 离线 | 优雅降级（本地 refs）✅；**但每次仍发 4 路网络请求**（DuckDuckGo/Arxiv/GitHub/Scholar 全失败被吞） | P2-25 新增 |
| 20 | tracer 落盘 | 依赖 CWD（`data/pipeline_traces.jsonl`）；本机 cwd=项目根时正常 | P2-16 确认 |

---

## 二、逐条实测证据（探针输出）

### 2.1 生产运行时核心链全空（根因 #1/#4/#5）

```
[A1] AgentOrchestrator() ctor: 87ms
    pcr=None intent=None l4=None behavior=None engineering=None llm=None discourse=None
    _compass=Y _context_assembly=Y _cognition_hub=Y _feedback_bridge=Y _plan_gate=Y _execution_pipeline=Y
[A2] process() returns: 12864ms, keys=['text','session','compass','context','cognition','latency_ms']
    has route: False | has intents: False | plan=False

[B1] bootstrap() ctor: 141ms — 同上六链全 None，支撑模块全 Y
[B4] bootstrap orch.process(warm): 12347ms（首次仍冷）
```

代码位置: `agent_native.py L28-31`（`self.pcr=pcr_router` 等）; `bootstrap_v6.py L19-26`（参数默认 None）; `bootstrap_v6.py L76-77`（传 None）; `v6_app.py L269-270`/`chat_api.py L31-32`（无参调用）。

### 2.2 12.9s 冷启动定位（#2/#3）

```
[C1] compass.measure: 3ms
[C2] context_assembly.assemble: 12464ms   ← 12.46s 都在这里（UnifiedContext 模型加载）
[C3] cognition_hub.converge: 14ms
[C4] warm process(): 11ms
```

→ 19s 总延迟 = 首次 `UnifiedContext.assemble` 冷加载模型 + 每节点重复 `orch.process()`。热路径单节点仅 7-11ms。

### 2.3 converge 崩溃路径（#7/#8）

```
[C2a] CRASH: ValueError: could not convert string to float: 'high'  ← P1-9
[C2b] required='false' string → edge.required=True (bool('false')=True)  ← P2-19
```

`float(data.get("confidence", 0.5))`（llm_dag_builder.py L301）无 try；`engine.build` LLM_DRIVEN 分支（L296）无 try → LLM 输出不规范即崩溃而非回退。

### 2.4 全局模板灾难性损坏（#11）

```
HYBRID mock LLM: {"action":"modify","add":[{"node_id":"subgraph_x","chain":"subgraph","deps":["ghost"]}]}
→ 约束失败 → fallback _build_template(intent, blueprint) ← 蓝图是已被污染的共享对象
→ RECOVERY DAG (pcr_0 + llm_1)
→ BUILTIN_TEMPLATES["task_planning"] 现在含 subgraph_x + ghost→subgraph_x 悬空边
→ 全局 validate: valid=False errs=['Edge from unknown node: ghost']
```

**后果**: 一次糟糕的 LLM override 使 task_planning 模板永久损坏 → 该意图所有后续请求 validate 失败 → 永远 RECOVERY。且缓存（L176/L216）会缓存这个坏结果。

### 2.5 RECOVERY strategy 覆盖（#12 — 新增）

```
returned dag: nodes=['pcr_0', 'llm_1'] strategy=HYBRID
rationale=约束检查失败后的最小保底DAG
```

`engine.py L211 dag.strategy = strategy` 在 fallback 之后执行，把 RECOVERY 结构标记成请求策略。下游 `v3_session_api` 的 tracer 记 `dag.strategy`（L198）→ 数据失真。

### 2.6 生产意图恒空 → 只选 general_chat（#14 — 新增）

```
F3: intent resolved to: 通用对话
blueprint: strategy=HYBRID nodes=4 rationale=通用对话:...
→ production ALWAYS builds general_chat (4 nodes) because orchestrator never sets intents
```

证据链: `v3_session_api.py L126-132`（cognitive_ctx 无 intents）→ L285-288（intent="通用对话"）→ `engine.build` → general_chat。**code_analysis/task_planning/data_search/causal_reasoning 模板在生产路径永远选不到**（除非显式传 intent，而 API 不传）。

### 2.7 同 Tick 依赖顺序敏感（#15 — 新增）

```
节点定义顺序: b(tick0,依赖a) → a(tick0) → c(tick1,依赖b)
tick0 nodes: ['a']   ← b 被跳过（"deps not ready"）
tick1 nodes: ['c']   ← c 也跳过（依赖 b 未完成）→ warning 日志，无显式错误
```

设计 §14.3"同 Tick 内并行"——实现是**按列表顺序串行 + required 依赖检查**。LLM_DRIVEN 的 LLM 乱序输出节点时，静默丢节点。修复: 同 Tick 内按拓扑序迭代或多轮收敛。

### 2.8 空串匹配 bug（#16 — 新增）

```
match(''        ) -> strategy=TEMPLATE template=标准代码分析路径（code_analysis）
```

根因: `skill_registry.py L209-213` 部分匹配 `known in intent or intent in known`——`"" in "代码分析"` 为 True → 空 intent 命中第一个 key。v3_session_api 里 intent 为空时先 fallback "通用对话"（L287-288），未触发；但任何直传空串的调用方（CLI/测试/未来 API）都会拿到 code_analysis。修复: `if not intent: return default`。

### 2.9 权重演化与 degradation 无副作用（#17/#18）

```
initial: TEMPLATE 1.0 / HYBRID 0.7 / LLM_DRIVEN 0.2
3x low → LLM_DRIVEN weight 0.0（success_rate 0/3）
2x high → 0.4（2/5）
MetaFeedback 3 低分审计 → actions=[{action:degrade, LLM_DRIVEN→HYBRID}]
但 registry weights 零变化 ← 降级只是打日志+返回 dict，不改权重
```

### 2.10 learn() 每次 4 路网络（#19 — 新增）

```
learn() 即使离线也发起 DuckDuckGo/Arxiv/GitHub/Scholar 4 路并行搜索（source_registry search_all）
全部失败被 except 吞 → 用本地 reference_map
网络慢时每条路径都有 timeout → LLM_DRIVEN 延迟被拖长
```

---

## 三、新增/升级的问题清单（相对 v1 综合分析版）

| 编号 | 问题 | 证据 | 级别 |
------|------|------|------|
| P0-1变 | 坏 LLM override → 模板永久损坏 → 全意图永久 RECOVERY | §2.4 | P0 |
| P1-22 | RECOVERY 后 strategy 被覆盖为请求策略（数据自相矛盾） | §2.5 | P1 |
| P1-23 | 同 Tick 依赖顺序敏感 → 静默丢节点 | §2.7 | P1 |
| P1-24 | `match("")` 空串 → code_analysis（子串匹配边界） | §2.8 | P1 |
| P1-25 | 生产路径只有 general_chat 被选（核心链空 → 意图恒"通用对话"） | §2.6 | P1（与 P0-4 同根因） |
| P2-25 | learn() 每次 4 路网络请求，离线也发 | §2.10 | P2 |
| P2-21修正 | 未知链 fallback 是死代码（构造期拒绝，不可达） | F2 | P2 |
| 独立 | ModelService 读 `~/.config/memorygraph/discourse.yaml` 权限被拒 | A2 日志 | 环境/实现 |

---

## 四、修复优先级建议（实现层，按"最小正确路径"排序）

1. **P0-1变（最高）**: `build()` 开头 `blueprint = copy.deepcopy(blueprint)`——单行修复即可隔离全部 override/strategy 污染；`dag.strategy = strategy` 移到 deepcopy 之后作用于副本。
2. **P1-25/P0-4**: 二选一——(A) `bootstrap()`/`v3_session_api` 注入真实 PCRRouterV2+Intent（与 `cli/registry.py L273` 对齐）; (B) 执行器直接调链组件、删关键词 fallback 伪造数据。推荐 B（与 PCR/子图施工一致）。
3. **P1-9**: converge 的 `float()` 加 try → 失败返回 None（已有 fallback 语义）。
4. **P1-23**: Decider/Executor 同 Tick 内按拓扑序迭代（2 轮收敛即可），或明确文档"同 Tick 节点必须拓扑有序"。
5. **P1-24**: `match` 空串守卫。
6. **P1-22**: fallback 后不覆盖 strategy（保留 RECOVERY 标记）。
7. **P2-25**: learn() 网络调用移到显式开关（如 `learn_offline=True` 默认），离线不发请求。

> 注: 探针脚本（`_audit_probe_a/a2/b/c/c2/d/e/f.py`）已归档到 `docs/only/blueprint/probes/`，可复现本报告全部实测。

---

## 五、剩余核查补遗（第二套运行时 + CLI 基础设施 + 测试）

### 5.1 生产 API 是"两套运行时混合"（修正 §三 结论的精度）

实测 + 代码追查修正: 生产 API **同时**使用两套运行时，蓝图 Decider 只挂在其中一套（空壳）上:

| 路径 | 运行时 | 核心链 | 状态 |
------|--------|--------|------|
| Phase 1 认知分析 + Phase 3.5 蓝图 Decider | `AgentOrchestrator()` 无参构造（v3_session_api L124/L173） | **pcr/intent/l4/behavior/engineering/llm 全 None** | ❌ 空壳 |
| Phase 4 后 post-LLM | `get_engine()` → auto-start → `CognitiveRuntimeEngine` + `DeciderStateMachine`（cli/engine.py L46-59, L270-273） | **真实**（V4 Router + IntentParser + Planner + 8 个 phase handlers） | ✅ 活 |

`core/agent/event/handlers.py L89-309` 的 `register_all_handlers` 注册 PCR/INTENT/DISCOURSE/BEHAVIOR/META/PROFILE/PERSIST/ASSOCIATION 8 个 handler → `cli/engine.py L273` 在 start_engine 时调用 → StateMachine 是"活的"。

**但** `get_engine()` 的 auto-start 依赖 `start_engine()` 成功；而 `start_engine` 结尾 `_save_state()`（L361）在 .venv 下抛 PermissionError → start_engine 失败 → `get_engine()` 抛异常 → v3_session_api L271 静默吞掉 → **post-LLM StateMachine/EventBus publish 每次请求都被跳过**（见 §5.2）。

### 5.2 state.json 权限失败（交接 §2.1 确认 + 环境差异修正）

```
实测: ce._save_state() RAISED: PermissionError: [Errno 13] Permission denied:
      'C:\Users\APTShark\.dialogmesh\state.json'
      （parent 可写、文件存在 144B 可读，但 .venv 下写被拒）
      atexit 回调也崩: "Exception ignored in atexit callback <function _save_state>"
```

**环境差异修正（用户补充证据，2026-08-02 Hermes venv 3.11 实测）**:

```
3.11 (Hermes venv, 当前开发环境):
  ✅ start_engine → running, 49 subs
  ✅ _save_state 正常 (state.json 144B 可写)
  ✅ get_engine OK

3.13 (.venv, 审计用):
  ❌ PermissionError: ~/.dialogmesh/state.json
  → start_engine 失败 → atexit 崩
```

→ **PermissionError 是环境相关的权限行为（3.13 复现，3.11 不复现），不是代码 bug**。但"`_save_state` 无 try/except + atexit 崩溃"本身成立——任何环境都该防御。

调用点（全部无 try/except）: `start_engine` L361、`get_session` L417、`set_session` L423、`atexit.register` L427。

**连锁影响（比交接文档更深）**:
- CLI `dm engine start` → exit=-1（**仅 3.13 等失败环境复现**；3.11 环境正常）；
- API 每次 `send_message` → Phase 4 后 `get_engine()` → auto-start 失败 → 异常被 v3_session_api L271 `except` 吞 → StateMachine + EventBus publish 静默跳过（**仅失败环境**）；
- `get_engine()` 失败后 `_engine=None`（L55）→ 下一请求重新完整执行 start_engine（registry resolve 37 子系统）再失败 → 每请求重复巨额初始化（**仅失败环境**）；
- `stop_engine`/进程退出 → atexit 崩溃。

**定级修正**: 环境相关部分（PermissionError→CLI exit=-1/API 静默跳过）降为 **P1**（取决于目标运行时版本: 若生产固定 3.13 则仍 P0）；防御缺失部分（无 try/except + atexit 无保护）**保持 P0 语义**（任何环境都该修，低成本高收益）。

### 5.3 两套 EventBus + 三个 Decider（命名分裂实锤）

| 概念 | 位置 | 谁在用 |
------|------|--------|
| EventBus v2（asyncio NATS 模式） | `core/agent/event/event_bus.py` | bootstrap_v6（API） |
| EventBus（ring buffer） | `core/agent/events/event_bus.py`（**复数 events**） | cli/registry L265（CLI） |
| Decider（蓝图 DAG 执行） | `core/agent/blueprint/decider.py` | agent_native.process_dag |
| GlobalDecider（状态机协调） | `core/agent/state/global_decider.py` | cli/registry L267（CLI） |
| DeciderStateMachine（阶段路由） | `core/agent/event/statemachine.py` | cli/engine L272 |

**CLI `dm decider` 命令操作的是 GlobalDecider/DeciderStateMachine，不是蓝图 Decider**——`blueprint_cmd.py` 的 `cmd_decider_show/chains/execute` 读 `e._decider`（GlobalDecider）和 `e._state_machine`（DeciderStateMachine）。所以"假执行"的根因之一是**连错了对象**。

### 5.4 生产路径只选 general_chat（复核）

`v3_session_api` 的 intent 来源是 `AgentOrchestrator()` 的 process()（无 intents）→ 恒 "通用对话" → `engine.build` 恒 general_chat。CLI 路径同理（`CognitiveRuntimeEngine` 的 intent 来自真实 IntentParser，但它不走 BlueprintEngine）。**5 个内置模板在两条生产路径都选不到**（除显式传 intent 的测试/CLI 手工调用）。

### 5.5 测试是假的（零断言）

`core/agent/cli/tests/test_cli.py L104-121` `TestBlueprintDecider`:
- `test_blueprint_show`: start_engine(mock) → cmd_blueprint_show(Namespace()) → stop_engine——**无任何断言**（只测不抛异常）；
- `test_decider_chains`: 同上。

且这些测试在 .venv 下会因 §5.2 的 `_save_state` PermissionError 在 `start_engine` 直接失败（anaconda 环境可写才可能通过）。

### 5.6 新增问题汇总（第二轮补遗）

| 编号 | 问题 | 证据 | 级别 |
------|------|------|------|
| P0-26 | `_save_state` 无 try/except（4 处）+ atexit 无保护——防御缺失任何环境成立；PermissionError 为环境相关（3.13 复现/3.11 正常） | §5.2 | P0（防御语义）/ P1（环境部分） |
| P0-27 | `get_engine()` 失败后 `_engine=None` 不缓存失败 → 每请求重复完整 start_engine（仅失败环境触发；防御性修复仍值得做） | §5.2 | P1 |
| P1-28 | 两套 EventBus（event/ vs events/）双运行时各自为政 | §5.3 | P1 |
| P1-29 | CLI `dm decider` 命令操作 GlobalDecider/StateMachine 而非蓝图 Decider | §5.3 | P1 |
| P1-30 | `/v6/chat` answer 取 `process().plan`（空壳无 plan）→ 回复 `"{}"` | chat_api.py L79 | P1 |
| P2-31 | `p9_cmd.py` blueprint/decider/meta 细粒度命令全部假执行（打印预设 JSON） | p9_cmd L211-247 | P2 |
| P2-32 | `TestBlueprintDecider` 零断言 + 依赖 state.json 可写 | test_cli L104-121 | P2 |

### 5.7 CLI 运行时注册表（37 子系统，供施工参考）

`cli/registry.py L248-379`: Tier 0（event_log/event_bus/decider 必选）+ Tier 1（pcr_router 工厂=PCRRouterV2 L271-275 / topic_tree / discourse_tree / granularity）+ Tier 2（intent_parser / planner / observation_pool / context_assembler / domain_selector / perspective_planner / behavior_graph / causal_substrate / meta_subscriber / assoc_subscriber / l1-l3 关联链 / meta_cognition / inertia / behavior_discovery / belief_map / **subgraph=SubgraphCompiler L351** / parameter_registry / engineering_knowledge / mind / abc_orchestrator / strategy_engine / memory_compiler / context_ir_compiler / format_serializer / event_log_store / ocean_analyst）。

**这是"真接线"的参考模板**——蓝图 Decider 施工时若走"直接组件调用"方案，可直接复用 registry 的注入方式（`_instances["engine"]=engine` + factory）。
