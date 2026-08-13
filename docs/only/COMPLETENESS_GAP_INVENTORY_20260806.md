# 后端完备性缺口总清单 — 全量盘点（2026-08-06）

> 触发: 用户要求"一次性找出所有未做完的简化 + 对比缺失要施工的——否则后端
> 不能称之为完备"。
> 方法: **代码探针实测**（三轮, 非文档复读）——docs 中的待办多是 8-02 的,
> 大量已施工; 本清单只列**当前代码仍缺**的项, 每条带证据文件。
> 关联: `benchmark/BENCHMARK_EXTERNAL_20260806.md`（对标 GAP-1~7 + E2 蒸馏自查）。
> **2026-08-06 第一批施工完成更新:
> GAP-D2 / GAP-D1 / GAP-D5 已修复（见
> `blueprint/LEARNING_CLOSED_LOOP_IMPL_20260806.md`）——
> learn_blueprint 生产注入 + 蒸馏原料管道 + 技能生命周期。
> 全量 1744 passed / 0 failed / 16 skipped（净增 12 项）。**
> **2026-08-06 第二批施工完成更新:
> GAP-E1/E2 / GAP-1 / GAP-2 已修复（见
> `blueprint/SECOND_BATCH_IMPL_20260806.md`）——
> executor meta/behavior 占位真接线 + 权限引擎细化（OpenWorker 模式）+
> 定时自动化持久实体（AutomationTask/TaskRun/Scheduler）。
> 全量 1776 passed / 0 failed / 16 skipped（净增 32 项）。
> 剩余: GAP-O1/O2/O3 + GAP-P1（第三批）+ GAP-F1/F2（第四批, 阶段 B）。**
> **2026-08-06 第三批施工完成更新:
> GAP-O1/O2/O3 + GAP-P1 已处理（见
> `blueprint/THIRD_BATCH_IMPL_20260806.md`）——
> memory/ 归档（A17 保留）/ coordinator 判定修正（已接线, 非孤儿）/
> PCR 模型统一（SemanticEncoder 优先）/ 控制面板参数化。
> 全量 1782 passed / 0 failed / 16 skipped。
> 剩余: GAP-F1/F2（第四批, 阶段 B 前端）+ P2 项。**

---

## 一、真缺口清单（探针实测确认, 按域分组）

### A. 学习闭环断线（最高价值）

| # | 缺口 | 证据 | 说明 | 优先级 |
|---|------|------|------|:---:|
| GAP-D1 | ~~蒸馏原料管道断~~ ✅ 已修 | LearningBridge.ExecutionTraceStore → distill_once → A24 验证 → 沉淀 | 2026-08-06 第一批 | — |
| GAP-D2 | ~~learn_blueprint 生产零注入~~ ✅ 已修 | v3_session_api run_dag 后注入 learn_from_execution; 共享 registry | 2026-08-06 第一批 | — |
| GAP-D3 | **suggest_blueprints 零调用方** | `meta_feedback.py:193` 仅定义 | 新意图→模板建议链断 | P1 |
| GAP-D4 | **update_source_credibility 零调用方** | `meta_feedback.py` 仅定义 | 来源可信度学习断 | P2 |
| GAP-D5 | ~~技能生命周期缺失~~ ✅ 已修 | SkillLifecycle 活性状态机（active→stale→archive→prune + pin/引用保护/dry-run） | 2026-08-06 第一批 | — |
| GAP-D6 | **A24 逆向动力工程形态未完成** | `PARADIGM.md:744` 未勾选: coverage 量化/DMN-ECN 调度/启发链存储检索 | 仅域内部分落地（行为 explicit_commitment / 意图 DerivationCompressor / 关联 causal_provenance） | P2 |

### B. 执行层占位链（executor 里仍全是占位）

| # | 缺口 | 证据 | 说明 | 优先级 |
|---|------|------|------|:---:|
| GAP-E1 | ~~_handle_meta 占位~~ ✅ 已修 | 真调 engine._run_meta_consume + trace 记录（2026-08-06 第二批） | — | — |
| GAP-E2 | ~~_handle_behavior 占位~~ ✅ 已修 | 真调 engine._run_behavior_brain（2026-08-06 第二批） | — | — |
| GAP-E3 | `_handle_discourse` 占位 | `executor.py:923` deferred | 对话树节点不做事 | P2 |
| GAP-E4 | `_handle_engineering` 占位 | `executor.py:964` deferred | 工程链节点不做事 | P2 |
| GAP-E5 | `expand_from_dag_trace` 未实现 | `executor.py:448` 仅注释提及 | P0_RETRO §7.5 P1: DAG 快照→子图逆向扩展原语 | P2 |
| GAP-E6 | `route_mode` 未实现 | 全库无 route_mode 实现（仅 discourse_manager 名词） | P0_RETRO §7.6: checkpoint 已做（本批 PlanGate）, step 未做 | P2 |

### C. 对标缺失（BENCHMARK GAP 系列）

| # | 缺口 | 对标来源 | 优先级 |
|---|------|---------|:---:|
| GAP-1 | ~~权限引擎细化~~ ✅ 已修 | permission_engine.py（RiskClass/Mode/路径根/shell 操作符/standing rules, 2026-08-06 第二批） | — |
| GAP-2 | ~~定时自动化持久实体~~ ✅ 已修 | automation.py（AutomationTask/TaskRun/Store/Scheduler, 2026-08-06 第二批） | — |
| GAP-3 | ~~工具批次级介入（beforeToolBatch 合并 approve）~~ ✅ 已修 | OpenClaw agent-loop — classify_tool + route_batch + _handle_tool_batch（2026-08-06, GAP34_IMPL） | — |
| GAP-4 | ~~压缩反馈闭环（manual_compression_feedback）~~ ✅ 已修 | Hermes — CompressionFeedbackStore + window 压缩日志 + API + 前端 Dock 反馈区（2026-08-06, GAP34_IMPL） | — |
| GAP-5 | ~~回合污染跟踪（taint）~~ ✅ 已修 | OpenClaw agent-loop — executor _turn_tainted + [不可信] 标注 + 事件 tainted 字段（2026-08-07, P2_TAINT_WORLD_HEALTH_COST） | — |

### D. 设计承诺未落地（DESIGN_DEEP_AUDIT P2/P3）

| # | 缺口 | 出处 | 优先级 |
|---|------|------|:---:|
| GAP-P1 | 控制面板参数化: 深度/严格度/广度/决策模式未接进 engine.build | DESIGN_DEEP_AUDIT §P2 | P2 |
| GAP-P2 | 自调节闭环 + 三路融合 | DESIGN_DEEP_AUDIT §P3（依赖 Meta 闭环先有真实数据） | P3 |
| GAP-P3 | 冷路径热路径监视分层（Hot/Warm/Cold） | META_ARBITER P1-3 | P2 |

### E. 孤儿/未归一组件（PE 系列确认）

| # | 缺口 | 证据 | 优先级 |
|---|------|------|:---:|
| GAP-O1 | **memory/ 六文件孤儿** | `from core.agent.memory` 生产零引用（PE-1 确认） | P2 |
| GAP-O2 | ~~coordinator ??~~ ? ???? | ????discourse_manager 11 ? + task_engine/user_engine 3 ??; ? multi_tier vs llm_providers ??????P3 ??? | ? |
| GAP-O3 | ~~PCR fastembed ???~~ ? ?? | SemanticEncoder ???Try 0?+ ??????2026-08-06 ???? | ? |
| GAP-O4 | ~~world/importance 断线~~ ✅ 已接 | compiler._ensure_backbone 懒填充（TieredImportanceStrategy → compute_backbone_scores → write_backbone_to_graph）; 判定修正: 非孤儿, 是设计好但断线（2026-08-07） | — |

### F. 前端（阶段 B）

| # | 缺口 | 优先级 |
|---|------|:---:|
| GAP-F1 | 前端变更日志视图（git log + PR review 风格, P1-1） | P1 |
| GAP-F2 | 前端绑定 139 文件接真数据（P1-6） | P1 |
| GAP-F3 | 多渠道 + 多媒体（对标 GAP-7） | P3 |

---

## 二、修正记录（此前核查项已过时, 防重复施工）

| 项 | 旧记录 | 探针实测（2026-08-06） |
|---|--------|----------------------|
| ExecutionTree 零消费（用户核查"真缺失#1"） | "8 类 AgentTree 全部定义但零消费" | ✅ **已接**: `execution/pipeline.py:338` create_task + `agent_native.py:364` + `bootstrap_v6.py:211` |
| skeleton 库 5→20 | "设计说 ~20 只有 5" | ✅ **已补齐 20**: `skeleton_library.py:10` "20 common patterns" |
| 行为链四层决策树 P3-1 | "未落地" | ✅ **已实现**: `behavior/scheduler.py`（epsilon_cold/CI converged/diverged 参数化） |
| 行为链显式承诺 P3-2 | "零现状" | ✅ **已接**: explicit_commitment → brain + engine |
| 蓝图四保护 P2-14/15 | "设计有代码无" | ✅ **本批完成**: protection.py（PlanGate/Budget/LoopDetector/QualityGate） |
| EventBus 双套 P1-28 | "双运行时各自为政" | ✅ **M5 已归一**: 旧 deque 归档 un_use/event_bus_archived/ |
| CLI 假命令 P1-29/P2-31 | "假执行" | ✅ **M8 已修**: 内核 49/49 + CLI 消假执行 |
| v3_0 服务层 PE-3 | "双宿主并存" | ✅ **M7 已归档** v3_0 agent_service 零引用 |
| planning/blueprint.py 旧版 P2-22 | "并存" | ✅ 已归档（零引用） |
| coordinator PE-4 | "两套 LLM 分层" | ⚠️ 仍孤儿（见 GAP-O2）— 修正为未归一, 非"双宿主" |

---

## 三、施工顺序建议（依赖优先）

```
第一批（学习闭环断线 — 用户最关切）:
  GAP-D2 learn_blueprint 生产注入（learn_hook 接线 → LEARNED_TEMPLATES 真沉淀）
  → GAP-D1 蒸馏原料管道（执行轨迹 → DistillationEngine.scan → SkillCandidate
    → A24 可逆推验证 → SkillRegistry）— 与 D2 共享 learn_hook 入口
  → GAP-D5 技能生命周期（接在蒸馏后: 活性状态机 + 可选 LLM 合并 + dry-run/报告）

第二批（执行层占位 → 真链）:
  GAP-E1/E2 meta/behavior 真接线（事件已有, 补消费者; 与 GAP-D1 原料同源）
  → GAP-1 权限引擎细化（吸收 OpenWorker RiskClass/Mode/standing rules）
  → GAP-2 定时自动化持久实体（蓝图 + scheduler）

第三批（孤儿归一 + 设计承诺）:
  GAP-O1/O2 memory/coordinator 归位（接持久化底座或归档）
  → GAP-O3 PCR 模型统一
  → GAP-P1 控制面板参数化

第四批（阶段 B 前端 + P2 项）:
  GAP-F1/F2 前端 → GAP-3/4/5/6 + GAP-P2/P3
```

---

## 四、验证口径

- 每条缺口有代码证据（文件:行）, 非文档推测。
- 全量 core/agent 1732 绿是"域内完备"基线; 本清单是"系统完备"缺口——
  测试绿掩盖的接线断裂（learn_hook 生产零注入就是例子）。
- 探针临时脚本: `scripts/_gap_probe{1,2,3}_tmp.py` + `_gap_scan_tmp.py`（用后即删）;
  原始扫描结果: `docs/only/_gap_scan_all.txt` / `_gap_design_deep.txt` /
  `_gap_probe*.txt`（汇总后清理）。

---

## 五、召回/蓝图缺口（2026-08-08 用户盘点 — 先记录, 后续整理施工）

> 用户结论: "蓝图系统覆盖面很薄, 做得烂" + "锚点定位应是混合算法
> （向量只是其中一路）+ 溯源置信度 + 搜索引擎 + SPO 关系扩散 + LLM 挑选"。
> 本轮实测: **组件 80% 已存在, 但没串成一条统一召回链**。
> 状态: 只记录缺口, 施工排期在 §六/后续整理。
> **2026-08-08 晚第一批施工完成（GAP-R1/R2/R5/R6 部分）:
> `core/agent/recall/recall_service.py`（混合锚点 BGE+BM25+SPO+HyDE+关联链
> + k-hop 扩散 + 溯源置信度 + A18 反馈自适应）; 内核端点 /v6/recall +
> CLI dm recall + ChunkStore 解孤儿 + 9 测试绿 + HTTP 真数据验证。
> 设计+文献: `docs/only/recall/RECALL_CAPABILITY_20260808.md`。剩余: 第二批
> （subgraph 改造/置信度持久化/搜索引擎/LLM 挑选/前端展示/黄金集）。**

### R. 召回能力缺口（B2-3 P1"召回能力接口"一直未施工的实锤）

| # | 缺口 | 证据 | 说明 | 优先级 |
|---|------|------|------|:---:|
| GAP-R1 | **统一召回接口缺失** | subgraph_compiler 仍 11+ 处 getattr 抓现成数据; B2-3 P1 未施工 | 子图/多 agent/执行层无法统一消费"锚点→扩散→组装" | P1 |
| GAP-R2 | **ChunkStore 零消费方（孤儿）** | 全库仅 registry 注册, 无 search/add 调用 | Atom 切分/去重/向量后端全闲置 | P1 |
| GAP-R3 | **溯源置信度未进锚点打分** | FederatedAnchorIndex.priority() = score×温度, 无 source_confidence | 网页/推导/直接命中应有来源可信度权重 | P2 |
| GAP-R4 | **搜索引擎路已注册但查询词错误** | sources.py 有 duckduckgo/tavily/scholar/github/arxiv; 审计: 查询词是中文 intent 非 query 原文 | 网页召回一路等于没接 | P1 |
| GAP-R5 | **SPO 关系扩散未实现** | SyntacticDecomposer 已产出 EDU.subject/predicate/obj; 无扩散消费方 | a\*b（主\*谓\*宾）→ 图扩散 → 子图抓取 → 剪枝, 整条缺 | P1 |
| GAP-R6 | **question 式召回未实现** | DESIGN_FULL_READ §12.3 设计（问题预生成/HyDE/混合检索 0.7/0.3）; 无代码 | query → LLM 扩展 2-3 问题 → 分别召回 → 融合 | P2 |
| GAP-R7 | **LLM 挑选器缺失** | 无候选集 rerank/select 模块 | 扩散候选 ≤30 → LLM 一次挑选（A16 快反馈） | P2 |
| GAP-R8 | **前端召回白盒展示缺失** | 无召回来源/置信度/扩散路径视图; 无 git 式 diff 视图; 无右屏协同展示 | A19 白盒: 召回链路应可视 | P2 |
| GAP-R9 | **~/.dialogmesh 权限坑** | state.json/discourse_trees 写入 Errno 13（本机 ACL） | state 迁移 data/ 或修 ACL（基本能力） | P1 |
| GAP-R10 | **蓝图覆盖面薄（用户判断）** | 模板覆盖业务流少; 需 LLM 生成+成功沉淀（FLOW_SELF_GROWTH） | 与 GAP-R1 同源: 无召回底座, 蓝图无从自我生长 | P1 |

### 关键组件现状（防重复施工, 已存在）

```
混合锚点骨架:  FederatedAnchorIndex（6 源并行 + 温度×相关度合并）✅
BM25:          topic_quick_match.py（BM25+FTS5+kurtosis）✅
SPO 三元组:    SyntacticDecomposer → EDU.subject/predicate/obj ✅
向量:          UnifiedStore（BGE+LSH）/ SemanticEncoder ✅
网页工具:      IngestionPipeline sources（duckduckgo/tavily/scholar/github/arxiv）✅ 注册
召回消费方:    behavior/causal/blueprint 各自的 retrieve(query, top_k=5) — 互不相通 ⚠️
```

### 目标模型（用户 2026-08-08 拍板方向, 待正式记录）

```
混合锚点: 向量(BGE) + BM25 + 网页(搜索引擎) + 溯源置信度加权
          （score × source_confidence × 温度权重）
关系扩散: query → SPO 拆解 → a/b 实体 → 图上 k-hop（hierarchical 1.0 /
          causal 0.9 / reference 0.8 / similarity 0.6）→ 候选集
LLM 挑选: 候选 ≤30 → LLM 一次排序/挑选（不生成, <1s）
question 召回: query → LLM 扩展问题 → 多路召回 → 0.7/0.3 融合
消费方:   子图（编译）/ 多 agent（直连）/ 执行层（工具选择）— 同一接口
```

### 五续、零消费/零引用组件探针（2026-08-08, `scripts/_gap_probe_20260808.py`）

> 方法: 代码探针（813 生产 py, 排除 tests/un_use/archived）。
> 结论: **用户判断成立 — 大量设计好的组件是"注册了/定义了但没接线"**。

#### 5.1 registry 注册但零消费（12 个）
```
granularity / causal_substrate / belief_map / context_ir_compiler /
format_serializer / event_log_store / llm_coref_verifier / cascade_detector /
nats_bridge / pg_bridge / redis_hotstore / otel_bridge
```

#### 5.2 高价值零引用类（设计特征从未接线, 按域）

| 域 | 零引用类 | 设计意图 |
|---|---|---|
| 召回 | `HybridSearchEngine` (persistence/hybrid_hyde.py) | **HyDE 混合检索（用户问的 question 召回!）** |
| 召回 | `WaveQueryEngine` (persistence/wave_query.py) | **A25 水波多跳扩散查询** |
| 召回 | `LSHIndex` (compiler/lsh_index.py) | 向量 LSH 剪枝 |
| 召回 | `SafeUnifiedSearch` (persistence/store_safety.py) | 统一搜索安全层 |
| 召回 | `TopicBacktracker`/`FormatRouter` (event/discourse_gaps.py) | 主题回溯/格式路由 |
| 审计 | `AuditTrail` (persistence/audit_trail.py) | **A17 审计轨迹（记录永不可删!）** |
| 可靠性 | `WriteAheadLog` (scheduler/write_ahead_log.py) | **WAL 预写日志（崩溃恢复）** |
| 工程 | 6 个 engineering_bridges (PCRBridge/IntentBridge/ContextManagerBridge/ServiceLayerBridge/CognitiveProfileBridge/ObservabilityBridge) | 工程链桥接层 |
| 提取 | 4 个 ExtractionProvider (Regex/Stanza/LMStudio/DeepSeek) | extraction_blueprint 的 provider 族 |
| 适配 | BehaviorAdapter/UserProfileAdapter/CausalAdapter (multi_domain_adapters.py) | 多域存储适配 |
| 监控 | EngineeringMonitor / SandboxExecutor / MetaSelfRepair / LearningLoop / PersistenceManager / MemoryManager / ProfileEvolution / MoodClassifierLLM | 各域设计组件 |
| 可插拔 | NATSBridge/ChromaBridge/OTelBridge (event/pluggable.py) | 事件桥接 |

#### 5.3 占位/deferred 标记（真缺口, 非抽象基类）
```
executor.py:1143  _handle_discourse → "对话树: 后续接入" (GAP-E3)
executor.py:1184  _handle_engineering → "工程链: 待接入" (GAP-E4)
chunking/strategies.py:231  LLMChunkStrategy "returns node as-is" (stub)
projection_resolver.py  code/knowledge/conversation/skill/implementation 5 个投影 stub
cross_domain_expander.py  Event ID 多域扩散 stub（A25 扩散本体就是 stub!）
lsp_extractor.py  Tier 2 LSP 提取 stub
context/store.py:45-65  ContextSource 协议 NotImplementedError ×6（抽象, 待定）
```

#### 5.4 结论（用户判断实锤）
```
"蓝图系统覆盖面很薄" = 设计文档里的组件大量以类形态存在, 但:
  ① 无统一召回接口 → 各模块自写 retrieve, 锚点/扩散/HyDE 组件全孤儿
  ② 执行层 discourse/engineering 仍是 deferred 占位
  ③ 审计/WAL/监控等"基本能力"类存在但从未接进主路径
→ 施工顺序建议: 先盘点归类（真接线 vs 归档）, 再按域分批接线,
  与 GAP-R1（统一召回接口）同步推进。
```

#### 5.5 孤儿组件 → 设计文档追溯（2026-08-08, `scripts/_gap_trace_20260808.py`）

> 目的: 分清"设计承诺未兑现"（真缺口） vs "已废弃/阶段 3"（归档）。

| 组件 | 设计出处 | 设计内容 | 判定 |
|---|---|---|---|
| granularity | ARCHITECTURE_AUDIT:423/519/636 | GranularityRegulator 切分（LangChain 递归切分对标 + non-chunkable 标记） | 🔴 真缺口（registry 挂 `_granularity`，引擎用 `_granularity_regulator`，双实例） |
| causal_substrate | ENGINEERING_V3_3_CAUSAL_SUBSTRATE | 因果基地 8 元角色 + DoCalculus | 🔴 设计文档"几乎空" |
| belief_map | association AUDIT:111/214 | 重复 BeliefAccumulator（简单贝叶斯+EMA），I1-2 已答归关联链 | 🟡 重复, 归关联链 |
| context_ir_compiler | BUSINESS_CHAIN_02_CONTEXT:28-60 | ContextAssembler 多源组装→CrossDomainContextIR | 🟡 引擎有 _context_assembler, registry 编译器重复 |
| format_serializer | DESIGN_CLI:99-103 | `dm context ir format` xml/markdown/json | 🔴 真缺口（前端要的 serializer 族） |
| llm_coref_verifier | COREFERENCE_HYBRID_DESIGN | 3-tier 共指融合（Stanza/Semantic/LLM verifier） | 🔴 设计 ✅ 接线缺 |
| cascade_detector | DESIGN_GUARD_SYSTEM | 背压 + 级联检测 + 断路保护 | 🔴 设计 ✅ 接线缺 |
| nats/pg/redis/otel bridge | DEEP_ASSESSMENT_PHASE2 / DESIGN_DISTRIBUTED | 可选依赖/分布式阶段（G5 触发） | 🟢 阶段 3, 不施工 |
| **HybridSearchEngine** | DESIGN_02_CONTEXT_AND_MEMORY:148-149 | **HyDE 原文: "LLM 展开查询为假设答案再语义检索" + 混合检索 语义0.7+BM25 0.3 双通路去重** | 🔴 真缺口（用户问的标准就在这） |
| **WaveQueryEngine** | BUSINESS_CHAIN_01:126-135 | 水波展开, 强度由 CohesionScorer 9 维分决定（非简单语义距离） | 🔴 真缺口（A25 扩散引擎） |
| LSHIndex | G10_STORAGE_DECISION | UnifiedStore BGE+LSH 剪枝 | 🟡 UnifiedStore 内含, 独立类重复 |
| AuditTrail | A17（记录永不可删）+ DESIGN_EXECUTION_LAYER 元认知仲裁:审计轨迹 | 审计/决策记录 | 🔴 真缺口（A17 底线组件零接线） |
| WriteAheadLog | BUSINESS_CHAIN_1.5_PLANNING:216 | DeciderState + WAL（设计自己标 ❌ 未做） | 🔴 真缺口（崩溃恢复） |
| ExtractionProvider 族 | extraction_blueprint / GUI_API /v6/extraction | 提取蓝图 provider 族（Regex/Stanza/LMStudio/DeepSeek） | 🔴 真缺口（extraction 蓝图就是 stub） |
| multi_domain_adapters | DESIGN_03_INPUT_AND_SKILL:389 DomainAdapter | 多域存储适配 | 🟡 待查接线 |
| EngineeringMonitor | engineering/AUDIT_ENTRY:20 | 工程链监控 | 🔴 审计已标"仅测试" |
| SandboxExecutor | DESIGN_TOOL_REGISTRY T5 Level3 Sandbox | 工具沙箱执行 | 🔴 真缺口 |
| MetaSelfRepair | COMPLETENESS_AUDIT:48 | 元认知自修复（record_accuracy 从不被调） | 🔴 真缺口 |
| LearningLoop | LLM3_V6_COGNITIVE_INTEGRATION | 对内学习循环 | 🟡 simulation_engine 已实现, 类重复 |
| ProfileEvolution | TREE_MANAGER_AUDIT:41 | 画像演化 | 🔴 死树 |
| MoodClassifierLLM | V4.0 坐标路由器 §3.3 | Z 轴 LLM fallback 75% | 🔴 PCR 审计标"设计 75% 代码无" |

> 判定口径: 🔴真缺口=设计承诺未接线, 应排期施工 | 🟡重复/待查=需归一 | 🟢阶段3=归档等分布式

---

## 六、2026-08-11 追加 — 召回评测驱动的 3 个真缺口

> 触发: goldset 重建后重跑记忆评测基线 + REFINE_CHAIN_DUMP 全链路复查
> （用户: "蓝图不需要覆盖这个？" + "这个暴力截断不是超级简化？"）。
> 三条均有实测证据（docs/test/REFINE_CHAIN_DUMP_20260810.md 316 行,
> 8 query 全链路 L0/L1/L2）。

| # | 缺口 | 证据 | 说明 | 优先级 |
|---|------|------|------|:---:|
| GAP-R11 | **recall → 执行层注入未接线** | RECALL_EXECUTION_BRIDGE_DESIGN §四 现状核查: ❌ 未接线 | 设计主路径 = 蓝图 DAG subgraph 锚点节点（`chain="subgraph", params.recall_anchor=True`）产出 `{anchors,hits}` → 下游 agentic 工具节点消费; 兜底 = v3 编码请求 format_anchors 注入 tool_loop。两路径都停在设计, 粗召回结果不进执行层上下文 → "最后一公里"缺。 | P1 |
| GAP-R12 | **蓝图 subgraph 转查阅任务未接线** | RECALL_EXECUTION_BRIDGE_DESIGN §四: ❌ 未接线（api_viz_edit 有 subgraph 模式, 未接执行层） | 锚点 path 索引（file: 行号）已生成, 但没有"锚点 → dir_list/grep/file_read 精确查阅"的节点串联; 粗召回只能给候选, 无法靠文件树导航读真内容。 | P1 |
| GAP-R13 | **锚点文本 200 字符硬截断, 语义不闭环** | REFINE_CHAIN_DUMP r000: 显示 "…以下是具" 断句（RecallHit 构造 `text[:200]` + `RecallResult.__init__` 再 `[:200]`; L1 用 `[:300]`; dump L0 打印再 `[:150]`） | 截断为 token 预算设计（候选锚点不塞原文）, 但叠加 R11 未接线 → 截断成为唯一信息来源, 断句处语义残缺无 path 精确查阅兜底; 且三层截断（200/300/150）口径不统一。 | P1 |
| GAP-R14 | **chunk_document 孤立标题残块** | goldset r017 = 仅 7 字符 "你想尝试的模式"（heading 无子内容独立成块） | `_tree_chunks` heading 分支: 标题 + 子段落合并成块, 但无子内容的孤立标题仍独立成块 → 语义残缺进召回池。应: 无子内容 heading 合并到相邻块, 或打 "heading-only" 标签降权。 | P2 |

### 关联结论（用户两问）

1. **"调用是蓝图吗？"** — 不是。生产 API（v3_session_api:472 / stubs_api:193）与评测
   脚本（memory_bench/refine_ablation）都是直调 `RecallService.recall()`, 同一调用方式;
   蓝图管任务编排（宏观 DAG）, recall 是基础能力层, 层级不同不算绕过。但蓝图对 recall
   的覆盖（R11/R12）确实缺失, 是 v2.1 主项。
2. **"暴力截断是超级简化？"** — 截断本身是 token 预算设计（候选锚点不塞原文,
   RECALL_EXECUTION_BRIDGE §三 format_anchors 160 字符片段）, 不是"大小统一方便管理";
   但 R11 未接线使截断成为唯一来源 → 实际效果等同超级简化。修 R11 后截断才有兜底。
