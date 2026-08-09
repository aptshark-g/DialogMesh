# 关联链（Association Chain）审计入口 — 2026-08-02

> 目的: 固化关联链审计启动前的全部基础信息（设计/实现/测试/断链实锤），作为深度审计的唯一入口。
> 恢复顺序: 读本文档 → 按 §8 规划推进 → 探针复现（§6.2）→ 设计↔实现对照。
> 相关交接: `docs/only/STATE_HANDOFF_20260802.md`（§八 P1#3 关联链 EDA 独立服务）。

---

## 1. 模块定位（来自设计 + 哲学公约）

- **关联链 = 所有关系的统一基座，双向引擎**（不是被动图数据库）: 五层漏斗 句法→补全→语义→信念→意图→时序→因果。
- **哲学定位**（`docs/only/wise/PARADIGM.md`）:
  - A22 因果哲学: 因果 = 约束空间里的稳定投射，不是世界固有属性；发现型三层（CausalSubstrate 骨架匹配 prior≤0.7 → do-calculus 负向 HARD_BLOCK → 键合图/Petri 确认）。
  - A23 因果检验哲学（学术三层，**设计空白未实现**）: 溯源置信 → 反事实推导 → 仿真检验。
  - 关联链是 10 条业务链之一，L4 时序是关联链 × 行为链 × 工程链三方交汇点。
- **执行层关系**（蓝图决策 §7.3）: 关联链/元认知 = 独立服务（防广播风暴，M→1 定向通道），P1 待做。
- **与 PCR 协同**: PCR 是第 3 层粗处理（zone 粗判），关联链 L3 语义意图可被 PCR 输出辅助；关联链给出凝练规则辅助 PCR。

---

## 2. 设计资产盘点（8 篇，全部已读）

| 文档 | 行数 | 核心内容 |
|------|-----|---------|
| `docs/BUSINESS_CHAIN_06_ASSOCIATION.md` | 260 | 五层漏斗全景 + 双向消费（对话树/画像/行为链/工程链/元认知/用户）；L5 伪因果 conf≥0.7 晋升、实因果人工标注 |
| `docs/v5/DESIGN_ASSOCIATION_CHAIN_L1_L4.md` | 191 | L1-L4 统一设计 + 前沿对标（Biaffine/OG-RAG/BLF/T-BN/HyperHawkes）；L4 四大组件；L5 待实现 |
| `docs/v5/DESIGN_UNIFIED_INTENT_ASSOCIATION.md` | 168 | Intent+Association 合并 3-Tier 管道（T0 结构 0.1ms / T1 BGE+SVO 1-5ms / T2 LLM 懒加载）|
| `docs/v5/ASSOCIATION_CHAIN_GAPS.md` | 3(长行) | 差距分析（内容截断，需重读全文）|
| `docs/v3.0/DESIGN_RELATION_SUBSTRATE.md` | 413 | RelationEdge 双正交维度（relation_kind × semantic_strength）+ Evidence 证据链 + 因果=解释层（conf>0.8 + ≥2 来源 + mechanism）|
| `docs/v3.0/ENGINEERING_V3_3_CAUSAL_SUBSTRATE.md` | 9(长行) | 因果基地: 8 元角色 + ~20 骨架 + 三步映射 + structural_prior ≤0.7 + DeltaAdjuster |
| `docs/v5/DESIGN_V4.0_COGNITIVE_COORDINATE_ROUTER.md` | 257 | 三维坐标（X 认知距离/Y 操作粒度/Z 反馈期望）+ 6-zone 路由 + 后验校准 |
| `docs/blog/chapter2_relation_over_prompt.md` | 576 | 关系哲学: Observation 5 域投影 → Hypothesis 7D 信念 → Knowledge → Skill；Context Engineering |

### 2.1 二级/交叉引用设计文档（关联链相关，第二轮查漏补入）

| 文档 | hits | 与关联链的关系 |
|------|:---:|----------------|
| `docs/COREFERENCE_HYBRID_DESIGN.md` | 13 | L1 指代消解混合设计（T1 Stanza + T2 语义 + T3 LLM 融合公式）——`llm_coref_verifier.py` 引用它 |
| `docs/v3.0/DESIGN_HYPOTHESIS_ENGINE.md` | 30 | Hypothesis Engine 设计（Match→Vote→Decay→Resolve）——L2.5 7D 信念的源头；`cognition/hub.py` 用它 |
| `docs/v3.0/design_layer0_pcr_and_layer1_intent_parser.md` | 28 | L1 意图解析（PCR + IntentParser 协同）——统一意图管道的前置设计 |
| `docs/v3.0/DESIGN_V3_1_BEHAVIOR_SUMMARY.md` | 27 | §2.5 约束补全编译器（HybridCompiler）——L1.5 认知补全的对应设计（BUSINESS_CHAIN_06 §2.2 引用）|
| `docs/v3.0/DESIGN_OBSERVATION_COMPILER.md` | 1+ | Observation Compiler（5 认知域投影）——关联链上游观察层 |
| `docs/v5/ENGINEERING_MULTI_INTENT_SPLIT.md` | 15 | 多意图切分（multi_intent_splitter 设计）——L3 意图的细分 |
| `docs/v5/DISCUSSION_PARALLEL_REUSE.md` | 19 | 并行复用讨论（快慢双通道）——L1.5/融合双轨设计依据 |
| `docs/v5/DESIGN_V4_COGNITIVE_INTEGRATION.md` | 8 | v4 认知集成——关联链与 13 模块的集成面 |
| `docs/v5/DESIGN_HYBRID_ARCHITECTURE.md` | 12 | 混合架构（算法+LLM）——关联链每层快慢通道的架构依据 |
| `docs/ARCHITECTURE_AUDIT.md` | 14 | 架构审计（关联链 L1.5/L2.5 未接入的早期记录）|
| `docs/DEEP_AUDIT_ROUND2.md` | 17 | 深度审计（含关联链）|
| `docs/COMPLETENESS_AUDIT.md` | 2 | 官方完整性审计（10 业务链，关联链=L1-L5 漏斗）|
| `docs/v5/FULL_MODULE_INVENTORY.md` + `MODULE_AUDIT_2026_07_24.md` | 5+5 | 模块清单/审计（官方统计 37 子系统）|
| `docs/v3.0/DESIGN_COMPETITOR_ABSORPTION.md` | 11 | 竞争吸收（A20 来源追溯）——因果溯源设计依据 |
| `docs/v3.0/THOUGHT_IMPRINT.md` | 2 | 因果哲学源头（约束空间投射、键合图 0.95 vs LLM 0.3-0.5）|
| `docs/OPENSOURCE_DEEP_READ.md` | 1 | entity_extractor gleaning 设计来源（GraphRAG 模式）|
| `docs/legacy/pcr_gap_assessment_v2_2.md` | 13 | PCR 差距（含关联链协同的早期评估）|
| `docs/v5/BUSINESS_FLOW_V6.md` | 9 | v6 业务流（关联链在完整流程中的位置）|

**关键设计要点（审计对照基准）**:
- RelationEdge 模型: `relation_kind`（structural/behavioral/temporal）× `semantic_strength`（association/reference/dependency/implementation）+ `predicate/inverse` + `evidence[]` + `mechanism`（因果解释层）。
- 置信度融合: `1 - ∏(1 - max_conf_per_source)`；创建>0.15、升级 dependency>0.7、因果 mechanism>0.8 且 ≥2 来源。
- L2.5 信念凝聚: 贝叶斯序贯 `P = prior + (1-prior)*likelihood*conf`，LOCK≥0.85，5 轮强制结晶，7D 信念（support/conflict/stability/coverage/recency/novelty/entropy）。
- L3 语用意图: 四视角投票（对话树/画像/关联/PCR），2v2 死锁 → LLM 裁决。
- L4 时序: IntentTransitionMatrix（T-BN）+ TemporalDialogGraph + 时间衰减 + IntentDriftDetector（JS 散度）。
- L5 因果: 伪因果自发现（conf≥0.7 多源）→ 用户确认 → 实因果；元认知发现矛盾 → 降级 L4 重验。

---

## 3. 实现资产盘点（`core/agent/association/` 24 文件 + 外围）

### 3.1 核心包（24 个 .py，约 3,300 行）

| 层 | 文件 | 行数 | 状态 |
|----|------|-----|------|
| 入口 | `association_funnel.py` | 418 | ✅ 旧漏斗 V2（LLM 假设生成+规则验证），被 assoc_subscriber 使用 |
| 入口 | `stage_manager.py` | 58 | ✅ 4 阶段合并（stage1-4 超时阈值）|
| 入口 | `fusion_engine.py` | 80 | ✅ FusionEngine（StageManager+ConflictResolver+GlobalWorkspace）|
| 入口 | `conflict_resolver.py` | 43 | ✅ 轨道优先级 + 冲突检测 |
| 入口 | `global_workspace.py` | 27 | ✅ 压抑计数 + 主导选择 |
| 入口 | `models.py` | 63 | ⚠️ `SkeletonMatch`/`CausalConstraints` 是 **stub**（断链根因）|
| L1 | `l1_modifier.py` | 135 | ✅ DepRelClassifier + ModifierExtractor（config 驱动）|
| L1 | `entity_extractor.py` | 171 | ✅ LLM gleaning 实体提取（GraphRAG 模式）|
| L1 | `pronoun_resolver.py` | 200 | ✅ Stanza 指代消解（zh 无 coref 模型 → 结构回退）|
| L1 | `semantic_coref.py` | 91 | ✅ sentence-transformers 语义指代（T2）|
| L1 | `hybrid_coref.py` | 133 | ✅ T1+T2+T3 融合指代（0.3/0.4/0.5 权重）|
| L1 | `llm_coref_verifier.py` | 166 | ✅ LLM 指代验证 + F1 评估（T3）|
| L1.5 | `l1_5_completer.py` | 304 | ✅ CollaborativeCompleter（syntax+LLM+consensus 融合）|
| L1.5 | `context_qualifier.py` | 87 | ✅ 依赖注入限定器（替代硬编码 depends_on）|
| L2 | `l2_config.py` | 27 | ✅ config/l2_config.json 加载器 |
| L2.5 | `l2_5_belief.py` | 285 | ✅ BayesianUpdater + BeliefAccumulator（7D + trace）|
| L3 | `l3_intent.py` | 217 | ✅ MultiPerspectiveValidator（4 视角 + LLM 死锁）|
| L4 | `l4_temporal.py` | 240 | ✅ L4TemporalEngine（转移矩阵 + JS 漂移 + LLM 协作）|
| L4 | `l4_collaborative.py` | 182 | ✅ L4CollaborativeEngine（算法→LLM→反馈闭环）|
| L5 | `causal_substrate.py` | 57 | ❌ **断链**（调 `m.to_prior()`，SkeletonMatch stub）|
| L5 | `skeleton_library.py` | 25 | ✅ 5 个骨架（设计说 ~20，只有 5）|
| L5 | `skeleton_matcher.py` | 76 | ❌ **断链**（`CausalConstraints(*mapped)` stub）|
| L5 | `delta_adjuster.py` | 30 | ✅ DeltaAdjuster（50 轮周期调 δ）|
| L5 | `meta_roles.py` | 12 | ✅ 8 元角色 DOMAIN_MAP |

### 3.2 外围实现（10 文件）

| 文件 | 行数 | 说明 |
|------|-----|------|
| `core/agent/assoc_subscriber.py` | ~80 | AssociationSubscriber（订阅 PCR/Route/Intent/Reply/Behavior 事件 → AssociationFunnel）|
| `core/agent/v4/assoc_subscriber.py` | ~80 | 几乎同上的副本 |
| `core/agent/causal/planner.py` | 470 | CausalPlanner（v4 adapter: BehaviorGraph + CausalSubstrate + CausalContextSource）|
| `core/agent/compiler/relation_substrate.py` | ~430 | RelationSubstrate（L2 语义本体，被 18 处引用）|
| `core/agent/compiler/topic_quick_match.py` | ~230 | TopicQuickMatcher（**SyntaxError**：`from __future__` 位置错误，line 8）|
| `core/agent/compiler/llm_relation_extractor.py` | ~250 | LLMRelationExtractor + RelationClusterer + OpenRelation |
| `core/agent/observation/surface_relation_extractor.py` | ~80 | 表层关系提取 |
| `core/agent/observation/tiered_relation_extractor.py` | ~160 | 分层关系提取 |
| `core/agent/storage/relation_graph.py` | ~220 | RelationGraph 存储 |
| `core/agent/v4/cognitive/belief_map.py` | ~200 | **另一个 BeliefAccumulator**（被 cognitive_bridge 注册为 "belief_map"）|
| `core/agent/v4/causal_substrate/adapter.py` | 184 | 双 CausalSubstrateAdapter 之一（RuntimeAdapter 版）|
| `core/agent/v4/causal_substrate/source.py` | 76 | ❌ **断链**（import 不存在的 `V4CausalSubstrate`）|
| `core/agent/behavior/causal_adapter.py` | ~200 | 双 CausalSubstrateAdapter 之二（ContextSource 版，bridge re-export 它）|

### 3.3 消费方/接线点（第二轮查漏补入）

| 消费方 | 位置 | 与关联链的关系 | 接线状态 |
|--------|------|----------------|---------|
| `cognition/hub.py` CognitionHub | `agent_native.py` + `bootstrap_v6.py` 使用 | 三合一: HypothesisPipeline + **BeliefAccumulator（L2.5）** + RelationClusterer | ⚠️ 真实接线（bootstrap 加载），但依赖 `hypothesis/pipeline.py` 存在 |
| `context/source.py:831` | ContextAssembler 内 | 又一个 CausalSubstrateAdapter（Lazy initializer）| ⚠️ 延迟 import，构造失败静默 |
| `event/subscribers.py:95` | wire_subscribers() | **第二个 AssociationSubscriber**（用 engine._l1_modifier + _l2_5_belief）| ❌ engine 无这两个属性（仅测试 dummy）→ 静默无操作 |
| `event/handlers.py:271` | register_pipeline_handlers() | ASSOCIATION Phase 预处理: pronoun resolution + context qualification（用 engine._pronoun_resolver + _context_qualifier）| ⚠️ CLI engine.py:162-163 注册了 lazy loader；runtime engine 未注册 → 两套 engine 不一致 |
| `event/cognitive_loop.py` | BehaviorLearner | 触发 `_causal_planner.slow_path()` | ❌ CausalPlanner **无 slow_path 方法**（只有 record_step/process_chain）→ AttributeError 被吞 |
| `event/storage.py` | SQLite WarmStore | `associations` 表 + insert_association() | ✅ 存储层就绪 |
| `do_calculus/` | `do_calculus.py` + validator | A22 负向验证（HARD_BLOCK），模型齐全 | ⚠️ 只被 `integration.py` 引用（integration 已断链）→ 实际无调用方 |
| `intent/` | dual_track / multi_perspective / multi_intent_splitter / ambiguity_bridge | L3 意图侧（多视角验证的产出/消费）| ⚠️ 需单独审计与关联链 L3 的关系 |
| `tiered/fusion.py` | TieredFusionEngine | 包装 association FusionEngine（Tier 0/1/2 渐进融合）| ⚠️ 代码在，调用方待查 |
| `hypothesis/` | pipeline.py + models.py | 7D 信念（CognitionHub 用）| ✅ 存在 |
| `v3_common/intent_parser.py` | service / mcp / cli registry / tools | 旧 IntentParser（3000 行 8 阶段）| ⚠️ 仍被 8 处引用（DESIGN_UNIFIED 说要改造未做）|
| `v4/unified_parser.py` | — | v4 统一解析 | ⚠️ 待确认 |
| `v4/cognitive/mind_relation.py` | — | Mind 关系（likes_relations → relation_substrate）| ⚠️ 引用 relation_substrate |
| `v4/cognitive/subgraph_compiler.py` | — | 子图消费 relation_substrate（world_provider.relation_substrate）| ⚠️ 需确认 world_provider 接线 |
| `memory/federated_index.py` | — | EntityNode from RelationSubstrate | ⚠️ 引用 |
| `execution/closure.py` | — | 标记 RelationSubstrate 因果边（learning closure）| ⚠️ 引用 |
| `state/interaction_graph.py` | — | 从 RelationSubstrate 动态构建 InteractionGraph | ⚠️ 引用 |
| `api/stubs_api.py` | — | `/relations` `/causal` `/belief` 端点（V6RelationsResponse）| ⚠️ 多为空壳（relations: [], substrates: 0）|

---

## 4. 配置资产

- `config/deprel_config.json`（2.2KB）: 39 项 deprel→role 映射 + modifier_roles + core_roles + relation_labels（零硬编码 ✅）
- `config/l2_config.json`（2.3KB）: L1.5 置信权重、BM25 探针阈值、L3 profile 阈值 + behavior_map、L2.5 likelihood_matrix（已在 config ✅，设计说待迁已完成）+ thresholds、LLM 调用参数
- `config/mood_profiles.yaml`: Z 轴情绪描述符（32 项，坐标路由用；工作区有未提交改动，需确认来源）
- `config/NRC-VAD-Lexicon-v2.1.txt`: Z 轴 fallback 词表（54k，英文，手动下载）

---

## 5. 测试现状（2026-08-02 实测）

### 5.1 关联链测试文件（`tests/`）

| 文件 | 测试数 | 状态 |
|------|:---:|------|
| `test_association_funnel.py` | 2 | ✅ passed（浅断言: 只 assert >0）|
| `test_l1_modifiers.py` | 4 | ✅ passed |
| `test_l1_5_completer.py` | 1 | ✅ passed |
| `test_l2_entity_graph.py` | 3 | ❌ **收集即挂**（topic_quick_match SyntaxError）|
| `test_l2_5_belief.py` | 3 | ✅ passed |
| `test_l3_intent.py` | 1 | ✅ passed |
| `test_multi_intent_split.py` | 2 | ✅ passed |
| `test_l4_temporal.py` | 0 | ⚠️ 无测试函数（只有脚本/数据）|

实测: 6 个文件 13 passed（9.35s）；`test_l2_entity_graph.py` 因 `core/agent/compiler/topic_quick_match.py:8` `from __future__ import annotations` 不在文件开头 → SyntaxError。

### 5.2 测试质量警示

- 现有断言多为 `> 0` / `llm_calls > 0` 类浅断言（"绿了不代表对"），无对抗性测试。
- L4 无测试；L5 因果基板无测试（且代码本身断链）。
- `v3_2/tests/test_fusion/*` 存在但未纳入本次运行（旧 fusion 指向 `core.agent.association.fusion_engine`，需要单独验证）。

### 5.3 旧版测试包（第二轮查漏补入，待验证）

| 测试 | 指向 | 风险 |
|------|------|------|
| `v3_2/tests/test_causal_substrate/test_core.py` | `core.agent.association.models`（stub）| ❌ 导入即挂（D8）|
| `v3_2/tests/test_fusion/*`（7 文件）| `core.agent.association.fusion_engine` + models | ⚠️ 若 models 部分字段变化会挂 |
| `v3_2/tests/test_do_calculus/test_do_calc.py` | `core.agent.do_calculus.*` | ⚠️ do-calculus 无调用方，测试孤立 |
| `runtime/tests/test_behavior_causal_integration.py` | bridge adapter（ContextSource 版）| ⚠️ 与 v4 RuntimeAdapter 版混用风险 |
| `compiler/tests/test_linkage_phase1.py` + `test_linkage_quality.py` + `test_semantic_world.py` | `compiler.relation_substrate` | ⚠️ RelationSubstrate 契约测试，需纳入 |
| `event/tests/test_subscribers.py` | AssociationSubscriber（dummy engine）| ⚠️ 只测 dummy 注入，未测真实 engine |

---

## 6. 断链与命名分裂（探针实锤，2026-08-02）

### 6.1 断链清单（4 处核心）

| # | 位置 | 断链 | 后果 |
|---|------|------|------|
| D1 | `association/skeleton_matcher.py:27` + `:76` | `CausalConstraints(*mapped)` / `SkeletonMatch(4位置参数)`，而 `models.py` 两者是 stub（无字段/无 __init__）| TypeError 运行时必炸 |
| D2 | `association/causal_substrate.py:24` | `m.to_prior()`（SkeletonMatch stub 无此方法）| AttributeError |
| D3 | `v4/causal_substrate/source.py:8` | `from core.agent.causal_substrate.adapter import V4CausalSubstrate`，不存在（只有 CausalSubstrateAdapter）| ImportError |
| D4 | `runtime/engine.py:431-433` | `self._l1_extractor` / `self._run_association_chain(...)` **方法不存在**（全库仅 1 处调用点）| AttributeError 被 try/except 吞 → **关联链冷路径从未运行**（静默降级，与 PCR/行为链同型）|
| D5 | `v3_2/causal_substrate/__init__.py:2-3` | `from core.agent.causal_substrate.adapter import CausalSubstrate`（adapter 只导出 CausalSubstrateAdapter）+ `from core.agent.causal_substrate.models import ...`（**顶层 models 不存在**）| ImportError；真正实现残留在 `v3_2/causal_substrate/models.py`（有 `to_prior` 的正确 dataclass）|
| D6 | `event/cognitive_loop.py` BehaviorLearner | `cp.slow_path()`（CausalPlanner 只有 record_step/process_chain，**无 slow_path**）| AttributeError 被 try/except 吞 → 学习闭环静默失效 |
| D7 | `event/subscribers.py:95` AssociationSubscriber | 依赖 `engine._l1_modifier` / `engine._l2_5_belief`（**只在测试 dummy 赋值**，生产 engine 无）| 静默无操作（`getattr` 返回 None → 直接 return）|
| D8 | `v3_2/tests/test_causal_substrate/test_core.py` | `from core.agent.association.models import SkeletonMatch, CausalConstraints`（stub）| 测试导入即挂（与 D1 同根因）|

探针输出原文:
```
[FAIL] skeleton_matcher.ConstraintExtractor.extract: TypeError: CausalConstraints() takes no arguments
[FAIL] causal_substrate.process_single: TypeError: CausalConstraints() takes no arguments
[FAIL] v4.causal_substrate.source: ImportError: cannot import name 'V4CausalSubstrate' from 'core.agent.causal_substrate.adapter'
[FAIL] runtime.engine.CognitiveRuntimeEngine._run_association_chain: (hasattr=False) 方法不存在
AgentPipeline lazy import failed: No module named 'core.agent.v3_2.integration'（顺带复现，integration 全断链）
```

### 6.2 三套并行实现（命名分裂）

1. **分层 L1-L5 实现**: `l1_modifier / l1_5_completer / l2_5_belief / l3_intent / l4_temporal / l4_collaborative`（对应 v5 设计，较新；被 `event/handlers.py` 的 ASSOCIATION Phase 部分消费）。
2. **旧漏斗 V2**: `association_funnel.py`（LLM 假设生成+规则验证）——**被 `assoc_subscriber.py` 使用**，但 assoc_subscriber 从未被 engine 实例化（D4）。
3. **`v4/cognitive/belief_map.py`**: 又一个 `BeliefAccumulator`（简单贝叶斯+EMA+持久化），被 `v4/cognitive_bridge.py` 注册为 "belief_map"（13 模块注册表，`cls.__new__(cls)` 兜底空壳）。
4. **`v3_2/causal_substrate/models.py` 残留实现**: 正确的 `CausalConstraints`/`SkeletonMatch`（带 `to_prior`）残留在 v3_2，顶层 `association/models.py` 反而是 stub（D1/D5）。

### 6.3 三处 CausalSubstrateAdapter（命名分裂 ×3）

- `behavior/causal_adapter.py` → `CausalSubstrateAdapter(ContextSource)`（旧，bridge `core/agent/causal_substrate/adapter.py` re-export 它；`runtime/engine.py` 走这条）
- `v4/causal_substrate/adapter.py` → `CausalSubstrateAdapter(RuntimeAdapter)`（新，`source.py` 想用它但断链 D3）
- `context/source.py:831` → 内联 `CausalSubstrateAdapter`（Lazy initializer，第三个同名类）

### 6.4 其他

- `core/agent/integration.py` 全部 `.behavior_graph.*` 旧路径 import（行为链审计已确认断链）→ `AgentPipeline` lazy import 静默失败。
- `pcr_router_v2.py` 对 association 只有 docstring 提及（无真实调用）——PCR 与关联链当前**零协同**。

---

## 7. 设计↔实现差距速览（初步）

| 设计点 | 实现状态 |
|--------|---------|
| L1 Stanza 依存 + 39 deprel config | ✅ `l1_modifier.py` + config |
| L1 指代消解（代词转换）| ✅ hybrid_coref（T1+T2+T3）|
| L1.5 快慢双通道补全 | ✅ `l1_5_completer.py`（但 nomic 走 127.0.0.1:1234 LM Studio，非统一网关）|
| L2 语义本体 RelationSubstrate | ✅ `compiler/relation_substrate.py`（18 处引用，但无关联链漏斗接线）|
| L2.5 贝叶斯+7D | ✅ `l2_5_belief.py`（likelihood 已迁 config）|
| L3 四视角投票 | ✅ `l3_intent.py` |
| L4 时序+漂移 | ✅ `l4_temporal.py` + `l4_collaborative.py`（无测试）|
| L5 因果基板 | ❌ 断链（D1/D2/D5），骨架库仅 5 个（设计 20），正确模型残留在 v3_2 |
| 因果解释层 mechanism（RelationSubstrate）| ⚠️ 模型有字段，无产出路径 |
| 因果检验三层（A23）| ❌ 设计空白（未实现）；do-calculus 实现存在但无调用方（integration 断链）|
| 双通道（快/慢）路由 | ❌ 无统一编排（stage_manager 只存在于 fusion_engine 内部）|
| 与行为链/工程链 L4 交汇 | ⚠️ 行为链 causal_adapter 在，工程链无接线 |
| 与 PCR 协同（zone→intent）| ❌ 零接线 |
| 用户可修改/标注（白盒）| ❌ 无 API/CLI 暴露 |
| 坐标路由（V4.0 三维）| ⚠️ 代码在（v4/classifier + mood_* + router_v4），未接入关联链 L3 |
| 统一意图管道（3-Tier）| ⚠️ 旧 IntentParser 仍被 8 处引用，Tier 改造未做 |

---

## 8. 审计规划（后续 4 步）

1. **盘点全景**（✅ 已完成两轮）: 设计 8+18 篇 ↔ 实现 24+13+18 消费方 ↔ 测试 8+6 包 ↔ 配置 2 个 ↔ 断链 D1-D8。本入口文档为最终索引。
2. **设计深度解读**: 五层漏斗 + RelationSubstrate 双正交维度 + 因果哲学（A22 发现型三层已落 CausalSubstrate+do-calculus；A23 检验型三层=设计空白）+ 二级文档（COREFERENCE/HYPOTHESIS/INTENT）逐节解读，输出 `DESIGN_DEEP_READ_ASSOCIATION_20260802.md`。
3. **实现深度审计**: 逐文件核查四套并行实现（分层 L1-L5 / 漏斗 V2 / v4 belief_map / v3_2 残留）的真实状态、断链根因链（D1-D8）、谁真正被接线（event_bus/CLI/engine/v4 bridge/CognitionHub）、测试质量（含旧测试包），输出 `ASSOCIATION_IMPL_AUDIT_20260802.md`。
4. **汇总 + 拍板点**: `ASSOCIATION_AUDIT_20260802.md`（设计↔实现对照 + P0/P1 修复清单 + 待拍板决策）。

### 待拍板点（审计后讨论）

- 三套实现如何归一（分层 L1-L5 vs 漏斗 V2 vs v4 belief_map）？
- （补充）第四套 `v3_2/causal_substrate/models.py` 残留实现如何处置：把正确 dataclass 迁回顶层替换 stub（D1/D5 的根修）？
- 关联链 EDA 独立服务（§7.3）与 D4 冷路径接线的先后？
- L5 因果基板是补 stub 复活，还是按 RelationSubstrate 因果解释层重构？
- 因果检验三层（A23）是否进入本次施工范围？
- 骨架库 5 → 20 是否补齐？
- do-calculus 实现已存在但零调用方：负向验证（HARD_BLOCK）接入哪条链路（行为链 weight updater / 子图 / 工程链）？
- 统一意图管道（旧 IntentParser 仍被 8 处引用）是否与关联链 L3 合并施工？
- `event/handlers.py` ASSOCIATION Phase 与 `runtime/engine.py` 冷路径（D4）双轨如何归一？

---

## 9. 复现命令

```powershell
# 探针脚本（断链复现）
@'
import sys
sys.path.insert(0, r'C:\Users\APTShark\PycharmProjects\DialogMesh')
def probe(label, fn):
    try:
        fn(); print(f'[OK]   {label}')
    except Exception as e:
        print(f'[FAIL] {label}: {type(e).__name__}: {e}')
def t1():
    from core.agent.association.skeleton_matcher import ConstraintExtractor
    class FakeOut:
        undefined = False
        slots = {'action': type('A', (), {'value': 'run'})()}
    ex = ConstraintExtractor(); ex.extract(FakeOut())
probe('skeleton_matcher.ConstraintExtractor.extract', t1)
def t2():
    from core.agent.association.causal_substrate import CausalSubstrate
    cs = CausalSubstrate(type('G', (), {'edges': {}, 'nodes': {}})())
    cs.process_single(type('O', (), {'undefined': False, 'slots': {'action': type('A', (), {'value': 'run'})()}})())
probe('causal_substrate.process_single', t2)
def t3():
    from core.agent.v4.causal_substrate.source import CausalSource
probe('v4.causal_substrate.source', t3)
def t4():
    import core.agent.runtime.engine as m
    print('has _run_association_chain:', hasattr(m.CognitiveRuntimeEngine, '_run_association_chain'))
probe('runtime.engine._run_association_chain', t4)
'@ | C:\Users\APTShark\anaconda3\python.exe -

# 关联链测试（注意 test_l2_entity_graph 收集挂）
$env:HF_HUB_OFFLINE='1'; $env:TRANSFORMERS_OFFLINE='1'
C:\Users\APTShark\anaconda3\python.exe -m pytest tests/test_association_funnel.py tests/test_l1_modifiers.py tests/test_l1_5_completer.py tests/test_l2_5_belief.py tests/test_l3_intent.py tests/test_multi_intent_split.py -q --tb=short
```

---

## 10. 参考链接（相关模块审计）

- 行为链: `docs/only/behavior/BEHAVIOR_DEEP_INVESTIGATION.md`（因果基板与行为链强耦合）
- 蓝图: `docs/only/blueprint/P0_RETRO_20260802.md`（§7.3 关联链 EDA 独立服务）
- 子图: `docs/only/subgraph/DESIGN_SUBGRAPH.md`（子图消费关联链意图）
- PCR: `docs/only/pcr/`（zone 粗判与关联链协同）

--- END OF DOCUMENT ---
