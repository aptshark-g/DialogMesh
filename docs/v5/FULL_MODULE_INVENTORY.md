# DialogMesh v6 — 全版本全模块完整库存 (最终版)

> 2026-07-24 · v3_0 + v3_2 + v4 + v6 + 设计文档
> 合并自: v1详细列表 + planner/context/topic_tree/v3_2补充

---

## 零、总览

```
版本     文件     代码行    状态
v3_0     ~45      ~9,000    cognitive tree + compiler + observability + llm providers
v3_2     ~54      ~3,000    大量stub + 1292L ParameterRegistry
v4       ~130     ~13,000   cognitive(36f) + scheduler(9f) + 其他(~30模块stub)
v6       ~100     ~50,000   pcr + intent + association + behavior + discourse + 持久化 + 记忆 + planner + context + engineering

设计     230+篇   —         v3.0:105篇, v5:18篇, 根级:40篇, merge:6篇
```

---

## 一、v3_0/cognitive_tree + cognitive_compiler (知识超图引擎, ~9,000L)

详见 `FULL_MODULE_INVENTORY_V1.md` 第一节。核心发现: 10种CogType + 8种CogEdgeType + 6种生命周期 — 完整但未迁移到v6。

## 二、v4/cognitive — 认知子系统 (36文件, ~7,000L)

详见 `FULL_MODULE_INVENTORY_V1.md` 第二节。核心: 13/13模块已通过cognitive_bridge加载。

## 三、v6 Current — 已在管线 + 未接入

详见 `FULL_MODULE_INVENTORY_V1.md` 第三节。

---

## 四、planner/ (28f, 7,908L) — 规划+技能生命周期 ⭐ 新发现

**这是一个完整的 Skill 生命周期管理系统，v6从未使用。**

| 模块 | 行数 | 功能 |
|------|------|------|
| models.py | 1,197L | Skill/Plan/Task/Artifact数据模型 — **核心** |
| planner.py | 793L | 主规划器: L1(规则) + L2(LLM) + L3(优化) |
| executor.py | 582L | 对话树执行器, 任务编排, 结果回写 |
| skill_engine.py | 545L | 技能执行引擎, 支持本地/远程/LLM三种执行模式 |
| optimizer.py | 421L | 规划优化器, 约束满足 + 成本最小化 |
| strategy_selector.py | 409L | 上下文感知策略选择器 |
| scheduler.py | 344L | 规划调度器, 优先级+依赖+DAG拓扑 |
| skill_registry.py | 326L | 技能注册表, 版本管理, 依赖解析 |
| fallback.py | 317L | 降级回退引擎, 3级回退链 |
| decomposition.py | 287L | 递归任务分解, 收敛条件检测 |
| dependency_resolver.py | 228L | 依赖图解析, 拓扑排序, 环检测 |
| skill_matcher.py | 201L | 意图→技能语义匹配 |
| distillation_engine.py | 198L | 蒸馏引擎: v4存储扫描→Skill候选 |
| agent_allocator.py | 177L | 多Agent分配, 负载均衡 |
| skill_pool.py | 55L | Skill生命周期: Candidate→Verified→Core |
| evaluation_engine.py | 33L | 多维Skill信念评估 |

**v6当前用 llm_planner.py(66L)** — 仅薄封装。相当于用1%的代码替代了这个7,908L的系统。

---

## 五、context/ (19f, 5,418L) — 上下文工程完整管线 ⭐ 新发现

**v6当前完全未使用。**

| 模块 | 行数 | 功能 |
|------|------|------|
| source.py | 835L | ContextSource抽象接口 — 多知识域上下文检索基类 |
| manager.py | 724L | 上下文管理器: 聚合/排序/注入 |
| window.py | 425L | 上下文窗口管理, 滑动+固定+混合 |
| assembler.py | 373L | 上下文聚合器, 多源排序+消重 |
| pruner.py | 303L | 子图溢出裁剪(4轮trim+3步landing) |
| graph_source.py | 351L | ConceptGraph子图编译源 |
| cross_domain_ir.py | 279L | 跨域IR: intent感知的中间表示 |
| models.py | 250L | 上下文数据模型 |
| budget_allocator.py | 217L | 三层预算分配(domain/entity/turn) |
| topic_tree_source.py | 183L | TopicTree上下文源(带回溯) |
| cross_ref_builder.py | 106L | 跨域cross_ref指针生成 |
| domain_selector.py | 100L | intent→域选择矩阵 |
| cross_domain_expander.py | 58L | Event ID多域扩展(stub) |
| store.py | 450L | 上下文存储(内存+SQLite) |

**v6当前走 discourse_block_tree.build_context()** — 这个管线功能更完整。

---

## 六、topic_tree/ (11f, 2,120L) — 话题树自适应热模型 ⭐ 新发现

| 模块 | 行数 | 功能 |
|------|------|------|
| manager_v2.py | 1,091L | **TopicTreeV2** 核心 — 话题CRUD+合并+搜索+热度 |
| heat_model.py | 171L | ARC启发式自适应热模型, 拓扑加权 |
| models.py | 153L | 话题树/图数据模型 |
| context.py | 121L | 双视角+多视角+行为锚上下文 |
| manager.py | 122L | 引擎集成层 |
| fact_store.py | 103L | 不变事实+可变关系存储 |
| compass_patch.py | 29L | 三范式罗盘接入 |

**与 discourse_block_tree 功能重叠** — 设计为并行话题系统。

---

## 七、llm_providers/ (24f, 3,672L) — 多LLM基础设施

| 类别 | 模块 | 行数 | 功能 |
|------|------|------|------|
| Provider层 | openai_provider.py | 358L | OpenAI兼容 |
| | local_provider.py | 327L | LM Studio本地 |
| | gateway_provider.py | 163L | Switch Gateway路由 |
| | failover_provider.py | 139L | 故障转移 |
| | circuit_breaker.py | 380L | 断路器+降级 |
| | hybrid_router.py | 191L | 混合路由 |
| | provider_manager.py | 325L | Provider生命周期 |
| | streaming.py | 292L | 流式响应 |
| LLM实例 | answer_llm.py | 28L | 回答生成器 |
| | intent_llm.py | 22L | 意图分析师 |
| | meta_cognitive_llm.py | 23L | 元认知监督者 |
| | pcr_llm.py | 21L | 认知分析师 |
| | planning_llm.py | 22L | 规划师 |
| | reflective_llm.py | 22L | 系统复盘师 |

**v6当前: DeepSeek直连** — 6LLM多实例分工设计了但未启用。

---

## 八、engineering/ (15f, 812L) — 工程知识图谱

| 模块 | 行数 | 功能 |
|------|------|------|
| chain.py | 135L | 工程链主干 |
| knowledge_graph.py | 95L | 5层知识图(约束/模式/决策/质量/反模式) |
| constraint_engine.py | 66L | 类型匹配+反模式检测 |
| models.py | 65L | 工程数据模型 |
| type_system.py | 41L | 类型注册+is_a推导 |

---

## 九、v4/ 非cognitive目录 (~30个stub模块)

| 模块 | 行数 | 功能 |
|------|------|------|
| cognitive_scheduler/ | 1,659L(9f) | 完整认知调度系统 |
| causal_substrate/ | 270L(3f) | 因果基座 |
| persistence/ | 95L | v4持久化适配 |
| skill_layer/ | 84L | 技能层(stub) |
| world/ | 42L | 世界模型(stub) |
| optimizer/ | 47L | 优化器(stub) |
| runtime/ | 41L | 运行时(stub) |
| un_use/ | 311L(4f) | 废弃模块 |

其余均为 <50行 stub。

---

## 十、v3_2/ (~54f, ~3,000L) — 过渡版本

大部分为测试文件+stub __init__.py。

**唯一有内容的模块:**
| 模块 | 行数 | 功能 |
|------|------|------|
| un_use/parameter_registry.py | 1,292L | ParameterRegistry — 自适应参数系统 |

其余目录(behavior_graph/compiler/fusion/do_calculus/foa/predictor/rewarder/negative_kb)均仅含 <5行 stub。

---

## 十一、v3_common/ (13f, 5,131L) — 共享基础层

详见此前审计。已清理: system_bootstrap→un_use, orchestrator→un_use, expertise_probe→llm_expertise替代。保留: data_models, gates, blueprints, health_check等。

---

## 十二、v3_legacy/ (1f, 886L) — data_models.py 保留

---

## 附录: 重叠与重复 (需整合)

| 功能域 | v3_0 | v4 | v6 | 选择 |
|--------|------|----|----|------|
| 规划+技能 | — | skill_layer(stub) | llm_planner(66L) | **planner/(7,908L)** |
| 上下文工程 | — | context(stub) | discourse.build_context | **context/(5,418L)** |
| 话题树 | — | — | discourse_block_tree | **二选一** |
| LLM Providers | 5p(1798L) | (6LLM实例) | DeepSeek直连 | **待定** |
| 知识图引擎 | CognitiveTree | SubgraphCompiler | RelationSubstrate | **v3_0设计** |
| EventBus | cog/event_bus | — | 设计存在 | **v3版** |
| 蓝图 | v3_common/blueprints | ABC层 | — | **ABC+blueprints** |
| 观测遥测 | telemetry+tracer | MonitorReport | metrics+logger | **v6版, 缺遥测** |
