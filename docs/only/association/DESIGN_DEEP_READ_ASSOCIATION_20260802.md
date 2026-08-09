# 关联链设计深度解读 — 2026-08-02

> 目的: 全部关联链相关设计文稿精读后的逐层解读 + 设计间矛盾点 + 接口期望（为代码审计提供基准）。
> 范围: 核心 8 篇（入口文档 §2）+ 二级 18 篇（§2.1）全部精读。
> 前置: `docs/only/association/ASSOCIATION_AUDIT_ENTRY_20260802.md`（资产盘点 + 断链清单）。

---

## 1. 定位演变时间线（设计层面的演进）

| 时间 | 文档 | 关联链定位 |
|------|------|-----------|
| 07-05 | `THOUGHT_IMPRINT` | 行为推演树三链并行（行为/因果/关联在 TopicTreeNode 中并行）；因果=约束空间投射；BehaviorGraph 独立图引擎，TopicTreeNode 只存拓扑索引 |
| 07-12 | `DESIGN_HYPOTHESIS_ENGINE` | 共识形成系统（Match→Vote→Decay→Resolve），7D 信念，跨域共识冻结 Knowledge |
| 07-16 | `DESIGN_RELATION_SUBSTRATE` | 统一关系基座：五张平行图（ConceptGraph/BehaviorGraph/CausalSubstrate/KnowledgeSpace/SemanticObject）合并；**因果不是 type 是解释层** |
| 07-19 | `BUSINESS_CHAIN_06` | 五层漏斗（句法→补全→语义→信念→意图→时序→因果）+ 双向消费 |
| 07-21 | `DESIGN_UNIFIED_INTENT_ASSOCIATION` | IntentParser + Association 合并 3-Tier 管道（结构→语义→LLM）|
| 07-22 | `DESIGN_HYBRID_ARCHITECTURE` | Association = 广播风暴根源②（消费 6 链/产出影响 3+ 链）→ 冷路径 Event Sourcing 隔离 |
| 07-22 | `DISCUSSION_PARALLEL_REUSE` | PCR=关联链 L3 粗处理；IntentParser=关联链 L1-2 粗处理；P0 复用 |
| 07-23 | `DESIGN_ASSOCIATION_CHAIN_L1_L4` | L1-L4 完成 + 前沿对标（Biaffine/OG-RAG/BLF/T-BN/HyperHawkes）|
| 07-24 | `DESIGN_V4_COGNITIVE_INTEGRATION` | 6 桥接点（PCR→Ocean、Behavior→Pattern、Discourse→Memory、L4→BeliefMap、多信号→Fusion、Trigger→Meta）|
| 07-24 | `ENGINEERING_MULTI_INTENT_SPLIT` | 多意图拆分五链路（链路2=关联链），L3 从单意图验证扩展为拆分验证 |
| 07-31 | `ARCHITECTURE_AUDIT` | **重新定位：前置富化器**（切分前完成代词解析+上下文限定，修正"切分后运行只能修碎片"的错误）|
| 07-31 | `ARCHITECTURE_AUDIT` | 模型分层经验：7-30B 结构化提取最佳区间（L1/L2/L1.5）；70B+/Gateway 用于 L3 交叉验证 |
| 07-31 | `DEEP_AUDIT_ROUND2` | Batch 6 关联链 Phase 2 组件全真实工作；Batch 7 stanza zh 无 coref 模型（静默失败已修）|
| 08-02 | `BUSINESS_FLOW_V6`（参照） | 链06 状态=🟢 完成（设计态），路径四分类（Hot/Fast/Async/Slow/Tick）|

**核心结论**: 关联链经历了「独立因果链 → 五层漏斗 → 统一关系基座 → 前置富化器 + 冷路径微服务」四轮定位演变。最新的两轮（前置富化器、微服务隔离）尚未完全落到代码。

---

## 2. 五层漏斗逐层解读

### 2.1 L1 句法表层

- **设计**: Stanza 依存 + 39 deprel→role 映射 → SVO + 修饰语 context；用户不可见。
- **前沿**: Dependency Path Embedding + Biaffine Attention SRL。
- **演进**: v3 `ModifierExtractor`（接收 stanza Document）→ 被 **PronounResolver（新 L1）** 替代（DEEP_AUDIT Batch 6 明确"L1 旧实现是遗留契约，不修，标记遗留"）。
- **关键补充（ARCHITECTURE_AUDIT 前置富化器）**: L1 在切分**前**做 `resolve()`（代词→对象），产出 enriched_text 供 chunk 自包含。
- **关键修正（DEEP_AUDIT Batch 7）**: stanza 中文无 coref 模型 → 用 parse-only pipeline（tokenize,pos,lemma,depparse）+ PRON→最近前序 NOUN/PROPN 结构降级。已修复到 `pronoun_resolver.py`。
- **接口期望**: `resolve(text, lang) -> enriched_text`；`recent_entities` 追踪。

### 2.2 L1.5 认知补全

- **设计**: 快通道（画像命中/上文继承/历史锚点 <5ms）+ 慢通道（轻量 LLM ~50ms）+ 兜底保留原文。
- **对应设计**: `DESIGN_V3_1_BEHAVIOR_SUMMARY §2.5` 约束补全编译器（HybridCompiler）。
- **HybridCompiler 核心哲学（THOUGHT_IMPRINT 判断 2/3）**: 
  - LLM 不做约束消解（注意力竞争导致弱约束压制），只做**粗切割**（语块语义角色标注 + 置信度）。
  - 规则不做全量消解（组合爆炸），只对 LLM 不确定维度（conf<0.75）**选择性深挖**。
  - 流式验证：LLM 流式输出时规则并行校验，硬冲突即时标记→输出完成后覆盖（不重跑）。
  - 二合一 vs 纯 LLM：正确率高、token 省 35%（~700→~450/轮）。
- **降级路径**: 纯规则四步流水线（语法分解→约束激活→约束消解→稳定性评估），LLM 不可用时使用。
- **实现对照**: `l1_5_completer.py`（语法候选 + LLM 排序 + 共识融合）+ `context_qualifier.py`（依赖注入）。
- **模型分层**: 7-30B 最佳（ARCHITECTURE_AUDIT 实测结论），本地 LM Studio qwen2.5-7b。

### 2.3 L2 语义本体

- **设计**: RelationSubstrate 统一关系基座。RelationEdge 双正交维度（relation_kind × semantic_strength）+ RDF 方向（predicate/inverse/direction）+ 证据链（Evidence）+ 生命周期（ttl/decay）。
- **因果不是 type 是解释层**: `causal = high-confidence structural edge + mechanism explanation`（conf>0.8 + ≥2 不同来源 evidence + mechanism 非空）。
- **置信度融合**: `1 - ∏(1 - max_conf_per_source)`；阈值：创建>0.15、升级 association→reference>0.5（≥2 证据）、→dependency>0.7（≥1 文档/代码证据）、生成 mechanism>0.8。
- **检索**: BM25 + nomic 向量 + LLM 多源证据；1-2 hop entity_neighbors。
- **实现对照**: `compiler/relation_substrate.py`（V3 更新：LLM-native 开放类型取代硬编码 3×4 分类）。
- **StateGraph 整合（BUSINESS_FLOW_V6）**: 对话树 + 关联链 = 统一网状结构（block.entities→substrate.nodes、block.intent→belief_pool.posterior、block.cohesion→transition.weight）。

### 2.4 L2.5 信念凝聚

- **设计**: 贝叶斯序贯 `P = prior + (1-prior)*likelihood*conf`；LOCK≥0.85；5 轮强制结晶；7D 信念（support/conflict/stability/coverage/recency/novelty/entropy）；僵持（entropy>0.5）→LLM。
- **两套信念哲学并存（关键矛盾）**:
  - `DESIGN_HYPOTHESIS_ENGINE`（共识模型）: "Belief 不存现算"、"Evidence 只投离散票（Support/Conflict/Neutral）不产生浮点"、"置信度=共识度"、"Knowledge 冻结不可逆"；冻结条件 5 维 AND（support≥8, conflict≤3, stability≥0.70, coverage≥0.40, 共识域≥2）。
  - `BUSINESS_CHAIN_06` + `l2_5_belief.py`（贝叶斯连续模型）: 连续概率更新 + 阈值锁定。
  - **不一致**: 两个设计都叫"L2.5 信念凝聚"，但一个离散投票共识、一个连续贝叶斯。实现（l2_5_belief.py）是连续贝叶斯 + 7D 说明性字段；`hypothesis/` 包是离散 Match→Vote→Decay→Resolve。需要拍板归一方向。
- **多意图桥接**: `ambiguity_bridge.py`（死锁→L2.5 贝叶斯证据流）`ingest_ambiguity_evidence()`。

### 2.5 L3 语用意图

- **设计**: 四视角投票（对话树/画像/关联/PCR），3+ accept 或 2 accept 0 reject = 共识，2v2 死锁 → LLM 裁决（weight 0.5）。
- **演进**: 单意图验证 → **拆分方案验证**（ENGINEERING_MULTI_INTENT_SPLIT: `validate_split()` 输入 sub_intents list）。
- **多意图拆分五链路**（ENGINEERING_MULTI_INTENT_SPLIT）:
  - 链路1 画像 / 链路2 **关联链**（L1 modifier + L1.5 completer + L2 substrate + 行为模式）/ 链路3 话语 / 链路4 字面 / 链路5 工程（接口预留）。
  - 融合三策略: `vote_consensus`（std<0.3，0ms）/ `weighted_mix`（0.3≤std≤0.5，0ms）/ `llm_adjudicate`（std>0.5，100-300ms）。
  - PCR 调控: complexity>0.8 → 强制 LLM 裁决；noise>0.7 → literal 权重×1.5、discourse×0.7。
  - 歧义消解五级（成本升序）: 上下文继承（60-80%）→ 行为链推断（50-70%）→ 画像推断（40-60%）→ LLM（80-95%）→ ask_user（100%）。
- **PCR 协同（DISCUSSION_PARALLEL_REUSE）**: PCR expectation/cognitive_profile = L3 粗粒度版本，作为先验注入 FusionEngine。

### 2.6 L4 时序模式

- **设计**: T-BN 意图转移矩阵 + TemporalDialogGraph（角色+语义+时间戳）+ 时间衰减 `exp(-Δt/τ)` + IntentDriftDetector（JS 散度>0.3）。
- **三方交汇**: 关联链 × 行为链 × 工程链（BUSINESS_CHAIN_06 §2.6、PARADIGM A14 强绑定）。
- **LLM 协作（l4_collaborative 双轨）**: 算法→结构化 context→LLM 推理→修正（confirm/adjust threshold）→算法自适应；NOT 文本→LLM→文本→丢弃。
- **与 BeliefMap 桥接（V4_COGNITIVE_INTEGRATION Bridge 4）**: L4 转移矩阵+漂移 → belief_map 输入；belief 累积>0.85 → L4 transition 权重调整。
- **接口期望**: `record(transition)` / `predict_next()` / `check_drift()` / `collaborative_*`。

### 2.7 L5 因果链（三层递进）

- **发现型三层（A22，已设计+部分实现）**:
  1. 粗发现 — CausalSubstrate 8 元角色 + ~20 骨架 + 三步映射（NL→约束→候选→匹配度→structural_prior≤0.7）；离线预计算+在线只读缓存；行为链>10 步触发；δ 从 0.05 动态调。
  2. 负向验证 — do-calculus 后门准则 HARD_BLOCK（P(do(x))≥0.95→HARD_BLOCK，否则 WARN 降级）；**只验证不发现**。
  3. 深度确认 — 键合图/Petri网/系统动力学 离线分析，人工标注确认；晋升路径：伪因果→用户确认→实因果。
- **检验型三层（A23，设计空白）**: 溯源置信（来源决定可信度：键合图 0.95/人工 0.9/LLM 0.3-0.5）→ 反事实推导（Pearl 第三层：必要性/可逆性/部分干预）→ 仿真检验（matlab 动态验证）。
- **哲学边界（THOUGHT_IMPRINT）**: 因果=约束空间内稳定投射；structural_prior 永远说"稳定性"不说"必然性"（上限 0.7）；约束≠因果（约束满足是因果候选必要条件）；do-calculus 只做负向排除。
- **竞品吸收（COMPETITOR_ABSORPTION P2-8）**: MRAgent 因果发现管线简化版（LLM 扫描候选因果对→hypothesis 池→频次验证晋升），约 400 行，可先做频次版。

---

## 3. 前置富化器定位（2026-07-31 最重要的设计修正）

```
当前 (错误):
  raw → cut() → fragments → extract()
        ↑ 代词未解析          ↑ 事后补

修正:
  raw → resolve() → enriched → cut() → self-contained chunks
        ↑ L1 代词→对象  ↑ L2 加限定
```

**变换示例**: "auth模块要重构。它用JWT。token过期后需要刷新。"
- 阶段1 代词解析（L1 Modifier）→ `[auth模块]用JWT。[JWT token]过期后需要刷新。`
- 阶段2 上下文限定（L2 Belief）→ `[auth模块,依赖JWT]用JWT。[JWT token,需刷新机制]过期后需要刷新。`
- 阶段3 切分 → 每个 chunk 自包含，不丢信息。

**收益**: 切分不丢信息 / chunk 可独立消费 / 聚类压缩直接用丰富文本 / non-chunkable 跳过。
**对应基础设施**: L1 ModifierExtractor（resolve_pronouns）+ L2 BeliefAccumulator（qualify）+ L3 Validator（cross_check 限定质量）。

---

## 4. 混合架构与广播风暴（DESIGN_HYBRID_ARCHITECTURE）

- **问题边界**: 10 链中 8 条热路径（<10ms）不需要事件溯源；真正需要隔离的是 Meta 和 Association（广播风暴根源）。
  - Meta: 消费 8 链，产出影响 3+ 链。
  - **Association: 消费 6 链（PCR/Router/Intent/DiscourseTree/TopicTree/Behavior），产出影响 3+ 链（Context 追加 hidden_relation / LLM 增强 causal_chain / Behavior 学习 temporal_pattern）。**
- **方案**: 热路径直连（on_event 同步管道不变，链完成后 publish fire-and-forget）+ 冷路径 Event Sourcing（EventLog SQLite append-only + EventBus 环形缓冲 + Subscriber 增量拉取 from last_seq）。
- **一致性**: 写入单线程强一致 / 读取单调不重不丢 / 崩溃从 last_seq 重放 / 纠错删投射重放 / 反压丢最旧+计数。
- **与蓝图 §7.3 的关系**: 蓝图决策将关联链/元认知设为独立服务（M→1 定向通道），与本文档的冷路径 Event Sourcing 同源；P1 待做。

---

## 5. 核心数据模型汇总（跨文档）

| 模型 | 来源 | 关键字段 |
|------|------|---------|
| RelationEdge | RELATION_SUBSTRATE | identity/source/target/predicate/inverse/direction + relation_kind×semantic_strength + confidence + evidence[] + mechanism + ttl/decay_rate |
| Evidence | RELATION_SUBSTRATE | evidence_id/source(document·code·behavior·git·heading)/claim/confidence/predicate/raw_ref |
| BeliefState | HYPOTHESIS_ENGINE | support/conflict/novelty/stability/coverage/recency/entropy（离散投票）|
| HypothesisNode | HYPOTHESIS_ENGINE | statement/objects/topic/domain_signals/edges/status(active·merged·frozen·stale) |
| KnowledgeNode | HYPOTHESIS_ENGINE | belief_score 快照 + frozen_at（冻结不可逆）|
| ObservationBundle | OBSERVATION_COMPILER | 1:1 Event + domain_observations（5+1 域: engineering/behavior/dialogue/memory/user/causal）|
| Interpretation | OBSERVATION_COMPILER | 同域候选（competing_with 显式互斥），无 confidence（竞争交给 Hypothesis Engine）|
| SubIntent | MULTI_INTENT_SPLIT | text/category/entities/chain_votes/ambiguity_score/needs_clarification/dependencies |
| IntentContext | PCR LAYER0 | expectation/noise/complexity/cognitive_profile + 派生策略（execution_mode/thresholds/prompt_style）|
| IntentTransition | L1_L4 §L4 | from/to/turn/confidence（T-BN 转移矩阵）|
| CausalConstraints | CAUSAL_SUBSTRATE | domain_hint/has_feedback/involves_dissipation/involves_storage/causal_direction/involves_transformation |
| SkeletonMatch | CAUSAL_SUBSTRATE | roles/coverage/score/is_multi + to_prior()（score>0.8→0.7, >0.5→0.3, else 0）|

---

## 6. 设计间矛盾/张力点（需拍板）

### 张力 1: 两套 L2.5 信念哲学
离散投票共识（HYPOTHESIS_ENGINE）vs 连续贝叶斯（BUSINESS_CHAIN_06/l2_5_belief.py）。
- 共同点：7D 字段、冻结/锁定阈值、LLM 僵持触发。
- 分歧：Evidence 投离散票还是算后验概率；belief_score 是导出函数还是字段。
- 影响：`hypothesis/` 包（742L MatchVote+DecayResolve+Pipeline）与 `association/l2_5_belief.py`（285L）是两套实现，且 `cognition/hub.py` 同时引用两者。

### 张力 2: 快慢双通道 vs 五层漏斗的顺序
- 漏斗是 L1→L1.5→L2→L2.5→L3→L4→L5 线性递进。
- 前置富化器要求 L1/L2 在切分前完成（管线顺序调整）。
- 快慢双通道（HOT/Fast/Async/Slow/Tick 五路径）要求 L1.5 异步、L5 慢路径。
- 需明确: 哪些层同步必需、哪些层可异步后补（用户之前拍板：PCR 给粗切分，关联链在 LLM 回答期间做细切分——与前置富化器+异步路径一致）。

### 张力 3: 因果的"解释层"（RelationSubstrate）vs "基板"（CausalSubstrate）
- RELATION_SUBSTRATE: 因果 = mechanism 解释层（conf>0.8 + ≥2 来源），废弃 CausalSubstrate。
- CAUSAL_SUBSTRATE 工程: 8 元角色三步映射 structural_prior（≤0.7），作为 BehaviorEdge.δ 权重项。
- 两者不是互斥：基板产 structural_prior（先验），解释层产 mechanism（可解释性）。但代码里 `association/causal_substrate.py` 断链（D1/D2），`models.py` stub 未承接任何一版。

### 张力 4: 统一意图管道（3-Tier）vs 多意图拆分（五链路）
- UNIFIED_INTENT: T0 结构→T1 BGE/SVO→T2 LLM，线性管道。
- MULTI_INTENT_SPLIT: 五链路并行 + 三策略融合 + 歧义门控。
- 关系：3-Tier 是意图分类的纵向分层，五链路是拆分验证的横向并行；两者都需要接入（链路2=关联链本身）。

### 张力 5: 关联链是"漏斗"还是"服务"
- BUSINESS_CHAIN_06: 五层漏斗（数据流）。
- HYBRID_ARCHITECTURE/BLUEPRINT §7.3: 独立服务/冷路径微服务（防广播风暴）。
- 漏斗是内部结构，服务是部署形态——不矛盾，但代码目前既没实现完整漏斗流水，也没实现服务隔离。

---

## 7. 设计对实现的接口期望（代码审计基准）

| 层 | 期望接口 | 实现文件 | 状态 |
|----|---------|---------|------|
| L1 | `resolve(text, lang)->enriched` + `recent_entities` | pronoun_resolver.py | ✅（Batch 7 已修 zh 降级）|
| L1 | `classify(deprel)` + `extract(stanza_doc)`（旧契约，遗留）| l1_modifier.py | ⚠️ 遗留标记 |
| L1 | T1+T2+T3 融合 `resolve()->CorefResult` | hybrid_coref.py | ✅ |
| L1.5 | `complete(text, modifier_context, entity_clusters)->CompletionResult` | l1_5_completer.py | ✅ |
| L1.5 | `qualify(enriched_text, entities)->text`（依赖注入）| context_qualifier.py | ✅ |
| L2 | `add_conversation_edge` / `query` / 证据融合 / mechanism | compiler/relation_substrate.py | ⚠️ 无产出路径 |
| L2.5 | `ingest(evidence)` / `status()` / `needs_llm()` / `ingest_ambiguity_evidence` | l2_5_belief.py | ✅ |
| L3 | `validate()` 四视角 + LLM 死锁；扩展 `validate_split()` | l3_intent.py | ⚠️ 无 validate_split |
| L3 | 五链路并行验证 + FusionDecider + AmbiguityGate/Resolver | intent/multi_intent_splitter.py 等 | ⚠️ 文件存在待核 |
| L4 | `record/predict_next/check_drift` + `collaborative_*` | l4_temporal.py + l4_collaborative.py | ✅（无测试）|
| L5 | CausalSubstrate 三步映射 → structural_prior ≤0.7 | causal_substrate.py + skeleton_* | ❌ 断链 D1/D2/D5 |
| L5 | do-calculus 后门准则 HARD_BLOCK（负向验证）| do_calculus/* | ⚠️ 实现存在无调用方 |
| 冷路径 | AssociationSubscriber（EventLog 增量拉取 + 触发发现）| assoc_subscriber.py | ❌ D4 从未实例化 |
| 前置富化 | resolve→enriched→cut 管线顺序 | event/handlers.py ASSOCIATION Phase | ⚠️ engine 无 _pronoun_resolver |
| 融合 | 分阶段（10ms→80ms→150ms）+ 全局工作空间 | fusion_engine.py + stage_manager + global_workspace | ⚠️ 调用方待查 |

---

## 8. 设计层面的质量评价（诚实评估）

**强项**:
- 关系建模成熟：双正交维度 + 证据链 + 因果解释层的分层（RelationSubstrate v2 修正了 v1 把 causal 当 type 的错误）。
- 哲学→参数映射清晰：约束稳定性→structural_prior≤0.7；纠错即训练→奖励双倍惩罚；先信任规则→δ 从 0.05 起。
- 前沿对标扎实（L1-L4 每层都有论文/开源参照），且不是照搬——BLF/T-BN 等都落到具体组件。
- 前置富化器修正是真实的架构改进（切分前消解 vs 切分后补）。
- 广播风暴分析精确到"消费几条链/影响几条链"。

**弱点/风险**:
- 设计文档严重碎片化：同一主题（信念、因果、意图）多文档并行，存在张力 1-5 未收敛（39 篇设计仅 23% 被业务链引用）。
- 新旧契约并存：L1 两代、BeliefAccumulator 两套、CausalSubstrate 两版、AssociationSubscriber 两处。
- 因果检验三层（A23）明确是"设计空白"——PARADIGM 已标注。
- 多意图拆分设计完整（7-12 天估算）但依赖工程链/画像/行为链查询接口（部分未实现）。
- 混合架构（Event Sourcing）与蓝图执行层（混合式 DAG+事件）需要对齐，避免两套"冷路径"。

---

## 9. 待拍板设计决策（合并入口文档 §8）

1. L2.5 信念哲学归一：离散投票共识（HYPOTHESIS_ENGINE）还是连续贝叶斯（BUSINESS_CHAIN_06）？或混合（贝叶斯核 + 7D 可解释 + trace）？
2. L5 因果实现路线：复活基板（补 models 非 stub + 三步映射）还是按 RelationSubstrate 解释层（mechanism 产出）还是两者衔接（基板产 prior、解释层产 mechanism）？
3. 前置富化器管线的接入位置：`event/handlers.py` ASSOCIATION Phase vs `runtime/engine.py` 冷路径（D4）——需要二选一或统一。
4. 多意图拆分（五链路）是否作为 L3 的正式扩展进入施工（依赖工程链/画像接口）？
5. 因果检验三层（A23）本次是否立项（至少溯源置信层）？
6. 微服务隔离（冷路径 Event Sourcing）与蓝图混合执行的边界如何对齐？

---

## 10. 参考文档清单（本次精读 26 篇）

核心 8 篇 + 二级 18 篇，全部列于 `ASSOCIATION_AUDIT_ENTRY_20260802.md` §2/§2.1。本解读新增深度引用：
- `ARCHITECTURE_AUDIT.md` §AssociationChain 前置富化器 + 模型分层（2026-07-31 讨论）
- `DEEP_AUDIT_ROUND2.md` Batch 6/7（关联链 Phase 2 真实工作 + stanza zh coref 根因）
- `BUSINESS_FLOW_V6.md`（链06 状态 + StateGraph 网状结构 + 路径四分类）
- `THOUGHT_IMPRINT.md`（因果/约束补全/分阶段融合/δ 的哲学源头）

--- END OF DOCUMENT ---
