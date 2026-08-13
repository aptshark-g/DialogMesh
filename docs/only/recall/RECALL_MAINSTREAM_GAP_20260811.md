# 召回对标主流 + 差距与加强设计（2026-08-11）

> 触发: 用户 "既然我们的召回都不是主流水平的，为什么不加强一下？先去收集信息然后准备设计"
> 方法: 走 7877 代理抓取权威来源（HyDE 论文 / GraphRAG 论文 / RRF 原始论文 /
> Cohere Rerank 官方 / Pinecone Hybrid Search / RAGAS 三指标文档）
> 原始素材: docs/only/recall/RECALL_MAINSTREAM_REFS_20260811.json
> **2026-08-11 追加: 用户指出素材过老 → 补抓 arXiv cs.IR 2026-08 最新论文 6 篇**
> （Beyond Top-K / Adaptive Hybrid / RAG Failure Audit / SAGE / VDGR-RAG /
> Listwise Rerank, 摘要见 RECALL_MAINSTREAM_REFS_20260811.json papers_2026）

---

## 一、主流方案要点（有原文依据）

### 1. HyDE（Precise Zero-Shot Dense Retrieval, arXiv 2212.10496）
- 核心: query → 指令 LLM 生成"假设文档"（捕获相关性模式, 可能含幻觉细节）
  → 无监督对比编码器（Contriever）编码 → 在语料向量空间找邻域
- 意义: 零样本检索强于 Contriever, 接近微调检索器; 编码器稠密瓶颈自动过滤幻觉细节
- **我们现状**: recall_service 有 `_hyde_anchors`（query 扩展为 2-3 问题）,
  但**只用于扩展查询词**, 不是"生成假设文档再检索"——半实现

### 2. GraphRAG（arXiv 2404.16130）
- 核心: LLM 两阶段建图索引（实体+关系社区检测）→ 局部/全局查询
  （局部 = 实体关联遍历, 全局 = 社区摘要）
- 意义: 解决 RAG 对全局性问题（"数据集主题是什么"）失效的问题
- **我们现状**: 有 ConceptGraph + `expand_from_graph`（compile_context,
  max_hops=2）, 但**只在子图编译器里用, 评测 goldset 无图数据时退化为透传**

### 3. RRF（Cormack et al. 2009, SIGIR）
- 公式: 融合分 = Σ 1/(k + rank_d), k 通常 60
- 意义: 无需调权重的 rank 级融合, 尺度不敏感
- **我们现状**: ✅ 已实现（fuse_mode="rrf", 1/(60+rank)）, 评测确认
  rrf top1 42.5% vs linear 30%（旧集）——这部分是达标的

### 4. Rerank（Cohere 官方）
- 核心: 两阶段——粗召回 top-100 候选 → 交叉编码器/LLM 精排 → top-10
- 意义: 粗召回优化"召回率", 精排优化"精确率", 两阶段各司其职
- **我们现状**: 有 L2 LLM 选择（refine_bench）, 但**评测证明是负增益**
  （L2 20% vs L0 53.3% top1）——根因是 LLM 简单挑选 + 候选集质量问题,
  不是 rerank 思路错

### 5. Hybrid Search（Pinecone 官方）
- 核心: 语义（向量）+ 词法（BM25）互补; 无领域微调数据时 BM25 兜底
- 意义: 领域特定术语（代码/缩写）词法强, 语义泛化向量强
- **我们现状**: ✅ 已实现（vector + bm25 + spo + assoc 四路 RRF）

### 6. RAGAS 三指标（官方文档）
- Context Precision: 加权排序质量（分母=相关项数）
- Context Recall: claim 级召回（LLM 拆参考 claims → 判定上下文支持）
- Faithfulness: claim 级生成忠实度（幻觉率 = 1 - F）
- **我们现状**: CP ✅; **CR / F ❌ 未实现**（memory_bench 只做块级命中）

---

## 二、差距清单（诚实, 按价值排序）

| # | 差距 | 主流做法 | 我们现状 | 优先级 |
|---|------|---------|---------|:---:|
| G1 | **评测只有块级 top-k** | BEIR/TREC: MRR + nDCG + Recall@k; RAGAS: CR（claim 级） | 会话集无 MRR/nDCG, 只有 top1/3/5 + CP | P0 |
| G2 | **Context Recall / Faithfulness 未实现** | LLM claim 级判定 | 标准文档有公式, 代码无 | P0 |
| G3 | **HyDE 是半实现** | 生成假设文档 → 编码 → 邻域检索 | 只扩展查询词, 无假设文档 | P1 |
| G4 | **L2 LLM 精排负增益** | 交叉编码器/LLM 精排 top-100→10 | 简单挑选, 候选集质量差 | P1 |
| G5 | **真图检索未进主链路** | GraphRAG 社区/实体遍历 | 只存在于子图编译器, goldset 无图退化 | P1 |
| G6 | **无公开基准对照** | BEIR 子集 / C-MTEB 中文检索 | 只有自建黄金集/文档集 | P2 |

### 2026 最新进展印证（补, 用户"素材太老"质疑成立）

| 论文 (arXiv) | 核心发现 | 对我们意味着什么 |
|---|---|---|
| Beyond Top-K (2608.06305) | chunk→embed→top-k 对表格/层级文档**结构性不健全**（86.8% 行是表格, 单位继承 13 行外表头） | 块级 top-k 评测**只是下限**; 表格/结构化块需要目录/图推理兜底（对齐 VDGR-RAG） |
| Adaptive Hybrid (2608.07152) | 固定 Top-L 截断融合 **≠** 全列表融合; 未读跨列表排名可改 Top-K 成员 | 我们的粗筛 top-C + RRF 有同类隐患; 需按 query 动态深度 |
| RAG Failure Audit (2608.08944) | 离线反事实审计: 加缺失支持/删已验证非支持 → 测响应变化 | **Context Recall/Faithfulness 的工程正解**（claim 级, 我们 ❌ 未实现） |
| SAGE (2608.08237) | 按查询难度**动态选 k**（易少检难多检）, 满足 SLO | 替代固定 top_k; 与我们的 DYNAMIC_TIERING_PREFETCH 同向, 可对齐 |
| VDGR-RAG (2608.07994) | 向量 + 目录推理 + 图遍历 + 反思 四合一 | 与我们"图检索进主链路"设计同向, 是完整形态参考 |
| Listwise Rerank (2608.09650) | 列表级 LLM reranker vs 交叉编码器系统对比 | 我们 L2 负增益根因可能是"点式挑选", 应改列表级/交叉编码器 |

---

## 三、加强设计建议（v2.2 施工方向, 待用户拍板）

### 方向 A: 评测补齐（先做, 回答"到底行不行"）
1. **MRR + nDCG** 加入 memory_bench（连续排序度量, 补 top1 二元判定盲区）
2. **Context Recall 实现**: goldset query→reply, LLM 拆参考 claims,
   判定 recall top-k 上下文能否支持每条 claim（走 8080 网关）
3. **Faithfulness 实现**: agent_bench 扩展, 回复拆 claims → 上下文支持判定

### 方向 B: 召回增强（做了才有意义）
4. **HyDE 真实现**: query → LLM 生成假设文档 → BGE-M3 编码 → 邻域检索
   （不是扩展查询词）; 可先用 deepseek 生成, 后转本地小模型
5. **Rerank 正解**: 粗召回 top-100 → 精排候选集质量提升
   （LLM 给"问题+每候选 160 字片段"打相关分, 而非挑编号）;
   消融确认候选集质量是 L2 负增益根因后再定; **参考 Listwise Rerank
   (2608.09650): 列表级打分优于点式挑选**
6. **图检索进主链路**: ConceptGraph.compile_context 结果并入 recall 融合
   （domain "G" 参与 RRF）, 不再只在子图编译器里用;
   **参考 VDGR-RAG (2608.07994) 四合一 + Beyond Top-K (2608.06305)
   表格/层级文档需要图/目录推理**
7. **动态 top-k（SAGE 对齐）**: 按查询难度/召回分数分布动态选 k,
   替代固定 top_k; 与我们 DYNAMIC_TIERING_PREFETCH 合并设计

### 方向 C: 基准对齐（对外可信）
8. C-MTEB 中文检索子集 / BEIR nq 适配（块级评测, 与业界同台对比）

---

## 四、设计决策（我的判断, 待确认）

1. **先做方向 A（评测补齐）**: 现在"29.3% top1"无法回答 JD 要的
   "记忆检索准确率 / 幻觉率"——CR/F 是硬缺口, 先补上才能谈优化
2. **MRR/nDCG 是零成本增益**: 数据已有（hits 排序）, 加两个指标即可,
   立刻让评测更主流
3. **HyDE 真实现 / Rerank 正解是核心增强**: 与现有四路融合正交,
   做完可消融验证（A18 反馈也能源源不断改进）
4. **图检索进主链路** 依赖真实图数据（当前 goldset 无图）, 排在图构建
   完善后

> 用户此前判断 "Rust 重构提速度" 仍在待办（RECALL_RUST_DESIGN）; 建议
> 先补评测（方向 A）确认哪些路有效, 再决定 Rust 迁哪些计算核心——避免
> 把无效路线也 Rust 化。
