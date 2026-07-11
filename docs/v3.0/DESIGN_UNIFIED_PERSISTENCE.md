# Unified Graph Store: 通用图持久化层

> 替代现有只绑 TopicNode 的 GraphStore，支持所有域模型的统一存储。
> 参考 RAG 大小块设计 + JVM GC 分层模型。

> 版本: v1.0 | 日期: 2026-07-10

---

## 目录

1. 现状问题
2. 核心设计：通用节点 + 多粒度索引
3. 分层存储（GC 模型）
4. 水波检索扩展
5. 各域映射
6. 与现有设计的算法对应
7. 实现计划

## 1. 现状问题

当前 GraphStore 的 graph_nodes 表只接受 TopicNode 类型。
DiscourseBlock(v2) / Artifact / KnowledgeNode / BehaviorEdge / CausalEdge / UserProfile —— 
全部没有持久化，进程退出即丢失。

根本问题：存储层知道节点的具体类型。应该反过来——存储层不知道类型，
只提供通用行，类型信息作为一行字段。

## 2. 核心设计：通用节点 + 多粒度索引

### 2.1 通用节点表

`
graph_nodes {
  node_id TEXT PRIMARY KEY,
  node_type TEXT NOT NULL,      -- topic_block / artifact / constraint / behavior / causal / profile
  domain TEXT NOT NULL,          -- T / E / B / K / P (对应 ContextCompiler 的五域)
  session_id TEXT,               -- 所属会话（可空，跨会话的节点为 NULL）
  data JSON NOT NULL,            -- 节点数据，自由格式
  summary TEXT,                   -- L1 摘要（节点级，~2句）
  l2_summary TEXT,                -- L2 摘要（话题级，LLM 生成）
  activation_count INT DEFAULT 0, -- 电容模型：每访问+1
  importance REAL DEFAULT 0.0,    -- 结构重要性（betweenness-based）
  tier TEXT DEFAULT H,           -- H/W/C/A: Hot/Warm/Cold/Archive
  source_events TEXT,             -- 创建此节点的原始 Event ID 列表（JSON数组）
  created_at TIMESTAMP,
  updated_at TIMESTAMP
}
`

### 2.2 多粒度索引（RAG 大小块）

每个节点有三种检索粒度：

| 粒度 | 存储字段 | 用途 | 召回场景 |
|:---|:---|:---|:---|
| 全文 (Full) | data | 精确事实检索 | 需要节点的完整内容 |
| 摘要 (Coarse) | summary | 话题级浏览 | 快速了解这个话题在讲什么 |
| 极简 (Tiny) | l2_summary | 跨会话概览 | 搜索长历史时先看标题，再决定是否加载全文 |

这和 RAG 的大小块策略一致：粗粒度摘要用于快速扫描和过滤，细粒度全文用于精确召回。

## 3. 分层存储（JVM GC 模型）

每个节点有 tier 字段，四级分层。分层决策基于 activation_count + importance。

| 层 | 存储位置 | 保留内容 | 访问延迟 | 升级条件 | 降级条件 |
|:---|:---|:---|:---|:---|:---|
| H (Hot) | Python dict 内存 | 完整 data + summary + l2_summary | <1ms | — | activation_count 连续10轮=0 |
| W (Warm) | SQLite graph_nodes | 完整 data + summary + l2_summary | <10ms | 被跨会话检索命中 | importance < 0.3 且 activation < 5 |
| C (Cold) | SQLite + 压缩 l2_summary | summary + l2_summary + 索引, data 移除 | <50ms | 被跨会话检索命中 | importance < 0.1 |
| A (Archive) | 压缩 JSONL 磁盘归档 | 仅 node_id + l2_summary + source_events | <500ms | 手动触发回升 | 永久不活跃 |

GC 触发条件：
- tier=H 的节点数超过阈值（默认1000）→ 降级最不活跃的到 W
- 定期扫描（每小时）：importance < 0.3 的 W 降级到 C
- C 节点保留索引（node_id + summary + source_events）——足够让 WaveQuery 检索到。
如果需要全文，从 Archive 回升（类似 JVM Full GC 时的 object promotion）。

## 4. 水波检索扩展

WaveQuery 从只支持 TopicNode 扩展到支持通用节点：

`
wave_from_node(anchor_id, max_depth=3,
               domain_filter=[E, B],    -- 限定域
               tier_filter=[H, W],       -- 只查热/温层
               granularity=coarse)       -- 先用摘要快速扫描
`

检索策略借鉴 RAG 两阶段：
1. Coarse scan: 用 summary/l2_summary 字段做快速关键词/embedding 匹配 → 候选集
2. Full recall: 对候选集中的节点，从 data 字段加载完整内容 → 精确回答

## 5. 各域映射

| 域 | 现有模型 | node_type | 存储内容 | 粒度策略 |
|:---|:---|:---|:---|:---|
| T (对话树) | DiscourseBlock | topic_block | 话语文本+意图+实体 | summary=话题摘要, l2_summary=LLM生成 |
| E (工程链) | Artifact | artifact | 名称+类型+状态 | summary=模块名+状态摘要 |
| E (工程链) | KnowledgeNode | constraint/pattern/decision/quality/antipattern | 名称+描述+模板 | summary=规则摘要, l2_summary=模式简介 |
| B (行为链) | BehaviorEdge | behavior_edge | 操作类型+上下文+置信度 | summary=操作摘要 |
| K (因果链) | CausalEdge | causal_edge | 因果对+骨架+置信度 | summary=因果摘要 |
| P (用户画像) | ProfileDimension | profile_dim | 维度名+值+置信度 | summary=维度摘要 |

每个域的模型通过适配器转为通用 Node 存入 graph_nodes 表。
加载时通过 node_type 字段反序列化为正确的模型类。

## 6. 与现有设计的算法对应

| 设计中的算法 | 来源文档 | 在本层中的角色 |
|:---|:---|:---|
| 电容模型 (activation_count) | DESIGN_V4_CONTEXT_ENGINEERING.md | 节点访问计数，驱动分层升降 |
| 水波检索 (WaveQuery) | core/agent/persistence/wave_query.py | 多跳扩展检索 |
| 重要性评分 (importance) | DESIGN_V4_KNOWLEDGE_REFINEMENT.md | 结构/语义重要性，驱动 C→W 回升 |
| 分层策略 (Hot/Warm/Cold/Archive) | RFC_PARAMETER_REGISTRY.md | tier 升降规则 + 时间边界 |
| Patch Chain | DESIGN_V4_CONTEXT_ENGINEERING.md | 存储层的增量更新模型（Phase 2） |
| RAG 大小块 | 本文档借鉴 | Coarse scan → Full recall 两阶段检索 |

## 7. 实现计划

| 阶段 | 内容 | 预估 |
|:---|:---|:---|
| Phase 1 | UnifiedGraphStore（通用表+适配器）+ 工程链接入 | ~250 行 |
| Phase 2 | DiscourseBlock 接入 + 分层升降逻辑 | ~200 行 |
| Phase 3 | BehaviorGraph/CausalSubstrate/UserProfile 接入 | ~200 行 |
| Phase 4 | WaveQuery 扩展 + 两阶段检索 | ~150 行 |
| Phase 5 | Archive + Patch Chain | ~200 行 |

---

> 不再绑 TopicNode。所有域共用一张图，按粒度分层检索。

## 8. 三种强化检索模式

基于 RAG 17 种方案中三个未被 DialogMesh 覆盖的能力。

### 8.1 问题预生成

每个节点存入时自动生成 1-3 个潜在用户问题，存为 generated_questions 字段。
生成时机: Memory Compiler Checkpoint，与 L1 Summary 一起生成。
问题-问题匹配比问题-内容匹配更贴近用户自然提问方式。

### 8.2 HyDE (假设性文档嵌入)

用 LLM 先展开用户查询为假设答案，再用假设答案做语义检索。
用户查询 -> HyDE LLM(本地小模型) -> 假设答案 -> embedding -> 语义检索。
比原始查询有更丰富的语义锚点。与主检索并行，不增加端到端延迟。

WaveQuery 新增: hyde_expand: bool = False, hyde_model: str = local

### 8.3 混合检索 (语义 + 关键词双通路)

两条独立通路并行跑，各自返回 top-K，最后合并去重重排序。
通路 A (语义): embedding 余弦 -> top-10。擅长同义词和模糊表达。
通路 B (关键词): BM25/精确词匹配 -> top-10。擅长精确匹配专业术语。
合并: 去重 -> 语义 0.7 + 关键词 0.3 -> 重排序 -> top-10。

WaveQuery 新增: hybrid: bool = False, semantic_weight=0.7, keyword_weight=0.3

## 9. RAG 17 策略 x DialogMesh 映射

已覆盖 (绿色):
- 语义切分 -> TopicBoundaryDetector 六信号融合
- 上下文关联检索 -> DiscourseBlock cross_ref 指针
- 节点摘要生成 -> L1/L2 Summary
- 相邻切片扩展 -> WaterWave 水波激活 (锚点 + k 跳)
- 检索结果压缩 -> BudgetAllocator
- 知识图谱融合 -> Typed Edge + CausalSubstrate
- 分层索引 -> 话题树锚点定位 + 深度展开

本次新增 (红色 -> 绿色):
- 问题预生成 -> generated_questions 字段 (Section 8.1)
- HyDE -> hyde_expand 模式 (Section 8.2)
- 混合检索 -> hybrid 模式: 语义+关键词双通路 (Section 8.3)

部分覆盖 (黄色，后续迭代):
- 查询改写 -> CoreferenceResolver (刚设计)
- 回退提问 -> TopicTree 父话题回溯
- 子问题拆解 -> TaskPlanning (设计有，代码未实现)
- 重排序 -> ComplexityScorer
- 反馈闭环 -> BehaviorRewarder
- 检索前判断 -> IntentParser
- 检索质量校验 -> HallucinationDetector
- 大小块检索 -> 多粒度索引 (UnifiedGraphStore Section 2.2)

## 10. 性能优化：动态索引锚点 + 主干染色

### 10.1 问题

当前 2000 节点全表扫描 400ms，5 万节点预估 10s+。
瓶颈不在 SQLite——在水波检索遍历全表后逐条 Python 侧匹配。

### 10.2 动态索引锚点（Python 阶段）

本质：基于 activation_count 和 recency 的物化视图。

`
HotIndex: activation_count > 10 OR (now - updated_at) < 1h
WarmIndex: 其余所有节点
`

检索流程：先查 HotIndex（50-200 节点，<5ms），命中直接返回。
miss 回退 WarmIndex 全扫。99% 查询命中 HotIndex——用户最近几轮对话就是热点。

实现：SQLite partial index（WHERE activation_count > 10） + UnifiedSearch 加一条先查 hot 分支。约 30 行。

### 10.3 主干染色（Rust 阶段）

本质：图中心性预计算。五域节点形成自然簇：
- C 域（对话树）节点聚类在话题块附近
- E 域（工程链）节点聚类在 Constraint/Pattern 周围
- 跨域边（C→E, B→K）是簇间连接

`
预计算 Backbone（betweenness > 0.6 的边）：
  C_cluster ── E_cluster ── B_cluster ── K_cluster
      |                           |
  P_cluster ──────────────────────┘
`

检索从 O(depth^n) 降到 O(backbone_hops + cluster_size)：
- 先沿 Backbone 走跨簇边（5 跳以内）
- 进簇后在簇内做 BFS（簇大小 << 总节点数）

为什么 Python 不做：Backbone 重算每次需要全图 betweenness（O(N²)），写入频率 59/s 无法承受。
Rust 阶段用 petgraph 原生 betweenness + 后台线程异步重算。

### 10.4 收益预估

| 优化 | 5000 节点 | 50000 节点 | 实现代价 | 语言 |
|:---|:---|:---|:---|:---|
| 动态索引锚点 | 检索 5-10ms | 检索 10-30ms | ~30 行 SQL | Python |
| 主干染色 | — | 检索 10-50ms | ~200 行 + petgraph | Rust |
| 两者叠加 | — | 检索 2-5ms | — | Rust |