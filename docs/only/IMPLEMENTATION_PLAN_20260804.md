# 施工总计划 — 后端全通 → 前端绑定（2026-08-04）

> 定位: 全部拍板完成后的施工总纲。策略（用户拍板）: **后端全通可全测无误，
> 再绑前端**（B4-5 内核唯一哲学: 后端是真值源，前端是传输投影）。
> 前端已通部分（GatewayPage/ProviderSelector /v6/gateway/*）保持为"协议样板"，
> 不扩展、不计完成度。

---

## 一、阶段划分

```
阶段 A 后端全通（当前）:
  按 M1→M9 顺序模块化施工，每模块:
    实现定案文档全部施工前置 → 后端测试全绿（含监控/压测）→ import 探针无断链
  验收 = 后端所有 /v6/* 端点返回真实数据（无 stubs_api 假数据/假执行）

阶段 B 前端绑定（后端全通后）:
  一次性接前端 15 页 + GraphEditPanel + 图表
  前提: 后端全通（协议已定，前端=纯接线）
```

---

## 二、模块施工顺序（依赖驱动）

```
M1  网关（B8-4）        ✅ 完成 2026-08-04（14/14 测试）
M2  白盒编辑后端（B5-3 层1 + G4/FE-1）✅ 完成 2026-08-04（29/29 测试）
M3  认知层（B1-8 + LLM-1 + LLM-3）✅ 完成 2026-08-04（11/11 测试）
M4  执行层（G1+G3 StateMachine + X 系列）✅ 完成 2026-08-04（10/10 测试）
M5  EventBus 生命周期（G2）✅ 完成 2026-08-04（12/12 测试 + 回归 110/110 + 压测 3 项）
M6  存储接线（G10）✅ 完成 2026-08-04（22/22 测试 + 回归 78/78 + M5 核心 71/71）
M7  服务层薄中间件（B4-1）✅ 完成 2026-08-04（8/8 测试 + 全栈 10/10 + 回归 91/91）
M8  CLI/REST 对齐（B4-5）✅ 完成 2026-08-04（内核 49/49 + 回归 127/127 + 前端 86 路径全覆盖）
M9  子图编辑层2/3（B5-3 serializer + 行为回流）✅ 完成 2026-08-04（11/11 测试 + 回归 89/89）
    → M1-M9 模块化施工清单全部完成（阶段 A 核心 9 模块）
```

---

## 三、模块施工清单（定案文档引用）

### M2 白盒编辑后端（B5-3 层1 + G4/FE-1）
```
✅ M1-P7 已做: api_viz_edit 挂 v6_app + init(engine)
✅ M2-P1  B5-3-P2: /v6/edit/revert 恢复端点（读 journal before → 应用回滚）
✅ M2-P2  B5-3-P5: 三档模式开关（默认智能 / 白盒 / 全白）
✅ M2-P3  api_viz_edit 5 端点验证（graph/tree/objects/relations/ir 真数据）
✅ M2-P4  后端测试（edit/revert/journal 全链路 29/29）
（serializer 家族 = B5-3-P3 归 M9；前端 = 阶段 B）
```

### M3 认知层（B1-8 + LLM-1 + LLM-3）
```
✅ B1-8-P1  B 套调度归档（范围修正: 只归档 scheduler/policy, path_* 保留
           — engine._scheduler 实际是 PathAwareScheduler）P1
✅ B1-8-P2  engine._cognitive_observer/_cognitive_scheduler 懒初始化 + 配置开关 P1
✅ B1-8-P3  run_cognitive_loop 接 engine 可选前置（A16 快慢, _run_cognitive_prepass）P1
✅ B1-8-P4  Workspace → cognitive_tree 写入（record_llm_thought 唯一写树入口）P2
✅ B1-8-P5  补 workspace/graph/merge/trace + 认知接线测试 11/11 P2
✅ LLM-3-P1  runtime/cli engine 挂 cognitive_tree（懒初始化）P1
✅ LLM-3-P2  执行前预测接入（predict_execution 读思考树历史）P1
✅ LLM-3-P3  对内学习闭环（record_execution_outcome: 对照+差异回写+统计）P1
LLM-3-P4  输出吸收（工程链检查项 / 元认知 / skill）P2
LLM-3-P5  simulation_engine 扩展执行预测域 P2
✅ LLM-1     6 LLM 思考记录 → CognitiveCompiler → cognitive_tree
           （compiler 坏件修复 + record_llm_thought 入口就绪）
（施工记录: docs/only/llm_cognitive/COGNITIVE_IMPL_PROGRESS_20260804.md）
```

### M4 执行层（G1+G3 + X 系列）
```
✅ G1+G3-P1  修 StateMachine（X3 补 3 handler + X4 输出传递 + X5 result 兜底）P0
✅ G1+G3-P2  StateMachine 支持 DAG 拓扑序执行（run_dag + CHAIN_TO_PHASE）P0
✅ G1+G3-P3  v3_session_api L125 归一（空壳 orch.process → 引擎 PCR+Intent 真数据）P0
✅ G1+G3-P4  agent_native 处置（无参构造清零, bootstrap 有参装配保留）P1
✅ G1+G3-P5  GlobalDecider 注入 StateMachine（复用 registry 实例, 状态底座）P1
✅ X1 已修（M1-P5）/ ✅ X2 on_event 递归（M3）/ ✅ X3 3 handler 补全 /
✅ X4 输出传递 / ✅ X5 result 兜底 / ✅ X6 死代码归档（_on_event_continue）/
✅ X7 幽灵调用 → handle_context / ✅ X8 planner 懒初始化
（施工记录: docs/only/execution/EXECUTION_IMPL_PROGRESS_20260804.md）
```

### M5 EventBus 生命周期（G2）
```
G2-P1  event_consumer 表 + per-subscriber 水位线 P1
G2-P2  semantic_value 锚点数计算 P1
G2-P3  温减枝接入（importance 三信号 + 水位线）P1
G2-P4  冷摘要化（结构降级 C → LLM 摘要 B）P2
G2-P5  A24 锚点完整性校验 P2
G2-P6  events/event_bus.py 归档 un_use P2
```

### M6 存储接线（G10）
```
✅ G10-P1  UnifiedStore → ChunkStore backend（向量接线）P1
  unified_store 文本级 API（index_texts/add_text/search_texts）+ chunk_store
  backend="unified"（BGE+LSH, 关键词降级）; DM_CHUNK_BACKEND env 驱动
✅ G10-P2  TieredStorageManager → 主存储路径（分层接线）P1
  StorageLayer(enable_tiered=True) + dm tiered stats|archive|rehydrate;
  默认 data/dialogmesh/, ~/.dialogmesh 不可写自动降级 :memory:
✅ G10-P3  孤儿后端处置（勘误: 4 后端均有活跃消费方 → 保留为可插拔后端）
  unified_graph_store 半实现完成（open/is_open/stats/query_nodes/
  run_maintenance/SnapshotRecord/snapshots）+ unified_search/domain_adapter
  补缺失 + 4 处 CLI 假执行修复
✅ PE-3    FactStore 批量写（begin_batch/end_batch 延迟落盘 + write_stats）
详细记录: docs/only/storage/STORAGE_IMPL_PROGRESS_20260804.md
```

### M7 服务层薄中间件（B4-1）
```
✅ B4-1-P1  v6_app 薄中间件层（rate_limiter/queue/session 挂 FastAPI）P1
  service_middleware.py: ServiceLayer + RateLimit/QueueGuard/Session
  三个中间件 + /v6/service/* 路由（stats/会话）
✅ B4-1-P2  core/service/v3_0 归档（先迁移 test_fullstack）P2
  test_fullstack → test_fullstack_v6（v6_app 真数据链 10/10）;
  v3_0 + service 壳（agent_service/orchestrator/api）→ un_use/;
  service/protocol+models+stores 保留为协议/组件资产;
  start_dev 入口 → v6_app
真实缺陷修复: RequestQueue 惰性队列/锁、RateLimiter 租户令牌退还、
  v3_session_api task_graph UnboundLocalError
详细记录: docs/only/service/SERVICE_IMPL_PROGRESS_20260804.md
```

### M8 CLI/REST 对齐（B4-5）
```
✅ B4-5-P1  CLI 补全（消假执行）P1
  core/agent/kernel/ 新建（唯一命令内核, 60+ 函数）
  p9_cmd 40+ 假 handler → 内核真实调用
  blueprint_cmd cmd_decider_execute 假执行 → 真 StateMachine 管线
  p5_cmd cmd_rules_delete 假删除 → 真 ABC remove_rule
✅ B4-5-P2  REST 对齐（消 stubs 假数据）P1
  stubs_api 重写: 全端点转发内核 + 删假 gateway 路由 + 删重复端点
  api_annotate 真实 JSONL 挂载 + v4_router + 缺口补齐 18 端点
  v6_app 删假 demo/usage/gateway + 新增 /v1/health
  前端 86 路径 → 后端 100% 覆盖（0 missing）
详细记录: docs/only/cli_rest/CLI_REST_IMPL_PROGRESS_20260804.md
```

### M9 子图编辑层2/3（B5-3）
```
✅ B5-3-P3  serializer 家族: JSON / XML / markdown / 自然语言
  core/agent/v4/cognitive/serializers.py（4 形态 + 别名归一 + XML 转义）
  SubgraphCompiler set_format/serialize + REST /v6/edit/serialize|format
✅ B5-3-P4  编辑行为显式进行为链（journal → _emit_behavior_edit →
  BehaviorGraphAdapter.record_step, correction=True）
  详细记录: docs/only/viz_edit/M9_SERIALIZER_IMPL_PROGRESS_20260804.md
B2-3-P1  持久化层召回能力接口（锚点+扩散+RAG 适配）P1
B2-3-P2  子图 compile_dialogue 从持久化取数（替换 11+ getattr）P2
```

---

## 四、模块级补全（穿插在各模块内，不单独成模块）

```
意图    I3-I12 ✅ 完成 2026-08-04（记录: intent/I_IMPL_PROGRESS_20260804.md）
画像    P2-P12 + H1-H6 ✅ 完成 2026-08-04（记录: profile/PROFILE_IMPL_PROGRESS_20260804.md）
对话树  D 系列 ✅ 完成 2026-08-04（记录: discourse_tree/D_IMPL_PROGRESS_20260804.md）
关联链  Phase 6（Event Sourcing 独立服务）✅ 完成 2026-08-02
        （记录: association/ASSOCIATION_IMPL_PROGRESS_20260802.md §8）
行为链  DPO ✅ 完成 2026-08-04（3.1 粗糙点 + 3.2 测试 + 3.3 B5/B7/持久化;
        记录: behavior/DPO_IMPL_PROGRESS_20260804.md）
causal  C1-C5 ✅ 完成 2026-08-05（CausalPlanner 挂载+slow_path/CognitionHub 喂数据/
        discourse 符号/裁决注释; 记录: causal/CAUSAL_IMPL_PROGRESS_20260805.md）
主题树  T1-T7 ✅ 完成 2026-08-05（T1 宽异常兜底 / T2-T3 API 断点 / T4 V1V2 归一 /
        T5 阈值参数化 / T6 激活策略 / T7 编码器契约;
        记录: topic_tree/TOPIC_TREE_IMPL_PROGRESS_20260805.md）
元认知  M5/M8/M9 ✅ 完成 2026-08-05（M5-M1 FeedbackBridge 写回 / M5-M2 订阅接线 /
        M5-M3 每5轮闭环 / M4 retrospect 真实意图 / M8 三套归一（v4 内核 +
        MetaConsumer 组件 + v3 归档）/ M9 cognitive_loop 归档 + TriggerEngine
        保留组件资产; 记录: meta/META_IMPL_PROGRESS_20260805.md）
规划    PL-1/2/3 ✅ 完成 2026-08-05（models.py git d993553 完整恢复 + 5 skill
        模型并入内核 / v4/skill_layer 门面化 / 三套归一（planner 内核 +
        v3_0 门面 + v4 门面）; planner 27/27 + 跨模块回归无新破坏;
        记录: planner/PL_IMPL_PROGRESS_20260805.md）
SD      SD-1/2/3 ✅ 完成 2026-08-05（FileSandbox.review 接 AST 语义约束
        （删函数 block / 签名·导入 require_approval / SQL·exec·网络恒 block）/
        bootstrap_v6 注入 differ+constraint / SD-3 新增测试 19 项 /
        SD-2 索引补录; SD 19/19 + 回归 88/88;
        记录: execution/SD_IMPL_PROGRESS_20260805.md）
```

> 模块级补全进度: 对话树 ✅ / 意图 ✅ / 画像 ✅ / 关联链 Phase 6 ✅（2026-08-02）/
> 行为链 DPO ✅ / causal C1-C5 ✅ / 主题树 T1-T7 ✅ / 元认知 M5/M8/M9 ✅ /
> 规划 PL-1/2/3 ✅ / **SD-1/2/3 ✅（本批）**。
> 剩余批次顺序建议: 阶段 B 前端绑定 → 全量 LLM 测试。
> 模块级补全清单 9 批全部完成。

---

## 五、验收门槛（阶段 A → 阶段 B）

```
① 后端所有 /v6/* 端点真实返回（rg stubs_api 假数据 = 0）
② CLI dm <命令> 无假执行（蓝图审计 decider execute 修复）
③ 全量后端测试绿（含压测/监控，非表面绿）
④ import 探针无断链（断链检测 CI 概念）
⑤ key 无泄漏 + 死代码已归档
```

---

> 关联: GLOBAL_PENDING_DECISIONS_20260803.md（130 项总表）/
> 各定案文档（B84/B18/B53/LLM3/G2/G10/B4-1/B4-5）/
> 语言战略 LANG_STRATEGY_20260804.md（Python 先写 → Rust 重写）
