# 设计全貌 ↔ 审计内容 对应关系核查（docs ↔ docs/only）

> 日期: 2026-08-03 | 任务: 用户要求「对设计内容全貌核查，建立 docs/only（梳理内容）与
> docs（完整文档全貌）的对应关系，找出不能匹配的内容，评估完整重构可行性」。
> 方法: 全量文件盘点 + 双向引用矩阵（每个 docs/ 设计文档在 docs/only 中被引用的次数与位置
> 的机械扫描）+ 关键未匹配文档首段精读分类。
> 结论先行: **对应关系总体成立（18 业务链 + 跨切面均有映射），但存在 5 类未匹配内容
> （约 60 个真缺口文档），完整重构可行但需要先做 4 个前置决定。**

---

## 一、体量全貌

```
docs/        完整文档全貌:  ~360 文件 / ~4,200KB
  ├─ 根级:   ~100 文件（BUSINESS_CHAIN_* / DESIGN_* / 审计报告）
  ├─ v3.0/:  106 文件（大设计 + ENGINEERING_* 工程文档 + REVIEW/LITERATURE）
  ├─ v5/:     52 文件（V5-V6 设计演进）
  ├─ merge/:   6 文件（00-04 合并设计总纲）
  ├─ project/: 2 文件（持久化 / 服务层补充）
  ├─ blog/:    3 文件（哲学博客）
  ├─ legacy/:  3 文件（PCR 旧评估）
  └─ api/architecture/design/: 5 文件

docs/only/   梳理内容:  89 文件 / 1,057KB（17 模块目录 + 12 根级交接/规划）
```

---

## 二、对应关系主矩阵（18 业务链 + 跨切面 ↔ docs/only 目录 ↔ 关键设计文档）

| # | 业务链/域 | docs/only 目录 | 覆盖的设计文档（docs/）| 引用量 |
|---|-----------|---------------|------------------------|:--:|
| 00 | PCR | pcr/ (7) | design_layer0_pcr_and_layer1_intent_parser / design_pcr_interface_v2_1 / design_pcr_issues_discussion / ENGINEERING_PCR / PCR_COMPLETE / legacy/ 3 件 | 65 |
| 01 | 对话树 | discourse_tree/ (5) | design_discourse_block_tree + v2 / BUSINESS_CHAIN_01 / BUSINESS_CHAIN_AUDIT_DIALOGUE_TREE / DESIGN_FULL_CONCEPT(部分) | 15 |
| 01 | 意图 | intent/ (3) | design_layer1_intent_parser / ENGINEERING_INTENT_PARSER / ENGINEERING_MULTI_INTENT_SPLIT / DESIGN_AGENT_NATIVE_INTENT / BUSINESS_CHAIN_01_INTENT + UNIFIED_INTENT | 8 |
| 02 | 上下文 | context/ (5) | design_context_window / ENGINEERING_CONTEXT_MANAGER / DESIGN_CROSS_DOMAIN_CONTEXT / DESIGN_V4_CONTEXT_ENGINEERING / BUSINESS_CHAIN_02 / topic_tree 深读 | 10 |
| 02 | LLM 回复侧 | llm_cognitive/ (2) | ENGINEERING_LLM_PROVIDERS / DESIGN_MULTILAYER_LLM_COGNITIVE / ENGINEERING_MULTILAYER_LLM / BUSINESS_CHAIN_02_LLM_RESPONSE_SIDE | 5 |
| 03 | 用户编辑树 | discourse_tree/（并入）| BUSINESS_CHAIN_03_USER_EDIT_TREE / DESIGN_GRAPH_EDITOR* | 1 |
| 04 | 元认知持久化 | persistence/ (3) | ENGINEERING_PERSISTENCE / DESIGN_UNIFIED_PERSISTENCE / project/design_persistence / BUSINESS_CHAIN_04 / DESIGN_DIALOGUE_TREE_PERSISTENCE_ADAPTER | 10 |
| 05 | 行为链 | behavior/ (6) | BUSINESS_CHAIN_05 + SUPPLEMENT / DESIGN_V3_1_BEHAVIOR_SUMMARY / ENGINEERING_V3_3_BEHAVIOR_GRAPH + EMBEDDING / DESIGN_BEHAVIOR_LLM_COLLABORATIVE | 6 |
| 06 | 关联链 | association/ (6) | BUSINESS_CHAIN_06 / DESIGN_ASSOCIATION_CHAIN_L1_L4 / ENGINEERING_V3_3_CAUSAL_SUBSTRATE + DO_CALCULUS / DESIGN_RELATION_SUBSTRATE / DESIGN_UNIFIED_INTENT_ASSOCIATION | 4 |
| 07 | 工程链 | engineering/ (4) | BUSINESS_CHAIN_07 / DESIGN_ENGINEERING_CHAIN + ONTOLOGY / ENGINEERING_TOOL_REGISTRY(部分) | 3 |
| 08 | 画像 | profile/ (4) | design_cognitive_profile_v2 / ENGINEERING_COGNITIVE_PROFILE_V2 / BUSINESS_CHAIN_08 + FEEDBACK / DESIGN_STATE_EVOLUTION_SYSTEM(部分) | 3 |
| 09 | 元认知 | meta/ (3) | BUSINESS_CHAIN_09 / DESIGN_METACOGNITION_RUNTIME / DESIGN_HYPOTHESIS_ENGINE / LITERATURE_REVIEW_COGNITIVE_PROFILE_V2 / L5 记忆设计 | 4 |
| 1.5 | 规划 | planner/ (3) | DESIGN_PLANNING_SKILL_LAYER / ENGINEERING_PLANNING_SKILL / DESIGN_TASK_PLANNING_DYNAMIC / BUSINESS_CHAIN_1.5 / PLANNER_CONTEXT_AND_REST | 2 |
| 10 | 子图 | subgraph/ (3) | BUSINESS_CHAIN_10 / DESIGN_CROSS_DOMAIN_CONTEXT(部分) / DESIGN_SEMANTIC_WORLD_MODEL(部分) | 3 |
| 11 | 蓝图 | blueprint/ (14) | DESIGN_BLUEPRINT_ORCHESTRATION / DESIGN_BLUEPRINT_SYSTEM / ENGINEERING_BLUEPRINT / DESIGN_SYSTEM_SCHEDULER / DESIGN_EVENTBUS_V2* | 5 |
| 2.1 | 主题树 | context/（并入）| design_topic_tree / ENGINEERING_TOPIC_TREE / DESIGN_TOPIC_TREE_GRANULARITY / TOPIC_TREE_DISCUSSION / BUSINESS_CHAIN_2.1 | 14 |
| — | 执行层/StateMachine | execution/ (4) | DESIGN_EXECUTION_LAYER / DESIGN_GLOBAL_STATE_MACHINE / DESIGN_RUNTIME_KERNEL / DESIGN_FILESANDBOX / DESIGN_PERMISSIONS / DESIGN_GUARD_SYSTEM / DESIGN_SEMANTIC_DIFF（SD 批次补录） / BUSINESS_CHAIN_STATE_MACHINE | 5 |
| — | LLM 认知层 | llm_cognitive/ (2) | DESIGN_MULTILAYER_LLM_COGNITIVE / design_cognitive_compiler / DESIGN_COGNITIVE_DYNAMICS_V6 / ENGINEERING_COGNITIVE_COMPILER / tiered 系列 | 10 |
| — | 因果基板 L5 | causal/（新）+ association | ENGINEERING_V3_3_CAUSAL_SUBSTRATE + DO_CALCULUS / DESIGN_HYPOTHESIS_ENGINE(部分) | 4 |
| — | 外围服务 | PERIPHERAL_DOMAINS_SURVEY + **frontend/（新增，FRONTEND_IMPL_AUDIT）** | DESIGN_FRONTEND* / FRONTEND_ARCHITECTURE* / DESIGN_DOCUMENT_INGESTION_LAYER* / DESIGN_OBSERVATION_COMPILER(部分) / ENGINEERING_SERVICE_LAYER* / DESIGN_GRAPH_EDITOR / DESIGN_SVG_FLOWCHART / DESIGN_SEMANTIC_DIFF（已补读）| — |
| — | 哲学 | wise/ (4) | blog/ 3 章 / THOUGHT_IMPRINT / DESIGN_COMPETITOR_ABSORPTION | 10 |

> `*` = 该设计文档在 docs/only 中未被引用（见 §三 未匹配清单），此处列为"应归属"而非"已覆盖"。

---

## 三、未匹配内容清单（不能建立对应关系的文档）

### 3.1 核查方法
```
对 docs/ 全部设计文档（根级 + v3.0 + v5 + merge + project + blog + legacy + api）做
「基名在 docs/only 全量 89 文件中的出现次数」扫描：
  - 0 次  → 完全未匹配（105 个）
  - >0 次 → 已建立对应关系（约 250 个）
二次精查（宽松子串 + 内容语义）排除"改名前缀"误报后，真缺口归类如下。
```

### 3.2 未匹配文档分类（5 类，约 60 个真缺口 + 45 个历史/元文档）

#### A 类：真设计缺口（有实质设计内容，审计未覆盖/未精读）—— 33 个 ⚠️
```
标注: 「部分覆盖」= 概念已在 docs/only 被讨论（模块有认知），但该设计文档本体
未被引用/精读——缺口在"设计文档级吸收"，修复成本低于纯零认知缺口。

认知空间/调度类:
  DESIGN_COGNITIVE_WORKSPACE.md      四空间模型（LLM 内部认知空间）—— 元认知/思考树核心
                                     （"四空间"概念在 meta/only 有 2 处 → 部分覆盖）
  DESIGN_COGNITIVE_SCHEDULER.md      认知调度器（谁/何时/多久/优先级）—— 执行层快慢系统
                                     （"调度/Scheduler"概念在执行/规划被广泛讨论 → 部分覆盖）
  DESIGN_COGNITIVE_SYSTEM_V5(_CN).md v5 认知系统总览
  DESIGN_COGNITIVE_RUNTIME.md        认知运行时
  DESIGN_MULTI_TIER_PIPELINE.md      多层级管线（与 tiered/ 相关）

记忆/持久化类:
  DESIGN_XML_MEMORY_CARDS.md         L5 XML 记忆卡（memory/ 孤儿模块的设计来源；
                                     "xml_cards"概念在 meta/persistence 5 处 → 部分覆盖）
  DESIGN_L5_LONG_TERM_MEMORY.md      L5 长期记忆（meta/wise 2 处提及，无完整审计）
  DESIGN_EVENT_SOURCING_CQRS.md      Event Sourcing + CQRS 内核（关联链 Phase 6 设计源；
                                     "Event Sourcing"概念在 association 等 13 处被讨论，
                                     但设计文档本体未引用 → 部分覆盖）
  DESIGN_UNIFIED_PERSISTENCE.md      统一持久化（persistence 5 处提及 → 部分覆盖）

推理/知识类:
  DESIGN_SEMANTIC_OBJECT.md          语义对象（v6 /objects 端点；association 1 处 → 部分覆盖）
  DESIGN_GRAPH_FALLBACK.md           图回退（仅 only 1 处概念）
  DESIGN_V4_KNOWLEDGE_REFINEMENT.md  v4 知识精炼（仅 only 1 处概念）
  DESIGN_NOISESPAN.md                噪声拓扑标记（PCR 演进；pcr 2 处 → 部分覆盖）
  DESIGN_SEMANTIC_WORLD_MODEL.md     语义世界模型（仅 subgraph 提一句）

服务/前端/工程类:
  project/design_service_layer_addon.md  服务层 v2.3（56KB！两处服务层实现的设计源；
                                         "服务层"概念 context/only 4 处 → 部分覆盖）
  ENGINEERING_SERVICE_LAYER.md           服务层工程文档（同上）
  DESIGN_FRONTEND.md + FRONTEND_ARCHITECTURE.md + FRONTEND_BUSINESS_FLOW.md
                                      （"frontend"概念 blueprint/pcr/only 8 处 → 部分覆盖）
  DESIGN_FRONTEND_CLI_MAPPING.md         前端-CLI 映射
  DESIGN_CLI_INSPECT.md + DESIGN_CLI_REFERENCE.md + DESIGN_TUI.md    CLI 设计三件
                                      （CLI 总体 DESIGN_CLI.md 已覆盖 59 处；这三件是子设计）
  DESIGN_DOCUMENT_INGESTION_LAYER.md     文档摄入层（仅 only 1 处概念）
  design_observability.md                可观测性设计（observability 概念 9 处 → 部分覆盖）
  DESIGN_API_EVENT_LOG.md                事件日志 API
  DESIGN_GRAPH_EDITOR.md                 图编辑器（用户编辑树关联；前端实现已审计 FRONTEND_IMPL_AUDIT）
  DESIGN_SVG_FLOWCHART.md                流程图

v3.3 行为子组件（4 个）:
  ENGINEERING_V3_3_FOA.md / ENGINEERING_V3_3_FUSION.md /
  ENGINEERING_V3_3_L1SUMMARY.md / ENGINEERING_V3_3_NEGATIVE_KB.md

跨切面/基础设施:
  DESIGN_DISTRIBUTED.md / DESIGN_EVENTBUS_V2.md / DESIGN_GATEWAY_V2.md
  （EventBus 概念在蓝图/执行层被讨论，但 DESIGN_EVENTBUS_V2 本体未引用 → 部分覆盖）
  CONTEXT_COMPRESSION_RESEARCH.md / ENGINEERING_V3_3_PREDICTOR.md / ENGINEERING_V3_3_REWARDER.md
  LLM_PROVIDER_GUIDE.md / MCP_DEPLOYMENT_BOUNDARY.md / mcp_industrial_assessment.md
```

> 修正说明（宽松复核后）: A 类中约 12 个实为「部分覆盖」——概念已在 docs/only 被讨论
> （如 Event Sourcing / 调度 / xml_cards / observability），但对应设计文档本体从未被
> 引用或精读。这类缺口只需补 1 份精读并与已有讨论衔接，但同样需进拍板池。

#### B 类：合并/总纲文档（已被 merge/ 或 docs/only 吸收）—— 4 个
```
DESIGN_00_OVERVIEW.md（= DESIGN_V4_CONTEXT_ENGINEERING + FULL_CONCEPT + THOUGHT_IMPRINT 合并）
DESIGN_03_INPUT_AND_SKILL.md / DESIGN_04_INTERFACE.md（merge 系列）
ARCHIVE_INDEX.md
→ 内容已存在于其源文档，源文档已建立映射 → 非真缺口
```

#### C 类：历史审计/状态快照（已被 docs/only 审计取代）—— 约 25 个
```
ARCHITECTURE_AUDIT_9_ISSUES / DESIGN_VS_IMPL_AUDIT / DESIGN_IMPLEMENTATION_DEEP_COMPARISON /
DEEP_ASSESSMENT_PHASE2 / FULL_ARCHITECTURE_AUDIT / FINAL_AUDIT(v5) / P0_AUDIT / P2_AUDIT /
SECURITY_PERFORMANCE_AUDIT / TECH_DEBT_TEST_AUDIT / GAP_ANALYSIS / CAPABILITY_GAP /
CURRENT_FLOW / coverage_map / LINKAGE_QUALITY_REPORT / linkage_audit / PHASE1_VERIFICATION /
quality_gates / TEST_LINKAGE_PLAN / V5_GAP_ANALYSIS / V3_COMMON_AUDIT_DECISIONS /
DECIDER_STATUS / UNIMPLEMENTED_ROADMAP / IMPLEMENTATION_REALITY / KEYS_TO_CLEAN /
FULL_MODULE_INVENTORY_V1 / MODULE_MIGRATION_PLAN / MESH_DEPENDENCY / DIAGNOSE_500 / TEST_REPORT
→ 均为一次性审计快照，docs/only 是其后继 → 可归档 un_use
```

> **2026-08-03 用户核查修正（9 个历史元文档 = 非真缺口，全部归类确认）**:
> 用户点名 9 个未引用文档应归为历史元文档而非真缺口，逐一核实:
> - BUSINESS_CHAIN_REMAINING.md — 剩余链记录（内容已被 BUSINESS_CHAIN_* 各文档吸收）
> - REMAINING_CHAINS_GAP.md — 空文件（0KB，无内容）
> - FRONTEND_AUDIT.md — 前端审计报告（2026-07-20 早于本次审计，被 FRONTEND_IMPL_AUDIT 取代）
> - implementation_assessment.md — 历史实现评估（merge/DESIGN_00 已吸收）
> - design_architecture_gaps.md / design_architecture_gaps_v2.md — 历史架构缺口记录
> - REVIEW_FULL_CONCEPT_ENGINEERING / REVIEW_MULTILAYER_LLM_CHECK /
>   REVIEW_PLANNING_DESIGN_ENGINEERING — 历史评审（v3.0/reviews/ 下 3 份）
> - IMPROVEMENTS.md（design/）— 历史改进清单
> → 以上 9+ 份全部确认"内容已被吸收或已被取代"，归 C/D/E 类处置，非 A 类真缺口。

### 🆕 2026-08-03 前端实现审计补全（最大盲区）
```
docs/only/frontend/FRONTEND_IMPL_AUDIT_20260803.md
  前端 frontend/ 139 文件（src 约 136 源文件）真实代码审计:
  - 白盒编辑 API（/v6/edit/* 5 端点）后端未注册 → 图编辑/对话树编辑 404（FE-1 P0）
  - 12+ 组件/hook/lib 死代码（FE-2）；四套 WebSocket 实现并存（FE-3）
  - 对应设计: DESIGN_FRONTEND / FRONTEND_ARCHITECTURE / DESIGN_GRAPH_EDITOR /
    DESIGN_SVG_FLOWCHART / FRONTEND_CLI_MAPPING（BATCH5 已读设计，本审计补代码）
docs/only/landscape_read/SEMANTIC_DIFF_AUDIT_20260803.md
  DESIGN_SEMANTIC_DIFF（AST 级约束）设计↔实现对照:
  - 设计 10 分类/5 级风险 ↔ 实现 ChangeClass/RiskLevel 一致
  - SemanticDiffer 被 bootstrap 注入但 agent_native 零调用（SD-1 P1）
```

#### D 类：架构总览/入门（可归并）—— 约 8 个
```
ARCHITECTURE_INDEX / ARCHITECTURE_CONDENSED / ARCHITECTURE_MERMAID / ARCHITECTURE_OVERVIEW /
COARSE_MODULE_ARCHITECTURE / FINE_MODULE_DESIGN / SYSTEM_DESIGN / THREE_TIER_ARCHITECTURE /
INTEGRATION_ARCHITECTURE / DESIGN_SPECIFICATION / FULL_BUSINESS_FLOW / README / QUICKSTART /
CONFIGURATION / TROUBLESHOOTING / GUI_API
→ 作为入口/总览保留一份即可，其余并入架构索引
```

#### E 类：独立项目/外部评估 —— 约 8 个
```
GATEWAY_DESIGN / GATEWAY_FULL_AUDIT / GATEWAY_SAVE_AUDIT（网关独立项目 switch/）
EVALUATION_as_frontend_agent / EVAL_AND_FORMAT_ANALYSIS / quality_metrics_literature
REVIEW_FULL_CONCEPT_ENGINEERING / REVIEW_MULTILAYER_LLM_CHECK / REVIEW_PLANNING_DESIGN_ENGINEERING
→ 外部评审/评估，保留原文即可
```

---

## 四、完整重构可行性评估

### 4.1 结论：可行，但需先做 4 个前置决定

**可行的理由：**
1. **主映射已成立**——18 业务链 + 跨切面全部有 docs/only 对应目录与文档；
   审计深度达到"代码现状 + 设计精读 + 运行验证"四轮标准（19+4=23 项落盘）。
2. **未匹配内容可量化**——33 个真设计缺口（A 类）是可枚举的，不是黑盒；
   其中多数是"设计存在但实现未接线/未审计"（与已发现的 P-1/P-2 同型）。
3. **重构目标已清晰**——docs/only 已经是"以模块为纲、以现状为准"的新组织形态，
   重构 = 把 A 类缺口吸收进对应模块目录 + 把 B/C/D/E 类归档到 un_use 或合并索引。

**需要先做的 4 个前置决定：**
```
① A 类缺口的处置顺序：先审计吸收（每缺口补 1 份精读）还是先拍板去留？
   （推荐：先拍板——很多 A 类文档对应的实现是孤儿/断裂，如 DESIGN_XML_MEMORY_CARDS
    ↔ memory/ 零消费，直接吸收会固化错误）
② B/C/D/E 类的归档策略：统一进 docs/un_use/ 还是按"模块归属"散放？
   （用户既有偏好：归档进 un_use，糅合进在用内容）
③ 与全局拍板池的关系：A 类 33 缺口中有多个与已有待拍板直接相关
   （EVENT_SOURCING_CQRS ↔ 关联链 Phase 6 / COGNITIVE_WORKSPACE ↔ 元认知 M 系列 /
   NOISESPAN ↔ PCR / XML_MEMORY_CARDS ↔ memory 孤儿）→ 应先并入全局讨论而非单独处理
④ 重构的执行方式：逐模块施工（与审计同序）还是先建"模块↔文档"索引再批量迁移？
   （推荐：先建索引落盘 = 本文档，作为迁移地图；施工随各模块拍板执行）
```

### 4.2 风险提示
```
- A 类缺口若在未拍板前吸收进模块文档，会与"全部审计完再统一拍板"的既定策略冲突
  （局部最优 vs 全局一致）。
- 105 个未引用文档中约 45 个是历史快照，直接删除有风险——需先确认 docs/only 的
  对应结论已覆盖其内容（审计文档已记录关键结论，但"覆盖"与"吸收"是两回事）。
- merge/ 系列（B 类）若归档需保留溯源指针（原文件在 v3.0 不删除）。
```

---

## 五、建议的下一步（供拍板）

```
1. 将本文档并入 GLOBAL_AUDIT_PLAN（作为"设计全貌 ↔ 审计内容"收口映射）。
2. 全局拍板时，把 A 类 33 缺口按模块归入对应待拍板池：
   - COGNITIVE_WORKSPACE/COGNITIVE_SCHEDULER → 元认知 + 执行层
   - EVENT_SOURCING_CQRS → 关联链 Phase 6
   - XML_MEMORY_CARDS/L5 → 持久化存储架构拍板
   - NOISESPAN → PCR
   - SERVICE_LAYER_ADDON/ENGINEERING_SERVICE_LAYER → 服务层（两处实现归一）
   - CLI_INSPECT/REFERENCE/TUI → CLI 架构（与 DESIGN_CLI 已有映射衔接）
3. 重构施工 = 随各模块拍板，把 A 类文档精读吸收进 docs/only/<module>/，
   B/C/D/E 类归档 docs/un_use/（保留溯源指针）。
```
