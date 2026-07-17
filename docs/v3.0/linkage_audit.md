# DialogMesh v6 — Module Linkage Audit

## 审计日期：2026-07-17
## 方法：扫描 `core/agent/v4/` 全部 127 个 Python 模块，
##       逐个对比 `engine.py` 导入链

---

## 一、已接入引擎：42 个 (33%)

### State（全部接入，v6 新架构）

| 模块 | 引擎中的角色 |
|------|-------------|
| `state/state_object.py` | StateObject 基类 + Transition + 19 种 TransitionReason |
| `state/execution_trace.py` | ExecutionTraceV3 每轮录制 |
| `state/interaction_graph.py` | InteractionGraph 状态传播 |

### Runtime（全部接入）

| 模块 | 引擎中的角色 |
|------|-------------|
| `runtime/engine.py` | 主协调器——所有模块通过它交互 |
| `runtime/config.py` | World参数加载 |
| `runtime/adapter.py` | 引擎适配器 |
| `runtime/event_log_adapter.py` | 事件日志接入 |

### Cognitive v6（全部接入）

| 模块 | 引擎中的角色 |
|------|-------------|
| `cognitive/contextual_strategy.py` | 策略学习——每轮 record()，best_for() 选策略 |
| `cognitive/internal_monitor.py` | 6 类 Monitor 事件记录 |
| `cognitive/meta_consumer.py` | meta_analyze() 消费→生成警告 |
| `cognitive/reasoning_policy.py` | ReasoningPolicy 生成+apply() |
| `cognitive/policy_prompt.py` | LLM 驱动 Policy 生成 |
| `cognitive/pattern_learner.py` | Pattern→Policy 学习+持久化 |
| `cognitive/simulation_engine.py` | 用户认知状态模拟+预测 |
| `cognitive/signal_filter.py` | LLM 协调 TrackA+TrackB |

### Cognitive v4（接入）

| 模块 | 引擎中的角色 |
|------|-------------|
| `cognitive/convergence.py` | EMA 收敛 TrackA |
| `cognitive/dynamics.py` | 9 维动力学计算 |
| `cognitive/fusion.py` | FusionContext 渲染 |
| `cognitive/models.py` | UserTag/MemoryPoint |
| `cognitive/tag_layer.py` | TrackB 人格标签 |
| `cognitive/metacognition.py` | LLM 元认知 |
| `cognitive/workspace.py` | 认知工作区 |
| `cognitive/scheduler.py` | 任务调度器 |
| `cognitive/runtime.py` | 认知运行器 |

### Compiler（部分接入）

| 模块 | 引擎中的角色 |
|------|-------------|
| `compiler/semantic_object.py` | SemanticObject(StateObject) |
| `compiler/relation_substrate.py` | 统一关系底料 |
| `compiler/perspective_planner.py` | 视角选择 |
| `compiler/content_index.py` | 统一检索 |
| `compiler/content_provider.py` | 内容提供者 |
| `compiler/discourse_block_tree.py` | 对话块树 |
| `compiler/extraction_blueprint.py` | 四层提取蓝图 |
| `compiler/index_source.py` | Index 上下文源 |
| `compiler/object_runtime.py` | 对象运行时渲染 |
| `compiler/parameter_registry.py` | 19 参数软编码 |
| `compiler/semantic_path.py` | 语义路径 DAG |

---

## 二、孤岛：存在但未接入引擎的模块 (85 个, 67%)

### compiler/ — 最严重失联区

| 模块 | 设计用途 | 为什么失联 |
|------|---------|-----------|
| `object_builder.py` | Object Genesis 五段管道 | run_chat.py 手动调用，engine 不知 |
| `view_manager.py` | 持久化摄像头模型 | 设计完整但 engine 未调用 |
| `subgraph_compiler.py` | 优先级水波扩展 | 被 content_index 替代 |
| `lsh_index.py` | LSH 索引剪枝 | 可选模块，未接入 |
| `profile_source.py` | Profile 上下文源 | 被 engine._inject_cognitive_profile 替代 |
| `projection_resolver.py` | 投影解析器 | 被 ContentProvider 直接实现 |
| `soft_config.py` | 软编码加载器 | 只有 JSON 层面使用了 |
| `domain_adapters.py` | Topic/Behavior 上下文源 | assembler.py 中接入，非 engine |

### cognitive/ — 3 个失联

| 模块 | 设计用途 | 为什么失联 |
|------|---------|-----------|
| `memory_extractor.py` | MemoryPoint 提取 | engine 中直接用 MemoryManager |
| `cognitive_scheduler/path_policy.py` | 路径策略 | PathAwareScheduler 未接入 |
| `cognitive_scheduler/path_trigger_policy.py` | 触发策略 | 同上 |

### observation_compiler/ — 大面积失联

| 模块 | 设计用途 | 为什么失联 |
|------|---------|-----------|
| `behavior_domain_adapter.py` | 行为域适配器 | DomainAdapter 模式未完备 |
| `dialogue_domain_adapter.py` | 对话域适配器 | 同上 |
| `engineering_domain_adapter.py` | 工程域适配器 | 同上 |
| `memory_domain_adapter.py` | 记忆域适配器 | 同上 |
| `user_domain_adapter.py` | 用户域适配器 | 同上 |
| `document_domain_adapter.py` | 文档域适配器 | 同上 |
| `interpreter` x5 | 各域解释器 | 管线未打通 |
| `builder.py` | Observation 构建器 | 被 pool 直接处理 |
| `normalizer.py` | 归一化器 | 未接入 |
| `projector.py` | 投影器 | 未接入 |
| `surface_relation_extractor.py` | 表层关系提取 | 被 jieba_parser 替代 |
| `tiered_relation_extractor.py` | 分层关系提取 | 同上 |

### persistence/ — 全部失联

| 模块 | 设计用途 | 为什么失联 |
|------|---------|-----------|
| `annotation_store.py` | 标注存储 | 无持久化层 |
| `dialogue_tree_adapter.py` | 对话树持久化 | 设计存在但无实现 |
| `faiss_store.py` | FAISS 向量库 | 未接入 |
| `fts5_index.py` | FTS5 全文索引 | 未接入 |
| `hnsw_index.py` | HNSW 索引 | 未接入 |
| `hybrid_index.py` | 混合索引 | 未接入 |
| `milvus_store.py` | Milvus 向量库 | 未接入 |
| `unified_store.py` | 统一存储 | 设计存在但无实现 |
| `vector_store.py` | 通用向量存储 | 未接入 |

### world/ — 5/8 失联

| 模块 | 设计用途 | 为什么失联 |
|------|---------|-----------|
| `community.py` | 社区发现 | 未接入 |
| `extractor.py` | 世界模型提取 | 未接入 |
| `importance.py` | 重要性评分 | 未接入 |
| `schema.py` | 世界模型 Schema | 未接入 |
| `updater.py` | 世界模型更新 | 未接入 |

### 其他失联模块

| 模块 | 设计用途 | 为什么失联 |
|------|---------|-----------|
| `adapter/code/extractor.py` | 代码提取 | 被 tree_sitter_extractor 替代 |
| `adapter/code/tree_sitter_extractor.py` | tree-sitter 提取 | run_chat.py 外部调用 |
| `adapter/code/lsp_extractor.py` | LSP 提取 | 未完成 |
| `adapter/openclaw/` | OpenClaw 适配器 | 未接入 |
| `api/` | API 层 | CLI 模式使用，非 engine |
| `cli/` | CLI 命令 | 外部消费，非 engine |
| `context/budget_allocator.py` | 预算分配器 | 被 DomainSelector 替代 |
| `context/cross_domain_expander.py` | 跨域扩展 | 未接入 |
| `context/cross_ref_builder.py` | 交叉引用构建 | 未接入 |
| `context/graph_source.py` | 图源 | 被 content_index 替代 |
| `context/pruner.py` | 剪枝器 | 未接入 |
| `hypothesis_engine/decay_resolve.py` | 衰减解决 | 未接入 |
| `hypothesis_engine/match_vote.py` | 匹配投票 | 未接入 |
| `hypothesis_engine/session_manager.py` | 会话管理 | 未接入 |
| `skill_layer/distillation_engine.py` | 技能蒸馏 | 未接入 |
| `skill_layer/evaluation_engine.py` | 技能评估 | 未接入 |
| `skill_layer/executor_map.py` | 执行器映射 | 未接入 |
| `skill_layer/external_adapter.py` | 外部适配器 | 未接入 |
| `skill_layer/skill_pool.py` | 技能池 | 未接入 |
| `tiered/action_resolver.py` | 动作解析器 | v3 设计，未迁移 |
| `tiered/cognitive_compiler.py` | 认知编译器 | v3 设计，未迁移 |
| `tiered/context_compiler.py` | 上下文编译器 | v3 设计，未迁移 |
| `tiered/heat_bridge.py` | 热度桥接 | 未接入 |
| `tiered/intent_parser.py` | 意图解析器 | 被 PerspectivePlanner 替代 |
| `tiered/negative_kb.py` | 否定知识库 | 未接入 |
| `tiered/rule_engine.py` | 规则引擎 | 未接入 |
| `tiered/stanza_parser.py` | Stanza 解析器 | 下载失败原因未接入 |
| `tiered/syntactic_decomposer.py` | 句法分解器 | 被 discourse_block_tree 中的实现替代 |

---

## 三、设计缺口：设计有但代码未实现

| 设计文档 | 未实现部分 |
|---------|-----------|
| `DESIGN_COGNITIVE_DYNAMICS_V6.md` | Mind（长期心智）对象；ContextualStrategy 的 StrategyContext 维度；Transition→Dynamics 升级 |
| `DESIGN_STATE_EVOLUTION_SYSTEM.md` | Mind→Workspace 初始化流；InteractionGraph 动态边生成（非硬编码 6 条）；Knowledge Space 持久化 |
| `DESIGN_UNIFIED_PERSISTENCE.md` | 全部 persistence 模块——DialogueTreeAdapter, UnifiedStore, 向量索引 |
| `DESIGN_FULL_CONCEPT.md` | 概念全览图——缺实时概念发现；缺 LLM 驱动的关系抽取 |
| `DESIGN_ENGINEERING_ONTOLOGY.md` | 工程本体——只有接口，缺数据填充 |
| `DESIGN_DIALOGUE_TREE_PERSISTENCE_ADAPTER.md` | 对话树持久化适配器——设计存在，代码不存在 |
| `DESIGN_PLANNING_SKILL_LAYER.md` | 技能蒸馏+评估——skill_layer 下有文件但全部未接入 |
| `DESIGN_TASK_PLANNING_DYNAMIC.md` | 动态任务规划——无对应代码 |
| `DESIGN_INTERACTION_MODEL.md` | 交互模型——InteractionGraph 只实现了静态边的子集 |
| `DESIGN_HYPOTHESIS_ENGINE.md` | 假设引擎完整管线——decay_resolve, match_vote, session_manager 未接入 |
| `DESIGN_OBSERVATION_COMPILER.md` | 6 域适配器+解释器——全部未接入 |
| `DESIGN_SKILL_LAYER.md` | 技能层——executor_map, external_adapter, skill_pool 全部未接入 |
| `DESIGN_TIERED_ACTION_RESOLVER.md` | 动作解析器——v3 设计，未迁移到 v4 |
| `DESIGN_COMPETITOR_ABSORPTION.md` | 竞争对手吸收策略——缺实现 |

---

## 四、连接图（Engine 视角）

```
engine.on_event()
  │
  ├─ OBSERVE ── ConversationTracker(✅) + DiscourseBlockTree(✅) + BGE index(✅)
  │
  ├─ ACTIVATE ── DiscourseTree.activate()(✅)
  │
  ├─ INFER ── PerspectivePlanner(✅) + ContentIndex(✅) + ObjectRuntime(✅)
  │            + RelationSubstrate(✅) + ContextualStrategy(✅)
  │
  ├─ REFLECT ── CognitiveProfile(✅) + FusionContext(✅) + SignalFilter(✅)
  │              + SimulationEngine(✅) + InteractionGraph(✅)
  │
  ├─ META(5s) ── MetaConsumer(✅) → PolicyGenerator(✅) → ReasoningPolicy(✅)
  │               → LLMPolicyGenerator(✅) → PatternLearner(✅)
  │
  └─ MONITOR ── InternalMonitor(✅) → data/monitor/*.jsonl(✅)

未连接:
  ├─ Object Genesis(builder) ── 需外部 set_object_store() 调用
  ├─ Persistence ── PatternLearner 有 JSON 持久化，其他全部无
  ├─ Observation Compiler ── 6 域适配器全部失联
  ├─ Skill Layer ── 蒸馏/评估/执行全部失联
  ├─ World Model ── community/extractor/importance/schema/updater 全部失联
  ├─ Hypothesis Engine ── decay/match/session 全部失联
  └─ Tiered v3 ── action_resolver/cognitive_compiler/context_compiler 未迁移
```

---

## 五、优先级矩阵

| 优先级 | 类别 | 数量 | 影响 |
|--------|------|------|------|
| **P0** | v6 闭环内的缺口 | 2 | Mind 对象、InteractionGraph 动态边生成 |
| **P1** | 设计已完备但未接入的核心模块 | 12 | ViewManager, SubgraphCompiler, 6 域适配器, ObjectBuilder |
| **P2** | 持久化层 | 9 | AnnotationStore, UnifiedStore, 各种向量索引 |
| **P3** | v3 遗留未迁移 | 8 | ActionResolver, ContextCompiler, RuleEngine等 |
| **P4** | 可选/未来模块 | 54 | CLI子命令、外部适配器、各种解释器 |

### 建议下一步

1. **P0 优先**：实现 Mind 对象（长期心智），InteractionGraph 从 RelationSubstrate 动态建边
2. **P1 次之**：激活 ViewManager（持久摄像头）、ObjectBuilder 自动接入 engine.start()
3. **P2 第三**：统一持久化层——至少 PatternLearner + Profile 需要跨 session 保存
4. **P3/P4**：不追——v3 模块保持可用但不再主动迁移，除非用户明确指定
