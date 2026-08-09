# PCR 设计凝练讨论 — 草稿 (DRAFT)

> 创建: 2026-07-31 | 状态: 讨论中，未定稿
> 配套: `docs/only/PCR_DEEP_INVESTIGATION.md` (代码/接线调研)
> 目的: 记录讨论脉络与已核实事实，防止上下文失真；后续据此凝练正式 `DESIGN_PCR.md`

---

## 一、讨论脉络（截至本次）

1. 用户确认 PCR 后续归属 = 关联链 Layer 3（粗处理/防重复计算），不再走全算法管线，改"算法 + LLM 糅合"
2. 用户提出"罗盘式给 LLM"：维度可换，简单规则可降维；PCR 与子图强相关，协同各模块抓取召回数据后与 LLM 协同分析
3. 用户要求核实"结构化语法信息在 7-30B 模型有一定效果" → 已核实（见 §四）
4. 用户补充：主流意图分析多为"神经符号分类"风格，我们偏 NLP 混合，需调研主流方案并糅合 → 已调研（见 §五）

---

## 二、PCR 定位共识（讨论中已确认的方向）

- **定位**: 输入层粗处理网关，产出作为关联链 L3 先验（防重复计算），不负责深算
- **防重复计算机制**（已有设计）: `docs/v5/DISCUSSION_PARALLEL_REUSE.md` — PCR 产出 → `pcr_computed` 事件 → `AssociationSubscriber` 消费 → 注入 `FusionEngine` 作为 Layer 3 初始值
- **罗盘式**（已有雏形）:
  - `core/agent/compiler/three_paradigm_context.py`: 三范式罗盘（温度×距离×信息价值），哲学 "Not algorithm-decides → LLM-navigates"
  - `core/agent/topic_tree/compass_patch.py`: 罗盘注入 TopicTree 路由
  - V4.0 XYZ 三轴（认知距离×操作粒度×反馈期望）是另一套"罗盘"
- **当前实现现状**: 详见 PCR_DEEP_INVESTIGATION.md —— 设计多代、代码 3 套分裂、生产路径从未接线

---

## 三、待拍板分歧（上次讨论遗留）

| # | 分歧 | 选项 |
|---|------|------|
| D1 | 两套罗盘合并? | A) 抽象为可插拔维度集，XYZ 默认一组，ThreeParadigm 另一组，简单规则用子集 B) 保持两套独立 |
| D2 | PCR↔子图方向 | A) PCR→子图（LOGICAL_LEAP 触发水波扩展，BUSINESS_CHAIN_00 现有） B) 子图→PCR 供数（PCR 从各模块召回上下文） C) 双向 |
| D3 | 防重复计算落点 | 确认 PCR 只算粗坐标发 `pcr_computed`，L3 深算交关联链消费 |

---

## 四、文献核实结果（7-30B 结构化信息有效性）

**结论: U 型曲线方向成立，但文档两处引用查无此文，具体数字不可靠。**

| 文档引用 | 核实结果 | 说明 |
|---------|---------|------|
| Hewitt & Manning 2019 结构探针 | ✅ 真实 (NAACL 2019, N19-1419) | 内容是"探测语法内嵌于表示"，非"给 prompt 加标签" |
| Tenney et al. 2019 BERT Rediscovers | ✅ 真实 (P19-1452, 1298 cites) | 支持"大模型语法已隐式编码" |
| Tree-Planted Transformers 2024 | ✅ 真实 (arXiv 2402.12691) | 但摘要无"7B +5-12%/70B 无提升"数字；是训练期方法，文档误当推理期结论 |
| Shi et al. 2023 上下文分心 | ✅ 真实 (ICML 2023, arXiv 2302.00093) | 小模型对 prompt 噪音敏感 —— U 型左端硬证据 |
| Min et al. 2024 EMNLP "最小结构信号" | ❌ 查无此文 | arXiv/OpenAlex 均无 |
| "2025 语法增强元分析 348 篇 + 逆语法缩放" | ❌ 查无此文 | "Inverse Syntax Scaling" 非公认术语 |

**辨析: "7-30B"是两个不同命题**
- 消费端: 模型读语法标签的收益（U 曲线）— 项目经验: 3B 有害 / 7-13B 有用 / 70B+ 冗余（`docs/v5/ANALYSIS_GRAMMAR_TAGS_UTILITY.md`）
- 生产端: 模型按 schema 输出结构化结果（严格跟 schema 不编造字段）— `docs/ARCHITECTURE_AUDIT.md:603` 7-30B 最优
- 建议: 新设计弃用两条查无此文的引用，改用 Shi 2023 + 项目自证经验

---

## 五、主流意图分析方案调研（2026-07-31 联网核实）

### 5.1 神经符号方向（与用户判断一致，主流确实在走这条）

| 论文 | 年份 | 核心做法 | 与我们的关联 |
|------|------|---------|-------------|
| **NOEM³A** (arXiv 2511.19780) | 2025 | 轻量神经符号层：意图本体(ontology) → 检索小邻域注入 prompt → token 级解码先验限制到合法标签；TinyLlama/Llama-3.2-3B 在 MultiWOZ 2.3 提升 Exact Match + Slot-F1；SIS 层次感知诊断 | 与"罗盘维度可换+小模型符号约束"高度同构 |
| **ReacTOD** (arXiv 2605.19077) | 2026 | 有界 ReAct 循环内把 NLU 当离散工具调用；确定性符号校验器强制 action/schema/coreference 合规；拦截错误自纠率 93.1%；gpt-oss-20B JGA 52.71%、Qwen3-8B 47.34% | 我们的 Tiered Parser + Schema Guard 已有雏形，缺"自纠循环+校验器强约束" |
| Interpretable Neuro-Symbolic TOD (2203.05843) | 2022 | 任务导向对话的神经符号推理框架 | 背景参考 |

### 5.2 LLM 意图分类方向

| 论文 | 年份 | 核心做法 | 与我们的关联 |
|------|------|---------|-------------|
| **PAG-LLM** (2406.17163) | 2024 | LLM 生成输入多个 paraphrase → 各自分类 → 按置信度聚合；CLINC 错误降 22.7%、Banking 降 15.1%；解决幻觉标签(OOV) | 解决我们 LLM 标签 OOV 问题；我们缺聚合/去幻觉 |
| **QAID** (2303.01593) | 2023 | 意图检测重构成 QA 检索（utterance=query, intent name=answer）+ batch contrastive；few-shot SOTA | 对比我们 intent 名→向量相似度检索，方向一致 |
| Paraphrase-Aug (2204.01959) | 2022 | 用 LLM 做数据增强喂小分类器 | 我们 Tier 0/1 规则+嵌入可用 LLM 增强 |

### 5.3 工程化主流（Rasa / 生产 NLU）

| 方案 | 核心 | 与我们的关联 |
|------|------|-------------|
| **Rasa DIET** (arXiv 2004.09936) | Dual Intent+Entity Transformer；结论: 大规模预训练模型对意图/实体任务无明显收益，纯监督+轻量即可 SOTA | 支持我们"小模型+符号约束"路线，不必强上大模型 |
| **CLU/OOS 数据集** (1909.02027) | 首次引入 out-of-scope 预测；150 意图/10 域；经典分类器识别 OOS 困难 | 我们 PCR 的 UNKNOWN 期望 = OOS 问题，缺专门检测 |
| OOS 自监督判别训练 (2106.08616) | OOS 检测改进 | 同上 |
| 多意图+槽位联合 (2004.10087 AGIF / 2108.08042 / 2305.11023) | 一句话多个意图 + 槽位填充联合建模 | 我们的 MultiIntentSplitter 已有雏形，可对照 AGIF 图交互思路 |

### 5.4 LLM Router 方向（模型路由，区别于意图路由，参考）

- 2603.20895 LLM Router (Prefill Activations)、2408.12320 TensorOpera、2501.01818 Rerouting、2503.08704 生命周期漏洞
- 注: 这些是"选模型"不是"选策略"，与我们 PCR 的路由决策相关但不同层，仅作参考

---

## 六、与现有设计的差异分析（糅合点）

| 主流能力 | 我们现状 | 差距 |
|---------|---------|------|
| 意图本体 + 邻域检索注入 (NOEM³A) | 无意图本体概念；expectation 只有 4 离散值 | 缺: 本体层级 + 检索注入 + token 级解码先验 |
| 符号校验器 + 自纠循环 (ReacTOD) | Tiered Parser 有 Schema Guard（硬约束验证），无自纠 | 半有: 校验已有雏形，缺 ReAct 式自纠 + 结构化执行迹 |
| 解码先验/合法标签约束 (NOEM³A) | 无 | 缺 |
| paraphrase 聚合降错 (PAG-LLM) | 无 | 缺 |
| OOS/UNKNOWN 显式检测 (CLU) | expectation=UNKNOWN 存在但无专门检测机制 | 半有 |
| 多意图联合 (AGIF 等) | MultiIntentSplitter 有雏形 | 半有: 缺槽位联合 |
| 轻量模型即可 (DIET) | 我们 7-30B 结论一致 | ✅ 一致 |
| 罗盘标签给 LLM 导航 | ThreeParadigmContext 已有 | ✅ 已有，可作糅合载体 |

---

## 七、糅合方向建议（待讨论）

1. **意图本体层**: 建立轻量 intent ontology（可挂到关联链 L3/子图），PCR 检索小邻域注入 LLM prompt —— 对应 NOEM³A
2. **罗盘 = 可插拔维度集**: XYZ / 温度距离价值 / 本体邻域 都作为维度源；简单规则只算子集（Y 轴 or 语法信号）
3. **解码先验**: LLM 输出限制到合法标签集（对应 NOEM³A token 先验 + 我们 Schema Guard）
4. **符号校验 + 自纠**: Tiered Parser 的 Schema Guard 升级为校验器循环（对应 ReacTOD）
5. **UNKNOWN/OOS 显式化**: expectation=UNKNOWN 绑定 OOS 检测（距离/熵阈值 + 低置信度聚档）
6. **防重复计算主线不变**: PCR 粗坐标 → `pcr_computed` → 关联链 L3 消费
7. **文献引用清理**: 弃用 Min 2024 / 348篇元分析两条，保留 Shi 2023 + 项目经验

---

## 八、下一步

- [ ] 逐条拍板 D1/D2/D3（§三）
- [ ] 拍板 §七 糅合方向 1-7
- [ ] 凝练正式 `DESIGN_PCR.md` 草稿 v0.1
- [ ] 继续顺 CLI 看 Intent 模块实际接线

---

## 九、成熟开源项目源码级调研（2026-07-31，本地精读）

> 源码目录: `C:\tmp\oss-ref\`（outlines、snips-nlu 已克隆；rasa/haystack 按需拉取）
> 目的: 理论之外，看主流工程怎么"具体实现"意图分类/约束解码/路由

### 9.1 outlines (dottxt-ai, ★15.4k) — 结构化输出/约束解码

**核心链路**: `Term DSL → to_regex → FSM(Index) → token bitmask → 每步 mask logits`

```
用户定义输出类型 (Python类型/JSON Schema/Regex/CFG/Choice)
  → python_types_to_terms() 转成 DSL Term
  → to_regex() 递归转正则 (types/dsl.py: 组合子 + 运算符重载)
  → outlines_core.Index(regex, vocab) 编译成有限状态机
  → OutlinesCoreLogitsProcessor: 每生成一步 fill_next_token_bitmask → apply_token_bitmask
  → 非法 token logits 置 -inf，LLM 只能吐合法标签
```

**可借鉴设计**:
- `Choice([...])` 类型 = 合法标签集合的声明式表达；`Regex` = 格式约束（如 `[TOOL|ADVISOR|COMPANION]`）
- 双后端: llguidance(CFG) / outlines_core(JSON schema+regex) / xgrammar，可插拔
- Pydantic 集成: `Regex` 可直接当字段类型，输出自动校验
- 关键文件: `src/outlines/backends/outlines_core.py`(FSM+bitmask) · `types/dsl.py`(组合子) · `types/__init__.py`(内置类型库 uuid/ipv4/semver...)

### 9.2 Snips NLU (snipsco, ★4k) — 意图解析引擎

**核心架构: 级联两段式**（`nlu_engine.py` docstring 原文: "先保守高精度低召回，再 ML 高召回"）

```
SnipsNLUEngine.parse(text)
  → DeterministicIntentParser  (确定性, 高精度低召回)
      fit: 训练话语 → 实体占位符替换 → 生成正则模式
           过滤歧义模式(出现在>1个intent的删掉) → per-intent regexes
      parse: IGNORECASE 正则匹配, 取第一个命中
  → 未命中 → ProbabilisticIntentParser (ML, 高召回)
      Featurizer: TF-IDF n-gram + 词共现特征
                  chi2 特征选择(pvalue_threshold) + 词汇表截断
      LogRegClassifier: sklearn SGDClassifier + class_weight
  → 都未命中 → None intent (即我们的 UNKNOWN)
```

**可借鉴设计**:
- 确定性优先 + 统计回退的两段式 = 我们 PCR(Tier0 规则) + 下游的天然模板
- "歧义模式过滤": 同一模式出现在多个 intent 就丢弃 → 防误判，等价我们 PCR 的 ambiguity 处理
- 特征选择用 chi2 而非暴力全量 → 轻量（我们 Y 轴/expectation 可借鉴）
- intent_filter 参数: 运行时限定候选意图集（我们"关联链 L3 消费 PCR 后只算候选域"可参考）

### 9.3 Rasa DIET (RasaHQ, ★21k) — 生产级意图分类标杆

**核心架构: 双塔 Transformer + 标签嵌入 + 相似度匹配**（`diet_classifier.py` 1870 行）

```
训练: 消息塔(message featurizer→transformer) ∥ 标签塔(label features→dense)
      → 计算 i_scores = 消息表示 × 标签表示的相似度矩阵
      → 负采样 NUM_NEG=20: 拉远错误标签 (cross_entropy/margin loss)
预测: rank_and_mask 取 top-N + 置信度重归一化 → label_ranking
```

**默认配置关键参数** (`get_default_config`):
- `EMBEDDING_DIMENSION: 20` / `DENSE_DIMENSION: {TEXT:128, LABEL:20}` — 标签嵌入只要 20 维
- `NUM_NEG: 20`、`RANKING_LENGTH`、`RENORMALIZE_CONFIDENCES`、`SIMILARITY_TYPE: auto`
- 标签特征: 默认 one-hot；**若有意图名/示例特征则用预计算特征** (`_compute_default_label_features` vs `_extract_labels_precomputed_features`)

**可借鉴设计**:
- "标签嵌入"范式: 意图分类 = 消息表示 vs 意图名表示的相似度匹配（与 QAID 检索范式同构）
  → 我们 V4.0 的坐标投影本质就是这个：消息 → 坐标点，标签 → 坐标区
- 意图名特征化 → 天然支持 few-shot/zero-shot 新意图（不用重训分类头）
- 小维度嵌入 + 负采样 → 我们罗盘维度可换时可参考的轻量训练目标

### 9.4 Haystack routers (deepset, ★26k) — 路由组件

| 组件 | 实现 | 对应我们 |
|------|------|---------|
| `LLMMessagesRouter` (240L) | **LLM 做分类 → 输出 label → 正则 output_patterns 校验 → 路由到连接** | PCR 的"LLM 糅合 + 合法标签约束"极简版 |
| `ConditionalRouter` (26k) | Jinja2 条件表达式路由 | 我们各链间条件投递 |
| `MetadataRouter` (164L) | 元数据字段规则路由 + unmatched 兜底 | PCR → 8 链信号投递 + UNKNOWN 兜底 |
| `DocumentLengthRouter` 等 | 内置判据路由 | 罗盘简单维度（长度/类型） |

**关键启示**: LLM 路由的工业实践 = "LLM 给标签 + 确定性正则校验"，而非让 LLM 自由发挥。

### 9.5 四家对我们 PCR/Intent 的糅合对照

| 主流机制 | 出处 | 我们对应 | 差距 |
|---------|------|---------|------|
| 约束解码 (FSM bitmask) | outlines | Schema Guard(硬约束) 雏形 | 缺 token 级解码先验 |
| 合法标签 DSL (Choice/Regex) | outlines | expectation 4 离散值 | 缺声明式标签体系 |
| 两段式(确定性→ML) | Snips | PCR Tier0 + 下游 | 已同构，可强化歧义过滤 |
| 标签嵌入双塔相似度 | Rasa DIET | V4.0 坐标投影 | 概念同构，缺实现 |
| LLM 分类+正则校验 | Haystack | PCRRouterV2._llm_review | 缺输出约束化 |
| 元数据路由+unmatched | Haystack | 8 链信号投递 | 已有设计，缺接线 |

### 9.6 结论

主流做法收敛为: **轻量特征/规则(确定性) 先行 → 必要时 LLM 分类 → 输出用约束解码/正则校验强制合法**。这与我们"算法+LLM 糅合、罗盘式给 LLM、合法标签约束"的方向一致，且每一环都有成熟参考实现可抄。

---

## 十、BM25 / 主题切分 / 意图切分 查证（2026-07-31）

### 10.1 BM25 确认：是，标准 BM25，非 TF-IDF 纯版

| 位置 | 内容 |
|------|------|
| `core/agent/compiler/topic_quick_match.py` | 标准 BM25（k1=1.2, b=0.75, IDF 平滑 +1.0），jieba 分词，中文退化 2-gram；**BM25→峭度门→收敛/递归**；`dual_track_match`: BM25 快匹配 → LLM 慢验证 → 漂移迁移 |
| `core/agent/compiler/discourse_block_tree.py:410` | `_bm25_fallback` — LLM 摘要不可用时 BM25+kurtosis 兜底 |
| `core/agent/v4/persistence/fts5_index.py` | SQLite FTS5 BM25 ranking（历史主题检索） |
| `docs/BUSINESS_CHAIN_02_APPENDIX_TOPIC_MATCH.md` | 设计: SVO+BM25+画像+锚点 多源融合 → 峭度 → 收敛/递归（非纯 BM25，是多源融合架构） |
| 混合检索 | `docs/merge/DESIGN_02_CONTEXT_AND_MEMORY.md:149` 语义0.7+BM25 0.3 双通路；blog 提到 RRF 融合 BGE+dense（吸收自超图方案） |

**结论**: 不是"TF-IDF 变形"那么简单——是 BM25(稀疏) + BGE(稠密) 双轨 + 峭度门控 + LLM 验证。比纯 BM25 先进，但对比 2024-2026 主流仍偏传统。

### 10.2 意图切分 vs 对话树主题切分：确认高度同构、当前重复实现

**对话树切分**（`discourse_block_tree.py`）:
- `SyntacticDecomposer.decompose` (L125): 纯标点正则切 EDU `[。！？；，.!?;,\n]`
- `MacroMicroQuantizer.compute` (L239): 实体重叠快路径 → 9 维粘合度（BGE cos / intent_match / topic_embed / time_decay...）→ continue/fork 判定

**意图切分**:
- `core/agent/intent/multi_intent_splitter.py` (95行): **LLM-first** — LLM 决定是否多意图/切在哪，算法只给结构提示（stanza 子句或标点兜底）；信任 LLM 不再逐段验证
- `docs/v5/ENGINEERING_MULTI_INTENT_SPLIT.md`: 设计版 Stage A-E（LiteralSplitter 连词+依存 → ChainParallelVerifier 四链验证 → FusionDecider → AmbiguityGate → Resolver）
- v3 废弃版: `intent_parser.py` 正则切连词

**重叠点**（同一判断的两个视角）:
- 子句边界检测: EDU 标点正则 ≈ intent splitter 标点正则（同款）
- 相关度判断: 粘合度 continue/fork ≈ 意图边界 single/multi
- 重复计算: 同一轮输入，两套各自切一遍

### 10.3 "输入时即切 + LLM 思考时捕捉" 的可行性证据

- 对话树主线已是 Fast(输入侧) / Async(回复后) 双层：`BUSINESS_CHAIN_01_CONVERSATION_TREE.md` §2 — C 层规则 + B 层 LLM 意图分析在 Async；说明设计已认可"输入侧粗分、异步深分"
- 用户洞察的增量: 让 PCR/意图层产出 **segment 骨架**（子句边界+主题标签+粘合度），对话树直接挂载，而非自己重切；LLM 思考流（reasoning tokens）中捕获"还要 B"这类结构信号，比事后分析回复更早更准
- 现状缺口: 两套代码无共享内核；LLM 思考流未接入（`multi_intent_splitter._llm_split` 只解析最终 JSON，不消费 reasoning）

---

## 十一、主题切分（Topic Segmentation）调研待办 + 讨论结论沉淀（2026-07-31）

### 讨论结论（待确认，用户尚未最终拍板）
- 用户洞察: "意图切分" 与 "对话树主题切分" 底层同构（子句边界 + 相关度判断），当前两套代码重复实现
- 方向草案: 输入侧共享原语 `SegmentIR = {segments[], topic_labels[], cohesion[]}`；PCR/意图层产出骨架，对话树挂载消费；LLM reasoning 流作为第二证据源（Async 校准）
- 用户要求: 主题区分需先调研对应文献 + 成熟项目，学习后再细化

### 调研目标
1. 主题切分经典算法: TextTiling / TopicTiling / 贝叶斯分割 / 词汇链
2. 对话级主题切分 (dialogue topic segmentation): 数据集 + SOTA
3. LLM 时代主题切分: 用 LLM 切分的研究 + 是否与意图切分统一
4. 成熟开源项目: 可借鉴的 Segmenter 实现

---

## 十二、主题切分（Topic Segmentation）调研结果（2026-08-01，联网核实）

> 落盘详情: `C:\tmp\oss-ref\topic_seg_research.md`

### 12.1 经典算法谱系

| 算法 | 机制 | 状态 |
|------|------|------|
| **TextTiling** (Hearst 1997) | 句块词汇相似度(cos) → 平滑 → 深度谷值=边界；NLTK 有 564 行参考实现 | 经典基线 |
| **TopicTiling** (Riedl & Biemann 2012) | TextTiling + BM25 替换词汇相似度 | BM25 与主题切分的直接结合 |
| **Embedding-Enhanced TextTiling** (1610.03955) | 用嵌入增强 TextTiling（对话 session 切分） | 我们 DiscourseBlock 的 BGE+BM25 双轨同构 |
| 贝叶斯/词汇链 | 概率分割、词汇链密度 | 历史 |

### 12.2 对话级主题切分 (DTS) 主流（2021-2026）

| 论文 | 年份 | 核心 |
|------|------|------|
| Utterance-Pair Coherence (2106.06719, lxing532 ★75) | 2021 | 无监督：句对连贯性打分替代表面特征 |
| Topic-aware Utterance Repr (2305.02747) | 2023 | 主题感知话语表示 |
| HyperSeg (2308.10464) | 2023 | 超维计算 (HDC) 无监督切分 |
| **Def-DTS** (2505.21033) | 2025 | **LLM 演绎推理做 DTS**（LLM+reasoning 首次应用到 DTS）|
| **CobSeg** (2605.30668) | 2026 | 连贯边界建模：词汇转移(局部) + 语义不连续(全局) 双信号 |
| **Granularity-Aware Eval** (2512.17083) | 2025 | **F1 失效批评**：LLM 对话系统依赖切分管理超长上下文，评价要用粒度感知指标 |

### 12.3 神经切分（监督）

- Attention-based BiLSTM (1808.09935, 2018) — 首个监督神经切分
- **Transformer²** (2110.07160, 2021) — 句级预训练编码器 + 上层 Transformer 切分模型（与 Rasa DIET 双塔同构思路）

### 12.4 成熟项目（可借鉴）

| 项目 | 要点 |
|------|------|
| NLTK TextTiling (564L) | 完整参考: tokenize→block_comparison(cos)→smooth→depth_scores→boundaries；含 stopwords/段落断点 |
| Ighina/DeepTiling ★53 | TextTiling + 神经句编码器 (USE/BERT)；生产化文本切分+摘要+检索 |
| lxing532/Dialogue-Topic-Segmenter ★75 | 无监督 DTS 参考实现（DialSeg711 数据集 711 个对话） |
| Mark131434/DyDTS ★42 | 主题感知传播的动态切分 |
| textseg 仓库名 | GitHub 上无官方 `textseg/textseg`（TextSeg 数据集源码未收录；候选为 `contours/textseg` 实验性对比） |

### 12.5 对我们设计的启示

1. **TextTiling 是"主题切分"与"意图切分"统一的最佳锚点**：它切的是"话题块"，我们的 EDU 切分 + 粘合度（continue/fork）本质是 TextTiling 的对话版——用 BM25(≈TopicTiling) + BGE(≈Embedding-Enhanced) 双轨替代纯词频
2. **DTS 主流已进入 LLM 时代**：Def-DTS 用 LLM 演绎推理切分（对应我们 LLM-first MultiIntentSplitter）；CobSeg 强调"局部词汇转移 + 全局语义不连续"双信号（对应我们 MacroMicroQuantizer 的宏观4维+微观5维，方向一致且更细）
3. **粒度感知评估缺失**：我们对话树/意图切分无边界评估指标；可借鉴 2512.17083 的粒度感知 F1（P_k / WindowDiff 等经典指标 + LLM 时代新指标）
4. **统一 SegmentIR 有学术支撑**：TextTiling 家族就是"一个算法服务所有下游"（摘要/检索/索引）；对话版 DTS 同样服务 memory/continuity——与我们"输入侧共享 SegmentIR，对话树挂载、意图层消费"的方向一致
5. **参考实现路径**: NLTK TextTiling 算法骨架（564 行可抄）+ DeepTiling 的嵌入化改造 + Def-DTS 的 LLM 裁决层

---

## 十三、PCRRouterV2 设计审读与糅合清单（2026-08-01）

> 对象: `core/agent/pcr_router_v2.py`（599 行，当前实际主实现，全文已读）

### 13.1 实际设计管线（route()）

```
StructuralFeatures.extract(text) → Y轴粒度
  → (实体=0 且 文本>10字) LLM 实体补全 → 重算 Y
  → _compute_mood → Z轴 (LM Studio nomic → BGE → NRC-VAD → 结构fallback)
  → _compute_distance → X轴 (Stanza SVO → nomic cos + IDF → entity_density fallback)
  → _zone_from_xyz → 6 zone
  → _llm_review (偏差>0.3 覆盖坐标重算 zone)
```

### 13.2 7 个设计要点

1. **零硬编码词表**：动词=形态学启发式(后缀+辅音结尾短词)、实体=正则(hex/大写/引号)、疑问=标点+句尾虚词——全链路无关键词列表
2. **四级降级链**：Z 轴 LM Studio→sentence_transformers→fastembed→HF 镜像；X 轴 Stanza→NRC-VAD→entity_density——每轴都有 fallback 栈
3. **LLM 补全闸门**：实体=0 且文本>10 字才触发 LLM 实体提取（成本控制）
4. **LLM 协同审查**：模型大小感知(small 3 信号/medium 语法标签/large 仅坐标)，偏差>0.3 才覆盖(防抖动)
5. **X 轴已偏离设计**：设计 BGE(S,O)cos+IDF，实现 nomic(768d)+IDF，Stanza 失败退化为 entity_density*0.5+0.3——X 轴实际≈实体密度
6. **Y 轴公式与设计一致**：min(v/5,1)*0.4 + min(e/5,1)*0.3 + min(w/20,1)*0.3
7. **zone 阈值与设计不一致**：设计 x<0.2,y<0.2 vs 实现 x<0.3,y<0.3；ABYSS y>0.6,z>0.3 vs 设计 y>0.7,z>0.5——实现放宽

### 13.3 糅合清单（保留 5 条 / 废弃 2 条）

**值得糅合进新设计（5 条）**:
| # | PCRRouterV2 设计 | 糅合价值 | 如何糅合 |
|---|----------------|---------|---------|
| 1 | 四级降级链 + fallback 栈 | 高 | "罗盘维度可换"的工程形态：每维度=一组可插拔计算器(主/备/兜底) |
| 2 | LLM 补全闸门(实体=0 才调 LLM) | 高 | "算法粗处理+LLM 糅合"：算法先跑，LLM 只在零信号时介入 |
| 3 | LLM 协同审查的模型大小感知 | 高 | 与文献结论一致(7-30B 中间带受益)，新设计保留并文档化 |
| 4 | 零硬编码+形态学启发式 | 中 | 保留"无词表"原则，动词检测可换词性(中文 verb 偏低要修) |
| 5 | route(text)→PCRResult 契约 | 中 | 契约可统一，但维度必须可插拔(草稿 D1)，不能锁死三轴 |

**不建议糅合（2 条）**:
- X 轴退化成 entity_density：设计意图"语义距离"实现退化≈实体密度*0.5+0.3，要么修(补 BGE(S,O)cos 或子图召回做距离)，要么明确降级为"词汇新颖度"轴
- zone 阈值"放宽版"：三套代码各一套阈值，新设计必须定死一套并补断言测试(§7.4 优先级 1)

### 13.4 结论

PCRRouterV2 骨架值得保留（零硬编码+fallback 栈+LLM 闸门+审查），已实现"算法+LLM 糅合"雏形。缺三块新方向：**可插拔维度抽象**(三轴写死)、**子图/关联链协同**(不知道下游)、**segment 骨架输入**(只吃 text 不吃切分)。

**糅合路径**: PCRRouterV2 工程机制(降级链/闸门/审查)作实现层模板 → 三轴具体计算替换为可插拔维度集 → 接入子图召回 + SegmentIR。

---

## 十四、设计决策共识（2026-08-01 用户拍板）

> 本节约定 PCR 新设计的骨架方向，后续凝练 DESIGN_PCR.md 以此为基线

### 14.1 已拍板决策（对应草稿 §十三核心讨论点）

| # | 讨论点 | 决策 |
|---|--------|------|
| 1 | 产出形态 | **C) 两者融合**：坐标(XYZ/zone) 给算法/路由用；罗盘标签(温度/距离/价值) 给 LLM 导航用。同一 PCR 输出两类视图 |
| 2 | 维度可插拔 | **声明式注册**：维度集声明式注册、可插拔；权重不硬编码、可配置调整（调权重比斟酌去留容易） |
| 3 | 切分策略 | **三阶段渐进**：PCR 粗切分(输入时) → LLM 回答期间关联链细化(异步，利用 2-5s 等待) → LLM 后验维护(事后)。切不着急 |
| 4 | 子图协同 | **双向**：PCR 决定子图内容(路由→选域口径)；子图反哺 PCR 判断(预期上下文作先验偏置) |
| 5 | 关联链协同 | **双向**：PCR 是 L3 粗处理助关联链；关联链凝练规则辅助 PCR；关联链是 NLP 处理核心；PCR 只负责 L3 粗处理 |
| 6 | X 轴语义 | **混合保留**：nomic cos + IDF + entity_density 混合，权重可调；不删维度，调权重 |
| 7 | 验证策略 | **做完再检验**；明确认定：旧测试是"作假"（恒真断言），需重做真实路由断言测试 |

### 14.2 共识架构图

```
输入文本
  │
  ▼
PCR(粗) ── 粗切分 segment骨架 ──→ (给下游)
  │       坐标 XYZ + 罗盘标签(温度/距离/价值)
  │       路由 zone → 选子图域口径
  ▼
子图(预期上下文) ──反哺──→ PCR 坐标校正(后验偏置)
  ▼
关联链(L1-L5, NLP核心) ──凝练规则──→ 辅助 PCR 粗处理
  ▲           │
  │           ▼
  └── LLM回答期间 Async 细化切分 → LLM后验维护切分
```

### 14.3 关键约束（讨论确认）

- PCR 职责边界: 只做 L3 粗处理；决定"子图口径"(取哪些域)，不编译子图内容(SubgraphCompiler 的事)
- 切分是渐进精化: PCR 只承诺边界候选+置信度，关联链/后验可纠错，不级联放大
- 权重可调必须有验证基准: 否则"调了等于没调"（引出测试策略，见 §7.4/§13.3）
