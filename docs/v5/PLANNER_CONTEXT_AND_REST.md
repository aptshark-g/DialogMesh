# DialogMesh v6 — 全版本全模块最终库存

> 2026-07-24 · v3_0 + v4 + v6 + 设计文档 · 200+ 模块

---

## 总览

```
代码:   约 200 个 .py 文件, 约 80,000 行
设计:   约 230 篇 .md 文档
Rust:   5 文件, 1,007 行

分层:
  v3_0:    ~9,000L  (cognitive tree + compiler + observability + llm providers)
  v4:      ~13,000L (cognitive + scheduler + substrate + world)
  v6:      ~50,000L (pcr + intent + association + behavior + discourse + persistence + memory + planner + context + engineering)
  设计:    ~230 篇  (v3.0:105篇, v5:18篇, 根级:40篇, 其他:60+)
```

---

## 一、planner/ (28f, 7,908L) — 规划+技能生命周期

此目录实现了一个**完整的 Skill 生命周期管理系统**，包含规划、执行、蒸馏、验证四大环节：

| 模块 | 行数 | 功能 |
|------|------|------|
| models.py | 1,197L | 规划数据模型(Plan, Task, Skill, Artifact) — **核心** |
| planner.py | 793L | 主规划器 |
| executor.py | 582L | 对话树执行器 |
| skill_engine.py | 545L | 技能执行引擎 |
| optimizer.py | 421L | 规划优化器 |
| strategy_selector.py | 409L | 策略选择器 |
| scheduler.py | 344L | 规划调度器 |
| skill_registry.py | 326L | 技能注册表 |
| fallback.py | 317L | 降级回退引擎 |
| decomposition.py | 287L | 任务分解 |
| dependency_resolver.py | 228L | 依赖解析器 |
| skill_matcher.py | 201L | 技能匹配器 |
| distillation_engine.py | 198L | **蒸馏引擎**: v4存储扫描→Skill候选 |
| agent_allocator.py | 177L | Agent分配器 |
| skill_pool.py | 55L | Skill池生命周期(Candidate→Verified→Core) |
| evaluation_engine.py | 33L | 多维信念评估 |

**v6当前用 llm_planner.py(66L)** — 仅薄封装。这个完整系统未接入。

---

## 二、context/ (19f, 5,418L) — 上下文工程完整管线

| 模块 | 行数 | 功能 |
|------|------|------|
| source.py | 835L | **ContextSource抽象接口** — 多知识域上下文检索基类 |
| manager.py | 724L | 上下文管理器主类 |
| window.py | 425L | 上下文窗口管理 |
| assembler.py | 373L | 上下文聚合+排序 |
| pruner.py | 303L | 子图溢出裁剪(4轮trim+3步landing) |
| graph_source.py | 351L | ConceptGraph子图编译源 |
| cross_domain_ir.py | 279L | **跨域IR**: intent感知的中间表示 |
| models.py | 250L | 上下文数据模型 |
| budget_allocator.py | 217L | 三层预算分配 |
| topic_tree_source.py | 183L | TopicTree上下文源(带回溯) |
| cross_ref_builder.py | 106L | 跨域cross_ref生成 |
| domain_selector.py | 100L | 意图感知域选择矩阵 |
| cross_domain_expander.py | 58L | Event ID多域扩展stub |
| store.py | 450L | 上下文存储 |

**v6当前未使用** — 全部走 discourse_block_tree.build_context()。这个管线更完整。

---

## 三、topic_tree/ (11f, 2,120L) — 话题树自适应热模型

| 模块 | 行数 | 功能 |
|------|------|------|
| manager_v2.py | 1,091L | **TopicTree V2** — 核心话题管理器 |
| heat_model.py | 171L | 自适应热模型(ARC启发+拓扑加权) |
| models.py | 153L | 话题树/图数据模型 |
| context.py | 121L | 双视角+多视角+行为锚上下文组装 |
| manager.py | 122L | 引擎集成层 |
| fact_store.py | 103L | 不变事实+可变关系存储 |
| compass_patch.py | 29L | 三范式罗盘补丁 |

**v6当前用 discourse_block_tree** — topic_tree是另一个并行话题系统。

---

## 四、engineering/ (15f, 812L) — 工程知识图谱

| 模块 | 行数 | 功能 |
|------|------|------|
| chain.py | 135L | 工程链主干 |
| knowledge_graph.py | 95L | 5层知识图(约束/模式/决策/质量/反模式) |
| constraint_engine.py | 66L | 类型匹配+反模式检测 |
| models.py | 65L | 工程数据模型 |
| type_system.py | 41L | 类型注册+is_a推导 |
| registry.py | 42L | 模块注册表 |
| persistence.py | 53L | 持久化适配 |
| persistence_full.py | 53L | 全量持久化 |
| monitor.py | 24L | 管线监控 |

**v6当前用 engineering/chain.py(135L)** — 仅MCP桥接基础。

---

## 五、llm_providers/ (24f, 3,672L) 

### 基础设施

| 模块 | 行数 | 功能 |
|------|------|------|
| openai_provider.py | 358L | OpenAI兼容Provider |
| local_provider.py | 327L | 本地LM Studio Provider |
| provider_manager.py | 325L | Provider管理器 |
| streaming.py | 292L | 流式响应 |
| circuit_breaker.py | 380L | 断路器+降级 |
| base.py | 191L | Provider基类 |
| gateway_provider.py | 163L | Switch Gateway路由 |
| failover_provider.py | 139L | Failover提供商 |
| provider_factory.py | 100L | Provider工厂 |

### 6个专用LLM实例 (llm_instances/)

| 模块 | 功能 |
|------|------|
| answer_llm.py | 回答生成器 |
| intent_llm.py | 意图分析师 |
| meta_cognitive_llm.py | 元认知监督者 |
| pcr_llm.py | 认知分析师 |
| planning_llm.py | 规划师 |
| reflective_llm.py | 系统复盘师 |

**v6当前: DeepSeek直连** — 6LLM多实例设计了但未使用。

---

## 六、v3_common/ (13f, 5,131L) — 共享基础层

| 模块 | 行数 | 状态 |
|------|------|------|
| data_models.py | 886L | ✅ 保留 (共享数据契约) |
| orchestrator.py | 668L | ➡️ un_use/ |
| expertise_probe.py | 703L | ➡️ un_use/ → llm_expertise替代 |
| gates.py | — | ✅ 保留 (三层门控) |
| blueprints.py | — | ✅ 保留 (蓝图设计) |
| plugin_system.py | 210L | ➡️ discourse_block_tree/ |
| integration_bridge.py | — | ✅ 保留 |
| health_check.py | — | ✅ 保留 |
| adaptive_threshold.py | — | ✅ 保留 |
| serialization.py | — | ✅ 保留 |
| intent_rule_registry.py | 304L | ➡️ un_use/ |
| metrics.py | 221L | ➡️ observability/ (已合并) |
| structured_logger.py | 108L | ➡️ un_use/ |

---

## 七、v4/ (非cognitive, ~30模块, 多数 <100行stub)

| 目录/文件 | 行数 | 功能 |
|----------|------|------|
| cognitive_scheduler/ | 1,659L | **完整认知调度系统**(9文件) |
| causal_substrate/ | 270L | 因果基座(3文件) |
| persistence/ | 95L | v4持久化适配 |
| skill_layer/ | 84L | 技能层(distillation_engine+skill_pool) |
| causal/ | 53L | 因果推理 |
| context/ | 49L | v4上下文适配 |
| optimizer/ | 47L | 优化器 |
| world/ | 42L | 世界模型 |
| runtime/ | 41L | 运行时 |
| chunking/ | 26L | chunking |
| behavior_graph/ | 24L | 行为图 |
| document/ | 20L | 文档处理 |
| event_log/ | 18L | 事件日志 |
| observation_compiler/ | 15L | 观察编译器 |
| hypothesis_engine/ | 14L | 假设引擎 |
| adapter/ | 6L | 适配器 |
| cli/ | 4L | CLI入口 |
| tiered/ | 1L | 分层 |
| un_use/ | 311L | 废弃模块(4文件) |

---

## 八、docs/ 设计文档未读清单

### 最关键的未读设计 (design not yet mapped to implementation)

| 文档 | 内容 |
|------|------|
| BUSINESS_CHAIN_STATE_MACHINE.md | 全局状态机, 16状态字段 |
| BUSINESS_CHAIN_2.1_TOPIC_TREE.md | 话题树完整设计 |
| BUSINESS_CHAIN_1.5_PLANNING.md | 蓝图系统+技能生命周期 |
| BUSINESS_CHAIN_02_CONTEXT.md | 上下文工程完整管线 |
| BUSINESS_CHAIN_05_BEHAVIOR.md | 行为链设计 |
| BUSINESS_CHAIN_07_ENGINEERING.md | 工程链设计 |
| DESIGN_SPECIFICATION.md | v6完整规格说明 |

### docs/v3.0/ 105篇设计

包括: DDD领域设计, cognitive_compiler详细设计, discourse_block_tree四空间, cognitive_profile_v2, association链设计, 等等。

### docs/merge/ 6篇归档

包括: COGNITIVE_PIPELINE, OBSERVATION_COMPILER, etc.

---

## 九、重叠与重复 (需整合)

| 功能域 | v3_0 | v4 | v6 | 选择 |
|--------|------|----|----|------|
| **规划+技能** | — | skill_layer(stub) | llm_planner(66L) | **planner/(7,908L)** |
| **上下文工程** | — | context(stub) | discourse.build_context | **context/(5,418L)** |
| **话题树** | — | — | discourse_block_tree | **topic_tree/(2,120L) 或 discourse, 二选一** |
| **LLM Providers** | 5p(1798L) | — | DeepSeek直连 | **llm_providers/(3,672L) 或 DeepSeek** |
| **6LLM实例** | — | llm_instances/6文件 | — | **v4设计, v6未用** |
| **EventBus** | cog/event_bus(213L) | — | 设计存在 | **v3版可迁移** |
| **因果推理** | — | causal_substrate(270L) | — | **v4版** |
| **蓝图系统** | — | ABC层 | — | **v3_common/blueprints + v4/ABC** |

---

## 十、十个未接入的重量级系统

1. **planner/** — 完整Skill生命周期(7,908L) — 仅llm_planner薄层在用
2. **context/** — 完整上下文管线(5,418L) — 未用
3. **topic_tree/** — 自适应热模型(2,120L) — 未用
4. **cognitive_scheduler/** — 认知调度(1,659L) — 未用
5. **causal_substrate/** — 因果推理(270L) — 未用
6. **llm_providers/ 6LLM实例** — 多LLM分工 — 仅DeepSeek在用
7. **v3_0/cognitive_tree** — 知识超图(8,909L) — 未迁移
8. **v3_0/observability** — 观测+遥测(1,982L) — telemetry/tracer丢失
9. **v4/world** — 世界模型(42L stub) — 设计存在,代码为空
10. **engineering/ 知识图谱**(812L) — constraint_engine+knowledge_graph — 基础版在用
