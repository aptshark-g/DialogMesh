# 历史设计点追踪 —— 吸收 / 等效 / 遗漏

> 2026-07-22 · 对照所有 BUSINESS_CHAIN + DESIGN 文档

---

## 一、已被吸收 (代码已实现)

| 设计点 | 首次出现 | 吸收位置 | 说明 |
|--------|---------|---------|------|
| PCR NoiseSpan | DESIGN_NOISESPAN.md | 设计文档完整, 代码未实现 | 拓扑标记替代标量噪声度 |
| PCR expectation | BUSINESS_CHAIN_00 | `pcr_router_v2.py` | V2 用 zone 替代 discrete labels |
| PCR LLM fallback | rule_based.py@old | `pcr_router_v2.py` LLM 注入 | Tier2 调用 |
| Intent Multi-Tier | DESIGN_MULTI_TIER_PIPELINE | `association_funnel.py` Layer1-5 | 5层漏斗覆盖了 Multi-Tier 意图 |
| Intent recursive convergence | BUSINESS_CHAIN_02_APPENDIX | `tiered/topic_matcher.py` | 递归收敛快匹配 |
| Planner SkillMatcher | BUSINESS_CHAIN_1.5 | `planner/skill_matcher.py` | ✅ |
| Planner 5 strategies | planner/models.py | `planner/planner.py` | RULE→TEMPLATE→HYBRID→LLM→RECOVERY |
| Context 6 sources | BUSINESS_CHAIN_02 | `context/source.py` | Knowledge/World/Skill/... |
| Discourse Cohesion 9D | DESIGN_DISCOURSE_BLOCK_TREE | `compiler/discourse_block_tree.py` | ✅ |
| Profile TrackB+OCEAN | DESIGN_COGNITIVE_PROFILE | `cognitive/profile.py` | ✅ |
| EventBus+EventLog | DESIGN_API_EVENT_LOG | `events/event_bus.py`, `api/api_event_log.py` | ✅ |
| Meta subscriber | DESIGN_HYBRID_ARCHITECTURE | `meta/meta_subscriber.py` | ✅ 8事件订阅 |
| Association 5-layer | BUSINESS_CHAIN_06 | `association/association_funnel.py` | ✅ LLM+规则 |
| Decider/State Machine | DESIGN_GLOBAL_STATE_MACHINE | `state/global_decider.py` | ✅ 12事件类型 |
| Hybrid Architecture | DESIGN_HYBRID_ARCHITECTURE | engine | 热路径直连+冷路径EventSourcing |
| V4.0 Router | DESIGN_V4.0_COGNITIVE_COORDINATE_ROUTER | `router/router_v4.py` | Y=StructuralFeatures, Z=BGE情绪 |
| StructuralFeatures | structural_classifier.py | `classifier/` | ✅ 零硬编码 |

---

## 二、已被等效替代 (用了不同方案达到相同目的)

| 原始设计 | 等效替代 | 原因 |
|---------|---------|------|
| PCR 离散标签 (TOOL/ADVISOR/COMPANION) | V4.0 6-zone 连续空间 | 标签泛化 |
| PCR 硬编码关键词列表 | StructuralFeatures 语法特征 | 零硬编码红线 |
| PCR hardcoded suggestions | LLM generate() 动态生成 | 不可硬编码建议 |
| Intent 独立 Parser | AssociationFunnel Layer 1-3 | 意图=关联浅层 |
| jieba SVO 提取 | stanza SVO (已装,离线) | 更精准 |
| stanza STC 依存解析 | StructuralFeatures 替代 | stanza 离线超时,CPU太重 |
| Multi-Tier Pipeline | 5-layer Funnel | 漏斗模型更通用 |
| FusionEngine track fusion | AssociationFunnel ingest | 同一机制不同粒度 |
| Emotion keyword matching | BGE mood_profiles.yaml 向量 | 泛化 |
| NRC-VAD lexicon | 已下载, BGE优先, VAD兜底 | 多层fallback |

---

## 三、设计存在但未实现

| 设计点 | 设计文档 | 代码状态 | 缺失内容 |
|--------|---------|:---:|------|
| **Unified Intent Pipeline** | BUSINESS_CHAIN_01_UNIFIED | ⚠️ 部分 | Tier0置信门控, Tier1 BGE向量 |
| **Subgraph 跨链通信** | BUSINESS_CHAIN_10 | ❌ 零 | Meta子图, Dialogue子图, LLM调用 |
| **Engineering 约束推理** | BUSINESS_CHAIN_07 | ❌ 未接入 | ConstraintEngine, RecursiveMap |
| **Topic Tree 分支切换** | BUSINESS_CHAIN_2.1 | ❌ 未完成 | fork/merge/switch/resume |
| **Topic Tree 双层摘要** | BUSINESS_CHAIN_2.1 | ❌ 未完成 | L1分支级 + L2跨分支 |
| **Planner Distillation** | BUSINESS_CHAIN_1.5 | ❌ 未触发 | 蒸馏引擎, Skill 提炼 |
| **PCR NoiseSpan 实现** | DESIGN_NOISESPAN | ❌ 未实现 | 拓扑标记输出 |
| **Cognitive Compiler** | DESIGN_COGNITIVE_COMPILER | ⚠️ 闲置 | 多域投影, Hypothesis竞争 |
| **Observation Compiler** | blog/chapter2 | ⚠️ 闲置 | 5域投影 (code有,未触发) |
| **Hypothesis Engine** | blog/chapter2 | ⚠️ 闲置 | 7维信念, 解释生态 |
| **Semantic World Model** | blog/chapter2 | ⚠️ 闲置 | 9种边, 社区检测, Backbone |
| **Skill Layer** | blog/chapter2 | ⚠️ 闲置 | Candidate→Verified Skill |
| **ABC Framework** | BUSINESS_CHAIN_REMAINING | ⚠️ 代码存在 | learn_from_feedback 空壳 |
| **Mind** | DESIGN_STATE_EVOLUTION | ⚠️ 代码存在 | 长期心智, Attention Prior |
| **Cold→Hot 回写** | DESIGN_HYBRID_ARCHITECTURE | ❌ 未实现 | Meta→Intent, Assoc→Context |
| **Slow Path checkpoint** | DESIGN_COGNITIVE_RUNTIME | ⚠️ 框架存在 | trigger_checkpoint 未触发业务 |
| **Deep Path distillation** | DESIGN_COGNITIVE_RUNTIME | ❌ 未实现 | 5 模式→Skill |
| **Soft Config 系统** | ENGIEERING_PCR | ⚠️ 部分 | mood_profiles.yaml, 未全量 |

---

## 四、设计文档中有但代码完全没涉及

| 概念 | 来源 | 说明 |
|------|------|------|
| Cognitive Workspace | DESIGN_COGNITIVE_WORKSPACE | 一次推理的工作空间 |
| Observer | DESIGN_COGNITIVE_RUNTIME | CPU类比, 调度资源 |
| ExecutionTrace | DESIGN_COGNITIVE_RUNTIME | trace→replay→debug→meta-learn |
| PerspectivePlanner | DESIGN_COGNITIVE_COMPILER | 多视角规划 |
| RelationSubstrate | DESIGN_RELATION_SUBSTRATE | 关系基底 |
| ColdIndexer | v3_2 | 冷数据索引 |
| Consolidation | v3_2 | 数据合并 |
| Do-Calculus | v3_2 | 因果推断 (Pearl) |
| FOA (Focus of Attention) | v3_2 | 注意力聚焦 |
| Predictor/Rewarder | v3_2 | 预测+奖励系统 |
| L1/L2 Summary | v3_2 | 双层摘要 |
| Parameter Registry | v3_2→un_use | 参数注册 |
