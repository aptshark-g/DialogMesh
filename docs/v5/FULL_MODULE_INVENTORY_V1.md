# DialogMesh v6 — 全版本模块库存 (v3_0 × v4/cognitive × v6 current)

> 2026-07-24 · 清点全部 80+ 模块，标注功能重叠/设计丢失/可迁移

---

## 一、v3_0/cognitive_tree + cognitive_compiler (知识超图引擎, 8,909L)

### cognitive_tree/ — LLM认知空间

| 模块 | 行数 | 功能 | v6中对应/重叠 | 状态 |
|------|------|------|--------------|------|
| models.py | 479L | 10种CogType + 8种CogEdgeType + 6种生命周期 | RelationEdge(3×4硬编码) | **设计更优, 未迁移** |
| manager.py | 683L | CognitiveTree CRUD + 查询 + 遍历 | SubgraphCompiler(176L, 弱) | **功能超集, 待迁移** |
| cross_ref.py | 384L | 跨节点引用 + 证据链 | DiscourseBlockTree.GroupReference | **功能重叠, 可合并** |

### cognitive_compiler/ — 编译与推理

| 模块 | 行数 | 功能 | v6中对应 | 状态 |
|------|------|------|----------|------|
| compiler.py | 331L | 6个LLM实例推理→CognitiveTree统一入口 | agent_native(线性流程) | **多LLM编译, v6无** |
| edge_manager.py | 173L | 8种推理边显式管理 | RelationSubstrate(3种kind) | **语义更丰富, 待迁移** |
| event_bus.py | 213L | 认知事件总线 | EventBus(设计存在) | **可整合** |
| lifecycle.py | 187L | 节点生命周期 + 状态机 | 无 | **缺, 应迁移** |
| expertise_probe_v3.py | 151L | 冷启动专业度探测(通用特征, 无词表) | llm_expertise.py(LLM版) | **LLM版更优** |
| reflective.py | 78L | 系统偏见检测器 | MetaCognition(弱) | **可注入Meta** |
| tree_health.py | 78L | TreeHealthAnalyzer | 无 | **缺** |
| profile_updater.py | 138L | 用户画像深度更新器 | OCEANProfile(265L) | **设计重叠** |
| meta_cognitive.py | 97L | 事实性校验器 | MetaCognition(328L) | **v4版更全** |
| access_control.py | 47L | LLM访问权限矩阵 | 无 | **蓝图系统需要** |
| rule_conflict.py | 48L | 规则冲突检测 | 无 | **缺** |
| pcr_feedback.py | 46L | PCR反馈回路 | PCR V2(无反馈) | **缺闭环** |

### llm_providers/ — 旧LLM Provider层 (已废弃)

| 模块 | 行数 | v6对应 | 状态 |
|------|------|--------|------|
| base.py | 438L | core/agent/llm_providers/ | **重复, 当前v6版本在用** |
| openai_provider.py | 428L | 同上 | **重复** |
| hybrid_router.py | 407L | DeepSeek直连(当前用) | **过时** |
| failover_provider.py | 206L | — | **未迁移** |

### observability/ — 旧观测层

| 模块 | 行数 | v6对应 | 状态 |
|------|------|--------|------|
| metrics.py | 321L | observability/metrics.py | **已合并** |
| logger.py | 320L | observability/logger.py | **已合并** |
| store.py | 510L | persistence/sqlite_store.py | **已升级** |
| telemetry.py | 372L | 无 | **缺** |
| tracer.py | 207L | 无 | **缺** |
| alert.py | 252L | metacognitive_trigger.py | **已升级, v3版可删** |

---

## 二、v4/cognitive — 认知子系统 (36文件, ~7,000L)

### Layer 1: 用户认知

| 模块 | 行数 | 功能 | 接入状态 |
|------|------|------|----------|
| ocean_profile.py | 265L | OCEAN 10维 + MBTI转换 | ✅ 桥接已接 |
| bfi_calibrator.py | 201L | BFI-10文献锚定校准 | ✅ 桥接已接 |
| structural_signals.py | 220L | 结构信号提取(NS+FT) | ❌ 未接 |
| correction_journal.py | 156L | 用户修正日志+漂移检测 | ✅ 桥接已接 |
| dynamics.py | 172L | 认知动态计算 | ✅ 桥接已接 |
| convergence.py | 176L | 收敛引擎(电容模型) | ❌ 未接 |

### Layer 2: 融合与检索

| 模块 | 行数 | 功能 | 接入状态 |
|------|------|------|----------|
| fusion.py | 105L | TrackA+B融合→LLM上下文 | ✅ 桥接已接 |
| belief_map.py | 305L | 信念累积器+递归粒度 | ✅ 桥接已接 |
| tag_layer.py | 319L | L1+L2标签获取+g因子 | ✅ 桥接已接 |
| memory_extractor.py | 288L | MemoryPoint上下文提取 | ✅ 桥接已接 |
| subgraph_compiler.py | 176L | 跨链上下文编译(双视角) | ❌ 未接 |
| signal_filter.py | 160L | TrackA+B协调器 | ❌ 未接 |
| llm_profile_analyst.py | 186L | 三源融合画像 | ❌ 未接 |

### Layer 3: 元认知与自省

| 模块 | 行数 | 功能 | 接入状态 |
|------|------|------|----------|
| metacognition.py | 328L | 审查优先级+回顾+自审 | ✅ 桥接已接 |
| internal_monitor.py | 189L | 内部状态监控 | ✅ 桥接已接 |
| scheduler.py | 143L | 元认知调度 | ❌ 未接 |
| runtime.py | 132L | LLM推理循环 | ❌ 未接 |
| workspace.py | 143L | 认知工作空间图 | ❌ 未接 |
| version_control.py | 202L | Git风格版本控制 | ❌ 未接 |

### ABC 系统 (3层决策)

| 模块 | 行数 | 功能 |
|------|------|------|
| abc_orchestrator.py | 140L | 三层决策: C(神经符号)→B(LLM适配)→A(规则) |
| neuro_symbolic.py | 265L | C层: 可组合规则引擎 |
| llm_adapter.py | 75L | B层: 规则不足时LLM生成新规则 |

### 行为与学习

| 模块 | 行数 | 功能 |
|------|------|------|
| behavior_discovery.py | 242L | 3阶段行为发现 Pipeline |
| pattern_learner.py | 183L | 模式学习+策略建议 |
| simulation_engine.py | 238L | 内部模拟→评估→学习 |

### Mind (持久化认知结构)

| 模块 | 行数 | 功能 |
|------|------|------|
| mind.py | 137L | 统一认知结构: Relation+Attention+Mistakes |
| mind_attention.py | 100L | 用户注意力模式 |
| mind_relation.py | 178L | 关系增信学习 |
| mind_mistakes.py | 128L | 失败模式学习 |

### 其他

| 模块 | 行数 | 功能 |
|------|------|------|
| inertia_graph.py | 232L | 跨链惯性权重图 |
| models.py | 196L | UserTag + MemoryPoint + MemoryChunk |
| contextual_strategy.py | 193L | 策略×上下文匹配 |
| p2_advanced.py | 252L | 因果晋升+TTL+子图缓存 |
| reasoning_policy.py | 202L | 结构化反馈→系统推理方式 |
| policy_prompt.py | 107L | LLM动态策略生成 |
| quality_scorer.py | 126L | 内部质量评分 |
| monitor_report.py | 162L | 统一基准监控+回放 |

---

## 三、v6 Current — 当前实现

### 已在管线中 (agent_native wired)

| 模块 | 行数 | 上接(消费) | 下接(产出) |
|------|------|-----------|-----------|
| pcr_router_v2.py | — | MessageReceived | Routed |
| multi_intent_splitter.py | — | MessageReceived | IntentLocked |
| l4_temporal.py | — | IntentLocked | TemporalPredict |
| l4_collaborative.py | — | TemporalPredict | VerifiedTransition |
| behavior/models.py | — | IntentLocked | BehaviorObserved |
| engineering/chain.py | — | IntentLocked | ToolPlan |
| agent_native.py | 169L | All | Plan |
| metacognitive_trigger.py | 168L | BlockUpdated | MetaTriggered |
| v4/cognitive_bridge.py | 200L | All perception | CognitiveContext |
| persistence/broker.py | 234L | All events | persisted |

### 已完成未接入

| 模块 | 行数 | 缺接入 |
|------|------|--------|
| llm_relation_extractor.py | 203L | L2 relation分类 |
| dual_track.py | — | hot+cold intent |
| multi_perspective.py | — | 4视角分析 |
| ambiguity_bridge.py | — | 死锁→信念桥 |
| three_paradigm_context.py | 173L | 温度×距离×价值→LLM |
| posterior_corrector.py | 141L | 后验修正 |
| ragraph.py | 176L | RAG+图检索 |
| federated_index.py | 192L | 6源联邦索引 |
| compression_router.py | 136L | P×I存储路由 |
| strategy_federation.py | 276L | 策略联邦 |
| xml_cards.py | 305L | XML记忆卡 |
| cluster_map.py | 173L | 聚类可视化 |
| subgraph_compiler.py | 176L | 跨链上下文 |

---

## 四、功能重叠矩阵 (需要整合)

| 功能域 | v3_0实现 | v4/cognitive实现 | v6实现 | 选哪一个 |
|--------|----------|------------------|--------|----------|
| 知识图引擎 | CognitiveTree(683L, 10节点+8边) | SubgraphCompiler(176L, 弱) | RelationSubstrate(453L, 3×4) | **v3_0 CognitiveTree** |
| 关系分类 | — | — | RelationSubstrate._infer_strength + LLMRelationExtractor | **LLMRelationExtractor** |
| 多LLM编译 | CognitiveCompiler(331L, 6LLM) | — | agent_native(169L, 线性) | **CognitiveCompiler** |
| EventBus | cog/event_bus(213L) | — | EventBus(设计存在, 未实现) | **整合作业** |
| 蓝图编排 | — | ABC三层(abc_orchestrator) | agent_native(硬编码) | **ABC + 蓝图** |
| 用户画像 | ProfileUpdater(138L) | OCEANProfile(265L)+BFI(201L) | — | **v4版** |
| 元认知 | MetaCog(97L) | MetaCognition(328L) | MetaTrigger(168L) | **v4主+v3补充** |
| 版本控制 | — | VersionControl(202L) | — | **v4版** |
| LLM Providers | 5个provider(1798L) | — | DeepSeek直连 | **当前v6** |
| 观测 | 5个module(1982L) | MonitorReport(162L) | metrics+logger(已合并) | **v6版, 缺telemetry/tracer** |

---

## 五、结论: 三类缺口

### A. 设计存在, v3有实现, v6丢失 (5个)
- Cognitive Tree 知识超图 (10节点+8边) → RelationSubstrate 降级为3×4
- CognitiveCompiler 6LLM编译入口 → agent_native 降级为线性
- AccessControl 权限矩阵 → 缺失
- Lifecycle 节点生命周期 → 缺失
- ExpertProbe(通用特征版) → 被LLM版替代

### B. v4有, v6未充分用 (8个)
- ABC 三层决策系统
- SimulationEngine 内部模拟
- Mind(注意力+错误+关系)
- NeuroSymbolic 规则引擎
- VersionControl
- Workspace+ExecutionTrace
- ContextualStrategy
- InertiaWeightGraph

### C. v6新建, 独立待接入 (13个)
- 见上文"已完成未接入"列表
