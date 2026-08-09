# 未对应设计文档批量精读 · 批 3 — 推理 / 知识

> 日期: 2026-08-03 | 批次: 3/8 | 状态: 已读完（5 文档全文精读）

---

## 1. DESIGN_SEMANTIC_OBJECT.md（v3.0, 486 行）— v4 统一对象模型

**核心命题**: SemanticObject 是**纯数据对象**，ObjectRuntime 负责行为——数据和行为分离。
旧假设（ConceptNode = 标签+文本容器，数据行为混在一起）→ 新假设（SemanticObject =
identity + composition + projections + relations 纯数据；render 是 ObjectRuntime 的行为）。

**三段设计的关系**:
```
DESIGN_PERSPECTIVE_PLANNER → 怎么看（视角决策，决策层）
DESIGN_SEMANTIC_OBJECT     → 世界的基本单位是什么（对象模型，数据层）
DESIGN_SEMANTIC_WORLD_MODEL → 世界是什么（全局模型，全局层）
```

**对象操作系统**: Graph 时代（A→BFS→Node）→ Object Runtime 时代
（Runtime→Perspective→LOD→ProjectionResolver→ContentProvider→Context）。
"这不是 RAG 改进，这是对象运行时。"

**SemanticObject 数据模型**: identity/name/composition_edges（7 类型: contains/pipeline/
phase/owns/implements/strategy/refines）/ projection_resolvers（存 Resolver 注册名非内容）/
semantic_path（物理→语义坐标）/ relations。LOD（连续细节层次 1.0-4.0: level/token_budget/
strategy，from_horizon）。

**ProjectionResolver（分离式投影）三要素**: ① 注册式解析器（不存内容，注册中心函数）
② ContentProvider 隔离存储（Resolver 不知 Pool/CodeGraph/KnowledgeSpace）③ resolve(view)
接受 view 参数（同对象可返 summary/detail/history 不同视图）。Skill 挂在对象的
skill_projection 上（不再悬空）。

**ObjectRuntime 接口**: render（perspective 决定激活投影 + LOD 决定展开深度，LOD≥2 展开
composition，≥3 展开 relations）/ zoom（重定位+渲染）/ navigate（composition 定位子对象）。
Perspective→view 映射: architecture→definition / execution→detail / engineering→full /
evolution→history。

**Phase A 实现路线**: Step1 数据模型(100行) → Step2 ContentProvider(80行) → Step3
ProjectionResolver(100行) → Step4 ObjectRuntime(100行)。原则: 数据无渲染逻辑 / 行为不碰存储。

**冲突登记（暂不裁决）**:
- 与 v6 /objects 端点（已存在）: 语义对象 API 有实现但"纯数据 + 渲染分离"的对象模型
  未落地 → 半实现。
- 与子图/上下文表达哲学: 对象+投影（多视图）与子图编译（结构化上下文）是两条渲染路线，
  归属与分工待统一。

---

## 2. DESIGN_GRAPH_FALLBACK.md（v3.0, 86 行）— 大规模检索的锚点优先策略

**问题**: `_build_bge_index` 对 10,477 对象全量点积 O(N×512)=5M 次浮点，百万节点不可行。

**方案: Anchor-First, Graph-Second** 四级降级链:
```
Tier 1: LSH bucket hash（O(k×bands)≈64ops）→ 100 候选
Tier 2: HNSW 近似 NN（O(log N)≈14 hops）→ 50 候选（BGE 向量可用时）
Tier 3: BFS 图扩展（RelationSubstrate 2 跳）→ +200 相关节点
Tier 4: BGE 精确打分（O(300×512)≈0.15M ops）→ 只在 ~300 子图上
复杂度: O(N) → O(log N + k×branch^depth)
```

**现有模块接线表**: compiler/lsh_index.py(114行) / persistence/hnsw_index.py(396行) /
persistence/hybrid_index.py(196行) / persistence/faiss_store.py(205行)——**全部已存在但未接入**；
relation_substrate 已接入 engine。

**Fallback degradation chain（4 级）**: BGE+缓存→HNSW→图→BGE / BGE 无缓存→LSH→图→BGE /
无 BGE→LSH→Jieba→图→子串 / 无图→LSH→Jieba→子串。

**冲突登记（暂不裁决）**:
- 与 L5 锚点定位+图扩散、子图混合 RAG 完全同构（同一机制三份设计）→ 归一归属待定。
- 与持久化审计（hnsw/faiss/milvus 依赖缺失）: 设计假设这些索引已接入，实际未接入。

---

## 3. DESIGN_V4_KNOWLEDGE_REFINEMENT.md（v3.0, 329 行）— 知识精炼与信念维护

**核心命题**: "知识在输入时产生"是错误假设（用户一句话可能属于多链，无唯一归属）→
五层替代三层。

**五层架构**:
```
Event IR（统一事件中间表示，不持久化，类比 LLVM IR）
  → Observation Pool（观察池，快速写入暂不解释，Observation 永远不删）
  → Knowledge Refinement（多解析器竞争解释）
  → Hypothesis Pool（贝叶斯信念更新）
  → Persistent Knowledge（最终持久化）
  → Skill Layer（蒸馏长期经验模板）
```

**Event IR**: id/kind（dialog.message/ui.drag/config.change/api.call 等固定大类）/
payload（完全动态，不预设 schema）/refs/metadata。**Vocabulary 替代 Schema**: Core（稳定
标签）+ Candidate（LLM 新创建待批准）+ Unknown Tag Pool——系统可成长不被 schema 锁死。

**Observation Pool 两条流水线**: 快速回复（Observation→直接参与上下文，不等精炼）+
后台精炼（多 Analyzer 慢消费→Hypothesis）。**Pull 不是 Push**——没有中央调度器，多个
Analyzer 像 Kafka 多 Consumer 竞争消费同一条 Observation。Observation 永远不删（Analyzer
会升级，删了没机会重新解释）。

**Knowledge Refinement（竞争解释权）**: 多个 Analyzer 同时消费同一条 Observation 各自生成
Hypothesis 竞争置信度。**LLM 只出现在 Hypothesis 生成阶段**；后续几千次信念更新全是算法
（LLM 放在概率图模型前端）。

**Hypothesis Pool 贝叶斯更新**: Observation 是证据，真相是 Hidden Variable；支持/反驳证据
加权 + 时间衰减；冷却分层（Hot 1天 1000 / Warm 1月 5000 / Cold 半年 100K / Archive 冻结）。

**Belief Update Engine（Git 式增量）**: 不全局重算，只重算受影响 Hypothesis（影响变更集 +
图传播）。理论基础: TMS（真值维护）/ Incremental View Maintenance / Belief Propagation。

**Skill Layer**: 不是手写 prompt，是从 Observation 蒸馏的稳定经验模板（类比 AlphaGo 保存
Policy 而非棋谱）。Skill 结构: prerequisite/preferred_order/required_constraints/
common_failures/references/lifecycle(draft/verified/core/deprecated)/confidence。

**冲突登记（暂不裁决）**:
- 与关联链 L2.5 信念（BeliefAccumulator）: 本文档的 Hypothesis Pool 是更完整的贝叶斯
  蓝图，与已实现的 L2.5 的关系（合并 or 分层）待统一。
- 与观察编译器（observation/ 活跃）: Observation Pool 概念已有实现（pool.py 4.5KB +
  document pipeline 喂入），但"多 Analyzer 竞争解释"（consumer_marks）未落地。
- "LLM 只在 Hypothesis 生成"与用户"算法与 LLM 糅合"哲学方向一致 → 待统一为
  神经符号协同规范。

---

## 4. DESIGN_NOISESPAN.md（v5, 269 行）— 局部噪声拓扑标记系统

**核心命题**: 替代 PCR v2.4 的全局 `noise_level: float`——全局标量丢信息（无法区分
"噪声高→拒绝"），改为 char 级局部标记 + 类型化处理。

**数据模型**: NoiseType（9 种: TYPO/AMBIGUOUS_ANAPHORA/JARGON_ABUSE/UNRELATED_FLUFF/
LOGICAL_LEAP/PROMPT_INJECTION_SUSPECT/CONTEXT_BREAK/STRUCTURAL/LEXICAL）+ NoiseSpan
（start_char/end_char/noise_type/severity/suggested_correction/reason/suppress）+
NoiseAssessment（spans + noise_level 降级聚合 + noise_source + 三维认知因子）。

**6 种噪声 × 下游处理**:
```
TYPO      → 链02 input_corrections 自动纠偏（实体提取前）
AMBIGUOUS → 链01 强制 CLARIFICATION（阻止 FAST_EXECUTE）
JARGON    → 链02 system_instruction 加 plain language
FLUFF     → 链02 剪枝不送 LLM 上下文
LEAP      → 链10 触发子图水波扩展补缺口
INJECTION → 链02 suppress + XML 转义隔离（<ignore>span</ignore>）
```

**检测算法**: TYPO（QWERTY 键盘距离 + 词频 + 中文字形/拼音相似）；模糊指代（强指代词
"这个/那个/它/刚才的" × 历史解析候选数）；注入攻击（9 个正则模式: 忽略指令/你现在是/
override 等）。

**三维认知刷新感知（v2.4 保留）**: 时间间隔 / 指代 / 描述方式——区分"认知刷新"与
"上下文断裂"。

**PCROutput_v1 修改**: v5.0 新字段 noise_assessment.spans[]；旧 noise_level 废弃但保留
兼容（旧代码 if noise_level>0.8: reject 仍工作；降级: 旧版 PCR 无 noise_assessment →
下游回退旧行为）。

**冲突登记（暂不裁决）**:
- 与 PCR 审计（坐标/zone 体系已定）: NoiseSpan 是 PCR 输出的扩展维度，与已定的
  zone/compass 体系的关系（新增字段 vs 独立信号）待统一。
- 与安全护栏（prompt injection）: INJECTION 检测的 9 个正则较初级，与 security/
  input_sanitizer 的职责边界待统一。

---

## 5. DESIGN_SEMANTIC_WORLD_MODEL.md（v3.0, 260 行）— 语义世界运行时

**范式转变**: RAG 范式（文本→Chunk→Embedding→Top-K→LLM）→ Semantic World Runtime
（现实输入→构建世界模型→对象化→关系化→多尺度观察→上下文编译→LLM 推理）。
"LLM 不直接面对信息碎片，而是通过一个可缩放的世界接口观察。"

**核心命题对照**:
```
信息 = 独立片段(Chunk)        → 信息 = 持续展开的结构实体(SemanticObject)
图上的 Node = 世界的 Object   → Node 是子图的入口，不是终点
检索 = 找到相关文本            → 渲染 = 构造适合当前问题的局部世界
Context = 拼接片段            → Context = 世界视图(World View)
```

**宏观架构**: 世界构建层（DocumentExtractor/CodeExtractor 预留/BehaviorRecorder →
Observation）→ 语义世界模型（SemanticObjectBuilder → SemanticObject + RelationSubstrate +
Projection System）→ RecursiveZoom + RelationQuery + WorldView。

**模块职责**: SemanticObject（是什么）/ RelationSubstrate（与其他东西什么关系: depends/
implements/produces/causes/follows）/ Projection（从哪个世界看: design/code/knowledge/
behavior/causal）/ RecursiveZoom（LOD 1-4 连续缩放）/ PerspectivePlanner（怎么看）/
ContextCompiler（压缩成 LLM 可读上下文）。

**运行时查询流程**: IntentParser(target=Runtime, world=design) → PerspectivePlanner →
SemanticIndex.locate → SemanticObject → RecursiveZoom(LOD=3) → RelationSubstrate.query →
Projection.resolve('design','definition') → ContextCompiler → Context IR（Level1 定义/
Level2 Composition/Level3 展开详情）→ LLM。

**RecursiveZoom**: LOD1 一句话摘要 → LOD2 子节点名称+定义段落 → LOD3 子节点概览+关系边 →
LOD4 更深（连续尺度，非离散层）。

**冲突登记（暂不裁决）**:
- 与子图审计（SubgraphCompiler 已实现 327 行水波扩散）: 本文档的 World View + RecursiveZoom
  是子图的上位概念 → 子图/世界模型/上下文三层关系待统一。
- 与 v4/world（42.7KB 活跃实现）: world/ 包已实现 schema/extractor/compiler/importance，
  本文档是其设计源 → 实现缺口 = ObjectRuntime/Projection 层未落地。

---

## 批 3 汇总（冲突登记清单，待哲学统一）

| # | 冲突点 | 涉及文档/审计 |
|---|--------|--------------|
| B3-1 | 对象+投影渲染 vs 子图编译（两条上下文渲染路线）| SEMANTIC_OBJECT + WORLD vs 子图审计 |
| B3-2 | 锚点检索机制三份设计（GRAPH_FALLBACK/L5/子图）| GRAPH_FALLBACK vs L5 + 子图 |
| B3-3 | Hypothesis Pool vs 关联链 L2.5 信念 | KNOWLEDGE_REFINEMENT vs 关联链 |
| B3-4 | 多 Analyzer 竞争解释（consumer_marks）未落地 | KNOWLEDGE_REFINEMENT vs observation 审计 |
| B3-5 | NoiseSpan 与 PCR zone/compass 体系的关系 | NOISESPAN vs PCR 审计 |
| B3-6 | INJECTION 检测 vs security/input_sanitizer 职责边界 | NOISESPAN vs 外围盘点 |
| B3-7 | World View+RecursiveZoom vs SubgraphCompiler 层级 | WORLD vs 子图审计 |
| B3-8 | ObjectRuntime/Projection 实现缺口（world/ 只实现数据层）| WORLD vs 外围盘点 |

