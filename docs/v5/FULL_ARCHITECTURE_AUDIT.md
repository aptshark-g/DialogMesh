# DialogMesh v6 — 全模块设计×实现对照

> 2026-07-24 · 设计汇总 + 实现汇总 两张表

---

## 表一：设计汇总 (50模块)

### 引擎层 (Engine — EventBus + StateGraph)

| 模块 | 消费事件 | 产出事件 | 路径 | 设计来源 |
|------|----------|----------|------|----------|
| EventBus | — | MessageReceived, Tick | async | docs/ARCHITECTURE_OVERVIEW.md |
| StateGraph | MessageReceived, * | state_update | core | docs/architecture/ARCHITECTURE.md |

### Chain 03 — Intent / 意图

| 模块 | 消费事件 | 产出事件 | 路径 | 设计来源 |
|------|----------|----------|------|----------|
| MultiIntentSplitter | MessageReceived | IntentLocked | hot(<1s) | docs/BUSINESS_CHAIN_03_INTENT.md |
| DualTrack | MessageReceived | IntentLocked | hot+cold | dual_track.py docstring |
| MultiPerspective | MessageReceived | IntentInsight | cold(async) | multi_perspective.py docstring |
| AmbiguityBridge | IntentLocked(ambiguous) | BeliefUpdate | slow | ambiguity_bridge.py docstring |
| LiteralChain | MessageReceived | LiteralIntent | hot | literal_chain.py docstring |

### Chain 04 — PCR / 路由

| 模块 | 消费事件 | 产出事件 | 路径 | 设计来源 |
|------|----------|----------|------|----------|
| PCRRouterV2 | MessageReceived | Routed | hot | docs/BUSINESS_CHAIN_00_PCR.md |
| LLMExpertiseProbe | Routed | ExpertiseSignal | hot | pcr/llm_expertise.py |

### Chain 05 — Behavior / 行为

| 模块 | 消费事件 | 产出事件 | 路径 | 设计来源 |
|------|----------|----------|------|----------|
| BehaviorModels | IntentLocked | BehaviorObserved | async | docs/BUSINESS_CHAIN_05_BEHAVIOR.md |
| LLMCollaborative | BehaviorObserved | PatternDiscovered | cold | behavior/llm_collaborative.py |

### Chain 06 — Association / 关联

| 模块 | 消费事件 | 产出事件 | 路径 | 设计来源 |
|------|----------|----------|------|----------|
| L1 Syntax | MessageReceived | SyntacticEdge | hot | docs/BUSINESS_CHAIN_06_ASSOCIATION.md |
| L1.5 LLM | MessageReceived | SemanticEdge | hot | docs/BUSINESS_CHAIN_06_ASSOCIATION.md |
| L2 RelationSubstrate V3 | SyntacticEdge, SemanticEdge | EntityRelation | async | docs/v3.0/DESIGN_RELATION_SUBSTRATE.md |
| L2 LLMRelationExtractor | EntityRelation(open) | EntityRelation(classified) | cold | compiler/llm_relation_extractor.py |
| L2.5 BeliefAccumulator | EntityRelation | BeliefUpdate | async | v4/cognitive/belief_map.py |
| L4 TemporalPredict | BeliefUpdate | TemporalTransition | cold | association/l4_temporal.py |
| L4 Collaborative | TemporalTransition | VerifiedTransition | cold | association/l4_collaborative.py |

### Chain 01 — Discourse / 对话树

| 模块 | 消费事件 | 产出事件 | 路径 | 设计来源 |
|------|----------|----------|------|----------|
| Segmenter | MessageReceived | EDUs | hot | docs/BUSINESS_CHAIN_01_CONVERSATION_TREE.md |
| DiscourseBlockTree | EDUs | BlockUpdated | async | docs/v3.0/design_discourse_block_tree.md |
| TopicQuickMatch | BlockUpdated | TopicAnchored | async | compiler/topic_quick_match.py |
| SummaryEngine | BlockUpdated | SummaryGenerated | cold | discourse_block_tree/summary_engine.py |
| PosteriorCorrector | SummaryGenerated | BlockReassigned | cold | compiler/posterior_corrector.py |

### Chain 02 — Context / 上下文

| 模块 | 消费事件 | 产出事件 | 路径 | 设计来源 |
|------|----------|----------|------|----------|
| ContextManager | * | ContextAssembled | hot | docs/BUSINESS_CHAIN_02_CONTEXT.md |
| TemperaturePatch | ContextAssembled | SortedContext | hot | context/temperature_patch.py |
| ThreeParadigmContext | SortedContext | LabelledContext | hot | compiler/three_paradigm_context.py |

### Chain 07 — Engineering / 工程

| 模块 | 消费事件 | 产出事件 | 路径 | 设计来源 |
|------|----------|----------|------|----------|
| EngineeringChain | IntentLocked | ToolPlan | cold | engineering/chain.py |

### Chain 08 — Profile / 画像

| 模块 | 消费事件 | 产出事件 | 路径 | 设计来源 |
|------|----------|----------|------|----------|
| OCEANProfile | Routed, CorrectionApplied | ProfileUpdated | async | docs/BUSINESS_CHAIN_08_PROFILE.md |
| BFICalibrator | ProfileUpdated | BFIAdjusted | cold | v4/cognitive/bfi_calibrator.py |
| CorrectionJournal | MetaDecision | CorrectionApplied | async | v4/cognitive/correction_journal.py |
| LLMProfileAnalyst | ProfileUpdated | ProfileInsight | cold | v4/cognitive/llm_profile_analyst.py |

### Chain 09 — Metacognition / 元认知

| 模块 | 消费事件 | 产出事件 | 路径 | 设计来源 |
|------|----------|----------|------|----------|
| MetacognitiveTrigger | BlockUpdated, PatternDiscovered, * | MetaTriggered | async | docs/BUSINESS_CHAIN_09_METACOGNITION.md |
| MetaCognition | MetaTriggered | MetaDecision | cold | v4/cognitive/metacognition.py |
| InternalStateMonitor | MetaDecision, state_update | MonitorAlert | async | v4/cognitive/internal_monitor.py |
| DynamicsComputer | MetaDecision | InertiaUpdated | cold | v4/cognitive/dynamics.py |
| TriggerWiring | MetaTriggered(cold_blocks) | compress_cold_blocks | async | observability/trigger_wiring.py |

### Chain 10 — Execution / 执行

| 模块 | 消费事件 | 产出事件 | 路径 | 设计来源 |
|------|----------|----------|------|----------|
| AgentOrchestrator | All signals | Plan | hot | orchestrator/agent_native.py |
| LLMPlanner | Plan | Action | hot | planner/llm_planner.py |

### L5 — Memory / 长期记忆

| 模块 | 消费事件 | 产出事件 | 路径 | 设计来源 |
|------|----------|----------|------|----------|
| CompressionRouter | BlockUpdated | StorageDecision | cold | docs/v5/DESIGN_L5_LONG_TERM_MEMORY.md |
| RAGraphBridge | StorageDecision(rag) | RetrievedContext | cold | memory/ragraph.py |
| FederatedAnchorIndex | MessageReceived | AnchorSet | hot | memory/federated_index.py |
| StrategyFederation | RetrievedContext | ValidatedRule | cold | memory/strategy_federation.py |
| XMLMemoryCards | StorageDecision | StructuredMemory | cold | docs/v5/DESIGN_XML_MEMORY_CARDS.md |
| ClusterMap | ValidatedRule | VisualizationData | cold | memory/cluster_map.py |

### Persistence / 持久化

| 模块 | 消费事件 | 产出事件 | 路径 | 设计来源 |
|------|----------|----------|------|----------|
| UnifiedBroker (Py) | All events | persisted | async | persistence/broker.py |
| LSMStore (Py) | persisted | disk | sync | persistence/lsm_store.py |
| UnifiedBroker (Rust) | All events | persisted | async | persistence_rs/src/unified.rs |
| LSMStore (Rust) | persisted | disk | sync | persistence_rs/src/lsm_store.rs |
| FederatedIndex (Rust) | anchor_lists | merged_anchors | sync | persistence_rs/src/federated_index.rs |
| RustBridge | — | auto-select Py/Rust | — | persistence/rust_bridge.py |

---

## 表二：实现汇总 (50模块)

### ✅ 已完成 + 已接入管线

| 模块 | 代码 | 测试 | 接入点 | Rust |
|------|------|------|--------|------|
| PCRRouterV2 | ✅ | 13/13 | agent_native L1 | |
| MultiIntentSplitter | ✅ | ✅ | agent_native L2 | |
| L1 Syntax | ✅ | ✅ | engine hook | |
| L1.5 LLM | ✅ | ✅ | engine hook | |
| DiscourseBlockTree | ✅ | ✅ | engine hook | |
| Segmenter | ✅ | ✅ | engine hook | |
| L4 TemporalPredict | ✅ | ✅ | agent_native L3 | |
| L4 Collaborative | ✅ | ✅ | agent_native L3 | |
| BehaviorModels | ✅ | ✅ | agent_native L4 | |
| LLMCollaborative | ✅ | ✅ | agent_native L4 | |
| AgentOrchestrator | ✅ | ✅ | core | |
| MetacognitiveTrigger | ✅ | ✅ | trigger_wiring | |
| LSMStore (Py) | ✅ | ✅ | broker | |
| UnifiedBroker (Py) | ✅ | ✅ | 10-chain | |
| LSMStore (Rust) | ✅ | ✅ | rust_bridge | ✅ |
| UnifiedBroker (Rust) | ✅ | ✅ | rust_bridge | ✅ |
| FederatedIndex (Rust) | ✅ | ✅ | standalone | ✅ |
| RustBridge | ✅ | ✅ | auto-select | ✅ |
| V4 CognitiveBridge | ✅ | ✅ | agent_native | |
| V4 Cognitive 13mod | ✅ | — | bridge | |

### ✅ 已完成 — 未接入

| 模块 | 代码 | 测试 | 缺失接入 |
|------|------|------|----------|
| DualTrack | ✅ | — | 替换/并列 MultiIntentSplitter |
| MultiPerspective | ✅ | — | cold路径, intent_insight事件 |
| AmbiguityBridge | ✅ | — | deadlock→belief_bridge事件 |
| LiteralChain | ✅ | — | literal_intent事件 |
| LLMExpertiseProbe | ✅ | ✅ | Routed→ExpertiseSignal |
| LLMRelationExtractor | ✅ | ✅ | L2 open-type分类 |
| PosteriorCorrector | ✅ | — | SummaryGenerated→BlockReassigned |
| ThreeParadigmContext | ✅ | — | 温度×距离×价值注入LLM |
| TemperaturePatch | ✅ | — | Context温度排序 |
| CompassPatch | ✅ | — | TopicTree三范式罗盘 |
| TriggerWiring | ✅ | — | cold_blocks→compress |
| RAGraphBridge | ✅ | ✅ | StorageDecision→RetrievedContext |
| FederatedAnchorIndex | ✅ | ✅ | MessageReceived→AnchorSet |
| CompressionRouter | ✅ | ✅ | BlockUpdated→StorageDecision |
| StrategyFederation | ✅ | ✅ | RetrievedContext→ValidatedRule |
| ClusterMap | ✅ | ✅ | ValidatedRule→可视化 |
| XMLMemoryCards | ✅ | ✅ | StorageDecision→StructuredMemory |

### 📋 设计存在 — 未实现

| 模块 | 设计文档 | 缺口 |
|------|----------|------|
| ContextManager | docs/BUSINESS_CHAIN_02_CONTEXT.md | context/ 目录无实现 |
| L5计算层(伪因果) | docs/v5/DESIGN_L5_LONG_TERM_MEMORY.md | 3层太复杂, 暂缓 |
| ReactFlow可视化 | — | 前端任务 |
| EngineeringChain完善 | engineering/chain.py | 仅MCP桥接基础 |

### ⚠️ 已接入但质量待验证

| 模块 | 问题 |
|------|------|
| V4 CognitiveBridge | 13模块接入但未在真实数据跑过 |
| RelationSubstrate V3 | LLM分类已装, 但build方法仍用heuristic fallback |
| Evaluation Framework | 6场景跑通, 但未接真实LLM评分 |
