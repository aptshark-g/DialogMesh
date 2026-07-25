# DialogMesh v6 — 全版本全模块完整库存 (最终版 V2)

> 2026-07-24 · 全部清点完毕 · v3_0 + v3_2 + v4 + v6 + 设计文档 · ~250+ 模块

[前面 1-11 节保持不变, 此处追加最后3节]

---

## 十三、PCR/ (29f, ~10,400L) — 前置认知路由

### 核心模块

| 模块 | 行数 | 功能 |
|------|------|------|
| datacontract.py | 528L | 版本化数据契约 |
| lifecycle.py | 345L | PCR生命周期管理 |
| fallback.py | 256L | PCR降级策略引擎 |
| config.py | 229L | PCR配置管理 |
| registry.py | 228L | 插件发现+注册 |
| interface.py | 204L | PCR抽象接口 |
| grammar_tagger.py | 146L | Stanza双轨结构标记(S/V/O/NEG/...) |
| llm_expertise.py | 132L | **LLM专业度探针** (零硬编码, 替代v3_common/expertise_probe) |
| telemetry.py | 119L | PCR遥测收集器 |
| rule_based.py | 37L | 已废弃 → PCRRouterV2 |

### 测试文件 (14个, ~6,800L)

| 模块 | 行数 |
|------|------|
| intent_trace_cli.py | 1,044L |
| test_integration.py | 685L |
| test_datacontract.py | 604L |
| test_rule_based.py | 582L |
| test_frontend_layer.py | 538L |
| test_lmstudio_integration_v2.py | 463L |
| test_frontend_service_integration.py | 460L |
| test_mcp_layer.py | 446L |
| test_service_layer.py | 436L |
| test_production_optimizations.py | 434L |
| test_v24_orchestration.py | 415L |
| test_lmstudio_integration.py | 384L |
| mock_pcr.py | 368L |
| demo_full_pipeline_trace.py | 355L |

---

## 十四、Intent/ (8f, ~1,000L) — 意图模块

| 模块 | 行数 | 功能 |
|------|------|------|
| multi_perspective.py | 210L | 4视角DeepSeek意图分析 |
| dual_track.py | 155L | 热路径子图+冷路径元认知 |
| literal_chain.py | 139L | LLM-first字面验证链 (零硬编码) |
| multi_intent_splitter.py | 117L | LLM-first多意图拆分器 |
| models.py | 111L | 意图数据契约 |
| coordinator.py | 109L | Agent-native意图协调器 (单LLM调用) |
| ambiguity_bridge.py | 100L | 死锁→L2.5信念桥接 |
| llm_chain.py | 87L | LLM驱动链基类 |

---

## 十五、Association/ (19f, ~2,200L) — 关联链

| 模块 | 行数 | 功能 |
|------|------|------|
| association_funnel.py | 418L | 关联漏斗 V2 (LLM假设+规则验证) |
| l1_5_completer.py | 304L | L1.5协同补全器 (语法候选+LLM排序) |
| l2_5_belief.py | 285L | L2.5信念累积器 (贝叶斯+7D状态) |
| l4_temporal.py | 240L | L4时序模式 (T-BN+JS漂移) |
| l3_intent.py | 217L | L3语用意图验证 |
| l4_collaborative.py | 182L | L4双轨反馈闭环 |
| l1_modifier.py | 135L | L1修饰语提取 (配置驱动) |
| fusion_engine.py | 80L | 多源融合引擎 |
| skeleton_matcher.py | 76L | 骨架匹配器 |
| stage_manager.py | 58L | Stage4集成STRATEGIC规划 |
| causal_substrate.py | 57L | 因果基座stub |
| conflict_resolver.py | 43L | 冲突解析stub |
| models.py | 41L | 关联数据模型 |
| delta_adjuster.py | 30L | 边权重有界增量 |
| global_workspace.py | 27L | 共享工作空间stub |
| l2_config.py | 27L | L2配置加载器 |
| skeleton_library.py | 25L | 骨架库stub |
| meta_roles.py | 12L | 元角色stub |

---

## 十六、Behavior/ (16f, ~1,700L) — 行为链

| 模块 | 行数 | 功能 |
|------|------|------|
| adapter.py | 428L | v4 BehaviorGraph适配器 |
| causal_adapter.py | 220L | CausalSubstrate适配器 |
| llm_collaborative.py | 201L | **行为LLM协同分析** |
| models.py | 151L | BehaviorGraph数据模型 |
| runtime_hook.py | 119L | 引擎运行时集成钩子 |
| graph_store.py | 119L | BehaviorGraph核心 |
| source.py | 82L | ContextSource提供者 |
| cold_start.py | 58L | 冷启动种子管理 |
| statistics.py | 55L | 图统计 |
| weight_updater.py | 50L | EMA权重更新器 |
| causal_discovery.py | 38L | 因果发现stub |
| fast_correction.py | 37L | 快速纠正通道stub |
| pruning.py | 31L | 图剪枝stub |

---

## 十七、DiscourseBlockTree/ (17f, ~2,000L) — 对话块树

| 模块 | 行数 | 功能 |
|------|------|------|
| manager.py | 256L | 对话块树核心编排器 |
| plugin_system.py | 210L | 插件注册表 |
| test_discourse_block_tree.py | 207L | 完整测试 |
| models.py | 163L | 块/段/引用数据模型 |
| syntactic_decomposer.py | 156L | Stage2: 句法分解器 |
| adapter.py | 137L | V2集成适配器 |
| summary_engine.py | 136L | 四级摘要引擎(v1→v4) |
| macro_micro_quantizer.py | 134L | Stage3: 宏微观量化器 |
| topic_markers.py | 117L | 分层话题切换检测 |
| indexer.py | 107L | O(1)名称/实体/话题索引 |
| granularity_regulator.py | 98L | BDI+BOR颗粒度调节器 |
| context_builder.py | 95L | 温度上下文构建器 |
| header_injector.py | 85L | Stage1: 头部注入器 |
| segmenter.py | 85L | LCseg/TextTiling分句器 |
| test_integration.py | 31L | 集成测试 |
| _debug.py | 1L | debug flag |

---

## 十八、根目录 .py (29文件, ~5,000L) — 全部为测试/入口/main脚本

| 文件 | 行数 | 类型 |
|------|------|------|
| interactive_test.py | 806L | 交互式测试 |
| main_v3.py | 575L | v3.0生产入口 |
| test_context_compression.py | 349L | 上下文压缩测试 |
| test_relationship_graph.py | 342L | 关系图测试 |
| run_chat.py | 305L | v4引擎+对话模式 |
| test_lmstudio.py | 269L | LM Studio连接测试 |
| test_lmstudio_standalone.py | 251L | LM Studio独立测试 |
| stress_test.py | 251L | 压力测试 |
| test_full_limits.py | 235L | 全功能极限测试 |
| test_dashboard_api.py | 213L | Dashboard API测试 |
| run_e2e_tests.py | 176L | 端到端测试 |
| test_full_conversation.py | 170L | 完整对话树测试 |
| tree_panel_new.py | 147L | 对话树面板 |
| complex_test.py | 144L | 复杂场景测试 |
| test_lightweight_three_tier.py | 137L | 三级存储测试 |
| test_end_to_end_topic_tree.py | 132L | 话题树端到端 |
| test_three_tier_storage.py | 106L | 三级存储架构测试 |
| test_multi_tier_llm.py | 100L | 多层LLM测试 |
| main.py | 97L | v4入口 |
| test_tree_data.py | 90L | 树数据测试 |
| verify_tool_registry.py | 65L | Tool注册表验证 |
| test_fixes.py | 51L | 修复测试 |
| diagnose.py | 47L | 诊断脚本 |
| test_final_dashboard.py | 44L | 仪表盘测试 |
| test_ui_fixes.py | 43L | UI修复测试 |
| test_context.py | 43L | 上下文检索测试 |
| test_ws.py | 12L | WebSocket测试 |

---

## 附录: 清理项 (根目录 29 个 .py 全部为测试/入口脚本, 可移入 tests/ 或 scripts/)

---

## 总统计

```
v3_0:      ~45f,  ~9,000L   (cognitive tree, compiler, observability, llm)
v3_2:      ~54f,  ~3,000L   (stub + ParameterRegistry)
v3_common:  13f,   5,131L   (data_models, gates, blueprints — 部分已清)
v3_legacy:   1f,     886L   (data_models)
v4:        ~130f, ~13,000L  (cognitive 36f + scheduler 9f + stub栈)
v6:        ~130f, ~80,000L  (pcr/intent/association/behavior/discourse/persistence/memory/planner/context/engineering + 根目录)

代码总计: ~380个.py, ~111,000行
设计文档: ~230篇 .md
测试文件: ~80个
```
