# 全局审计规划 — 全部审计完再统一讨论（2026-08-03）

> 定位: 用户拍板 —— **所有模块审计完成后再统一讨论/拍板/施工**。
> 理由: 大量「冲突」（如子图 vs 上下文、PCR vs 对话树切分、域矩阵不一致）在局部看是冲突，
> 看到全貌后很多是伪问题（哲学消解已验证: 17 项待讨论 → 12 项消解）。逐模块拍板会产生
> 局部最优与全局不一致，全部审计完 = 一次拿到全貌，再按范式公约统一裁决。
> 配套: `STATE_HANDOFF_ENGINEERING_CONTEXT_20260803.md`（本轮终态）+ `RECOVERY_PLAN_20260803.md`。

---

## 一、审计总进度（截至 2026-08-03）

### ✅ 已完成（10 个模块，四轮标准: 盘点→设计对照→设计精读→运行验证）
| 模块 | 代码位置 | 审计结论（一句话）| 文档目录 |
|---|---|---|---|
| 00 PCR | pcr_router_v2 + pcr_dimensions | 已改造，权重/坐标体系已定 | docs/only/pcr/ |
| 01 意图 | intent/ + multi_intent_splitter | R1-R6 拍板 + 5 链验证 + L3 接线 | docs/only/intent/ |
| 01 对话树 | discourse_block_tree/ + compiler/ | 5 套实现 + A/B 拆包 + 内核待拍板 | docs/only/discourse_tree/ |
| 02 上下文 | context/（16 文件）+ 5 套实现族 | 算法层可用 + 2 处 P0 bug + 主路径 0% 接线 | docs/only/context/ |
| 05 行为 | behavior/ + predictor/ + rewarder | P0-P3 断链修复完成，DPO 完成 | docs/only/behavior/ |
| 06 关联 | association/（24 文件）| Phase 0-5 施工完成，Phase 6 剩余 | docs/only/association/ |
| 07 工程链 | engineering/（11 文件）| 模型层可用 + 推理层空转 + 0% 接线 | docs/only/engineering/ |
| 08 画像 | profile/ + fact_store + inertia | FactStore 完成 + Track A 复活 | docs/only/profile/ |
| 10 子图 | v4/cognitive/subgraph_compiler | 设计完成 + A/B 路径修复 | docs/only/subgraph/ |
| 11 蓝图 | blueprint/（9 文件）| 审计 + 探针实测 + 施工中 | docs/only/blueprint/ |

### ✅ 本轮新增完成（2026-08-03 追加: 第一轮盘点 + 深层次复核）
| 模块 | 代码位置 | 审计结论（一句话）| 文档目录 |
|---|---|---|---|
| 09 元认知 | meta/ + metacognition.py + v4/cognitive/metacognition.py + meta_consumer.py | 4 个静默失效（FeedbackBridge 恒空 / MetaSubscriber 从未订阅 / v6 MetaConsumer 死代码 / v4 MetaCognition 参数断裂）| docs/only/meta/ |
| 1.5 规划 | planner/（20 文件）+ causal/planner.py | 20 测试失败= v4/skill_layer 包级断链（缺 3 模块）；主规划路径 runtime 恒 None | docs/only/planner/ |
| 04 持久化 | persistence/（32 文件）+ event/storage.py + v4/persistence | 6 套体系并存；StorageLayer 非孤儿但零关联；v4 PersistenceWiring 零调用；HNSW/Milvus/chromadb 依赖缺失 | docs/only/persistence/ |
| 执行层 | event/（14 文件）+ runtime/engine.py + execution/（9 文件）| 2 个生产 P0（NATS 无限重连阻塞启动 / on_event 无限递归）+ StateMachine 3 阶段无 handler + 数据流断 | docs/only/execution/ |

> 四模块两轮审计文档: `AUDIT_ENTRY_20260803.md`（第一轮盘点）+ `DEEP_AUDIT_20260803.md`
> （深层次复核，含第一轮勘误）。深层次复核方法: 源码精读 + 全库 rg（赋值/调用点）+
> 运行时探针（faulthandler 抓栈 / 直接调用 / 依赖可用性）。

### ⏳ 剩余（8 个审计目标，本轮盘点核实）

#### 1. 09 元认知（第二大脑）
- 代码: `meta/`（feedback_bridge.py + meta_subscriber.py）+ `v4/cognitive/metacognition.py`（13.8KB）
- 已知线索: 蓝图审计「Meta 学习闭环零调用方」；A10 四职责（协同/学习/裁决/复盘）
- 关联: 消费工程链约束 + 上下文证据 → 审核 → 回写（收口整个认知闭环）

#### 2. 1.5 规划（20 文件，体量大）
- 代码: `planner/`（planner.py 35.7KB / executor.py 26KB / skill_engine.py 23.9KB / optimizer.py 19KB / strategy_selector.py 18.3KB 等 20 文件）+ `causal/planner.py`（19.6KB）
- 已知线索: 关联链审计「CausalPlanner 无 slow_path（D6）」；规划 ↔ 上下文/子图/执行层强相关

#### 3. 2.1 主题树（8 文件）
- 代码: `topic_tree/`（manager_v2.py **44.8KB 巨文件** / heat_model.py / compass_patch.py / fact_store.py / manager.py / context.py / models.py）
- 已知线索: DESIGN_PCR 提过 compass_patch；主题树 ↔ 对话树/上下文/温度系统（A15）强相关

#### 4. 02 LLM 回复侧（14 文件，跨切面）
- 代码: `llm_providers/`（circuit_breaker 16.2KB / models 17.4KB / local_provider 12.5KB / provider_manager 14.5KB / openai_provider 15.1KB / streaming 10.8KB / hybrid_router / failover / gateway 等 14 文件）
- 已知线索: 蓝图 P0-2「llm_reply 不调 LLM」；走网关 vs 直连测试；快慢通道（A16）

#### 5. 03 用户编辑树（白盒编辑）
- 代码: `discourse/`（models.py 1.9KB 薄壳）+ 实际编辑逻辑在 `api/api_viz_edit.py` / blueprint §7
- 已知线索: 白盒化（A19）承诺 CRUD 通道；用户编辑 → 版本控制 → 元认知消费

#### 6. 04 元认知持久化 + 持久化层（33 文件，最大遗留）
- 代码: `event/storage.py`（13.3KB）+ `persistence/`（33 文件: graph_store 17.9KB / tiered_storage 13.3KB / window_snapshot 13.1KB / wave_query 11.4KB / sqlite_store 12.1KB / lsm_store / hnsw / faiss / unified_graph_store / unified_store / entity_index 12.8KB / hybrid_index 等）
- 已知线索: 关联链审计提过持久化问题；存储架构拍板未决（SQLite 拓展/redis 热层/FactStore 批量写缺陷）

#### 7. StateMachine（所有链的宿主，从未单独审计）
- 代码: `event/statemachine.py`（7.4KB）+ `runtime/engine.py`（宿主，已部分触及: `_compile_context` 幽灵调用 / PLANNING/CONTEXT/LLM 无 handler）
- 已知线索: 上下文审计已实锤 C4/C5；这是 10 链的编排宿主，必须单独审计

#### 8. 因果基板 L5
- 代码: `causal_substrate/`（adapter.py 薄壳）+ `do_calculus/`（6 文件: do_calculus 5.3KB / backdoor_criterion / d_separation / frontdoor_criterion / validator / models）
- 已知线索: 关联链 D1-D5 已覆盖部分；A22/A23 因果哲学（发现型三层已落，检验型三层未实现）

### ⏳ 剩余（2026-08-03 更新: 已完成 14，剩 4）
#### 已完成本轮: 09 元认知 / 1.5 规划 / 04 持久化 / 执行层（见上方新增表）
#### 仍剩余 4 个审计目标:
1. **2.1 主题树**（topic_tree/，manager_v2.py 44.8KB 巨文件）
2. **02 LLM 回复侧**（llm_providers/，14 文件，跨切面）
3. **03 用户编辑树**（discourse/ 薄壳 + api/api_viz_edit.py）
4. **因果基板 L5**（causal_substrate/ + do_calculus/）

> 审计顺序建议更新: ① 主题树 → ② LLM 回复侧 → ③ 用户编辑树 → ④ 因果基板 L5。

### ✅ 2026-08-03 终态更新: 四模块两轮审计全部完成（14+4=18/18 盘点完成）

| 模块 | 第一轮盘点 | 深层次复核 | 第二轮设计精读 | 设计文档数 |
|---|---|:--:|---|--:|
| 09 元认知 | `meta/AUDIT_ENTRY_20260803.md` | `meta/DEEP_AUDIT_20260803.md` | `meta/DESIGN_FULL_READ_20260803.md` | 11（本体 2 + 机制 B1-B9）|
| 1.5 规划 | `planner/AUDIT_ENTRY_20260803.md` | `planner/DEEP_AUDIT_20260803.md` | `planner/DESIGN_FULL_READ_20260803.md` | 8 |
| 04 持久化 | `persistence/AUDIT_ENTRY_20260803.md` | `persistence/DEEP_AUDIT_20260803.md` | `persistence/DESIGN_FULL_READ_20260803.md` | 6 |
| 执行层 | `execution/AUDIT_ENTRY_20260803.md` | `execution/DEEP_AUDIT_20260803.md` | `execution/DESIGN_FULL_READ_20260803.md` | 8 |

**本轮核心发现（跨四模块）**:
1. 元认知: 4 个静默失效（FeedbackBridge 恒空 / MetaSubscriber 从未订阅 /
   v6 MetaConsumer 未接线 / v4 MetaCognition 参数断裂）+ 假设引擎真实现真接线（v4 壳导入即炸）
2. 规划: **P0 包级断裂**——models.py 1,197L→0.7KB 重导出壳 → 7 模块 import 全炸 →
   orchestrator v3 连带炸 + runtime 静默降级（07-21 曾 70% 实现，08-xx 回归）
3. 持久化: ENGINEERING_PERSISTENCE 新增部分（MemoryStorage/CognitiveTree/SchemaMigration/
   FTS5/Redis）全部未落地；六套体系并存；CLI 会话中间件是最落地设计
4. 执行层: 2 个生产 P0（NATS 无限重连阻塞启动 / on_event 无限递归）+ 双决策器并存
   （GlobalDecider vs DeciderStateMachine）+ 双路径分裂（A 挂了 B 没挂）

### 🔍 2026-08-03 追加核查: 剩余 4 模块 = 已审计模块的子系统（用户判断成立）

> 用代码引用实证（rg 引用方/被引用方 + 源码精读）核查，剩余 4 个中有 3 个
> **确为已审计模块的组成部分**，1 个是跨切面基础设施（本不该按"模块"审计）。

#### 1. 因果基板 L5（causal_substrate + do_calculus）→ 归并关联链/行为链 ✅
```
core/agent/causal_substrate/adapter.py（692B）= 桥接薄壳
  → from core.agent.behavior.causal_adapter import CausalSubstrateAdapter（行为链因果适配器）
association/causal_substrate.py（5.3KB）= 关联链自己的因果基板
  → 消费 core/agent/do_calculus/（validator/models 真引用）
do_calculus/（6 文件）= 关联链 causal_substrate 的验证子组件（DoCalculusValidator 等）
v3_2/do_calculus = 门面重导出
结论: 因果基板 = 关联链（已审计, D1-D5 已覆盖）的组件 + 行为链（已审计）的
  causal_adapter。不需要单独完整审计；补 do_calculus 6 文件实现细节即可。
```

#### 2. 用户编辑树（discourse/ + api_viz_edit）→ 归并对话树 ✅
```
api/api_viz_edit.py（9.8KB）= 白盒编辑 API（/v6/edit/discourse-tree）
  → edit_tree 操作 engine._discourse_tree（对话树）reclassify/merge/split/rename
  → _journal() 回写 CorrectionJournal（元认知学习）
discourse/models.py（1.9KB 薄壳）= 对话树模型旧门面（inspect_v3_cmd 用）
结论: 用户编辑树 = 对话树（已审计 discourse_tree/）的链 03 外部修改通道 +
  白盒化（A19）API 层。归并到对话树/蓝图审计（蓝图 §7 已涉及编辑→版本→元认知）。
```

#### 3. 主题树（topic_tree/）→ 归并上下文 ✅（manager_v2 需补组件深读）
```
context_manager/discourse_manager.py（87KB，上下文审计发现的 context_manager 实现族）
  → 真使用 TopicTreeManagerV2 + EmbeddingEngine（route/get_current_node，L179-196,625-639）
业务链 2.1 主题树 ↔ 上下文（BudgetAllocator）+ 对话树 + 温度系统（A15）
结论: 主题树 = 上下文（已审计 context/）体系的组成部分 + 对话树话题层。
  归并到上下文审计；manager_v2.py 44.8KB 巨文件本身未被深度审计过
  → 建议在上下文施工时做一次组件级深读（或并入上下文待办）。
```

#### 4. LLM 回复侧（llm_providers/）→ 跨切面基础设施（非单模块）⚠️
```
消费方（真接线）: service/v3_0/agent_service（ProviderManager）/ api/api_gateway /
  cli/engine + cli/main（provider 创建）/ compiler/extraction_blueprint
横切所有模块: PCR/Intent/Answer 等 6 LLM 实例都是它的消费者
蓝图审计 P0-2 已触及（llm_reply 不调 LLM）；走网关 vs 直连待拍板
结论: LLM 回复侧是跨切面基础设施（所有模块的 LLM 通道），本质是执行层 IO 子系统
  + 蓝图 P0-2 已覆盖部分。不建议按"业务模块"审计，建议作为独立基础设施审计
  （circuit_breaker/provider_manager/streaming 等实现细节未审计过）。
```

#### 审计范围调整（全局剩余从 4 → 0 模块，改为 1 项补深 + 1 项基础设施）
```
① 主题树 manager_v2 组件深读 → 挂上下文审计（施工时做）
② LLM 回复侧 → 独立基础设施审计（跨切面，走网关/直连/熔断/流式）
③ do_calculus 6 文件 → 挂关联链审计补充
④ 用户编辑树 → 挂对话树/蓝图审计补充（api_viz_edit 已核）

→ 全局审计实际收敛: 18/18 模块盘点完成，业务链全覆盖；
  剩余工作 = 主题树组件深读 + LLM 基础设施审计 2 项（非 4 模块）。

### 🧠 2026-08-03 二次核查: LLM 思考树 + 未归入代码域（用户补充）

> 用户提示"可能还有一些，比如 LLM 的思考树"→ 全面盘点 `core/agent` 全部 70+ 目录
> 对照已审计模块，发现 **思考树体系（3 包）未归入 + 若干跨切面/宿主域未盘点**。

#### A. 思考树体系（新增审计项，用户点名）

| 包 | 体量 | 内容 | 消费方（活跃度）|
|---|--:|---|---|
| `v3_0/cognitive_tree/` | 65KB | 认知树/知识超图（CognitiveTree 管理器 + CognitiveTreeNode/Edge + CrossRef + AccessControlMatrix）| **6 个 LLM 实例**（pcr/intent/planning/meta/reflective/answer 全 import）+ orchestrator + context/manager + planner + security（bias/hallucination detector）|
| `v3_0/cognitive_compiler/` | 74KB | 认知编译器全套（compiler/edge_manager/event_bus/lifecycle/meta_cognitive/pcr_feedback/profile_updater/querier/reflective/rule_conflict/tree_health）| orchestrator/bootstrap + orchestrator/orchestrator 真接线（v3 路径）|
| 根级 `cognitive_compiler/` | 49.6KB | compiler/decomposer/dual_manager/entity_cache/injector/scorer | compiler 引用 v3_0 版；**decomposer/injector/scorer/dual_manager 全库零引用（孤儿）**|
| `tiered/` | 68.8KB | 分层编译管线（action_resolver/jieba/stanza/syntactic_decomposer/topic_matcher/cognitive_compiler/context_compiler/fusion/heat_bridge/pipeline）| **v6 活跃**：discourse_block_tree(RuleDecomposer) + extraction_blueprint(jieba/stanza) + observation 5 domain_adapter + runtime/p3_resolver(TieredCognitiveCompiler)|

```
结论: 思考树 = v3.0 认知树（知识超图）+ 认知编译器 + v6 分层编译（tiered）。
  v3 路径（6 LLM + orchestrator）活跃；v6 主路径（runtime/cli engine）不消费 cognitive_tree，
  但消费 tiered/（对话树 A 路径语法分解 + observation action_resolver）。
  → 新增 1 个审计项: 思考树体系（cognitive_tree + cognitive_compiler + tiered），
    与 LLM 回复侧审计合并为"LLM 认知层"专项。
```

#### B. 未归入代码域清单（分级，供拍板）

| 级别 | 目录 | 体量 | 状态 |
|:--:|---|---|--:|
| 🔴 宿主 | `orchestrator/` | 144KB/9f | AgentOrchestrator v3 + agent_native v6（蓝图审计触及，本体未审计）|
| 🔴 协调 | `coordinator/` | 93.5KB/7f | bayesian_engine/fusion/multi_tier_llm/small_model_client（未审计）|
| 🔴 观察 | `observation/` | 52KB/20f | 观察编译器全套（**活跃**: behavior/adapter + cli/registry + document/pipeline 消费；TRACEABILITY"闲置"已过时）|
| 🟡 记忆 | `memory/` | 45.8KB/6f | xml_cards/federated_index（**孤儿**: 全库零引用；L5 设计已精读见 meta DESIGN_FULL_READ）|
| 🟡 学习 | `learning/` | 54KB/8f | ingestion/credibility/sources（**活跃**: blueprint/meta_feedback + llm_dag_builder + cli/engine 消费）|
| 🟡 世界 | `world/` | 43.7KB/8f | 世界模型（TRACEABILITY"42L stub"过时——实际 43KB 完整实现，未审计）|
| 🟡 服务 | `core/agent/service/` + `core/service/` | ~248KB | 服务层两处（agent_service/api/session/rate_limiter/stores）|
| 🟡 前端 | `frontend/` | 77KB/6f | clarification_fsm/ui/multimodal/taskgraph_viz/websocket（未审计）|
| 🟢 任务 | `task_engine/` | 43.8KB/4f | TaskManager（context_manager v3 路径消费）|
| 🟢 用户 | `user_engine/` | 53.9KB/5f | UserManager/Extractor（context_layer 消费；画像审计已触及 v3 规则）|
| 🟢 安全 | `security/` | 22.9KB/6f | bias/hallucination detector（消费思考树）|
| 🟢 文档 | `document/` | 34KB/6f | extractor/parsers/pipeline（观察编译相关）|

> **归并判断**: 思考树体系（A）→ 新增"LLM 认知层"审计（含 LLM 回复侧）；
> orchestrator/coordinator → 并入执行层/蓝图审计补充；observation → 并入上下文/关联链补充；
> memory/learning → 并入元认知/L5 审计补充；world/service/frontend → 外围服务审计（P2）；
> task_engine/user_engine/security/document → 挂既有模块（画像/工程/观察）。

#### C. 审计收口（2026-08-03 最终）

```
① 主题树 manager_v2 组件深读（挂上下文）
② LLM 认知层专项 = 思考树（cognitive_tree + cognitive_compiler + tiered）+
   LLM 回复侧（llm_providers）——跨切面核心，1 个专项审计
③ 外围服务审计（world/service/frontend/orchestrator/coordinator）——P2 可选
④ 已归并: do_calculus→关联链 / 用户编辑树→对话树 / observation→上下文 /
   memory→元认知 / learning→蓝图 / security→工程

### 🧠 2026-08-03 三查: LLM 认知层专项审计完成（用户点名"思考树"）

> 新开专项 `docs/only/llm_cognitive/`（AUDIT_ENTRY + DESIGN_FULL_READ 七节），
> 覆盖: 思考树（v3_0/cognitive_tree 65KB）+ 认知编译器（v3_0 74KB + 根级 49.6KB）+
> tiered/ 分层编译（68.8KB）+ llm_providers（139.5KB）。

**核心实锤（5 项）**:
1. **LLM 间共享树通信全链路断**——6 个 LLM 实例（llm_engine.py）从不调用认知编译器、
   从不写树（build_cog_node 定义未用，process() 返回 node_id=None）；
   而编译器（唯一入口）完整实现 + v3 orchestrator 已接线。
2. **LLM Provider v3.0 升级全未落地**——cognitive_mode/generate_native_async/
   CognitiveModeProvider/模式路由零实现；根级与 v3_0 两套 Provider 并存；零测试。
3. **cognitive_tree CrossRef async 迁移 9 测试失败**（同型"演进→测试未同步"）。
4. **根级 cognitive_compiler 4 文件孤儿**（decomposer/injector/scorer/dual_manager）。
5. **v6 主路径不消费认知层**（runtime/cli 零引用 cognitive_tree），但 tiered/
   （v6 分层编译）活跃在对话树 A 路径 + observation action_resolver + runtime p3。

**审计状态更新**: 全部业务链 18 模块 + LLM 认知层专项 = **19 审计单元完成**；
剩余 = 主题树 manager_v2 组件深读（挂上下文）+ 外围服务审计（P2 可选）。
```
```

### 🧠 2026-08-03 四查: 用户核查新增全量补齐（3 新审计 + 1 外围盘点，全部落盘）

> 用户补充清单:「执行层多树图 / LLM 认知层（已做）/ 主题树 manager_v2 / 未归入代码域 /
> causal+cognition+assembly+discourse 遗漏」→ 本批全部核查完毕。

#### A. 新增落盘文档（本批）
```
docs/only/execution/TREE_MANAGER_AUDIT_20260803.md         执行层 7 树体系深审
docs/only/context/TOPIC_TREE_MANAGER_V2_DEEP_READ_20260803.md  主题树 manager_v2 深读
docs/only/causal/CAUSAL_COGNITION_ASSEMBLY_DISCOURSE_AUDIT_20260803.md  causal/cognition/assembly/discourse 遗漏审计
docs/only/PERIPHERAL_DOMAINS_SURVEY_20260803.md            外围 11 域盘点
```

#### B. 核心实锤（勘误 + 新发现）
```
① 执行层 7 树: "零消费"勘误——ExecutionTree/ConstraintTree 经 ExecutionPipeline
   （agent_native A 路径）真消费，但条件触发（需 LLM+plan_gate 免审）；5/7 死树
   （discourse/association/behavior/profile/meta 假消费）；B 路径零接触；p1_gaps.py
   与 server.py/normalizer.py 三孤儿。
② 主题树 manager_v2: 唯一深度消费方 discourse_manager（BGE 补丁）；测试 10/17 失败=
   EmbeddingEngine 只 catch ImportError（环境 ValueError 崩）；两个静默断点
   （context_assembly.get_current_branch / engineering_bridges.get_active_path 不存在）；
   V1/V2 双轨并存。
③ causal/cognition/assembly/discourse:
   - CausalPlanner 470 行实现完整但全库零实例化（runtime/engine.py:152 声明 None 后再无赋值）
     → D6「无 slow_path」根因勘误 = 引擎从未注入，slow_path 代码其实已写好（945-957）
   - CognitionHub 真接线（is_loaded=True 实测）但 ingest_relations 零调用 → converge 空转
   - UnifiedContext 的 DiscourseManager 半边整段注释 → "unified" 名不副实
   - discourse/ 薄壳断 inspect CLI（DiscourseBlockTree 符号缺失）
④ 外围 11 域: memory/ 孤儿确认（0 import）；world/observation/learning/frontend/
   coordinator/task/user/document 全部真接线（与"接线断裂"普遍现象相反）；
   chroma 三套并存（PE-2）；orchestrator v3-v6 双宿主（PE-3）。
```

#### C. 审计收口（全局终态）
```
19 审计单元 + 本批 4 项 = 23 项全部落盘。
剩余深读（施工时补）: coordinator multi_tier_llm_client/bayesian_engine、
  observation pool/tiered_relation_extractor、world importance/compiler（PE-5）。
剩余拍板（并入全局池）: C1-C5 / T1-T7 / X9-X14 / PE-1~PE-5（详见各文档）。
```

---

## 二、审计顺序建议

按「宿主优先 → 强关联优先 → 体量大的优先」：

```
第 1 批: StateMachine（宿主）+ 主题树（与上下文/温度强相关）
第 2 批: 规划（体量大）+ 因果基板 L5（A22/A23 落地核查）
第 3 批: 元认知（收口）+ 元认知持久化/持久化层（33 文件，存储底座）
第 4 批: LLM 回复侧（跨切面）+ 用户编辑树（白盒）
```

每个模块沿用四轮标准（盘点 → 设计对照 → 设计精读 → 运行验证），
落盘到 `docs/only/<module>/`，最终统一收敛到全局讨论。

---

## 三、全局讨论的收敛机制（全部审计后）

1. 每个模块审计产出「待拍板清单」→ 汇总为**全局拍板池**；
2. 用 PARADIGM 公约（A1-A25/P1-P28）做**全局哲学消解**（如本轮 17→5）：
   局部冲突 → 全貌下识别真伪；
3. 真冲突按 §5 元规则裁决（体验不阻断 > 单次准确 / 真实验证 > 指标好看 /
   安全不可协商 / 记录永不可删 / 回到约束空间）；
4. 消解后剩余的**真拍板点**统一施工（不逐模块施工，避免局部最优）。

---

## 四、压缩恢复指引

```
恢复顺序:
1. docs/only/RECOVERY_PLAN_20260803.md（总恢复入口）
2. docs/only/STATE_HANDOFF_20260803_FINAL.md（三模块施工终态）
3. docs/only/STATE_HANDOFF_ENGINEERING_CONTEXT_20260803.md（工程链/上下文终态 + 5 项核心讨论）
4. 本文档（全局审计规划: 剩余 8 模块清单 + 顺序）
5. 按顺序开第 1 批审计（StateMachine + 主题树）
```

> 2026-08-03 四查后更新: 第 5 步已完成——StateMachine 在执行层审计（execution/）覆盖、
> 主题树 manager_v2 深读已落盘；本批新增 4 文档见上。恢复入口改为
> `STATE_HANDOFF_GLOBAL_AUDIT_FINAL_20260803.md`（§四查后的交接终态）。
