# 未对应设计文档批量精读 · 批 2 — 记忆 / 持久化

> 日期: 2026-08-03 | 批次: 2/8 | 状态: 已读完（4 文档全文精读）

---

## 1. DESIGN_XML_MEMORY_CARDS.md（v5, 237 行）— XML+JSON 混合结构化记忆卡

**核心主张**: 用 XML（非 JSON）做用户记忆的存储格式，理由是 LLM 对 XML 的天然理解优势。

**文献支撑**: Anthropic Claude 2024（function calling 用 `<function_results>`）/ XML-CLIP
2023（实体抽取精度比 JSON 高 12%）/ StructGPT 2023（多跳推理 +8%）/ LangChain XML Agent /
ReAct（推理链天然 XML 化）。

**卡格式**（Advanced Memory Card）: `<memory_card id type confidence>` 内含 person/
relationship/backstory/attributes/evidence/meta（temperature/information_value/version）。
XML vs JSON 四点优势: 层次可视化 / 属性与值分离 / 混合内容（内嵌标记）/ evidence 溯源嵌套。

**六种基础卡类型**:
```
person卡      ← ocean_profile, bfi_calibrator
preference卡  ← behavior_discovery
fact卡        ← EntityNode (compiler/relation_substrate)
event卡       ← DiscourseBlock + summary v3
plan卡        ← L4 temporal prediction (association/l4_temporal)
heuristic卡   ← HeuristicChain (cognitive/derivation_compressor)
```

**索引与检索**: MemoryCardIndex 四维（embedding HNSW 768d + 卡类型 + person + 温度×信息价值），
三步检索（向量候选 → 联邦索引过滤 → XML 层次精确匹配）。XML XPath-like 匹配天然支持
`//memory_card[type="event" and event/@category="health"]`。

**对比**: 优于 AI Agent Book（Advanced JSON，无消歧/温度/溯源）、MemGPT（flat text）。
DialogMesh 独有: 温度×信息价值 + LRU 自晋升 / evidence 溯源 / 片段替换更新 / 启发卡。

**实现路径**: Phase 1 XML 格式+序列化(200行) → Phase 2 LSMStore memory_cards CF+联邦索引
(150行) → Phase 3 LLM 生成记忆+冲突检测+证据链(200行)。

**冲突登记（暂不裁决）**:
- 与 memory/ 包（孤儿）关系: memory/xml_cards.py 8.8KB 存在但零消费；本文档是它的设计源。
- 与持久化审计（存储架构待拍板）: XML 卡 + LSMStore + HNSW 的具体落点未定。
- 表达哲学（子图文档已确立"复杂清晰用 XML / 关系用 JSON / 模糊用自然语言"）: 本文档
  与子图表达哲学一致（XML 用于复杂层次）→ 待统一为表达形式规范。

---

## 2. DESIGN_L5_LONG_TERM_MEMORY.md（v5, 203 行）— 压缩分治 + RAG 定位 + 启发凝练

**核心哲思**: "记忆不是存什么，是**什么时候用什么方式取**"。三层分治:
高频平庸 → 压缩成规则（DerivationCompressor）/ 低频高价值 → RAG 原样保留 / 思考过程 → 启发凝练。

**信息论二维决策矩阵**（高频 P>0.3 × 高价值 I>0.6）:
```
高频高价值 → 压缩成规则+快速索引（"诊断→修复 成功率0.85"）
低频高价值 → RAG 原样保留（密码/密钥/罕见 bug）——关键
高频低价值 → 强压缩/丢弃
低频低价值 → 仅索引
信息价值公式（已实现）: ThreeParadigmContext._information_value()
  = 0.3×entity_rarity + 0.35×intent_novelty + 0.35×action_deviation
文献: Shannon(信息论) / MemGPT / GraphRAG / HippoRAG / MemoRAG / Letta / AriGraph
```

**图+RAG 两层检索（锚点定位）**: RAG 语义检索定位 EntityNode 锚点 → 沿 RelationSubstrate
边水波扩散 2 跳召回"实际发生过关系"的实体（非语义近似）。纯 RAG 问题: 高维相似 ≠ 因果相关。
现有代码映射: RAG 层（hnsw_index/faiss_store/milvus_store + nomic 768d）+ 图层
（relation_substrate 454L / subgraph_compiler 327L / graph_store 472L）——需要连接：
`RAG检索 → 定位EntityNode → 图扩散 → 组装上下文`。

**规则验证闭环**: 聚类→归纳规则→逆推验证→失败→多视角调整（结构/语义/时序/反例四视角
——与 MultiPerspectiveAnalyzer 同构复用）。

**启发式凝练（元认知专属持久化）**: 不是存"用户做了什么"，是存"系统怎么想的"——
HeuristicChain（条件+反例+验证路径+置信度）是元认知的持久记忆。

**五区存储**: Hot（当前轮全文 dict）/ Working（DiscourseBlockTree SQLite 渐进摘要）/
Archived（RAG VectorDB 原样保留）/ Compressed（DerivationCompressor 规则 JSON）/
Meta-Cognitive（HeuristicChain Rust）。检索优先级: Working → Archived → Compressed → Meta。

**实现路径**: Phase 1 RAG+图连接(P0 200行) → Phase 2 压缩分治(P1 300行) → Phase 3 规则
验证闭环(P2 400行) → Phase 4 启发凝练(P2 200行) → Phase 5 Rust 迁移(P3)。

**冲突登记（暂不裁决）**:
- 五区存储 vs 持久化审计的"六套体系并存": 本文档是理想态，现状是 6 套并存 → 存储架构
  拍板（SQLite 拓展/redis/统一存储层）时需对照。
- 与 FactStore 批量写缺陷（已审计未修）: 高频写入路径设计未含批量写策略。
- "锚点定位+图扩散"与子图审计（混合 RAG 抓取）完全同构 → 子图/持久化共用一机制，
  归属待统一（子图 vs 持久化层）。

---

## 3. DESIGN_EVENT_SOURCING_CQRS.md（v5, 195 行）— Event Sourcing + CQRS 内核

**根本矛盾**: v4 EventBus 从未建造 → v5 状态分散 + v6 广播风暴都是并发症。有了 EventBus
作为唯一事件分发层，状态自然收敛，链间自然隔离。

**三个需求一起满足**: 隔离（独立读模型）/ 一致性（写侧强一致 append-only，读侧最终一致
延迟可控 <10ms）/ 并行（无依赖链并行投射）+ 审计回放 + 重放纠错。

**核心机制**:
```
EventLog: append-only SQLite，唯一真相源——所有链只写 EventLog 不直接改 DB
EventBus: 环形缓冲(1024) + 订阅分发，零背压（满则丢弃+标记，EventLog 可重放）
Projection: 每链独立读模型，catch_up 从 EventLog replay → _evolve 纯函数
```

**vs 微服务**: 10 链单进程场景下微服务网络开销反而更大；ES+CQRS 单进程内存分发+SQLite
持久化效率更高（单链写 ~0.5ms / 跨链查 <1ms / 故障恢复重放 <1s）。

**迁移路径**: 当前顺序管道（on_event 12 链）→ EventLog+EventBus+Subscribers 订阅链式
（PCR.subscribe(MESSAGE_RECEIVED)→publish(PCR_COMPUTED)→Router→Intent→Profile→Behavior→Meta），
6 步实施后删除 sequential on_event。

**冲突登记（暂不裁决）**:
- 与关联链 Phase 6（Event Sourcing 独立服务 M→1 定向通道）: 本文档是全量 ES+CQRS 蓝图，
  Phase 6 是首个落地切片 → 范围待拍板（全量迁移 vs 渐进切片）。
- 与蓝图 EventBus 真并行 vs DAG 直调讨论: 本文档主张 EventBus 为唯一分发层，与蓝图
  "混合式（EDA+DAG）"结论方向一致但细节（同步分发 vs 异步、背压策略）待统一。
- 与执行层审计 X1（NATS 无限重连）: 本文档的 EventBus 是进程内环形缓冲，与 NATS 的
  关系未定义（NATS 已存在但卡启动）。

---

## 4. DESIGN_UNIFIED_PERSISTENCE.md（v3.0, 235 行）— 通用图持久化层

**现状问题**: graph_nodes 表只接受 TopicNode；DiscourseBlock/Artifact/KnowledgeNode/
BehaviorEdge/CausalEdge/UserProfile 全部未持久化，进程退出即丢失。存储层知道具体类型
是根本问题——应反过来（存储层不知道类型，类型作为一行字段）。

**通用节点表**: node_id/node_type(topic_block/artifact/constraint/behavior/causal/profile)/
domain(T/E/B/K/P)/session_id/data JSON/summary(L1)/l2_summary(L2)/activation_count(电容)/
importance(betweenness)/tier(H/W/C/A)/source_events/时间戳。

**多粒度索引（RAG 大小块）**: Full(data 精确事实) / Coarse(summary 话题级浏览) /
Tiny(l2_summary 跨会话概览)。两阶段检索: Coarse scan → Full recall。

**分层存储（JVM GC 模型）**: H Hot(Python dict <1ms) → W Warm(SQLite <10ms) → C Cold(
SQLite 压缩 data 移除 <50ms) → A Archive(JSONL <500ms)。GC: H>1000 降级最不活跃 / 每小时
importance<0.3 的 W→C / C 保留索引可回升（类似 JVM Full GC object promotion）。

**水波检索扩展**: wave_from_node 支持通用节点 + domain_filter/tier_filter/granularity。

**各域映射**: T 对话树 DiscourseBlock / E 工程链 Artifact+KnowledgeNode / B 行为链
BehaviorEdge / K 因果链 CausalEdge / P 画像 ProfileDimension——适配器转通用 Node，
加载按 node_type 反序列化。

**算法对应**: 电容模型（DESIGN_V4_CONTEXT_ENGINEERING）/ 水波检索（wave_query.py）/
重要性（DESIGN_V4_KNOWLEDGE_REFINEMENT）/ 分层策略（RFC_PARAMETER_REGISTRY）/ Patch Chain /
RAG 大小块。

**三种强化检索**: 问题预生成（节点存入时生成 1-3 个潜在问题，问题-问题匹配更贴近提问）/
HyDE（假设性文档嵌入）/ 混合检索（语义+关键词双通路）。

**实现计划**: Phase 1 UnifiedGraphStore+工程链接入(250行) → Phase 2 DiscourseBlock+分层
(200行) → Phase 3 BehaviorGraph/CausalSubstrate/UserProfile(200行) → Phase 4 WaveQuery
扩展(150行) → Phase 5 Archive+Patch Chain(200行)。

**冲突登记（暂不裁决）**:
- 与持久化审计核心发现（6 套体系并存 / HNSW/Milvus/chromadb 依赖缺失 / ENGINEERING_
  PERSISTENCE 未落地）: 本文档是"统一图存储"蓝图，与 ENGINEERING_PERSISTENCE（57KB）
  并行存在 → 两套统一蓝图合一方向待拍板。
- 与 FactStore/SQLite 现状: 本文档的 H/W/C/A 分层与 SQLite 现状的差距（redis 热层讨论）
  → 存储架构拍板时对照。

---

## 批 2 汇总（冲突登记清单，待哲学统一）

| # | 冲突点 | 涉及文档/审计 |
|---|--------|--------------|
| B2-1 | XML 卡设计源 vs memory/ 孤儿实现（零消费）| XML_MEMORY_CARDS vs 外围盘点 |
| B2-2 | 五区/四区存储 vs 6 套体系并存 | L5 + UNIFIED vs 持久化审计 |
| B2-3 | 锚点定位+图扩散归属（子图 vs 持久化）| L5 vs 子图审计 |
| B2-4 | ES+CQRS 全量蓝图 vs 关联链 Phase 6 切片 | EVENT_SOURCING vs 关联链 |
| B2-5 | 进程内 EventBus vs NATS 基础设施 | EVENT_SOURCING vs 执行层 X1 |
| B2-6 | 统一图存储 vs ENGINEERING_PERSISTENCE 双蓝图 | UNIFIED vs persistence 审计 |
| B2-7 | FactStore 批量写缺陷在五区设计中的落点 | L5 vs profile 审计 |

