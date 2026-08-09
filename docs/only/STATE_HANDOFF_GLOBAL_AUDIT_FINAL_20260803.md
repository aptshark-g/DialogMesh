# 压缩交接 — 全局审计终态（2026-08-03 四查后）

> 唯一恢复入口（本批）。恢复顺序: 本文档 → `GLOBAL_AUDIT_PLAN_20260803.md`（四查节）→
> 各模块审计文档（§四索引）。
> 状态: **23 项审计/盘点全部落盘；全局审计全覆盖完成；设计全貌对应关系核查完成
> （`DOCS_LANDSCAPE_MAPPING_20260803.md`）；进入全局拍板讨论阶段**。

---

## 〇、本批新增（2026-08-03 追加: 设计全貌 ↔ 审计内容对应关系核查）

```
docs/only/DOCS_LANDSCAPE_MAPPING_20260803.md
  核心结论: 对应关系总体成立（18 业务链 + 跨切面均有 docs/only 映射），
  但存在 105 个未引用设计文档，归类为 5 类:
    A 类 33 个真设计缺口（其中约 12 个为"部分覆盖"——概念已讨论、设计文档未精读）
    B 类 4 个合并/总纲（内容已被吸收，非真缺口）
    C 类 约 25 个历史审计/状态快照（被 docs/only 取代，可归档 un_use）
    D 类 约 8 个架构总览/入门（保留一份入口即可）
    E 类 约 8 个独立项目/外部评估（网关/评审，保留原文）
  完整重构可行，但需先做 4 个前置决定（A 类处置顺序 / 归档策略 / 与全局拍板池衔接 /
  执行方式），详见文档 §四。

## 〇.5、本批追加（2026-08-03: A 类 33 缺口批量精读完成 — 8/8 批）

```
docs/only/landscape_read/（新目录，9 文件）
  BATCH1_COGNITIVE_SPACE_SCHEDULER   6 文档: WORKSPACE/SCHEDULER/V5/RUNTIME/MULTI_TIER
  BATCH2_MEMORY_PERSISTENCE          4 文档: XML_CARDS/L5/EVENT_SOURCING/UNIFIED_PERSISTENCE
  BATCH3_REASONING_KNOWLEDGE         5 文档: SEMANTIC_OBJECT/GRAPH_FALLBACK/REFINEMENT/
                                        NOISESPAN/WORLD_MODEL
  BATCH4_SERVICE_LAYER_CLI           5 文档: service_layer_addon/ENGINEERING_SERVICE_LAYER/
                                        CLI_INSPECT/CLI_REFERENCE/TUI
  BATCH5_FRONTEND_GRAPHEDITOR        6 文档: FRONTEND 系列 + GRAPH_EDITOR/SVG_FLOWCHART
  BATCH6_DIL_OBSERVABILITY_EVENTLOG  3 文档: DIL/observability(1230L)/API_EVENT_LOG
  BATCH7_V33_BEHAVIOR_SUBCOMPONENTS  4 文档: FOA/FUSION/L1SUMMARY/NEGATIVE_KB
  BATCH8_INFRASTRUCTURE              9 文档: DISTRIBUTED/EVENTBUS_V2/GATEWAY_V2/
                                        COMPRESSION_RESEARCH/PREDICTOR/REWARDER/
                                        LLM_PROVIDER_GUIDE/MCP×2
  README_INDEX                       （总索引 + 51 项冲突登记聚类）

状态: 42 篇全部读完；冲突只记录不拍板（51 项，聚类 7 组）。
关键输入: B8-2 背压矛盾为唯一直接矛盾；聚类 1（三套决策/编排归一）为全局第一议题。
下一阶段建议: 哲学消解（PARADIGM 对照）→ 全局拍板。
```

## 〇.6、本批追加（2026-08-03: 前端实现审计 + SemanticDiff 补盲 + 映射归类修正）

```
docs/only/frontend/FRONTEND_IMPL_AUDIT_20260803.md   （新目录）
  frontend/ 真实代码审计（src 约 136 源文件）:
  - FE-1 P0: 白盒编辑 API（/v6/edit/* 5 端点）后端未注册 → 前端图编辑/对话树编辑
    必然 404（v6_app 注册列表 17 项无 api_viz_edit；唯一引用在 un_use/legacy_api.py
    且其 import 目标 core.agent.v4.api_viz_edit 不存在）
  - FE-2 P1: 12+ 组件/hook/lib 死代码（ThemeToggle/ClarificationPanel/StatusBar/
    ThinkingPanel/useV6TaskWS/graph-utils 等 0 引用）
  - FE-3 P1: 四套 WebSocket 实现并存（useWebSocket/websocket/websocketClient/ws）
  - 图编辑器读路径真接线（useV6Graph→getGraph/getDiscourseTree/getObjects），写路径断

docs/only/landscape_read/SEMANTIC_DIFF_AUDIT_20260803.md
  DESIGN_SEMANTIC_DIFF 设计↔实现对照（10 分类/5 级风险一致）:
  - SD-1 P1: SemanticDiffer 被 bootstrap 注入但 agent_native 零调用（AST 约束从未生效）
  - 设计文档 0 引用盲区已补，从 A 类缺口移除

DOCS_LANDSCAPE_MAPPING 修正:
  - 9 个历史元文档确认非真缺口（BUSINESS_CHAIN_REMAINING/REMAINING_CHAINS_GAP/
    FRONTEND_AUDIT/implementation_assessment/architecture_gaps×2/reviews×2/IMPROVEMENTS）
  - 前端从"部分覆盖"升级为"已审计"（FRONTEND_IMPL_AUDIT）
  - DESIGN_GRAPH_EDITOR/DESIGN_SVG_FLOWCHART/DESIGN_SEMANTIC_DIFF 已补对应
```

---

## 一、本批新增（用户核查清单全量补齐，4 份文档）

```
docs/only/execution/TREE_MANAGER_AUDIT_20260803.md
  执行层 7 树体系（tree_manager + pipeline + closure + sandbox/permissions）
  - "零消费"勘误: ExecutionTree/ConstraintTree 真消费（ExecutionPipeline→agent_native A 路径），
    但条件触发（LLM + plan_gate 免审）；5/7 死树；B 路径零接触
  - p1_gaps.py/server.py/normalizer.py 三孤儿；sandbox/permissions 约束空转（未传 constraint_tree）
  - 新待办 X9-X14

docs/only/context/TOPIC_TREE_MANAGER_V2_DEEP_READ_20260803.md
  主题树 manager_v2 44.8KB 组件深读（挂上下文）
  - 唯一深度消费方: discourse_manager（BGE 补丁）；测试 10/17 失败 = EmbeddingEngine 只 catch
    ImportError（环境 ValueError 崩）；context_assembly/engineering_bridges 两个静默 API 断点
  - V1/V2 双轨并存；V2 热区无热度模型（heat_model 被 V1 独占）
  - 新待办 T1-T7

docs/only/causal/CAUSAL_COGNITION_ASSEMBLY_DISCOURSE_AUDIT_20260803.md
  causal/cognition/assembly/discourse 新增遗漏
  - CausalPlanner 470 行完整实现但全库零实例化（runtime/engine.py:152 声明 None 后再无赋值）
    → D6「无 slow_path」根因勘误（slow_path 代码已写好 945-957，被恒 False 守卫挡住）
  - CognitionHub 真接线（is_loaded=True）但 ingest_relations 零调用 → converge 空转
  - UnifiedContext "unified" 名不副实（DiscourseManager 半边注释）；discourse/ 薄壳断 inspect CLI
  - 新待办 C1-C5

docs/only/PERIPHERAL_DOMAINS_SURVEY_20260803.md
  外围 11 域盘点（orchestrator/coordinator/observation/memory/learning/world/frontend/
  task_engine/user_engine/security/document）
  - memory/ 孤儿确认（0 import）；world/observation TRACEABILITY 说法已过时（都活跃）
  - chroma 三套并存；orchestrator v3-v6 双宿主
  - 新待办 PE-1~PE-5（均为 P2）
```

---

## 二、审计总进度（终态）

```
✅ 19 审计单元（18 业务链 + LLM 认知层专项）——前批完成
✅ 本批 4 项: 执行层多树图 / 主题树 manager_v2 / causal+cognition+assembly+discourse /
   外围 11 域盘点
→ 合计 23 项全部落盘

剩余深读（施工时补，非阻塞）:
  coordinator/multi_tier_llm_client + bayesian_engine（19.1+20.8KB）
  observation/pool + tiered_relation_extractor（4.5+5.5KB）
  world/importance + compiler（12.8+11.8KB）
```

---

## 三、全局待拍板池（压缩后讨论，全部源文档）

### 贯穿性系统问题（P-1~P-4，新增实例）
```
P-1 接线断裂 +4: closure.py 四类死线 / sandbox+permissions 约束空转 /
     CausalPlanner 零实例化 / CognitionHub 数据零喂入
P-2 多代演进分裂 +4: p1_gaps vs tree_manager ProfileTree / V1-V2 主题树 /
     chroma 三套 / orchestrator v3-v6 双宿主
P-3 测试缺失/断裂 +1: topic_tree 10/17 失败（环境+健壮性）
P-4 双路径分裂 +3: 执行层 / cognition+assembly / CausalPlanner 均只在 A 路径
```

### 各模块待拍板（并入前批）
```
执行层:  X1-X8（前批）+ X9-X14（本批: 5 死树去留 / B 路径接线 / 约束注入 / closure 处置 / 测试）
主题树:  T1-T7（EmbeddingEngine 健壮性 / 两个 API 断点 / V1-V2 归一 / 阈值参数化 / 激活轮数）
causal:  C1-C5（CausalPlanner 注入 / CognitionHub 喂数 / UnifiedContext 定位 / discourse 门面）
外围:    PE-1~PE-5（memory 孤儿 / chroma 归一 / v3-v6 宿主 / LLM 分层两套 / 施工时深读）
元认知:  M5/M8/M9   规划: models.py 恢复   持久化: 存储架构+FactStore
LLM 认知层: 共享树接线 / 认知模式落地 / v6 接入
```

---

## 四、审计文档索引（全量）

```
docs/only/GLOBAL_AUDIT_PLAN_20260803.md    全局计划（四查节 = 本批）
docs/only/STATE_HANDOFF_LLM_COGNITIVE_20260803.md   前批 LLM 认知层交接
docs/only/execution/     AUDIT_ENTRY + DEEP_AUDIT + DESIGN_FULL_READ + TREE_MANAGER_AUDIT
docs/only/context/       AUDIT_ENTRY + DESIGN_FULL_READ + DESIGN_IMPL_AUDIT + IMPL_VERIFY
                         + TOPIC_TREE_MANAGER_V2_DEEP_READ
docs/only/causal/        CAUSAL_COGNITION_ASSEMBLY_DISCOURSE_AUDIT（新）
docs/only/PERIPHERAL_DOMAINS_SURVEY_20260803.md（新）
docs/only/meta|planner|persistence|llm_cognitive|association|behavior|pcr|subgraph|
           blueprint|intent|discourse_tree|profile|engineering|wise/...
```

---

## 五、压缩后恢复三步

```
1. 读本文档（终态 + 拍板池 + 索引）
2. 读 GLOBAL_AUDIT_PLAN_20260803.md §四查（本批实锤汇总）
3. 按需读 4 份新文档（§一）→ 进入全局拍板讨论（P-1~P-4 + C/T/X/PE 系列）
```

---

## 六、关键约束备忘（沿用）

- 全部审计完再统一讨论/拍板/施工（用户拍板，避免局部最优）。
- 做完整不做简化、质量优先、真实测试；有模型就用；监控数据定位，禁止猜测。
- 环境: anaconda 3.9 跑 pytest（`C:\Users\APTShark\anaconda3\python.exe -m pytest`）。
- 当前环境坑: sentence-transformers→transformers numpy 版本检查 ValueError
  （topic_tree 测试 10 失败根因之一；EmbeddingEngine 需 catch 宽异常）。
- 避免直接跑 event/tests/test_pluggable.py 与 test_e2e.py（NATS 无限重连）。
