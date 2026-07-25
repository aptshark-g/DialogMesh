1|# DialogMesh v6 — 全版本全模块完整库存 (最终版 V2)
2|
3|> 2026-07-24 · 全部清点完毕 · v3_0 + v3_2 + v4 + v6 + 设计文档 · ~250+ 模块
4|
5|[前面 1-11 节保持不变, 此处追加最后3节]
6|
7|---
8|
9|## 十三、PCR/ (29f, ~10,400L) — 前置认知路由
10|
11|### 核心模块
12|
13|| 模块 | 行数 | 功能 |
14||------|------|------|
15|| datacontract.py | 528L | 版本化数据契约 |
16|| lifecycle.py | 345L | PCR生命周期管理 |
17|| fallback.py | 256L | PCR降级策略引擎 |
18|| config.py | 229L | PCR配置管理 |
19|| registry.py | 228L | 插件发现+注册 |
20|| interface.py | 204L | PCR抽象接口 |
21|| grammar_tagger.py | 146L | Stanza双轨结构标记(S/V/O/NEG/...) |
22|| llm_expertise.py | 132L | **LLM专业度探针** (零硬编码, 替代v3_common/expertise_probe) |
23|| telemetry.py | 119L | PCR遥测收集器 |
24|| rule_based.py | 37L | 已废弃 → PCRRouterV2 |
25|
26|### 测试文件 (14个, ~6,800L)
27|
28|| 模块 | 行数 |
29||------|------|
30|| intent_trace_cli.py | 1,044L |
31|| test_integration.py | 685L |
32|| test_datacontract.py | 604L |
33|| test_rule_based.py | 582L |
34|| test_frontend_layer.py | 538L |
35|| test_lmstudio_integration_v2.py | 463L |
36|| test_frontend_service_integration.py | 460L |
37|| test_mcp_layer.py | 446L |
38|| test_service_layer.py | 436L |
39|| test_production_optimizations.py | 434L |
40|| test_v24_orchestration.py | 415L |
41|| test_lmstudio_integration.py | 384L |
42|| mock_pcr.py | 368L |
43|| demo_full_pipeline_trace.py | 355L |
44|
45|---
46|
47|## 十四、Intent/ (8f, ~1,000L) — 意图模块
48|
49|| 模块 | 行数 | 功能 |
50||------|------|------|
51|| multi_perspective.py | 210L | 4视角DeepSeek意图分析 |
52|| dual_track.py | 155L | 热路径子图+冷路径元认知 |
53|| literal_chain.py | 139L | LLM-first字面验证链 (零硬编码) |
54|| multi_intent_splitter.py | 117L | LLM-first多意图拆分器 |
55|| models.py | 111L | 意图数据契约 |
56|| coordinator.py | 109L | Agent-native意图协调器 (单LLM调用) |
57|| ambiguity_bridge.py | 100L | 死锁→L2.5信念桥接 |
58|| llm_chain.py | 87L | LLM驱动链基类 |
59|
60|---
61|
62|## 十五、Association/ (19f, ~2,200L) — 关联链
63|
64|| 模块 | 行数 | 功能 |
65||------|------|------|
66|| association_funnel.py | 418L | 关联漏斗 V2 (LLM假设+规则验证) |
67|| l1_5_completer.py | 304L | L1.5协同补全器 (语法候选+LLM排序) |
68|| l2_5_belief.py | 285L | L2.5信念累积器 (贝叶斯+7D状态) |
69|| l4_temporal.py | 240L | L4时序模式 (T-BN+JS漂移) |
70|| l3_intent.py | 217L | L3语用意图验证 |
71|| l4_collaborative.py | 182L | L4双轨反馈闭环 |
72|| l1_modifier.py | 135L | L1修饰语提取 (配置驱动) |
73|| fusion_engine.py | 80L | 多源融合引擎 |
74|| skeleton_matcher.py | 76L | 骨架匹配器 |
75|| stage_manager.py | 58L | Stage4集成STRATEGIC规划 |
76|| causal_substrate.py | 57L | 因果基座stub |
77|| conflict_resolver.py | 43L | 冲突解析stub |
78|| models.py | 41L | 关联数据模型 |
79|| delta_adjuster.py | 30L | 边权重有界增量 |
80|| global_workspace.py | 27L | 共享工作空间stub |
81|| l2_config.py | 27L | L2配置加载器 |
82|| skeleton_library.py | 25L | 骨架库stub |
83|| meta_roles.py | 12L | 元角色stub |
84|
85|---
86|
87|## 十六、Behavior/ (16f, ~1,700L) — 行为链
88|
89|| 模块 | 行数 | 功能 |
90||------|------|------|
91|| adapter.py | 428L | v4 BehaviorGraph适配器 |
92|| causal_adapter.py | 220L | CausalSubstrate适配器 |
93|| llm_collaborative.py | 201L | **行为LLM协同分析** |
94|| models.py | 151L | BehaviorGraph数据模型 |
95|| runtime_hook.py | 119L | 引擎运行时集成钩子 |
96|| graph_store.py | 119L | BehaviorGraph核心 |
97|| source.py | 82L | ContextSource提供者 |
98|| cold_start.py | 58L | 冷启动种子管理 |
99|| statistics.py | 55L | 图统计 |
100|| weight_updater.py | 50L | EMA权重更新器 |
101|| causal_discovery.py | 38L | 因果发现stub |
102|| fast_correction.py | 37L | 快速纠正通道stub |
103|| pruning.py | 31L | 图剪枝stub |
104|
105|---
106|
107|## 十七、DiscourseBlockTree/ (17f, ~2,000L) — 对话块树
108|
109|| 模块 | 行数 | 功能 |
110||------|------|------|
111|| manager.py | 256L | 对话块树核心编排器 |
112|| plugin_system.py | 210L | 插件注册表 |
113|| test_discourse_block_tree.py | 207L | 完整测试 |
114|| models.py | 163L | 块/段/引用数据模型 |
115|| syntactic_decomposer.py | 156L | Stage2: 句法分解器 |
116|| adapter.py | 137L | V2集成适配器 |
117|| summary_engine.py | 136L | 四级摘要引擎(v1→v4) |
118|| macro_micro_quantizer.py | 134L | Stage3: 宏微观量化器 |
119|| topic_markers.py | 117L | 分层话题切换检测 |
120|| indexer.py | 107L | O(1)名称/实体/话题索引 |
121|| granularity_regulator.py | 98L | BDI+BOR颗粒度调节器 |
122|| context_builder.py | 95L | 温度上下文构建器 |
123|| header_injector.py | 85L | Stage1: 头部注入器 |
124|| segmenter.py | 85L | LCseg/TextTiling分句器 |
125|| test_integration.py | 31L | 集成测试 |
126|| _debug.py | 1L | debug flag |
127|
128|---
129|
130|## 十八、根目录 .py (29文件, ~5,000L) — 全部为测试/入口/main脚本
131|
132|| 文件 | 行数 | 类型 |
133||------|------|------|
134|| interactive_test.py | 806L | 交互式测试 |
135|| main_v3.py | 575L | v3.0生产入口 |
136|| test_context_compression.py | 349L | 上下文压缩测试 |
137|| test_relationship_graph.py | 342L | 关系图测试 |
138|| run_chat.py | 305L | v4引擎+对话模式 |
139|| test_lmstudio.py | 269L | LM Studio连接测试 |
140|| test_lmstudio_standalone.py | 251L | LM Studio独立测试 |
141|| stress_test.py | 251L | 压力测试 |
142|| test_full_limits.py | 235L | 全功能极限测试 |
143|| test_dashboard_api.py | 213L | Dashboard API测试 |
144|| run_e2e_tests.py | 176L | 端到端测试 |
145|| test_full_conversation.py | 170L | 完整对话树测试 |
146|| tree_panel_new.py | 147L | 对话树面板 |
147|| complex_test.py | 144L | 复杂场景测试 |
148|| test_lightweight_three_tier.py | 137L | 三级存储测试 |
149|| test_end_to_end_topic_tree.py | 132L | 话题树端到端 |
150|| test_three_tier_storage.py | 106L | 三级存储架构测试 |
151|| test_multi_tier_llm.py | 100L | 多层LLM测试 |
152|| main.py | 97L | v4入口 |
153|| test_tree_data.py | 90L | 树数据测试 |
154|| verify_tool_registry.py | 65L | Tool注册表验证 |
155|| test_fixes.py | 51L | 修复测试 |
156|| diagnose.py | 47L | 诊断脚本 |
157|| test_final_dashboard.py | 44L | 仪表盘测试 |
158|| test_ui_fixes.py | 43L | UI修复测试 |
159|| test_context.py | 43L | 上下文检索测试 |
160|| test_ws.py | 12L | WebSocket测试 |
161|
162|---
163|
164|## 附录: 清理项 (根目录 29 个 .py 全部为测试/入口脚本, 可移入 tests/ 或 scripts/)
165|
166|---
167|
168|## 总统计
169|
170|```
171|v3_0:      ~45f,  ~9,000L   (cognitive tree, compiler, observability, llm)
172|v3_2:      ~54f,  ~3,000L   (stub + ParameterRegistry)
173|v3_common:  13f,   5,131L   (data_models, gates, blueprints — 部分已清)
174|v3_legacy:   1f,     886L   (data_models)
175|v4:        ~130f, ~13,000L  (cognitive 36f + scheduler 9f + stub栈)
176|v6:        ~130f, ~80,000L  (pcr/intent/association/behavior/discourse/persistence/memory/planner/context/engineering + 根目录)
177|
178|代码总计: ~380个.py, ~111,000行
179|设计文档: ~230篇 .md
180|测试文件: ~80个
181|```
182|

---

## 十九、API层 (5f, 2,868L)

| 模块 | 行数 | 功能 |
|------|------|------|
| api.py | 1,852L | v4 REST API — FastAPI routes |
| api_gateway.py | 505L | Gateway API — provider管理+model选择+failover |
| api_viz_edit.py | 230L | 可视化交互API — 用户可编辑图/树/关系 |
| api_annotate.py | 158L | 监控标注API |
| api_event_log.py | 123L | EventLog append-only队列无关接口 |

---
## 二十、runtime/ (10f, 4,548L) — 认知运行时引擎 ⭐

| 模块 | 行数 | 功能 |
|------|------|------|
| engine.py | 3,519L | **CognitiveRuntimeEngine** — v4模块跨四个路径编排 |
| adapter.py | 179L | v4模块统一接口 |
| event_log_adapter.py | 151L | EventLog v4适配 |
| p3_resolver.py | 125L | v3_2遗留模块→v4包装 |
| p1_resolver.py | 121L | P1剩余模块接线 |
| config.py | 118L | 运行时配置(runtime.yaml) |
| async_dispatch.py | 91L | 异步LLM分发(线程池) |

---
## 二十一、context_manager/ (5f, 2,560L) — 上下文管理器(不同于context/)

| 模块 | 行数 | 功能 |
|------|------|------|
| discourse_manager.py | 1,988L | **DiscourseManager** — 三级协同+用户识别+任务引擎 |
| semantic_index.py | 240L | BGE向量语义索引 |
| context_layer.py | 190L | 系统上下文注入层 |
| turn.py | 121L | Turn数据模型(轮次→话语块) |

---
## 二十二、service/ (17f, 3,680L) — 服务层

| 模块 | 行数 | 功能 |
|------|------|------|
| agent_service.py | 530L | Agent服务(同步) |
| async_agent_service.py | 514L | Agent服务(异步) |
| api.py | 495L | FastAPI路由 |
| discourse_api.py | 265L | Discourse API |
| async_session_manager.py | 202L | 异步会话管理 |
| session_manager.py | 167L | 会话管理 |
| request_queue.py | 167L | 请求队列 |
| rate_limiter.py | 143L | 限流器 |
| distributed_lock.py | 179L | 分布式锁 |
| stores/sqlite.py | 174L | SQLite会话存储 |
| stores/async_sqlite.py | 190L | 异步SQLite |
| stores/redis.py | 144L | Redis会话存储 |

---
## 二十三、context_window/ + window/ (~1,800L) — 上下文窗口

| 模块 | 行数 | 功能 |
|------|------|------|
| context_window/window_manager.py | 255L | 窗口管理器 |
| context_window/compressor.py | 228L | 规则压缩器 |
| window/context_window_manager.py | 288L | 上下文窗口管理 |
| window/llm_compressor.py | 233L | LLM驱动压缩 |
| window/compressor.py | 214L | 历史压缩 |

---
## 二十四、tool_registry/ (10f, 3,442L) — 工具注册 ⭐

| 模块 | 行数 | 功能 |
|------|------|------|
| executor.py | 569L | 工具执行器 |
| binding.py | 490L | 工具绑定 |
| models.py | 408L | 工具数据模型 |
| registry.py | 312L | 工具注册表 |
| shortlister.py | 290L | 工具候选筛选 |
| discovery.py | 241L | 工具自动发现 |
| permission.py | 191L | 工具权限管理 |

---
## 二十五、cognitive_compiler/ (9f, 1,444L) — 认知编译器(不同于v3_0版)

| 模块 | 行数 | 功能 |
|------|------|------|
| injector.py | 307L | 上下文注入器 |
| decomposer.py | 289L | 任务分解器 |
| dual_manager.py | 230L | 双轨管理器 |
| compiler.py | 164L | 编译器主类 |
| scorer.py | 153L | 候选评分器 |
| entity_cache.py | 94L | 实体缓存 |

---
## 二十六、observation/ (23f, 1,355L) — 观察层(多域适配器)

| 模块 | 行数 | 功能 |
|------|------|------|
| models.py | 111L | 观察数据模型 |
| tiered_relation_extractor.py | 110L | 三层关系提取 |
| dialogue_interpreter.py | 106L | 对话解释器 |
| engineering_interpreter.py | 101L | 工程解释器 |
| pool.py | 100L | 观察池(订阅模式) |
| builder.py | 96L | 观察组装器 |
| interpretation_generator.py | 92L | 多候选解释生成 |
| document_domain_adapter.py | 90L | 文档域适配器 |
| behavior_interpreter.py | 74L | 行为解释器 |
| surface_relation_extractor.py | 59L | 表层关系提取 |
| 其余9个适配器+解释器 | <60L各 | 多域适配 |

---
## 二十七、coordinator/ (7f, 2,348L) — 协调器

| 模块 | 行数 | 功能 |
|------|------|------|
| multi_tier_llm_client.py | 535L | **多层LLM客户端**(低成本+高端, 自动回退) |
| bayesian_engine.py | 501L | **贝叶斯推断引擎**(Dirichlet/Beta/Gaussian建模) |
| small_model_client.py | 399L | 本地小模型客户端(LMStudio, 缓存+批处理) |
| adaptive_threshold.py | 393L | 自适应阈值系统 |
| complexity_evaluator.py | 277L | 复杂度评估器 |
| mode_router.py | 198L | 模式路由器(rule→small→large) |

---
## 二十八、其余模块速览

| 目录 | 行数 | 关键模块 |
|------|------|----------|
| tiered/ | 1,725L | TieredPipeline, TieredParser, HeatBridge, ActionResolver |
| document/ | 1,386L | DocumentIngestionPipeline, extractor/parsers |
| mcp/ | 1,336L | MCP Client/Server/Security |
| cli/ | 1,296L | v4 CLI(builder/inspect/maintenance) |
| user_engine/ | 1,243L | 用户提取+一致性校验+画像模型 |
| world/ | 1,182L | 语义世界模型(community/importance/compiler) |
| state/ | 914L | GlobalDecider, ExecutionTraceV3, InteractionGraph |
| config/ | 1,027L | Discourse配置+Prompt配置+日志 |
| onboarding/ | 846L | 引导Agent(589L)+提示词定义 |
| adapter/ | 781L | OpenClaw适配+CodeWorld |
| chunking/ | 759L | 可插拔分块策略 |
| hypothesis/ | 742L | MatchVote+DecayResolve+Pipeline |
| scheduler/ | 638L | WriteAheadLog+EventScheduler+DeciderState |
| security/ | 689L | 幻觉检测+偏误检测+输入消毒+SchemaGuard |
| optimizer/ | 582L | 贝叶斯优化器(高斯过程) |
| predictor/ | 681L | 认知画像+训练循环 |
| frontend/ | 2,123L | 澄清UI+多模态+WebSocket+TaskGraph可视化 |
| embedding/ | 622L | BGE+Layered+Predicate+ThreeTier |
| router/ | 393L | CoordinateRouter V4 + ZoneStrategy |
| cognitive/ | 426L | DerivationCompressor + LearningLoop |
| causal/ | 470L | CausalRetrievalPlanner |
| mood/ | 301L | VAD+LLM+BGE三版情绪分类器 |
| do_calculus/ | 361L | do-calculus三规则+d-separation |
| summary/ | 496L | L1+L2摘要引擎 |
| task_engine/ | 1,069L | 任务检测+里程碑+任务管理 |
| events/ | 189L | EventBus + EventIR |
| tool_registry/ | 3,442L | 完整工具生态 |

---
## 附录B: 最终总统计

```
版本/层         文件数    代码行    设计文档
v3_0              ~45     ~9,000     105篇(v3.0)
v3_2              ~54     ~3,000     -
v3_common         13      5,131      -
v3_legacy         1       886        -
v4/cognitive      36      ~7,000     -
v4/非cognitive    30+     ~6,000     -
v6 known          130+    ~50,000    18篇(v5)+40篇(根级)
v6 missed(本次)   200+    ~40,000    -
根目录测试        29      ~5,000     -

═══════════════════════════════════════
总计: ~540个.py, ~126,000行代码, ~230篇设计
```

> 清点完成。之前遗漏的 47 个目录(40,000行)现已全部纳入。
