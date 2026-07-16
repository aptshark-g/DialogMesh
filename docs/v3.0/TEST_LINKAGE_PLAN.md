# 模块间链路质量测试计划

## 测试架构

每个测试验证两个以上模块的实际交互产出，不测试单模块内部逻辑。

## 链路清单

### L1: 文档→概念→对象链
| 测试 | 验证 | 数据 |
|------|------|------|
| `pool_ingest_to_graph_nodes` | ObservationPool → ConceptGraph 节点数 ≥ 500 | 5 文档 |
| `graph_to_semantic_index` | ConceptGraph → SemanticIndex 可查询 | graph |
| `index_to_objects_count` | graph+index → SemanticObject count > 200 | graph+index |
| `objects_have_paths` | 每个 object 有 semantic_path/heading_path | objects |

### L2: 概念→上下文链
| 测试 | 验证 | 数据 |
|------|------|------|
| `world_view_architecture_nonempty` | SemanticWorld.render() → design content > 100 chars | pool+objects |
| `world_view_has_relation_entries` | provider.relation_query → world_relation entries ≥ 1 | pool+objects+rs |
| `context_assembler_produces_ir` | ContextAssembler.assemble_ir → entries with K+C+P domains | pool+graph+objects |
| `multi_perspective_different_targets` | primary targets ≠ secondary targets | pool+objects |

### L3: 事件→用户画像链
| 测试 | 验证 | 数据 |
|------|------|------|
| `on_event_changes_profile` | 3 turns → observations > 0, trust ≠ 0.5 | engine+pool |
| `correction_text_detected` | "我才是用户" → cognitive_inertia changes | engine+pool |
| `profile_injected_in_context` | P domain entries present after 2+ turns | engine+pool |

### L4: 事件→对话树链
| 测试 | 验证 | 数据 |
|------|------|------|
| `single_topic_single_branch` | 3 rounds same topic → depth=2, fork=0 | engine+pool |
| `multi_topic_creates_fork` | 3 different topics → ≥ 2 blocks | engine+pool |
| `importance_high_on_correction` | "不是" in text → block.importance ≥ 0.8 | engine+pool |
| `temperature_decays` | block age > threshold → temperature changes | engine+pool |

### L5: 提取→关系基座链
| 测试 | 验证 | 数据 |
|------|------|------|
| `slow_path_writes_edges` | 6 turns → RS dependency edges increase | engine+pool+rs |
| `extraction_jieba_has_relations` | Orchestrator.extract(design_text) → tuples ≥ 1 | orchestrator |
| `apply_extraction_adds_to_rs` | extraction result → RS.query(source) returns edge | engine+rs |

### L6: 视角→上下文链
| 测试 | 验证 | 数据 |
|------|------|------|
| `architecture_perspective_mapped` | "架构设计" → strategy="architecture" | planner |
| `companion_perspective_mapped` | "你觉得" → expect=COMPANION | planner |
| `perspective_affects_domains` | evolution → C domain weight > architecture → C weight | planner |

### L7: 世界视图→LLM 上下文链
| 测试 | 验证 | 数据 |
|------|------|------|
| `bge_semantic_finds_target` | "有记忆吗" → targets contains "MemoryManager" | objects+bge |
| `jieba_heading_priority` | heading match → targets found without BGE | objects |
| `llm_review_reranks` | LLM BGE review returns subset of candidates | objects+llm |

### L8: 认知运行时端到端
| 测试 | 验证 | 数据 |
|------|------|------|
| `enable_creates_observer` | enable_cognitive_runtime → observer not None | engine |
| `run_cognitive_produces_trace` | run_cognitive("q") → trace ≥ 2 steps | engine+llm |
| `scheduler_maps_reflection_to_task` | MetaReflection → CognitiveTask.type matches | scheduler+mc |
| `workspace_graph_push_pop` | push→pop → hypotheses merged | graph |

### L9: 历史检索链
| 测试 | 验证 | 数据 |
|------|------|------|
| `history_layer1_always_populated` | layer1 entries ≥ 1 per turn | engine+pool |
| `discourse_tree_injects_blocks` | active_blocks → tree_block entries present | engine+pool |
| `cold_blocks_produce_summary` | cold block → tree_block_summary entry | engine+pool |
| `persistent_bge_finds_past` | BGE cosine > 0.5 → past_session entry | engine+pool |

### L10: 边界情况
| 测试 | 验证 | 数据 |
|------|------|------|
| `empty_pool_graceful` | no pool → on_event returns without crash | engine |
| `no_llm_provider_graceful` | MockProvider → response contains mock text | engine |
| `extremely_long_text_truncation` | 10K char text → context doesn't overflow | engine+pool |

## 实现优先级

| Phase | 链路 | 测试数 | 耗时 |
|-------|------|--------|------|
| 1 | L1+L2+L5 | 12 | 20min |
| 2 | L3+L4+L6 | 12 | 20min |
| 3 | L7+L8+L9+L10 | 15 | 30min |
| **总计** | | **39** | **~70min** |
