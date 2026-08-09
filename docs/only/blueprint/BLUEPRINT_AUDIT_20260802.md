# Blueprint 系统深度审计报告 — 2026-08-02 (v2 深度版)
> **状态（2026-08-02）**: 本审计已完成使命。P0 施工完成，见 `P0_RETRO_20260802.md`（设计 vs 实现对照）+ `P0_TASK_PLAN_20260802.md`（完成状态）。后续工作转向 P1。

> 审计方法（对齐 PCR/行为链标准）: ① 设计文档逐节提取检查点 → ② 9 个实现文件逐函数细读 → ③ AST 全依赖 → ④ 运行时探针（含 mock LLM）→ ⑤ 调用链逐层追查（API→Decider→handlers→orch.process→bootstrap→registry）→ ⑥ 行号证据。
> 结论先行: 蓝图是**"构建可用、执行虚假"的半成品编排层**。深层根因不是 blueprint 包本身，而是**生产运行时（`AgentOrchestrator` + `bootstrap()`）从未注入 PCR/Intent/L4/Behavior/Engineering 核心链**——执行器每节点调用的 `orch.process()` 返回空 route/intents，所有 handler 静默落入关键词 fallback，向 LLM 注入的是**伪造的"管线分析"**。同时全局模板单例被 HYBRID 污染（P0）、llm_reply 节点不调 LLM（P0）、Meta 学习闭环零调用方（P1）。

---

## 一、设计检查点清单（DESIGN_BLUEPRINT_ORCHESTRATION.md 逐节提取）

### 1.1 核心承诺（行号 = 设计文档）

| # | 设计承诺 | 位置 | 实现状态 |
|---|---------|------|---------|
| D1 | LLM 是图的构建者，不是图的执行者 | L7-24 | ⚠️ 构建有，执行是重放线性管线 |
| D2 | 目标架构: Engine→Decider(EventBus)→PlanGate→Execution | L71-111 | ❌ EventBus 未接线（decider.py L42 `_bus=None`） |
| D3 | 5 策略: RULE_BASED/TEMPLATE/HYBRID(默认)/LLM_DRIVEN/RECOVERY | L112-125 | ✅ models.py VALID_STRATEGIES + engine 路由 |
| D4 | 最小闭环: 选蓝图→LLM 建 DAG→EventBus 执行→PlanGate 审核 | L126-149 | ⚠️ 前三步有壳，PlanGate 未接（executor 无 checkpoint 暂停） |
| D5 | 热路径 SkillRegistry 模式匹配 <500ms，非 LLM 推理 | L177-187 | ✅ 纯规则匹配 |
| D6 | 冷路径 Meta 异步学，不阻塞请求，影响下次 Tick | L188-203 | ❌ MetaFeedback 无消费者（§六） |
| D7 | Level 2 HYBRID = 单步路由（LLM 在分叉点介入） | L233-243 | ⚠️ 有 LLM override，但 mutate 全局模板（P0-1） |
| D8 | Level 3 LLM_DRIVEN 保护: PlanGate + Budget(≤7) + LoopDetector + QualityGate | L280-296 | ❌ 只有 Budget(MAX_NODES=7)✅；PlanGate/LoopDetector/QualityGate 无 |
| D9 | 三层范式: 发散(T=0.8,无上下文)→学习→收束(T=0.1,完整上下文) | L309-340 | ✅ llm_dag_builder 实现 |
| D10 | 约束层: 安全/资源(节点≤7)/依赖(拓扑,无环)/权限 | L370-384 | ⚠️ 资源/依赖有，安全/权限无 |
| D11 | 自调节闭环: 连续3低分降级, 5高分升级 | L438-452 | ⚠️ MetaState 有阈值逻辑，但无人调用（§六） |
| D12 | §14.1 全生命周期: EventLog→Meta 消费→回写 SkillRegistry | L465-515 | ❌ 无 EventLog 订阅循环 |
| D13 | §14.2 BlueprintDAG schema（nodes/edges/strategy/confidence/rationale） | L516-550 | ✅ models.py 对齐 |
| D14 | §14.3 EventBus 订阅表 8 subject（Tick 0/1/2/async，同Tick并行） | L551-564 | ❌ 无订阅表、无 EventBus |
| D15 | §14.4 ExecutionAudit + update_strategy_weights/suggest/trigger_degradation | L566-588 | ⚠️ 接口有，实现有 bug（P1-5）+ 无调用方 |
| D16 | §14.5 权重调整/模板建议/节点修正 | L590-602 | ⚠️ suggest 有，其余无 |
| D17 | §15 BlueprintDAG = TaskGraph 超集，统一前端渲染 | L605-660 | ❌ 无前端，无 node_type 协议实现 |

### 1.2 三份辅助文档

- `BUSINESS_CHAIN_11_BLUEPRINT.md`: 11 链定位图（PCR→Intent→Blueprint→DAG→EventBus→各链→LLM→Meta）+ 三阶段 + 代码映射表（只列 6 文件，漏 decider/tracer）+ 下游调控（§五 连续3次低分降级——设计与 D11 呼应）。
- `DESIGN_BLUEPRINT_SYSTEM.md`（7-25 早期）: TaskDecomposer/AgentAllocator/DependencyResolver 概念——已被 DAG 模型取代，未实现，无引用。
- `ENGINEERING_BLUEPRINT.md`: 数据契约 + 组件依赖图（v3_session_api→Engine→SkillRegistry/LLMDAGBuilder/ConstraintChecker/Executor，MetaFeedback→SkillRegistry）+ 文件清单（7 文件，漏 decider/tracer）。

---

## 二、逐文件逐函数细读（9 文件 + 行号证据）

### 2.1 models.py — ✅ 对齐 §14.2

- `BlueprintDAG.validate()`（L94-108）只查: 边端点存在、自环。**不含环检测**（环检测在 ConstraintChecker）。
- `BlueprintNode.__post_init__`（L34-39）校验 chain ∈ CHAIN_IDS、priority 0-9。
- `BlueprintDAG.__post_init__`（L76-81）校验 strategy ∈ VALID_STRATEGIES、confidence ∈ [0,1]。
- CHAIN_IDS（L17-25）含 `engineering`/`metap` 等 12 链。

### 2.2 skill_registry.py

| 行 | 函数 | 发现 |
|---|------|------|
| L171-199 | `_init_defaults` | 6 意图 × 权重种子（代码分析→TEMPLATE 1.0 等） |
| L201-238 | `match` | 部分匹配（L209-213: `known in intent or intent in known`）；权重选择 `weight × success_rate`（L222）；template_map（L227-234） |
| L240-253 | `update_weight` | **P1-BUG: L248 权重公式丢 base** — 注释"base × success_rate"但代码 `1.0 * w.success_rate`。实测: LLM_DRIVEN 0.2→1.0（一次成功） |
| L255-256 | `builtin_template` | 返回共享单例（与 P0-1 关联） |

### 2.3 llm_dag_builder.py

| 行 | 函数 | 发现 |
|---|------|------|
| L121-146 | `_call_llm` | 硬编码 `SWITCH_URL=127.0.0.1:8080`、`SWITCH_KEY=dm-client`、模型 `deepseek-v4-flash`（L33-36）；timeout=60s；失败返回 ""（优雅降级 ✅） |
| L148-163 | `_extract_json` | 处理 markdown fence + 裸 JSON；正则 `\{[\s\S]*\}` 贪婪（多对象时可能过捕） |
| L170-195 | `diverge` | T=0.8 发散；**不验证 LLM 输出必须含 pcr 起点/llm_reply 终点**（SYSTEM 有要求但无校验） |
| L199-241 | `learn` | 调 `IngestionPipeline.run(intent, max_results=3, fetch_full=True)`（L211-213）；映射 source 字段（arxiv/scholar/github）——**source 名与 sources.py 实际注册名一致**（arxiv/duckduckgo/tavily/scholar/github ✅ 非死代码）；**但查询词是 intent 中文（如"代码分析"）而非用户文本，arxiv 检索无意义**（设计质量问题） |
| L245-318 | `converge` | T=0.1 收束；节点解析 try/except（L280-289）；**L301 `float(data.get("confidence", 0.5))` 无保护——LLM 输出非数字 confidence（如 "high"）→ ValueError 冒泡 → engine.build 无 try → 崩溃**（P1-9）；`bool(e.get("required", True))` 对字符串 "false" 也成 True（L298） |
| L322-328 | `build_llm_driven` | 发散→学习→收束；hypotheses 空→返回 None |

### 2.4 engine.py

| 行 | 函数 | 发现 |
|---|------|------|
| L147-151 | `__init__` | 每实例新建 SkillRegistry + LLMDAGBuilder + ConstraintChecker + 内存 cache |
| L153-217 | `build` | **L167-168: intent=None 硬编码"通用对话"（"auto-detect"是假的）**；**L176: cache key `hash(text)%10000` 碰撞风险 + 缓存共享单例**；L182-183 TEMPLATE 返回共享单例；L184-185 HYBRID mutate 共享单例；**L196 约束失败 fallback 返回"已被污染的同一模板"**；**L211 `dag.strategy=strategy` 写回共享单例** |
| L219-221 | `_build_template` | 直接返回 BUILTIN_TEMPLATES 单例（P0-1 根源） |
| L223-262 | `_build_hybrid` | **L254 跨类调用私有方法 `self.builder._call_llm`**（耦合）；**L257 `_apply_llm_overrides(blueprint,...)` 直接改全局模板** |
| L264-289 | `_apply_llm_overrides` | 原地改 `dag.nodes/dag.edges`（L267-269, 279-281, 286-289）→ **P0-1 实锤** |
| L291-302 | `_build_llm_driven` | fallback 到 general_chat 单例并改其 strategy/rationale（L299-301，二次污染） |
| L44-104 | `ConstraintChecker.validate` | MAX_NODES=7 ✅（L35）；**MAX_DEPTH=18 而 docstring 写 "depth ≤ 3"（L36/42 不一致）**；data_key 白名单（L96-101）；llm_reply 必须存在（L82-85）；pcr 应为 root（L87-90 仅警告级 error） |
| L106-138 | 环检测 | DFS 三色 ✅；_max_depth 用 memo+visited（有环时 dfs 返回 0，环已单独检测 ✅） |

### 2.5 executor.py — 执行层核心问题

| 行 | handler | 发现 |
|---|---------|------|
| L163-179 | `_handle_pcr` | 调 `orch.process(text)` → 期望 `result["route"]`；**生产 orchestrator pcr=None → 无 route → L169-170 静默 except → L171-179 关键词 fallback 伪造 zone**（P0-4） |
| L181-199 | `_handle_intent` | 同上；fallback 关键词分段（L190-199）伪造 intents |
| L201-207 | `_handle_context` | 调 process() **无 try/except**（与其他 handler 不一致）；返回 `ctx.get("dialogue")` 是 SubgraphContext 对象不是 str |
| L209-213 | `_handle_subgraph` | **只是透传 context，未调 SubgraphCompiler**（与已施工的 `core/agent/v4/cognitive/subgraph_compiler.py` 零交互） |
| L215-235 | `_handle_profile` | **L235: API 失败→硬编码假画像 "MBTI: INFJ \| OCEAN=0.79..."（伪造用户数据）**（P0-4） |
| L237-239 | `_handle_llm_reply` | **只聚合上下文，不调 LLM**（P0-2）；Decider L123 取 `out.get("response", out.get("content", str(out)))` → 无 response/content → **llm_reply 是 dict 的 repr 字符串** |
| L241-245 | `_handle_behavior` | 返回 `result.get("cognition")`——**语义错位（behavior 节点返回 cognition）**；无 try/except |
| L247-263 | `_handle_meta/_handle_association/_handle_engineering/_handle_metap` | **全部是 status 占位符**（"async"/"deferred"），不做事 |
| L265-272 | `_handle_default` | 未知链→整条 process() 当兜底（放大延迟） |
| L67-128 | `execute` | 与 decider.execute 几乎完全重复（§五.6）；L91-94 同 Tick 依赖检查：**同一 Tick 内 required 依赖必然跳过**（LLM_DRIVEN 图可能同 Tick 有依赖） |
| L35-53 | `_get_orchestrator` | **惰性 import 并构造 `AgentOrchestrator()`——无参构造 → 核心链全 None（§四根因）** |

### 2.6 decider.py — executor 的复制品

| 行 | 发现 |
|---|------|
| L41-45 | `_bus = None`（**EventBus 从未接线**）；`_init_handlers()` 在构造期即执行 |
| L49-65 | 创建 BlueprintExecutor 实例，**抓取它的私有 handler**（`ex._handle_pcr` 等）+ `ex._get_orchestrator()`（构造期即建 AgentOrchestrator → 冷启动 19s） |
| L67-139 | `execute` 与 executor.execute 逐行重复（TickResult 都重复定义 L26-31）；L100-102 未知链→**fallback 到 llm_reply handler**（误导）；L123 llm_reply 提取同上 |

### 2.7 meta_feedback.py — 完整学习闭环是死代码

| 行 | 发现 |
|---|------|
| L41-65 | MetaState: LOW<0.4 / HIGH>0.75 / 连续3降级 / 连续5升级 ✅ 阈值合理 |
| L88-100 | `consume(audit)` — **零调用方**（rg 全库只有定义+docstring） |
| L102-110 | `update_strategy_weights` — 调 registry.update_weight（含 P1-5 bug）；**零调用方** |
| L112-145 | `check_degradations` — **只返回 actions list，不实际改 SkillRegistry**（"降级"无副作用）；零调用方 |
| L147-161 | `suggest_blueprints` — 读 `self.registry._strategy_weights`（**访问私有属性**）；零调用方 |
| L194-210 | `update_source_credibility` — 调 `CredibilityEvaluator._extract_domain`（**私有方法**）+ `update_consistency`（存在 ✅ L171-180）；零调用方 |

### 2.8 tracer.py

| 行 | 发现 |
|---|------|
| L16 | `TRACE_FILE = Path("data/pipeline_traces.jsonl")` — **相对路径依赖 CWD** |
| L19-52 | record 线程安全 ✅；v3_session_api L193 是唯一调用方 |

### 2.9 __init__.py — 导出含 decider ✅（agent_native.process_dag 依赖）

---

## 三、深层根因链：为什么执行是"假"的（运行时探针 + 调用链逐层追查）

### 3.1 根因: 生产运行时从未注入核心链

```
证据链（rg + 行号）:
  v6_app.py L269-270:  bootstrap()                        ← 生产 API 启动
  chat_api.py L31-32:   bootstrap()
  bootstrap_v6.py L76-77: pcr_router=pcr_router, intent_splitter=intent_pipeline
                        ↑ 参数默认 None（L19-26）→ 传 None
  agent_native.py L28-31: self.pcr=pcr_router(None); self.intent=intent_splitter(None)
                        self.l4=None; self.behavior=None; self.engineering=None; self.llm=None
  → orch.process():  L140 if self.pcr:（None→跳过）→ result 无 "route"
                     L151 if self.intent:（None→跳过）→ result 无 "intents"
  → executor._handle_pcr L167: result.get("route") → None → 关键词 fallback
```

**全库唯一给 PCRRouterV2 接线的地方是 `cli/registry.py L273`（CLI 运行时 `CognitiveRuntimeEngine`），但那是另一套运行时（StateMachine 路径），蓝图 Decider 完全不经过它。** `engineering_bridges.py L32` 的 PCRRouterV2 也只在 CLI 桥内。

**结论**: `AgentOrchestrator` 生产路径的 10 链管线中，PCR/Intent/L4/Behavior/Engineering/LLM 六条链结构性地不存在。蓝图执行器每节点调 `orch.process()` 只拿到 compass/context/cognition，route/intents 恒为空 → 全部静默降级到关键词规则 → 这些伪造结果被 v3_session_api L229-230 拼进 LLM prompt 作为"管线分析"。

### 3.2 探针实测证据（.venv Python 3.13）

```
Decider().execute(code_analysis DAG) → latency=18913ms, 3 ticks
  pcr_0      → {"route":{"zone":"ANALYSIS","confidence":0.6}}        ← 关键词 fallback（非真实 PCR）
  intent_1   → {"intents":{"segments":["讨论"],"confidence":0.7}}   ← 关键词 fallback（非真实 Intent）
  context_2  → 真实 SubgraphContext（只有 context 链真加载了）
  subgraph_3 → 透传 context（无 SubgraphCompiler 调用）
  llm_reply_4 → {"chain":"llm_reply","context":{...}}                ← 无 LLM 调用
  19s = Decider() 构造（_get_orchestrator 冷建 ExecutionPipeline 等重组件）+ 首节点 process() 冷启动
```

### 3.3 单例污染实锤（mock LLM）

```
HYBRID 路径 mock LLM 返回 {"action":"modify","remove":["subgraph_3","profile_4"]}
  → BUILTIN_TEMPLATES["task_planning"] 节点数 6→4（全局永久污染）
  → dag is BUILTIN_TEMPLATES["task_planning"] == True
```

### 3.4 权重公式 bug 实锤

```
update_weight("代码分析","LLM_DRIVEN",0.95) 一次成功 → LLM_DRIVEN weight 0.2→1.0
（base weight 0.2 被丢弃；设计意图是"base × success_rate"）
```

---

## 四、完整问题清单（分级 + 行号）

### P0（正确性/数据完整性 — 必须修）

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| P0-1 | 全局模板单例污染（构建层） | engine.py L182-183, L196, L211, L257, L264-289, L299-301 | HYBRID LLM 建议永久改变所有请求的模板；约束回退也无法恢复；`dag.strategy` 写回共享对象 |
| P0-2 | llm_reply 节点不调 LLM | executor.py L237-239; decider.py L123 | DAG 执行产物无最终回复；§14.3 "llm.reply 最终回复"是假的 |
| P0-3 | 执行层重放完整线性管线 | executor.py L163-207（每节点 orch.process） | 5 节点 DAG ≈ 19s；与设计"EventBus 并行、链消费事件"相反 |
| P0-4 | 伪造数据进入 prompt | executor.py L171-179（PCR fallback）、L190-199（Intent fallback）、L235（假画像） | 向 LLM 注入非真实 PCR/Intent/Profile 数据，且无标记；违反数据真实性 |

### P1（学习/维护/契约 — 应修）

| # | 问题 | 位置 |
|---|------|------|
| P1-5 | 权重公式丢 base | skill_registry.py L248 |
| P1-6 | Decider/Executor 双实现重复 + `_bus=None` | decider.py 全文件 vs executor.py |
| P1-7 | handler↔orchestrator 契约未对齐（route/intents 键恒空） | executor.py L167/L185 + agent_native.py L28-31 + bootstrap_v6.py L19-26 |
| P1-8 | `engine.build` intent "auto-detect" 是假的 | engine.py L167-168 |
| P1-9 | converge confidence 无类型保护 → 崩溃 | llm_dag_builder.py L301（float()） |
| P1-10 | Meta 学习闭环零调用方 + check_degradations 无副作用 | meta_feedback.py L88-161 |
| P1-11 | 缓存 key `hash(text)%10000` 碰撞 + 缓存共享单例 | engine.py L176-179, L216 |
| P1-12 | `_handle_behavior` 语义错位（返回 cognition） | executor.py L241-245 |
| P1-13 | `_handle_context` 无 try/except（与其他 handler 不一致） | executor.py L201-207 |

### P2（设计缺口 / 清理）

| # | 问题 | 位置 |
|---|------|------|
| P2-14 | LoopDetector / QualityGate 设计有，代码无 | engine.py |
| P2-15 | PlanGate checkpoint 不暂停执行 | executor.py |
| P2-16 | tracer 相对路径 | tracer.py L16 |
| P2-17 | 私有方法跨类/跨包调用（_call_llm / _extract_domain / _strategy_weights） | engine.py L254; meta_feedback.py L155, L203-210 |
| P2-18 | MAX_DEPTH=18 vs docstring "≤3" | engine.py L36/42 |
| P2-19 | `bool(e.get("required", True))` 字符串 "false" 为 True | llm_dag_builder.py L298 |
| P2-20 | learn() 用中文 intent 做 arxiv 检索（无意义查询词） | llm_dag_builder.py L213 |
| P2-21 | 未知链 fallback 到 llm_reply handler（误导） | decider.py L100-102 |
| P2-22 | 旧版 `planning/blueprint.py`（12.9KB）与 DAG 版并存，无归档无交叉引用 | planning/blueprint.py |

### 伪功能 CLI（blueprint_cmd.py）

| 命令 | 真相 |
|------|------|
| `dm blueprint show/validate/export` | `_build_dag("show"/"validate"/"export", "TEMPLATE")` — 硬编码文本当用户输入，与真实输入无关 |
| `dm blueprint build/build-hybrid/build-llm` | `_build_dag(text, strategy)` — **把用户文本当 intent 传**（engine.build 的 intent 参数） |
| `dm decider execute` | **假执行** — 只打印 `{"executed": True, "handlers": N}`，不跑 DAG |
| `dm decider show/chains` | 读 `e._decider`/`e._state_machine` 属性，通常不存在 → error/空 |

---

## 五、与 PCR/行为链审计的同型问题（第三次命中）

1. **多代演进 → 代码分裂**: 三套"蓝图"概念并存（`v3_common/blueprints.py` 固定蓝图 / `planning/blueprint.py` 旧技能蓝图 / `core/agent/blueprint/` DAG 版）+ 两套运行时（`AgentOrchestrator` + `CognitiveRuntimeEngine/StateMachine`），互不接线。
2. **try/except 静默吞**: `_handle_pcr/_handle_intent/_handle_profile` 吞异常 → 关键词/假数据 fallback（与 PCR 审计"lazy import 被吞"同型）。
3. **设计有、实现断**: EventBus 订阅表/PlanGate/LoopDetector/Meta 异步循环——文档写满，代码是占位符。
4. **零测试 + 伪命令**: blueprint 包无任何单测；CLI 测试只断言"命令不抛异常"；`decider execute` 假执行（用户批判的"绿了不代表对"）。

---

## 六、审计结论与施工建议

### 6.1 蓝图是否就是编排系统？

**不是（现状）**。它是一个可用的 DAG 构建器 + 伪造的执行器 + 未闭环的学习器。它不参与 CLI 启动路径（`cli/engine.py`），所以解决不了 state.json/atexit/pytest hang 等 CLI 基础设施问题。

### 6.2 建议施工方向（供拍板）

1. **先修 P0-1（最小改动最大收益）**: `build()` 返回 `copy.deepcopy(BUILTIN_TEMPLATES[...])`，LLM override 只作用于副本；顺带修 L211 `dag.strategy` 写回。
2. **P0-4 必须先定契约**: 明确 handler 数据源。两个选项:
   - A. 修生产运行时: `bootstrap()`/`v3_session_api` 注入真实 `PCRRouterV2` + Intent（对齐 `cli/registry.py L273` 的接线方式）——让 route/intents 有真实数据；
   - B. 执行器直接调各链组件（`pcr_router.route()` / `subgraph_compiler.compile_dialogue()`），不经过 `orch.process()` 整条管线——与 PCR/子图施工方向一致，**推荐**。
   无论 A/B，**删除关键词 fallback 伪造数据**（改为显式 `{"status":"unavailable"}`）。
3. **P0-2 llm_reply**: 复用 v3_session_api Phase 4 的 switch 调用，或明确"蓝图=管线分析器、回复外部化"并删除假节点。
4. **P1-6 统一执行器**: 留 Decider（agent_native 引用它），删 executor 重复逻辑；或反之（保留 executor，Decider 变薄壳）。EventBus 要么真接 §14.3 订阅表，要么明确不接（推荐后者，避免 NATS 依赖）。
5. **P1-10 Meta 闭环**: 若本轮不做，至少在文档标注"死代码待接"；做的话需要 EventLog 消费循环 + 真副作用（check_degradations 需实际改 SkillRegistry 权重）。
6. **补契约测试**（对齐 PCR 黄金样例标准，先红后绿）: ① 模板不可变（HYBRID 后 BUILTIN_TEMPLATES 不变）② LLM override 隔离 ③ llm_reply 真实调用 ④ 权重公式保留 base ⑤ fallback 不伪造数据。

### 6.3 待拍板点

- 执行层: **EventBus 真并行** vs **直接组件调用**（推荐后者）？
- llm_reply: 蓝图自己调 LLM vs 回复外部化？
- 生产运行时: 是否本轮给 `AgentOrchestrator` 注入真实 PCR/Intent（这同时是"10 链空转"问题的修复）？
- `planning/blueprint.py` + `v3_common/blueprints.py` 两套旧蓝图如何处理（归档/糅合）？
- Meta 学习闭环是否本轮施工（牵扯行为链/元认知）？
