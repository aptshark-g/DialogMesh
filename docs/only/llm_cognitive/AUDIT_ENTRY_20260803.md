# LLM 认知层专项审计 — 第一轮（代码现状盘点）

> 日期: 2026-08-03 | 范围: `llm_providers/`（139.5KB, 14 源文件）+ `v3_0/cognitive_tree/`（65KB）+
> `v3_0/cognitive_compiler/`（74KB）+ 根级 `cognitive_compiler/`（49.6KB）+ `tiered/`（68.8KB）
> 定位: 用户点名"LLM 的思考树"→ 盘点后发现这是跨切面认知层（思考树 + 认知编译器 +
> LLM Provider + 分层编译），v3 路径活跃、v6 部分活跃、且存在孤儿/断裂。
> 结论先行: **llm_providers 零测试；cognitive_tree CrossRef async 迁移致 9 测试失败；
> 根级 cognitive_compiler 4 文件孤儿；思考树 v6 主路径不消费（但 tiered/ 活跃）。**

---

## 一、文件清单与体量

### 1.1 `llm_providers/`（14 源文件 139.5KB）— LLM Provider 基础设施
| 文件 | 体量 | 定位 |
|---|--:|---|
| `provider_manager.py` | 14.5KB | ProviderManager（配置/注册/路由/统计）|
| `models.py` | 17.4KB | ProviderConfig/Capabilities/Health/RoutingDecision（12 模型）|
| `circuit_breaker.py` | 16.2KB | CircuitBreaker + Registry |
| `openai_provider.py` | 15.1KB | OpenAI Provider |
| `local_provider.py` | 12.5KB | LM Studio 本地 Provider |
| `streaming.py` | 10.8KB | StreamingAggregator/SSE/WebSocket/ProgressiveJSON |
| `base.py` | 8.4KB | LLMProvider ABC + GenerateRequest/Result |
| `hybrid_router.py` | 7.6KB | HybridRouter（快慢通道）|
| `gateway_provider.py` | 5.9KB | Switch Gateway 路由 |
| `failover_provider.py` | 6.6KB | Failover |
| `switch_provider.py` | 3.0KB | Switch |
| `deepseek_direct.py` | 3.9KB | DeepSeek 直连 |
| `mock_provider.py` | 2.9KB | Mock |
| `provider_factory.py` | 3.5KB | 工厂 |

### 1.2 `v3_0/cognitive_tree/`（65KB）— 思考树/认知知识超图
| 文件 | 体量 | 定位 |
|---|--:|---|
| `manager.py` | 28.0KB | CognitiveTree（add_node/update/edge/遍历 DFS/BFS/活跃分支/stale）|
| `models.py` | 19.4KB | CogType/CogNodeStatus/CogEdgeType/CognitiveTreeNode/Edge/LLMPermissions/AccessControlMatrix |
| `cross_ref.py` | 16.3KB | CrossRefLink/CrossRefManager（topic↔cognitive 引用）|
| `__init__.py` | 1.3KB | 门面 |

### 1.3 认知编译器（两处）
| 目录 | 体量 | 内容 |
|---|--:|---|
| `v3_0/cognitive_compiler/` | 74KB/13f | compiler/edge_manager/event_bus/lifecycle/meta_cognitive/pcr_feedback/profile_updater/querier/reflective/rule_conflict/tree_health |
| 根级 `cognitive_compiler/` | 49.6KB/6f | compiler/decomposer/dual_manager/entity_cache/injector/scorer |

### 1.4 `tiered/`（68.8KB/12f）— 分层编译管线
action_resolver(TieredActionResolver)/cognitive_compiler(TieredCognitiveCompiler)/context_compiler/
fusion/heat_bridge/jieba_parser/parser/stanza_parser/syntactic_decomposer/topic_matcher/pipeline(MultiTierPipeline)

---

## 二、消费矩阵（实锤）

### 2.1 思考树（cognitive_tree）— v3 路径活跃
```
6 个 LLM 实例（pcr/intent/planning/meta_cognitive/reflective/answer）→ import CogType/CognitiveTreeNode
llm_engine.py:12 → CognitiveTreeNode（LLM 思考记录）
orchestrator/orchestrator.py:48 + models.py:32 → 思考树节点
context/manager.py:25 → CognitiveTree（上下文）
planner/planner.py + skill_engine.py → CogType（规划决策记录）
security/bias_detector.py + hallucination_detector.py → 思考树节点（幻觉检测）
```
→ **v3 路径活跃**；**runtime/engine + cli/engine（v6 主路径）零引用**（rg 无结果）。

### 2.2 认知编译器（v3_0）— v3 路径真接线
```
orchestrator/bootstrap.py:32,36,255-293 → CognitiveCompiler + NodeLifecycleManager + EdgeManager + EventBus
orchestrator/orchestrator.py:42-45 → CognitiveCompiler + EventBus + MetaCognitiveValidator + ReflectiveAnalyzer
```

### 2.3 根级 cognitive_compiler — 部分孤儿
```
compiler.py → 引用 v3_0/cognitive_compiler（CognitiveTreeStore/EventBus）
decomposer.py / dual_manager.py / injector.py / scorer.py / entity_cache.py → 全库零引用（孤儿）
```

### 2.4 tiered/ — v6 活跃
```
compiler/discourse_block_tree.py:140 → RuleDecomposer（对话树 A 路径语法分解）
compiler/extraction_blueprint.py:49,75,82 → JiebaRelationParser/StanzaParser
observation/ 5 个 domain_adapter → DomainAdapter/EmbeddingIndex（action_resolver）
observation/tiered_relation_extractor.py → MultiTierPipeline
runtime/p3_resolver.py:50 → TieredCognitiveCompiler（v6 runtime 挂载）
```

### 2.5 llm_providers — 跨切面消费（全部主路径）
```
service/v3_0/agent_service + app_factory → ProviderManager
api/api_gateway.py:410 → OpenAIProvider
cli/engine.py:113,196-206 + cli/main.py → provider 创建（mock/openai/gateway）
compiler/extraction_blueprint.py:116-124 → Gateway/OpenAI Provider
```

---

## 三、测试现状（实锤）

```
llm_providers/tests/         只有 __init__.py —— 139.5KB 基础设施【零测试】
v3_0/cognitive_tree/tests/   ⚠️ 9 failed, 62 passed
  → TestCrossRefManager 9 失败: AttributeError 'coroutine' object has no attribute
    'get_link_detail/validate_consistency/prune_orphans/to_dict/...'
  → 根因: CrossRefManager 方法被改为 async（await），测试仍同步调用（未 await）
tiered/ / cognitive_compiler（两处） 无测试文件
observation/tests/           2 文件（test_dialogue_interpreter/test_tiered_rel_extractor）
```

---

## 四、实锤线索（第一轮）

1. **llm_providers 零测试** = 全部主路径依赖的 LLM 基础设施无任何测试保护。
2. **cognitive_tree CrossRef async 迁移断裂**（9 失败）= 同型"多代演进→测试未同步"。
3. **根级 cognitive_compiler 4 文件孤儿**（decomposer/injector/scorer/dual_manager）——
   TRACEABILITY"闲置"确认；compiler.py 转发到 v3_0 版。
4. **思考树双代并存**: v3_0/cognitive_tree（v3 用）+ v4/cognitive/*（v6 用，mind/workspace/
   neuro_symbolic）——两套认知记录体系。
5. **tiered/ 是 v6 认知编译的实际载体**（对话树分解 + observation action_resolver +
   runtime p3），但从未作为模块盘点（挂对话树/观察审计的组件）。

---

## 五、待第二轮确认清单

- [ ] 设计文档: `ENGINEERING_MULTILAYER_LLM.md`（1570）+ `DESIGN_MULTILAYER_LLM_COGNITIVE.md`（798）+
  `ENGINEERING_LLM_PROVIDERS.md`（791）+ `design_cognitive_compiler.md`（1735）+
  `ENGINEERING_COGNITIVE_COMPILER.md` + `DESIGN_COGNITIVE_DYNAMICS_V6.md`（305）精读
- [ ] 6 LLM 实例的 llm_engine 思考记录闭环（思考树实际写入路径）
- [ ] ProviderManager 路由/熔断/降级的实际状态（walkthrough 走网关 vs 直连）
- [ ] TieredCognitiveCompiler（runtime p3）与 v3_0 CognitiveCompiler 的关系
- [ ] cognitive_tree 与 v4/cognitive（mind/workspace）的边界
- [ ] 根级 cognitive_compiler 4 孤儿文件去留（含 decomposer 是否被 discourse A 路径替代）
- [ ] CrossRef async 迁移修复面
