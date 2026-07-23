# DialogMesh 模块化迁移计划

## 已融合 ✅
pcr, planner, context, behavior, association

## 待迁移 — 独占模块 (移入 agent/ 顶层)

### 大型模块 (>1000行)
| 模块 | 来源 | 行数 | 目标 |
|------|------|:---:|------|
| cognitive | v4 | 7173 | agent/cognitive/ |
| compiler | v3_2+v4 | 4946 | agent/compiler/ (需合并) |
| runtime | v4 | 4238 | agent/runtime/ |
| llm_providers | v3_0 | 3559 | agent/llm_providers/ |
| orchestrator | v3_0 | 2860 | agent/orchestrator/ |
| observability | v3_0 | 2764 | agent/observability/ |
| persistence | v4 | 2738 | agent/persistence/ |
| tool_registry | v3_0 | 2573 | agent/tool_registry/ |
| cognitive_compiler | v3_0 | 1860 | → 合并到 agent/cognitive/ |
| cognitive_scheduler | v4 | 1668 | → 合并到 agent/cognitive/ |
| cognitive_tree | v3_0 | 1593 | → 合并到 agent/cognitive/ |

### 中型模块 (300-1000行)
| 模块 | 来源 | 行数 | 目标 |
|------|------|:---:|------|
| tiered | v4 | 1740 | agent/tiered/ |
| cli | v4 | 1313 | agent/cli/ |
| observation_compiler | v4 | 1256 | agent/observation/ |
| world | v4 | 1231 | agent/world/ |
| state | v4 | 937 | agent/state/ |
| document | v4 | 884 | agent/document/ |
| predictor | v3_2 | 689 | agent/predictor/ |
| embedding | v3_2 | 655 | agent/embedding/ |
| scheduler | v4 | 641 | agent/scheduler/ |
| hypothesis_engine | v4 | 524 | agent/hypothesis/ |
| causal | v4 | 525 | agent/causal/ |
| chunking | v4 | 520 | agent/chunking/ |
| context_compiler | v3_2 | 473 | agent/context_compiler/ |
| engineering_chain | v3_2 | 468 | agent/engineering/ |
| optimizer | v4 | 457 | agent/optimizer/ |
| monitor | v4 | 447 | agent/monitor/ |
| l2_summary | v3_2 | 376 | agent/summary/ |
| do_calculus | v3_2 | 373 | agent/do_calculus/ |
| rewarder | v3_2 | 336 | agent/rewarder/ |
| security | v3_0 | 311 | agent/security/ |

### 小型模块 (<300行)
event_log, discourse_block_tree, knowledge, foa, l1_summary, negative_kb, conversation, classifier, adapter...

## 需要合并的
| 合并 | 来源 | 
|------|------|
| cognitive ← cognitive_compiler + cognitive_scheduler + cognitive_tree |
| compiler ← v3_2/compiler + v4/compiler |
