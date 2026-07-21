# DialogMesh v6 — 设计 vs 实现差距审计

> 2026-07-21 · 对比 DESIGN_FULL_CONCEPT.md + DESIGN_GLOBAL_STATE_MACHINE.md + 其他设计文档 vs 实际代码

---

## 总览

```
设计总模块数:   ~60 (4层 × 15子系统 + 横切)
代码文件存在:   ~45 (.py 文件存在且编译通过)
实际被调用:     ~8  (on_event 链中引用的)
实现率:         75% (代码存在) / ~15% (实际接入)
```

---

## Layer 0: Pre-Cognitive Router (设计 4 组件)

| 组件 | 代码存在 | 实际接入 | 说明 |
|------|:---:|:---:|------|
| NoiseDetector | ❌ | ❌ | 未实现 |
| ExpectationInfer | ✅ | ❌ | `_infer_expectation()` 存在但未调用 |
| CognitiveQuickScan | ❌ | ❌ | 未实现 |
| RouteDecision | ❌ | ❌ | DomainSelector 部分替代 |

**实现率: 0%**

---

## Layer 1: Intent Parser (设计 4 组件)

| 组件 | 代码存在 | 实际接入 | 说明 |
|------|:---:|:---:|------|
| Preprocessor | ✅ | ❌ | 文本预处理代码存在但未调用 |
| EntityExtractor | ✅ | ❌ | 实体提取器有但未接入 on_event |
| IntentClassifier | ✅ | ❌ | `_infer_expectation()` 部分替代 |
| AmbiguityResolver | ❌ | ❌ | 未实现 |

**实现率: 0%**

---

## Layer 1.5: Planning Skill (设计 6 组件)

| 组件 | 代码存在 | 实际接入 | 说明 |
|------|:---:|:---:|------|
| CognitiveCompiler | ✅ | ❌ | compiler/ 存在但 CognitiveCompiler 未接入 |
| PlanningPrimitives | ✅ | ❌ | 代码存在 |
| PlanningSkills | ✅ | ❌ | 代码存在 |
| MixedPlanningEngine | ❌ | ❌ | 未实现 |
| DynamicToolPlanning | ❌ | ❌ | 未实现 |
| ToolBindingGuard | ❌ | ❌ | 未实现 |

**实现率: 0%**

---

## Layer 2: Context Assembly + LLM (设计核心路径)

| 组件 | 代码存在 | 实际接入 | 说明 |
|------|:---:|:---:|------|
| DomainSelector | ✅ | ✅ | `_compile_context` 中调用 |
| PerspectivePlanner | ✅ | ✅ | `_compile_context` 中调用 |
| ContextAssembler | ✅ | ✅ | `assemble_ir()` |
| BudgetAllocator | ✅ | ⚠️ | 分配了但 to_prompt 未严格过滤 |
| SubgraphCompiler | ✅ | ❌ | 代码完整但未在 on_event 中调用 |
| GatewayLLMProvider | ✅ | ✅ | 替代了 OpenAIProvider |
| _direct_llm_call | ✅ | ✅ | 降级直连 |

**实现率: 80% (核心工作，但 Subgraph 未激活)**

---

## Layer 2: Discourse Tree

| 组件 | 代码存在 | 实际接入 | 说明 |
|------|:---:|:---:|------|
| DiscourseBlockTree | ✅ | ✅ | `on_event` 开头调用 `feed()` |
| SegmentationEngine | ✅ | ✅ | 在 `feed()` 内部 |
| BranchManager | ✅ | ✅ | fork/continue/merge |
| NodeEditor | ✅ | ✅ | V6 PUT endpoint |

**实现率: 100%**

---

## Layer 2: Topic Tree

| 组件 | 代码存在 | 实际接入 | 说明 |
|------|:---:|:---:|------|
| TopicTree | ✅ | ✅ | `TopicTreeContextSource` 在 assembler 中 |
| BehaviorChain集成 | ❌ | ❌ | v3.1 设计但未实现 |
| 双层摘要 | ❌ | ❌ | v3.1 设计但未实现 |

**实现率: 40%**

---

## 横切: Cognitive Profile (设计 6 组件)

| 组件 | 代码存在 | 实际接入 | 说明 |
|------|:---:|:---:|------|
| TrackA 认知动力学 | ✅ | ✅ | inertia/cog/attention 初始化 |
| TrackB 标签层 | ✅ | ⚠️ | `infer_from_trace` 有但 `on_event` 未调 |
| OCEANMapper | ✅ | ❌ | 代码存在但未接入 |
| ExecutionTrace | ✅ | ⚠️ | STRENGTHEN/WEAKEN 记录但未用于决策 |
| TagLayer | ✅ | ⚠️ | 同上 |
| g因子推断 | ❌ | ❌ | 未实现 |

**实现率: 40%**

---

## 横切: Behavior Chain (设计 5 组件)

| 组件 | 代码存在 | 实际接入 | 说明 |
|------|:---:|:---:|------|
| BehaviorDiscovery | ✅ | ❌ | `behavior_discovery.py` 完整但未调用 |
| PatternLearner | ✅ | ❌ | 有文件但未接入 on_event |
| BehaviorPredictor | ✅ | ❌ | 同上 |
| ConstraintCompleter | ✅ | ❌ | 代码存在但未接入 |
| BehaviorGraph | ✅ | ⚠️ | adapter 初始化了但未触发 |

**实现率: 10%**

---

## 横切: Association Chain (设计 5 组件)

| 组件 | 代码存在 | 实际接入 | 说明 |
|------|:---:|:---:|------|
| 5-Layer Funnel | ✅ | ❌ | tiered/fusion.py 存在但未接入 |
| Fusion Engine | ✅ | ❌ | cognitive/fusion.py 存在但未接入 |
| NegativeKB | ✅ | ❌ | 代码存在未接入 |
| CausalReasoning | ❌ | ❌ | 未实现 |
| AssociationGraph | ⚠️ | ❌ | InteractionGraph 部分替代 |

**实现率: 0% (代码在, 全未接)**

---

## 横切: Engineering Chain (设计 4 组件)

| 组件 | 代码存在 | 实际接入 | 说明 |
|------|:---:|:---:|------|
| ConstraintEngine | ✅ | ❌ | 代码存在但未接入 |
| RecursiveMap | ✅ | ✅ | V6 endpoint + engine 内部使用 |
| ParameterRegistry | ✅ | ✅ | `run_chat.py` 使用, 引擎有 load_defaults |
| TTLMigration | ❌ | ❌ | 未实现 |

**实现率: 50%**

---

## 横切: Meta Cognitive (设计 5 组件)

| 组件 | 代码存在 | 实际接入 | 说明 |
|------|:---:|:---:|------|
| MetaCognitionLayer | ✅ | ❌ | 代码完整但未触发 |
| AnnotationStore | ✅ | ✅ | V6 endpoint + engine 定期保存 |
| ReviewEngine | ✅ | ❌ | 代码存在未接入 |
| DriftDetector | ✅ | ❌ | 代码存在未接入 |
| SelfRepair | ✅ | ❌ | 代码存在未接入 |

**实现率: 20%**

---

## 横切: ABC Framework (设计 3 组件)

| 组件 | 代码存在 | 实际接入 | 说明 |
|------|:---:|:---:|------|
| Layer C 符号规则 | ✅ | ❌ | `neuro_symbolic.py` 完整但 `on_event` 未调用 |
| Layer B LLM规则 | ✅ | ❌ | `abc_orchestrator.py` 完整但未调用 |
| Layer A JSON默认 | ✅ | ❌ | 同上 |

**实现率: 0% (代码完备, 未接入)**

---

## 横切: Mind Space (设计 3 组件)

| 组件 | 代码存在 | 实际接入 | 说明 |
|------|:---:|:---:|------|
| UnifiedMind | ✅ | ❌ | `mind.py` 完整但未接入 on_event |
| InteractionGraph | ✅ | ⚠️ | 初始化了但未动态更新 |
| MindSpacePanel | ✅ | ✅ | 前端可视化 + V6 endpoint |

**实现率: 30%**

---

## 横切: Persistence (设计 4 组件)

| 组件 | 代码存在 | 实际接入 | 说明 |
|------|:---:|:---:|------|
| UnifiedStore | ✅ | ⚠️ | 代码存在, engine 调了 periodic save |
| AnnotationStore | ✅ | ✅ | 已集成 |
| CheckpointManager | ✅ | ✅ | `trigger_checkpoint()` 调用 |
| EventLog (JSONL) | ✅ | ✅ | `_event_log.put_event()` |

**实现率: 90%**

---

## 横切: Observability (设计 3 组件)

| 组件 | 代码存在 | 实际接入 | 说明 |
|------|:---:|:---:|------|
| InteractionMonitor | ✅ | ✅ | JSONL + HTML dashboard |
| SpanTracer | ✅ | ✅ | Waterfall |
| MetricsRegistry | ✅ | ⚠️ | 计数存在但未全面部署 |

**实现率: 85%**

---

## 汇总

```
                 代码存在    实际接入    实际实现率
Layer 0 PCR        25%         0%          0%
Layer 1 Intent     50%         0%          0%
Layer 1.5 Plan     50%         0%          0%
Layer 2 Context    95%        80%         76%
Discourse Tree    100%       100%        100%
Topic Tree         70%        40%         28%
Profile            80%        40%         32%
Behavior          100%        10%         10%
Association       100%         0%          0%
Engineering        75%        50%         38%
Meta Cognitive    100%        20%         20%
ABC Framework     100%         0%          0%
Mind              100%        30%         30%
Persistence       100%        90%         90%
Observability     100%        85%         85%
─────────────────────────────────
加权平均:         82%         28%         23%
```

---

## 核心问题

**代码写了 82%, 但只接了 28%。** 根本原因:

1. **`on_event` 太窄** — 只跑 adapters → context → LLM。60% 子系统从未触发
2. **Behavior/Meta/ABC 全是孤儿模块** — 代码完备但 `_update_behavior()`, `_update_meta()`, `_run_abc()` 被注释或从未调用
3. **TrackB 画像/OCEAN 从未更新** — ExecutionTrace 记录了 S/W/R 信号但未反馈给画像
4. **SubgraphCompiler 空转** — 代码完整但 LLM 调用从未用它按需扩展
5. **PCR/IntentParser 完全缺席** — 设计文档定义的 Layer 0-1 完全未实现

---

## 建议修复顺序

```
P0: on_event 补上缺失调用
    ├─ _update_profile(event)   ← 更新 TrackA/B
    ├─ _update_tree(event)      ← 行为发现 → PatternLearner
    ├─ _run_abc(event)          ← ABC 3层规则
    ├─ _update_meta(event)      ← 元认知审核
    └─ _update_mind(event)      ← Mind 关系学习

P1: SubgraphCompiler 接入 LLM
    └─ 按需扩展 → GatewayLLMProvider 加 context_entries

P2: PCR + IntentParser
    └─ 输入层噪声过滤 + 意图分类
```
