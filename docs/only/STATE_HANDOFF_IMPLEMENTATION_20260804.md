# 压缩交接 — 施工阶段启动（2026-08-04）

> 压缩后唯一恢复入口（本批）。恢复顺序: 本文档 → `IMPLEMENTATION_PLAN_20260804.md`
> → 各定案文档（见 §四）→ 各模块审计文档。
> 状态: **全部拍板完成（10 大项定案），阶段 A 后端模块化施工中；
> M1 网关 ✅（14/14）/ M2 白盒编辑 ✅（29/29）/ M3 认知层 ✅（11/11）/
> M4 执行层 ✅（10/10）/ M5 EventBus 生命周期 ✅（12/12 + 回归 110/110）/
> M6 存储接线（G10）✅（22/22 + 回归 78/78 + M5 核心 71/71）/
> M7 服务层薄中间件（B4-1）✅（8/8 + 全栈 10/10 + 回归 91/91）/
> M8 CLI/REST 对齐（B4-5）✅（内核 49/49 + 回归 127/127 + 前端 86 路径全覆盖）/
> M9 子图编辑层2/3（B5-3）✅（serializer 四形态 + 行为回流, 11/11 + 回归 89/89）；
> **M1-M9 模块化施工清单全部完成（阶段 A 核心 9 模块）**。
> 2026-08-04 追加: 模块级补全第一批（对话树 D 系列 + D-14 + M1-P12）✅
> （D-14 CohesionScore 字段 bug 修复 + D3 内核组装: CLI registry 切 B 内核 +
> B 补 A 兼容写操作面 + CLI 门面适配；71/71 对话树+CLI + 相关跨模块回归全绿。
> 施工记录: docs/only/discourse_tree/D_IMPL_PROGRESS_20260804.md）
> 2026-08-04 追加: 模块级补全第二批（意图 I3-I12）✅
> （I3 engine 主路径接 Agent-Native 意图管线 / I4 registry 切新包 /
> I8 mcp shim 引用防御 / I9 新增 fusion+ambiguity 11 项测试；
> intent 19/19 + CLI+kernel 77/77 + MCP 26/26。
> 施工记录: docs/only/intent/I_IMPL_PROGRESS_20260804.md）
> 2026-08-04 追加: 模块级补全第三批（画像 P2-P12 + H1-H6）✅
> （P2 Track A 复活: _feed_profile_runtime 从零调用 → PROFILE 阶段逐轮接线；
> P4 L3 profile 视角已存在+测试固化；P5 cognitive_state + B manager
> cognitive_hints（组块边界判据）；P6 双向先验（PCR→TrackA EMA +
> 画像→PCR subgraph_prior）；P7 inertia 多视角喂数据；P8 ProfileContextSource
> 从零引用 → engine 绑定 + handle_context P 域注入；P9 llm_profile_analyst/
> signal_filter 归档 v4/un_use；P10 g 因子领域化；P11 OCEAN 门面方法 +
> 双名注册归一 + p10_cmd 签名对齐 + save 落盘；P12 新增 19 项测试；
> P3 PROFILE_GAP 修正；H2 WRITE_GUIDANCE。画像 19/19 + 画像回归 39/39 +
> 跨模块 116/116 + 104/104。施工记录: docs/only/profile/PROFILE_IMPL_PROGRESS_20260804.md）
> 2026-08-04 追加: 模块级补全第四批（行为链 DPO B6 + B5/B7/承诺持久化）✅
> （3.1a 可观测 kind 门控消除假 reject 池 / 3.1b no_response 自对丢弃 /
> 3.1c apply_to_graph 归一化匹配对齐率 / 3.2 新增 test_dpo_learner 18 项 /
> 3.3 承诺持久化挂载 + B7 PCR 视角声明识别 + B5 回退重模拟 engine 接线；
> DPO 18/18 + 行为链 36/36 + 跨模块 81/81。施工记录:
> docs/only/behavior/DPO_IMPL_PROGRESS_20260804.md）
> 2026-08-05 追加: 模块级补全第五批（causal C1-C5）✅
> （C1 CausalPlanner 从零实例化 → 挂载+record_step+slow_path 接线；
> C2 CognitionHub.ingest_relations 从零调用 → 关联链 discovery 喂数据；
> C3 UnifiedContext DiscourseManager 裁决注释；C4 discourse/ 包补
> DiscourseBlockTree 符号（inspect CLI 修复）；C5 行为链挂载核对。
> causal 11/11 + 跨模块 99/99。施工记录:
> docs/only/causal/CAUSAL_IMPL_PROGRESS_20260805.md）
> 2026-08-05 追加: 模块级补全第六批（主题树 T1-T7）✅
> （T1 EmbeddingEngine 宽异常兜底（10 failed → 17/17）；
> T2/T3 get_current_branch/get_active_path 真实现（context_assembly +
> engineering_bridges 断点修复）；T4 V1/V2 归一（V2 唯一内核，
> manager.py 门面 + un_use/manager_v1.py 归档 + registry 指向 V2 +
> TopicTreeContextSource 改 V2 API）；T5 阈值全参数化
> （DEFAULT_TOPIC_TREE_CONFIG + 分类器/意图映射/分叉定位器）；
> T6 auto_activate 首轮建树；T7 编码器契约（register_encoder/身份标记/
> 跨空间语义置 0）。主题树 40/40 + 上下文 46/46 + CLI 28/28 +
> 综合回归 266 passed。施工记录:
> docs/only/topic_tree/TOPIC_TREE_IMPL_PROGRESS_20260805.md）
> 2026-08-05 追加: 模块级补全第七批（元认知 M5/M8/M9）✅
> （M5-M1 FeedbackBridge post_decision 写回（MetaSubscriber → 冷→热三层反馈）/
> M5-M2 MetaSubscriber 显式 subscribe + cli 延迟接线重订阅 / M5-M3 engine
> _init_meta_runtime + on_event_sm 每 5 轮 consume / M4 retrospect 真实意图 +
> reviewed 标志修复 / M8 三套归一（v4 唯一内核 + MetaConsumer 组件 consume_trace
> + v3 Adapter 归档 v4/un_use/metacognition_v3.py + registry 指向 v4）/
> M9 cognitive_loop 归档 v4/un_use/cognitive_loop_v1.py + TriggerEngine 保留组件。
> meta 16/16 + event 63/64 + v4/cognitive 32/33 + runtime 14/14 + CLI 28/28。
> 施工记录: docs/only/meta/META_IMPL_PROGRESS_20260805.md）
> 2026-08-05 追加: 模块级补全第八批（规划 PL-1/2/3）✅
> （PL-1 planner/models.py 从 git d993553 完整恢复（1014 行，34 规划模型）
> + 并入 v4 skill_layer 5 模型为唯一内核（39 模型，删除静默 fallback 壳）/
> PL-2 v4/skill_layer 门面化（__init__ + models 均 re-export 自 planner，
> 消除 3 个不存在模块引用）/
> PL-3 三套归一验证（planner 内核 + v3_0/planning 门面 + v4/skill_layer 门面）/
> 顺带修复 event/pluggable.py NATS connect 硬超时（原无超时 → 本地无服务时
> 无限挂起卡死 event 套件）。planner 27/27 + CLI 28/28 + topic_tree/meta/
> context/intent 121/121 + event 63/64（预存在）+ runtime 14/14 +
> causal/behavior 37/37；PCR test_integration 8 项失败 = 预存在（旧 IntentParser
> 弃用 shim，a984c79，与本批无关）。施工记录:
> docs/only/planner/PL_IMPL_PROGRESS_20260805.md）
> 2026-08-05 追加: 模块级补全第九批（SD-1/2/3）✅
> （SD-1 FileSandbox.review 接入 AST 级语义约束（SemanticDiffer.diff +
> SemanticConstraint.evaluate），真实写路径生效（删函数 block / 签名·导入
> require_approval / SQL·exec·网络恒 block）；bootstrap_v6 _load_file_sandbox
> 注入 differ+constraint；SandboxIntegration 透传。SD-3 新增
> execution/tests/test_semantic_diff.py 19 项（execution 首个测试目录）。
> SD-2 DOCS_LANDSCAPE_MAPPING 执行层行补录 DESIGN_SEMANTIC_DIFF。
> SD 19/19 + 回归 88/88 + import 探针 6/6。施工记录:
> docs/only/execution/SD_IMPL_PROGRESS_20260805.md）
> 下一阶段: 模块级补全（意图/画像/对话树/关联链/行为链/causal/主题树/元认知/规划/SD）+ 阶段 B 前端绑定**。

---

## 一、本轮完成（2026-08-04，施工阶段启动）

### 1.1 拍板收尾（全部落盘）
```
B84_GATEWAY_DECISION_20260804.md        B8-4 网关主路径（switch 唯一内核 + 降级）
B18_COGNITIVE_WORKSPACE_DECISION_20260804.md  B1-8 认知运行时归 A 套
B53_SUBGRAPH_USER_EDIT_DESIGN_20260804.md     B5-3 子图三层分离（用户控制权）
LLM3_V6_COGNITIVE_INTEGRATION_20260804.md     LLM-3 v6 接入认知层（对内预测学习）
G2_EVENTBUS_LIFECYCLE_20260804.md             G2 EventBus 生命周期（GAP-1~3 细化）
LANG_STRATEGY_20260804.md                    语言战略（Python 原型 → Rust 重写）
IMPLEMENTATION_PLAN_20260804.md              施工总计划（M1-M9 + 验收门槛）
```

### 1.2 M1 网关模块完成（✅ 14/14 + cli 27/28）
```
主路径归一: cli/engine 默认 gateway + 降级（running 48/49, 6.6s）/
  bootstrap_v6 + cli/main switch 探测
X1 修复: NATS 无限重连（asyncio.wait_for 硬超时，1.74s fallback）
key 安全: provider.yaml → ${DEEPSEEK_API_KEY} + git rm --cached +
  .gitignore + state.json + chat_mbti_test 硬编码 key
GatewayLLMProvider: dm-client 鉴权 + kwargs 兼容 + urllib 兜底
switch_active: 热切换配置（不再替换引擎 provider 为直连 OpenAIProvider）
死代码归档: gateway_v2 / v3_0/llm_providers / switch_provider → un_use/
v3 别名: provider_manager 依赖的 5 个 _v3 类补回根级（双套 Provider 归一闭环）
api_viz_edit 挂载 v6_app（FE-1/G4 已解锁）
审计: GATEWAY_AUDIT_ENTRY（switch 44 文件精读 + 调用点全量）+
  GATEWAY_BENCHMARK（LiteLLM/Portkey/one-api/cc-switch/Higress 对标）
```

### 1.3 遗留记录（不阻塞，归模块）
```
D-14  CohesionScore 字段 bug（compiler/discourse_block_tree.py total vs
      total_score）→ 归对话树模块（cli test 唯一失败，1/28）
M1-P11 v3.2 scripts 直连归一（cli_v32/api_v32 — 独立工具链）P2
M1-P12 discourse_block_tree:397 直连 1234 → 归对话树（与 D-14 一起）P2
M1-P14 switch UsageStats 成本累计（switch 侧）P2
```

### 1.4 M2 白盒编辑后端完成（✅ 29/29 + 回归无新破坏）
```
/v6/edit/revert 恢复端点（journal before → 应用回滚, 回滚本身 journaled A17）
/v6/edit/mode 三档模式开关（smart/whitebox/fullwhite, B5-3-P5）
/v6/edit/journal 白盒检查（A19）
5 端点结构化 journal + 真数据改造（graph/tree/objects/relations/ir）
engine._init_whitebox: CorrectionJournal/InteractionGraph/_last_context 懒初始化
测试: core/agent/api/tests/test_viz_edit.py 29/29
```

### 1.5 M3 认知层完成（✅ 11/11 + 回归无新破坏）
```
B1-8-P1  B 套调度归档（范围修正: scheduler/policy → un_use, path_* 保留 —
         engine._scheduler 实际是 PathAwareScheduler）
B1-8-P2/P3  engine 认知运行时懒初始化 + _run_cognitive_prepass（A16 快慢）
B1-8-P4/LLM-1  record_llm_thought 唯一写树入口（CognitiveCompiler 坏件修复）
LLM-3  predict_execution + record_execution_outcome（PREDICT/EXECUTE/COMPARE/LEARN）
真实 bug 修复: on_event_sm 无限递归（anti-recursion）/ CognitiveCompiler
  从未跑通过（can_write 缺失 + store API 不匹配 + CogNodeType 不存在）/
  path_scheduler config 断链（4d3aaf7 重构遗留）
测试: test_cognitive_runtime_wiring.py 11/11
记录: docs/only/llm_cognitive/COGNITIVE_IMPL_PROGRESS_20260804.md
```

### 1.6 M4 执行层完成（✅ 10/10 + 回归 96/96 + cli 38/39）
```
G1+G3-P1  StateMachine 补全（X3 补 PLANNING/CONTEXT/LLM + X4 输出传递 +
          X5 result 兜底）— 13 阶段全管线可跑
G1+G3-P2  StateMachine run_dag（BlueprintDAG 拓扑序执行 + CHAIN_TO_PHASE）
G1+G3-P3  v3_session_api L125 归一（空壳 AgentOrchestrator → 引擎 PCR+Intent
          真数据, 保留 fallback；P0 数据流断裂修复）
G1+G3-P4  agent_native 无参构造清零（bootstrap 有参装配保留）
G1+G3-P5  GlobalDecider 注入 StateMachine（复用 registry 实例, 状态底座）
X6  _on_event_continue 461 行死代码归档 un_use（A17 保留）
X7  _compile_context 幽灵调用 → handle_context 真 IR 组装
X8  _planner 恒 None → handle_planning 懒初始化 LLMPlanner
测试: event/tests/test_statemachine_m4.py 10/10
记录: docs/only/execution/EXECUTION_IMPL_PROGRESS_20260804.md
```

### 1.7 M5 EventBus 生命周期完成（✅ 12/12 + 回归 110/110 + 压测 3 项全绿）
```
G2-P1  event_consumer 表 + per-subscriber 水位线（register/ack_consumer/
        replay_for_consumer/all_registered_consumed/prunable_events;
        ack_event 保留单消费者快捷路径）
G2-P2  semantic_value 锚点数（cross_ref + l2_summary 存在性，不 LLM 打分;
        老库 ALTER TABLE 自动迁移）
G2-P3  温减枝（importance 三信号: recency 0.4 + activation 0.3 + semantic 0.3,
        低于阈值 → 结构降级 C 保留锚点）
G2-P4  冷摘要（cold_age = retention*3; 结构降级 C 先做 + llm_summarizer 可选）
G2-P5  A24 锚点完整性校验（摘要锚点集 ⊇ 原文锚点集，不完整跳过保原文）
G2-P6  旧 events/event_bus.py → un_use/event_bus_archived/（deque 满则丢弃归档）
EventBus v2 双模: async API 保留（agent_native/permissions/closure）+
  后台循环线程 + publish_sync/subscribe_sync/request_sync/drain_sync
  （CLI 引擎同步路径）; 修复 _deliver 重复入队 bug（原双倍投递）
消费方迁移: cli/registry → v2 / engine._publish → publish_sync /
  wire_subscribers → subscribe_sync + Event 解包 / meta_subscriber → v2 主题 /
  tests/test_integration → v2
测试: tests/test_event_log_lifecycle.py 12/12
记录: docs/only/event/EVENTBUS_IMPL_PROGRESS_20260804.md
```

---

## 二、施工总计划（阶段 A 后端全通 → 阶段 B 前端绑定）

```
M1  网关（B8-4）        ✅ 完成
M2  白盒编辑后端（B5-3 层1 + G4/FE-1）✅ 完成
M3  认知层（B1-8 + LLM-1 + LLM-3）✅ 完成
M4  执行层（G1+G3 + X 系列）✅ 完成
M5  EventBus 生命周期（G2）✅ 完成
M6  存储接线（G10）✅ 完成
M7  服务层薄中间件（B4-1）✅ 完成
M8  CLI/REST 对齐（B4-5）
M9  子图编辑层2/3（B5-3）
详细清单见 IMPLEMENTATION_PLAN_20260804.md
```

---

## 三、当前环境备忘（沿用）

```
- pytest 用 anaconda3（C:\Users\APTShark\anaconda3\python.exe -m pytest）
- 避免直接跑 event/tests/test_pluggable.py 与 test_e2e.py（NATS 相关，X1 已修但仍慎跑）
- start_engine 已可正常启动（NATS 1.74s fallback，不再卡死）
- 中文写入用 apply_patch（PowerShell 管道写 Python 会 GBK 乱码）
- 环境差异: anaconda3 有 faiss / .venv 无 / hermes 无
- switch 网关未运行（8080 无响应）— start_engine 会自动降级
- git 分支前缀 codex/；gateway/provider.yaml 已 untracked（key 安全）
```

---

## 四、恢复路径（压缩后三步）

```
1. 读本文档（M1-M9 完成态 — 阶段 A 核心 9 模块全完成）
2. 读 IMPLEMENTATION_PLAN_20260804.md（施工总计划 M1-M9 清单）
3. M6 完成详情 → docs/only/storage/STORAGE_IMPL_PROGRESS_20260804.md
   M7 完成详情 → docs/only/service/SERVICE_IMPL_PROGRESS_20260804.md
   M8 完成详情 → docs/only/cli_rest/CLI_REST_IMPL_PROGRESS_20260804.md
   M9 完成详情 → docs/only/viz_edit/M9_SERIALIZER_IMPL_PROGRESS_20260804.md
4. 下一阶段（M1-M9 后）:
   模块级补全: 意图 I3-I12 / 画像 P2-P12 / 对话树 D 系列+D-14 /
     关联链 Phase 6 / 行为链 DPO / causal C1-C5 / 主题树 T1-T7 /
     元认知 M5/M8/M9 / 规划 PL-1/2/3 / SD-1/2/3
   阶段 B: 一次性绑前端 15 页 + GraphEditPanel（后端全通后）
按需读: 各定案文档（§一 清单）/ GATEWAY_AUDIT_ENTRY + BENCHMARK /
  G10_STORAGE_DECISION_20260803.md（存储分层+触发条件）/ M3 施工记录
  （llm_cognitive/COGNITIVE_IMPL_PROGRESS）/ M4 施工记录
  （execution/EXECUTION_IMPL_PROGRESS）/ M5 施工记录
  （event/EVENTBUS_IMPL_PROGRESS）/ M6 施工记录
  （storage/STORAGE_IMPL_PROGRESS_20260804.md）/ M7 施工记录
  （service/SERVICE_IMPL_PROGRESS_20260804.md）/ M8 施工记录
  （cli_rest/CLI_REST_IMPL_PROGRESS_20260804.md）/ M9 施工记录
  （viz_edit/M9_SERIALIZER_IMPL_PROGRESS_20260804.md）/
  GLOBAL_PENDING_DECISIONS（130 项总表）
```

### 后续任务（M7 之后）
```
M6  存储接线（G10）✅ 完成（详见 §四 恢复路径）
M7  服务层薄中间件（B4-1）✅ 完成（详见 §四 恢复路径）
M8  CLI/REST 对齐（B4-5）✅ 完成（内核 49/49 + 回归 127/127 + 前端 86 全覆盖）
M9  子图编辑层2/3（B5-3）✅ 完成（serializer 四形态 + 行为回流, 11/11 + 回归 89/89）
    → M1-M9 清单全完成; 下一阶段 = 模块级补全 + 阶段 B 前端
模块级补全（穿插）: 意图 I3-I12 / 画像 P2-P12 / 对话树 D 系列 + D-14 /
  关联链 Phase 6 / 行为链 DPO / causal C1-C5 / 主题树 T1-T7 / 元认知 M5/M8/M9 /
  规划 PL-1/2/3 / SD-1/2/3
阶段 B（后端全通后）: 一次性绑前端 15 页 + GraphEditPanel
```

---

## 五、git 状态

```
已改动未提交（M1-M5 模块施工，用户未要求提交）:
  M1 网关: llm_providers（gateway_provider + v3 别名）/ cli/engine + main /
    bootstrap_v6 / api_gateway（switch_active）/ v6_app / nats_bridge（X1）/
    multi_tier_llm_client / chat_mbti_test（key 清除）/ gateway/provider.yaml
    （untracked）+ .gitignore
  M2 白盒编辑: api/api_viz_edit.py（revert/mode/journal/5 端点真数据）/
    runtime/engine.py（_init_whitebox + 三档模式）/ v4/cognitive/correction_journal.py
  M3 认知层: runtime/engine.py（认知运行时 + record_llm_thought + 预测学习 +
    on_event_sm anti-recursion）/ cognitive_compiler/compiler.py（坏件修复）/
    v3_0/cognitive_tree/models.py（PREDICTION）/ v4/cognitive_scheduler/
    （scheduler+policy 归档 un_use, path_* 保留）/ path_scheduler.py（config 断链）
  M4 执行层: event/statemachine.py（X4/X5/run_dag/decider）/
    event/handlers.py（PLANNING/CONTEXT/LLM + decider 注入）/ api/v3_session_api.py
    （L125 归一）/ engine.py（X4 收尾 + X6 死代码归档）
  M5 EventBus: api/api_event_log.py（水位线 + semantic_value）/ event/log_lifecycle.py
    （新增）/ event/event_bus.py（v2 双模 + _deliver 修复）/ cli/registry.py（→v2）/
    runtime/engine.py（publish_sync）/ event/subscribers.py（subscribe_sync）/
    meta/meta_subscriber.py（v2 API）/ tests/test_integration.py（v2）/
    tests/test_event_log_lifecycle.py（新增 12 测试）/
    un_use/event_bus_archived/event_bus_v1_ringbuffer.py（旧 bus 归档）
  docs/only/*（决策/审计/施工记录/交接）
```
