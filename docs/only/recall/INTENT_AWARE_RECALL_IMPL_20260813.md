# 意图感知召回 — 当前实现全景 + 设计对照（2026-08-13）

> 触发: 用户追问"我们的意图分析是怎么做的？是先语法树拆 SPO 然后进入
> 多意图拆解再合（类似 mapreduce）？还是实际上很粗糙？" — 需要一份
> **代码级事实描述**（不照设计文档背书）: 当前实现了什么、每项和设计
> 文档差多少。本文件 = 现状快照, 后续施工以此为准修订。
> 相关代码: core/agent/recall/recall_service.py（召回）
> core/agent/api/v3_session_api.py（意图分类 + task 轨 + 接线）
> core/agent/intent/*（意图拆分/验证副路径）
> 评测数据: docs/test/EVAL_100_RERANK_COMPARE_20260813.md

---

## 一、结论先行（诚实版）

1. **生产主路径的意图分析 = LLM 单标签分类, 不是语法树→SPO→多意图拆解→
   合并的 mapreduce**。一次 LLM 调用把整条消息归为 8 类固定意图集中的
   一个类别（`_GatewayLLMAdapter.classify_intent`, thinking 关闭）。
2. **SPO/语法树拆解在召回侧, 不在意图侧**（`recall_service._extract_spo`
   → SyntacticDecomposer, 用于约束投影对齐）。意图和 SPO 是两套独立机制。
3. 设计文档里的精密版（多意图拆分 → 5 链验证 → 融合 → 歧义门 → 冷路径
   多视角/信念/启发链蒸馏）**代码存在, 但 5 链里 4 条 abstain/pass,
   冷路径低频触发** — 形式在、实质薄。
4. 本轮（P1 第一批）把"意图"从死参数变成真实控制面: recall 按意图切换
   融合模式/重排权重/HyDE/扩散深度, A18 按意图独立反馈。评测: dialogue
   top1 69.2%→**76.9%**, doc top1 31.1%→**34.4%**, 任务规划意图
   38.9%→**55.6%**, 全意图无回退。

---

## 二、当前实现全景（代码级, 2026-08-13 快照）

### 2.1 意图分析

```
用户消息
  │
  ├─ 生产主路径（v3_session_api Phase 3.5, 每次消息都跑, ~1s）:
  │    _GatewayLLMAdapter.classify_intent(text)
  │      = deepseek-v4-flash 一次调用 → 8 类固定意图集中的一个标签
  │        记忆召回 | 任务规划 | 代码分析 | 数据搜索 | 因果推理
  │        | 通用讨论 | casual | 通用对话
  │      失败 → 降级 DualTrackIntentPipeline.process() 取 segments[0]
  │
  └─ 副路径（DualTrackIntentPipeline, 设计精密但非生产主路径）:
       热路径 MultiIntentSplitter.split():
         ① LLM 直接输出 {multi, segments}（不走语法树/SPO）
         ② 每个候选段过 5 链验证:
            literal（LLM 驱动, 有效）
            profile（无画像数据 → pass）
            association（无实体库 → pass）
            discourse（无历史 → pass）
            engineering（接口未接线 → 恒 pass）
         ③ FusionDecider: std<0.3 投票 / 0.3-0.45 加权 / >0.45 LLM 仲裁
         ④ AmbiguityGate: 熵/分歧/置信 → ask_user 升级
       冷路径（split_confidence<0.7 且每 3 次触发 1 次）:
         MultiPerspectiveAnalyzer → L2.5 信念 → DerivationCompressor
         蒸馏启发链回喂热路径
```

**2026-08-13 晚（意图副路径实质化, 本文件修订）**:
- **5 链数据源已接线**: DualTrackIntentPipeline 支持 resolver 形态动态
  数据源（profile=OCEAN 画像 / association=关联链状态快照 topic_shift/
  cohesion / discourse=话题列表）; 引擎 `_init_intent_runtime` 与 v3
  fallback 均已喂真实数据。profile/association 链从"恒 abstain"变为
  有信号可投票; engineering 链仍 abstain（接口未接, 诚实）。
- **多意图 segments 已消费**: 意图拆分段 → v3 API `_multi_segments` →
  recall(sub_queries=) 并行多路召回 → 蓝图 `intent_multi_recall` 模板
  （intent 节点 segments → statemachine 注入 recall_decompose.sub_queries）。
- **A18 持久化**: 置信度/重排权重覆盖落盘 learned_conf.json（重启不丢）;
  set_weight(intent, source, target="rerank") 白盒调权。

**真相（修订后）**: 生产意图 = LLM 单标签 + 多意图拆分段（消费于多路
召回）; 5 链验证实质从"只有 literal"变为"literal + profile + association
有真实信号, discourse 有历史, engineering 待接"。

### 2.2 召回链路（recall_service.RecallService.recall）

```
query + intent（W1 后半: 死参数变控制面）
  │
  ├─ 意图 profile 解析（INTENT_PROFILES）:
  │    融合模式（vector_primary / rerank）/ 重排权重 / HyDE 开关 /
  │    扩散深度 / 图扩展开关 / rerank 开关 — 每意图独立
  │
  ├─ 池: 热（会话树, sid 过滤） + 冷（全局 = 会话全量 + produced
  │       块 + 文档语料 DM_DOC_CORPUS=1, 10787 块）; 跨池去重
  │
  ├─ 锚点四路:
  │    vector（BGE-M3 余弦, Rust 批量内核, 两级粒度 summary 优先）
  │    bm25（Rust 稀疏内核, 真实 df, 中文 query 才启用）
  │    spo（SPO 约束投影对齐: 谓语0.5/主语0.3/宾语0.2, 候选集 cap=300）
  │    assoc（关联链检索, 无服务则跳过）
  │    + segment 多路（sub_queries=意图拆分段, 并行全路, 2026-08-13）
  │
  ├─ HyDE（2026-08-13 默认上线 DM_HYDE=1）:
  │    LLM 写假设答案 → 嵌入作 query vec（bm25/spo 仍用原 query）
  │
  ├─ 扩散: 锚点沿对话树 parent/child k-hop（k 按意图, 默认 2）
  │
  ├─ W3 图扩展（expand_graph=True, 生产已接）:
  │    ConceptGraph.compile_context（实体定位 + 边优先级扩散, 预算限定）
  │    → 树空/块空也能从持久化图抓; 节点 metadata.doc → path 供执行层
  │
  ├─ 融合: vector_primary（记忆召回等, 证据驱动）| rerank（任务/代码/
  │    数据/因果）| rrf | linear（保留消融）
  │
  ├─ 重排层（2026-08-13 新增, DM_RERANK=1 默认）:
  │    每源分数跨候选归一 → 按意图权重加权 → 稳定排序（确定性双跑）
  │    闲聊类意图（casual/通用讨论/通用对话）关闭重排
  │    权重可白盒覆盖（set_weight target="rerank", 持久化）
  │
  └─ top_k 输出（每 hit 带 path/来源/置信度/scores/rerank_score 白盒）
     A18: 置信度/权重覆盖落盘 data/recall_index/learned_conf.json
```

### 2.3 A18 反馈（按意图独立）

- `feedback(hit_id, useful, note, intent=)` → 只调该意图的源置信度
  （键 `意图:来源`）, 不带 intent 走全局（旧行为）。
- `weights(intent=)` → 白盒视图: 该意图的置信度 + 重排权重 + 融合模式。
- **未持久化**: 置信度/反馈日志当前进程内（记录可审计, 重启丢失）。

### 2.4 生产接线点

| 接线点 | 位置 | 状态 |
|---|---|---|
| v3 API Phase 3.5 意图分类 | core/agent/api/v3_session_api.py `_GatewayLLMAdapter.classify_intent` | ✅ 每次消息 |
| W5 task 轨（W1 验收后半） | v3 Phase 4: `is_code_request() or intent∈{任务规划,代码分析}` → TaskRunner（tool_loop + 蓝图约束 + 执行树落树） | ✅ 2026-08-13 |
| 召回→执行层桥 | v3 Phase 4: `recall(intent, expand_graph=True)` → format_anchors → compile_from_anchors 子图 | ✅ |
| 蓝图 recall_pipeline 节点 | core/agent/event/statemachine.py `_run_node` / `_recall_anchors`（intent 从 run_dag context 传入） | ✅ |
| /v6/recall | core/agent/kernel/dispatch.py `kernel_recall(intent=)` + stubs_api `/recall?intent=` | ✅ |
| 意图集软编码 | classify_intent 类别集 ↔ INTENT_PROFILES 键（改一处即可扩展） | ✅ |
| 蓝图 intent_multi_recall 模板（2026-08-13） | 多意图 → recall_decompose(sub_queries) → subgraph → llm_reply; v3 API 检测到多意图时 build(template=) 显式选择 | ✅ |

### 2.5 评测（意图感知）

- docs/test/recall_queries_100.md 新增第 6 列 intent（100 条全部标注,
  与 classify_intent 类别集对齐; 软拓展直接加行）。
- scripts/query_set.py 支持 intent 列（缺省 = 记忆召回）。
- scripts/eval_100.py: `--compare` 同进程跑 rerank OFF/ON 两次, 输出
  对比表 + 按意图细分 + 逐条明细 → EVAL_100_RERANK_COMPARE_20260813.md。

---

## 三、实测数据（2026-08-13, eval_100 全量, 无 LLM 路径）

### rerank 消融（OFF = 旧排序基线）

| 域 | 指标 | OFF | ON | Δ |
|---|---|---|---|---|
| dialogue | top1 | 69.2% | **76.9%** | +7.7pp |
| dialogue | top3 | 89.7% | 87.2% | -2.6pp |
| dialogue | MRR@5 | 0.798 | **0.833** | +0.035 |
| dialogue | nDCG@5 | 0.812 | **0.832** | +0.020 |
| doc | top1 | 31.1% | **34.4%** | +3.3pp |
| doc | top3 | 54.1% | 52.5% | -1.6pp |
| doc | MRR@5 | 0.412 | **0.450** | +0.038 |
| doc | nDCG@5 | 0.478 | **0.512** | +0.034 |

### 按意图 top1（OFF → ON）

| 意图 | OFF | ON | n |
|---|---|---|---|
| 任务规划 | 38.9% | **55.6%** | 18 |
| 记忆召回 | 37.3% | **40.3%** | 67 |
| 代码分析 | 100% | 100% | 3 |
| casual | 100% | 100%（首跑曾 66.7%, 关闭重排后修复） | 3 |
| 通用讨论 | 100% | 100%（首跑曾 50%, 同上） | 2 |
| 通用对话 | 75% | 75% | 4 |
| 因果推理 / 数据搜索 | 100% | 100% | 2/1 |

**解读**: 重排层是"激进 top1"策略 — top1/MRR/nDCG 全面提升, top3 略降
（-1.6~-2.6pp）; 闲聊类（casual/通用讨论/通用对话）关闭重排后无回退。
任务规划意图 +16.7pp 是重排权重（bm25 0.30 + spo 0.20）让词法/结构
独有命中上浮的直接证据。

---

## 四、与设计的逐项比较

### 4.1 意图分析

| 设计（文档） | 当前实现 | 差距 |
|---|---|---|
| 多意图拆分: LLM 判定 multi + segments（ENGINEERING_MULTI_INTENT_SPLIT） | 代码在（MultiIntentSplitter）, 但生产主路径只取**单标签**; segments 未被召回/执行消费 | 多意图→单标签, 拆分能力闲置 |
| 5 链验证（literal/profile/association/discourse/engineering）→ FusionDecider → AmbiguityGate | 链路完整, 但 4 条算法链无数据/未接线 → abstain; 实质只有 literal 链 | 形式在、实质薄（profile/assoc/engineering 数据源未接） |
| 冷路径: 多视角 → L2.5 信念 → 启发链蒸馏回喂 | 存在, 但每 3 次低置信才触发 1 次; MultiPerspectiveAnalyzer 未进生产主路径 | 低频、无观测 |
| 语法补全→SPO→约束投影（召回哲学 A12/P25） | ✅ 在召回侧（_extract_spo: 代词闭环→分句→SPO; 对齐: 谓语0.5/主语0.3/宾语0.2） | 无差距（但它在召回侧, 不在意图侧 — 与用户设想的 mapreduce 不同） |
| PCR zone → 意图映射（BLUEPRINT W1） | 意图分类已接网关 LLM; PCR zone 仍走兜底表, 未回灌意图 | zone→intent 映射未闭环 |

### 4.2 召回

| 设计 | 当前实现 | 差距 |
|---|---|---|
| 混合锚点（BGE+BM25+HyDE+SPO+关联链, A25/P28 嵌套证据组装） | ✅ 四路 + HyDE 默认上线 + 扩散 + W3 图扩展 | 关联链依赖服务存在性（生产未验证） |
| RRF 融合（A25: 多信号交叉） | ✅ 保留 rrf 模式; 默认 vector_primary（证据驱动, 消融确定） | 无差距（模式可切） |
| 重排/精排（两阶段 RAG 主流） | ✅ 特征加权重排（零 LLM, 确定性）; LLM 精排接口未接 | LLM 精排未做（成本/延迟考虑, 留接口） |
| 意图感知自适应（W1: 意图分类后 recall 按意图选路） | ✅ INTENT_PROFILES per-intent 融合/权重/HyDE/扩散; A18 per-intent 反馈 | 置信度未持久化; 权重表静态（A18 只调置信度, 不调权重） |
| 图扩展（SUBGRAPH_EXPANSION_UPGRADE 设计 1: DAG 分层 + 同步剪枝） | ConceptGraph._expand_subgraph_layered 存在; recall._graph_anchors 走 compile_context（实体定位+边优先级） | 图扩展**同步**（async_graph_expand 未接 recall）; 全局社区层（设计 3）未做 |
| 并行子问题分解（设计 2: LLM 拆 3-5 子问题并行召回） | parallel_decompose 开关存在, **默认关**; _hyde_anchors 已支持并行（线程池） | 默认关（延迟/成本）; 未按意图开 |
| 执行层桥（RECALL_EXECUTION_BRIDGE: 锚点带路径, 执行层精确查阅） | ✅ format_anchors 带 path; TaskRunner 注入; 子图编译带 file 引用 | 无差距 |
| task 轨（W5: intent=task → TaskRunner） | ✅ 任务规划/代码分析 → TaskRunner（tool_loop + 蓝图约束 + 执行树落树） | 无差距; 数据搜索意图未进轨（设计待定） |

### 4.3 PARADIGM 公理对照（本轮相关）

| 公理 | 落实 |
|---|---|
| A18 参数自适应闭环 | 部分: 每意图源置信度可反馈可查（白盒）; 权重表静态, 反馈只调置信度; 未持久化 |
| A25/P28 召回是重建上下文 | 部分: 混合锚点+扩散+图扩展+重排齐了; 执行层精确查阅链路通; 但图社区层（全局查询）缺 |
| P2 算法与 LLM 分工 | ✅ 意图分类=LLM（泛化）; 召回排序=算法（确定性, 重排零 LLM）; LLM 精排留接口 |
| P3 判断前先检索参照 | 部分: 召回先行; 意图分类未用 RAG 参照（直接 LLM） |
| A6 负向反馈 | 部分: feedback() 按意图回流置信度; 未接用户消息级自动反馈（需显式调用） |
| A12 约束空间 | ✅ SPO 约束投影对齐 + 图内容边扩展 |

---

## 五、差距清单（诚实, 按优先级）

- ~~P1 意图副路径实质化~~（✅ 2026-08-13 晚）: 5 链数据源已接
  （profile/association/discourse resolver + 真实信号投票）; 多意图
  segments 已消费（sub_queries 多路召回 + intent_multi_recall 模板）。
  **剩余**: engineering 链数据源（工程上下文约束）未接。
- ~~P1 per-intent 置信度持久化~~（✅）: learned_conf.json 落盘, 重启不丢;
  A18 权重白盒可调（set_weight target="rerank"）。**剩余**: 权重自动
  学习（当前只支持人工/反馈调置信度, 权重需显式 set）。
- **P1** 图扩展异步化（async_graph_expand 接 recall, 首 token 不等待）
  — 当前同步, 预算 max_nodes=12 控制成本; 实测图小时毫秒级, 图大后
  再异步。
- **P2** 全局社区层（GraphRAG 全局查询正解, 设计 3）; 社区摘要预生成后台。
- **P2** LLM 精排（重排后的可选增强, 成本/延迟换 doc top1 40%+）;
  重排 top3 略降的权重微调（-1.6~-2.6pp）。
- **P2** PCR zone → 意图映射闭环（zone 影响复杂度/噪声先验 → 融合权重）。
- **P2** 行为链深度偏好（W7）→ 扩展深度/扩散 k 自适应。
- **P2** 执行树消费端（行为链读 ExecutionTree 学模式、元认知读树发现偏差）。

---

## 五.5 doc 域加强（2026-08-14, 方案 A 落地 + B/C 待办）

> 触发: 用户"召回的那个文档的需要再加强，对话的还行" + "这类算子图
> 扩展的问题吗？实际上应该是抓颗粒度细化" — doc 域 11 条 miss 诊断
> （9 条 vec=None）后查行业方案（Parent-Child Chunking / LazyGraphRAG
> 2025）确认方向。

### 诊断结论（9 条 vec=None 的真相）

- **不是截断**：miss 块长度 83~474 字, 全在 1500/3000 窗口内（截断未生效）
- **小块缺父级上下文**：嵌入窗口只有"节标题+内容", 文件级语义
  （"v2 执行层分层施工"等文件标题）未参与嵌入 → 查询"agentic 工具
  节点"与该文件任何节块语义距离都远
- **跨块概念**：agentic/存储分层/隐式关系 等语义散布文件多节, 单块
  嵌入天然抓不全 — 这是"图/多粒度"问题, 非窗口问题（用户判断正确）

### 方案 A（已落地, 实测）

- 嵌入窗口 = `文件标题 | 节标题\n内容`（doc_title 取首个 H1, 无则文件名）
- 缓存升 v4 全量重算（12000 块; 增量落盘防超时白算）
- **实测**: doc top1 34.4→37.7%（+3.3pp）/ MRR@5 0.450→0.476 /
  nDCG@5 0.512→0.541 / Recall@5 63.9→67.2%; dialogue 76.9% 全基线
  回归（coarse 窗口无 doc_title 时与原字节一致, 防回归）
- ⚠️ doc Recall@20 83.6→77.0%（-6.6pp）: doc_title 使嵌入聚焦文件主题,
  长尾块排名下降 — top1/前5 提升换 Recall@20, 记录在案
- 生产侧同步: core/agent/recall/doc_corpus.py（doc_title + v4）;
  recall_service._vector_anchors coarse 兜底带 doc_title（有则加,
  无则字节一致）

### 方案 B（2026-08-14 施工, 净效果待设计）

- 命中小块后返回**父块上下文**（文件级摘要/父标题链段落）给 LLM/
  执行层 — LlamaIndex AutoMergingRetriever 同构
- 我们已有基础: 块带 path（执行层 file_read 全文）; 缺"父块摘要
  随召回结果返回"（format_anchors 只给 160 字片段 + path）

**已实现**: 文件级摘要三策略（mechanical 零成本 / small=LM Studio
qwen3.5-9b 关思考 4s/文档, 质量显著优于 mechanical, 679 文件 ~24 分钟
批量缓存 / llm 网关）; 两级检索（query→文件摘要向量 top-k→命中文件
节块直投候选+保底抬分）; parent_context 字段（RecallHit）; 摘要/向量
落盘（首查 23s→秒级）。

**诚实消融（负面结果）**: DM_FILE_BOOST=1 → doc top1 22/61, =0 → 23/61
— 文件层保底把"文件对但块弱相关"的块抬进 top-1, 挤掉真正相关块。
两级检索**默认关**（DM_FILE_BOOST=0）; 有效提升仍是方案 A（doc_title
嵌入, 34.4→37.7%）。改进方向: 文件命中后只在文件内部排序（不全局
保底）; 文件层信号进重排权重而非抬分。

**方案 B 返回层（2026-08-14 落地, 对齐 ParentDocumentRetriever）**:
检索仍只走小块（不动排序）, 命中的 doc 块在返回层附 `| 文件: {摘要}`。
修正两处接线缺口: ①`_ensure_blocks`（hot 池）透传 doc/path/doc_title
（此前只有冷池透传 → eval/bench 的 doc 块全在 hot 池, 摘要永远加载
不上）; ②`_ensure_file_summaries` 的 has_doc 门同时看冷池与 hot 池。
实测: eval_100（20260814, 语料 12056 块）doc 域 top5 锚点 parent_context
覆盖 256/305（84%）; 排序零影响（doc top1 37.7% 与基线一致）。

**语料卫生修复（2026-08-14, 基准可信度 P0）**: 排查跨域召回 gap 时发现
评测语料三处污染 — ①`DOC_DIRS=["docs","docs/only"]` 双 walk → docs/only
每块双份装载（`#2` 消歧后缀占位 top-k, recall@k 实际减半）; ②基准
`doc_recall_bench.py` 未排除 `docs/test/`（评测文档引用 query 原文,
实测 832 处 → 基准自污染, 污染块按字面命中排 top1）; ③`docs/notTish/`
（另一项目参考文档）入池。生产池 `doc_corpus.py` 早已排除 test/notTish,
基准与生产语义不一致。修复: 双文件 DOC_DIRS 收敛为 `["docs"]` + 基准
加 EXCLUDE_PREFIXES。效果: 语料 12056→8138 块, **doc top1 37.7%→50.8%**
（+13.1pp）/ top5 65.6→78.7% / Recall@20 77.0→90.2% / parent_context
覆盖 305/305; dialogue 76.9% 零影响。40%+ 目标达成（50.8%）。

**精排试点（2026-08-14, 两个负结果 + 一个结论）**: 干净语料上
fused top1 = 50.8%。
- LLM 单选试点（qwen3.5-9b, 关思考, top-15 候选 120 字）: 纯替换 41.0%
  （拆 13 / 补 7）; 受限覆盖 cap=4（LLM 挑选在融合排名 2-4 内才覆盖）→
  55.7%（模拟, +4.9pp）。13 条下行中 ≥5 条是黄金集口径问题（LLM 挑的
  文档直接含答案, 如 V2_EXECUTION_LAYER_IMPL / DESIGN_FULL_READ /
  DESIGN_AUDIT / RECALL_SUBGRAPH_BRIDGE）。
- cross-encoder 试点（bge-reranker-v2-m3, 本地 GPU, 479ms/query）:
  44.3%（拆 12 / 补 8）— 判别式精排也赢不了融合基线。
- RRF(fused+CE) 后期融合: 45.9%（MRR 0.588）— 把一个更差的信号
  平均进来同样拉低; 多信号融合不自动等于更强。
- **结论**: 融合基线（vector+bm25+spo+意图重排）已强于任何单信号精排;
  精排的价值不是"替换排序", 而是作为**正交意图轴**的受限修正（cap 式）
  或查询端意图扩展（HyDE/多查询, 已有）。黄金集单文件口径放大精排
  下行, 需多源口径配合评估。

**推理精排（2026-08-14, 环境受阻, 待网关）**: qwen3.5-9b 开思考后
思考长度不受控 — `reasoning_effort` / `thinking.budget_tokens` /
提示级"简短推理"全被 LM Studio 忽略, 599-1599 token 全被思考吃掉,
content 恒空, 60-70s/query 不可用。**解法**: LM Studio 的 llama.cpp
后端是引擎包装版不能独立用 → 下载官方 llama.cpp CUDA 版（b10428,
用户批准下载）直接跑同一 GGUF, `--reasoning on --reasoning-budget N`
显式开思考才执行预算（默认 auto 忽略预算）→ 4-15s/条受控思考。

**推理精排实测（2026-08-14, 用户假设直接检验）**: top-5 窄窗 +
方面覆盖协议（问题拆方面 → 候选逐条判覆盖 → 选覆盖最多无矛盾）+
thinking ON（预算 128）→ 61 条 doc: fused top1 52.5% / 推理 LLM
纯替换 44.3%（上行 1 / 下行 6 / 解析失败 4 / 平均 14.6s）— 混合后
~51-53%, **未赢 fused**。结论: 推理模型的"隐性意图轴"在黄金集
单文件口径下不体现为 top1 提升（意图判断常选中语义合理但不在
期望文件的候选, 与 LLM 单选/CE 同因）。意图轴更可能体现在
回答质量（groundedness/faithfulness）而非文件选择 — 待换评测
维度验证。技术收获: llama.cpp 预算控制打通, 9b 思考可用。

**B 尾巴消融（2026-08-14, 第三个文件层负结果）**: §五.5 预留方向
"文件层信号进重排权重"已实现（DM_FILE_RERANK=1, `_rerank` 加
`w_file × 文件摘要相似度`, 单测 32/32 绿）并消融: doc top1 50.8→
49.2% / MRR 0.610→0.577 / Recall@20 90.2→83.6%, 另加 ~700ms/query。
**否决, 默认关**。与 DM_FILE_BOOST（检索层保底 22/23 净损）同因:
mechanical 摘要（标题+引言）相似度信号太弱, 加权即引噪。文件层
方向唯一未试变体: small 摘要（LM Studio qwen3.5-9b 生成, 679 文件
已缓存）+ 重排加权 — 摘要质量上来后信号才可能有用, 挂账。

**small 摘要消融（2026-08-14, 排除摘要质量假说）**: DM_FILE_SUMMARY=
small（478 条高质量摘要, 向量已预热, 修复向量缓存无策略标记 bug —
`_load/_save_file_summary_vectors` 带 `_strategy` 指纹, 策略切换自动
弃旧向量）+ DM_FILE_RERANK=1 → doc top1 49.2%, **与 mechanical 版
逐条完全一致**。重叠分析: fused top5 的 doc 位与文件命中集重叠仅
40%。**机制结论: 文件层信号无效不是摘要质量问题, 是颗粒度错配 —
文件主题命中 ≠ 块级相关（"文件对但块弱"）, 抬排名必然把弱块顶上
来; 文件层信号只适合扩候选池（召回侧）, 不适合抬排名（检索保底
与重排加权均否决）。C 最小版应遵循同一原则: 社区/文件信号只做
召回扩展, 不做排序抬升。**（副作用: mechanical 向量缓存被 small
覆盖, DM_FILE_BOOST 实验需重预热, 该方向已否决影响小。）

**C 最小版实测（2026-08-14, 负结果 — 文件索引召回侧也无力）**:
已实现 DM_FILE_POOL=1（文件命中 → 该文件节块按自然分进
`RecallResult.pool_extras`, 不抬排序; 子图桥消费 pool_extras 作额外
锚点; 单测 33/33 绿）。实测: fused top-20 缺口 12 条, **pool_extras
救回 0 条**。根因诊断（small 摘要）: 缺口查询的期望文件几乎都不在
文件摘要向量命中集里（6 缺口: 5 个 0 命中, 1 个命中但块未进 pool）—
文件级索引在难点查询上召回侧同样无力, pool 机制只是"通道"没有
"内容"。结论: 缺口救回需要更强索引（图/社区/实体级）, 文件摘要
级别到顶; C 的社区层若仍基于文件摘要向量, 预期同样无效 — 需
换索引材料（社区摘要由高质量 small 摘要聚类, 或实体/关系索引）。

**质量筛选评测（2026-08-14, 部分可行）**: 推理 LLM（qwen3.5-9b,
thinking ON 预算 256, max_tokens 900）对"问题 + top-5 锚点 + 父摘要"
做可答性判断（能/不能 → 决定是否触发子图扩展/搜索/询问）。61 条
doc: 可解析 29 条中 precision 83.3% / recall 95.2%（20tp/4fp/1fn/4tn）,
但 **52% 解析失败**（content 无"能/不能"字样或思考超预算截断）;
平均 13s/query。结论: 方向可行（判断对时很准）, 生产需结构化输出
（JSON/tool call）+ 重试 + 格式兜底; 13s/条偏慢, 只适合"低置信时
触发"的闸门而非全量。

### 方案 C（待办, LazyGraphRAG / 社区层方向）

- 跨块概念查询 → 社区摘要层兜底（SUBGRAPH_EXPANSION_UPGRADE 设计 3
  在案未实现）: 图社区检测 + 每社区摘要预生成 + 查询期向量 top-k
- LazyGraphRAG（2025.06）印证: 索引成本可降到全量 GraphRAG 0.1%,
  分层社区摘要 + 跨粒度迭代加深 — 与我们"设计 3"方向一致

---

## 五.5 蓝图薄点修复记录（2026-08-13 晚, 分层决策落地）

按 TEMPLATE_LAYERING_DECISION_20260813.md（平台层硬编码 / 能力层工具 /
流程层模板）施工时实锤并修复两个既有蓝图薄点:

1. **anchors data_key 不在 ConstraintChecker 白名单**: recall_pipeline
   模板的 recall_anchor→subgraph 边（data_key="anchors"）校验恒失败 →
   build() 回退最小 DAG, "意图→召回→图扩展→回复"链路在构建层就断掉。
   → engine.py valid_keys 补 "anchors"。
2. **模板工具节点参数不进 handler**: 工具节点 params（top_k/parallel）
   缺 "args" 键时从不传给 ToolRegistry, 工具以默认值空跑（query 为空）。
   → statemachine 工具路径: params 保留键外直传 kwargs + query 缺省取
   上下文文本 + 多意图 segments 注入 sub_queries。
3. **工具批次同名结果互相覆盖**: BlueprintExecutor._execute_tool_specs
   按工具名 key 聚合, 批次内两个 file_read 只留最后一个（全量跑时随机
   丢内容）。原测试断言 `"a" in str(...)` 因临时路径含字母碰巧通过 —
   浅测试实锤。→ 修复: 同名工具按出现序 key 为 name#2/#3; 测试强化为
   独特内容串 + 断言双结果键（file_read 与 file_read#2 并存）。

新增: `intent_multi_recall` 模板（流程层入口）; engine.build(template=)
显式模板选择（cache key 含 template, 防碰撞）。

---

## 六、复跑方法

```powershell
# 重排消融对比（~4 分钟, 向量缓存热）
.venv\Scripts\python.exe scripts/eval_100.py --compare

# 单跑（rerank ON, 默认）
.venv\Scripts\python.exe scripts/eval_100.py

# 环境开关
# DM_RERANK=0   关闭重排（消融）
# DM_FUSION=rrf|linear|vector_primary   融合模式（意图 profile 优先于 env）
# DM_HYDE=0     关闭 HyDE（默认 1）
# DM_SPO_CAP=0  关闭 SPO 候选集（全池对齐, 慢）
# DM_DOC_CORPUS=0 关闭文档语料池
```
