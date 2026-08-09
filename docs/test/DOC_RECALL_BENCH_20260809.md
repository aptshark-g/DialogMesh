# 文档语料召回跑分（2026-08-09）

- 语料: 2444 块（docs + docs/only 全量 md, 章节切块, 块带 path 索引 = 执行层精确查阅来源）
- Query: 50（docs/test/recall_queries.json）
- 随机基线: 0.2%

## 指标

| 模式 | top1 | top3 | top5 | MRR |
|---|---|---|---|---|
| linear | 44.0% (22/50) | 30 | 37 | 0.534 |
| rrf | 42.0% (21/50) | 31 | 36 | 0.528 |

## 分级统计（按 query level）

| 级别 | 模式 | top1 | n | MRR |
|---|---|---|---|---|
| complex | linear | 48.3% | 29 | 0.575 |
| cross | linear | 25.0% | 4 | 0.312 |
| simple | linear | 41.2% | 17 | 0.517 |
| complex | rrf | 44.8% | 29 | 0.549 |
| cross | rrf | 25.0% | 4 | 0.383 |
| simple | rrf | 41.2% | 17 | 0.525 |

## 漂移候选（源块未进 top5, 文档审计线索）

- query: `agentic 工具节点怎么让 LLM 自己调工具` (期望 `docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md`) → top: ['docs/only/STATE_HANDOFF_BACKEND_BLUEPRINT_20260806.md', 'docs/only/reference/OPENCLAW_OS_TOOLS_20260808.md', 'docs/only/execution/V2_EXECUTION_LAYER_IMPL_20260809.md']
- query: `权限引擎在生产路径怎么挂载的，PermissionEngine 接到哪了` (期望 `docs/only/V1_FUNCTION_CHECKLIST_20260808.md,docs/only/bluepr`) → top: ['docs/only/wise/TIERED_NEGATIVE_KB_IMPL_20260807.md', 'docs/only/STATE_HANDOFF_COMPLETENESS_20260806.md', 'docs/only/execution/TREE_MANAGER_AUDIT_20260803.md']
- query: `统一召回用了哪些算法，RRF 融合提升多少` (期望 `docs/only/recall/RECALL_CAPABILITY_20260808.md`) → top: ['docs/only/recall/RECALL_BATCH2_PLAN_20260808.md', 'docs/only/recall/SPO_MODEL_STRATEGY_20260808.md', 'docs/only/llm_cognitive/DESIGN_FULL_READ_20260803.md']
- query: `SPO 约束投影怎么提炼主宾关系，谓语权重多少` (期望 `docs/only/recall/SPO_MODEL_STRATEGY_20260808.md`) → top: ['docs/only/recall/SPO_BILINGUAL_TWOSTAGE_20260808.md', 'docs/only/recall/SPO_BILINGUAL_TWOSTAGE_20260808.md', 'docs/only/recall/SPO_BILINGUAL_TWOSTAGE_20260808.md']
- query: `树是推理工作台是什么意思，遗忘怎么处理` (期望 `docs/only/wise/PARADIGM.md`) → top: ['docs/only/discourse_tree/DESIGN_AUDIT_20260803.md', 'docs/only/discourse_tree/DESIGN_READ_COMPLETE_20260803.md', 'docs/only/discourse_tree/DESIGN_AUDIT_20260803.md']
- query: `记录永不可删和抽象可逆推是哪几条公理` (期望 `docs/only/wise/PARADIGM.md`) → top: ['docs/only/subgraph/DESIGN_SUBGRAPH.md', 'docs/only/wise/MEMORY_FEDERATION_CLUSTERING_20260807.md', 'docs/only/discourse_tree/TREE_TIERING_DECISION_20260807.md']
- query: `偏差是养分怎么理解，归因回流到哪层` (期望 `docs/only/wise/PARADIGM.md`) → top: ['docs/only/blueprint/BIDIRECTIONAL_ATTRIBUTION_20260806.md', 'docs/only/blueprint/BIDIRECTIONAL_ATTRIBUTION_20260806.md', 'docs/only/blueprint/BIDIRECTIONAL_ATTRIBUTION_20260806.md']
- query: `阶段 A 和阶段 B 分别包含哪些模块` (期望 `docs/only/IMPLEMENTATION_PLAN_20260804.md`) → top: ['docs/only/frontend/FE_CONTRACT_REGISTRY_20260806.md', 'docs/only/behavior/BEHAVIOR_DEEP_INVESTIGATION.md', 'docs/only/behavior/DESIGN_BEHAVIOR.md']
- query: `本轮压缩交接的恢复入口是哪个文档` (期望 `docs/only/STATE_HANDOFF_20260809.md`) → top: ['docs/only/STATE_HANDOFF_BOOTSTRAP_WHITEBOX_20260805.md', 'docs/only/STATE_HANDOFF_20260803_FINAL.md', 'docs/only/STATE_HANDOFF_COMPLETENESS_20260806.md']
- query: `蒸馏原料管道怎么收集，HeuristicDistiller 从哪拿数据` (期望 `docs/only/blueprint/FLOW_SELF_GROWTH_20260806.md`) → top: ['docs/only/recall/SPO_MODEL_STRATEGY_20260808.md', 'docs/only/wise/HEURISTIC_DISTILLATION_DESIGN_20260806.md', 'docs/only/COMPLETENESS_GAP_INVENTORY_20260806.md']
- query: `技能生命周期怎么做活性管理的` (期望 `docs/only/blueprint/FLOW_SELF_GROWTH_20260806.md`) → top: ['docs/only/blueprint/BLUEPRINT_THIN_AUDIT_20260808.md', 'docs/only/V1_FUNCTION_CHECKLIST_20260808.md', 'docs/only/COMPLETENESS_GAP_INVENTORY_20260806.md']
- query: `对话树和召回是什么关系，命中怎么并行` (期望 `docs/only/recall/RECALL_EXECUTION_BRIDGE_DESIGN_20260809.md`) → top: ['docs/only/discourse_tree/KERNEL_ABSORPTION_20260803.md', 'docs/only/discourse_tree/KERNEL_ABSORPTION_20260803.md', 'docs/only/association/DESIGN_PHILOSOPHY_CHECK_20260802.md']
- query: `编码类请求怎么识别，施工信号有哪些` (期望 `docs/only/recall/RECALL_EXECUTION_BRIDGE_DESIGN_20260809.md`) → top: ['docs/only/blueprint/ERROR_META_REFLECTION_20260806.md', 'docs/only/COMPLETENESS_GAP_INVENTORY_20260806.md', 'docs/only/blueprint/P0_COUPLING_INVENTORY_20260802.md']
- query: `replanner 自动换方案为什么没做，MC 全场景缺什么` (期望 `docs/only/blueprint/EXECUTION_LAYER_ARCHITECTURE_20260809.md`) → top: ['docs/only/blueprint/BIDIRECTIONAL_ATTRIBUTION_20260806.md', 'docs/only/execution/V2_EXECUTION_LAYER_IMPL_20260809.md', 'docs/only/blueprint/META_ARBITER_ASYNC_INTERVENTION_20260806.md']

## 复跑

```bash
python scripts/doc_recall_bench.py --queries docs/test/recall_queries.json
```
