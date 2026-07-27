# 学习摄入管线 — 搜索→抓取→评估→持久化

> 2026-07-26 · 接入 Blueprint §十二学习阶段 + L5 因果层第一步

---

## 一、定位

```
Blueprint learn() 阶段:
  发散假设 → [学习摄入] → 收束过滤

         搜索层            抓取层             评估层             存储层
  ┌─────────────────┐ ┌───────────┐ ┌───────────────────┐ ┌──────────────┐
  │ arxiv API        │ │ urllib    │ │ 来源可信度评估      │ │ HybridIndex  │
  │ DuckDuckGo       │ │ requests  │ │ domain × freshness │ │ FTS5Index    │
  │ Semantic Scholar │ │ bs4 提取  │ │ × citations        │ │ VectorStore  │
  │ GitHub API       │ │ OCR(PDF)  │ │ × consistency      │ │ GraphStore   │
  │ 框架文档         │ │ markdown  │ │ → credibility 0-1  │ │              │
  └─────────────────┘ └───────────┘ └───────────────────┘ └──────────────┘
```

---

## 二、搜索源分层

### L1: 学术 + 结构化 (低延迟)

| 源 | API | 返回 | 速率 |
|------|-----|------|------|
| arxiv | `export.arxiv.org/api` | XML(标题+摘要) | 1 req/3s |
| Semantic Scholar | `api.semanticscholar.org` | JSON(标题+摘要+引用) | 100 req/5min |
| GitHub | `api.github.com/search` | JSON(repo+README) | 10 req/min |

### L2: 通用网页 (中延迟, 需抓取)

| 搜索引擎 | API | 返回 |
|---------|-----|------|
| DuckDuckGo | `duckduckgo.com/html` | HTML(标题+摘要+URL) |
| Tavily | `api.tavily.com` | JSON(结构化摘要, 专为agent设计) |

### L3: 多模态 (高延迟, 需OCR/模型)

| 类型 | 处理 |
|------|------|
| PDF文档 | PyMuPDF 提取 → 如扫描件 → OCR |
| 图片(架构图/截图) | OCR → 文本 / 多模态模型直接理解 |
| 视频 | 暂不入(成本太高) |

---

## 三、抓取 → 提取 → 分块

```
fetch(url) → HTML/PDF/Markdown
  → BeautifulSoup/marker-pdf 提取纯文本
  → 分块: 512 token/chunk, 128 token overlap
  → nomic-embed-text → 768d vector
  → metadata: {source_url, domain, timestamp, content_type, title}
```

**OCR 分支**(可选, 按需):

```
PDF 是扫描件?
  ├── 是 → OCR(pymupdf + tesseract) → 文本
  └── 否 → 直接提取
```

**多模态分支**(可选, 按需):

```
内容是图表/截图?
  ├── 启用多模态模型 → 直接理解 + 生成描述
  └── 未启用 → OCR → 文本
```

---

## 四、双仓存储 — ChromaDB + HybridIndex

### 4.1 分离原则

```
外部内容 (ChromaDB)              内部知识 (HybridIndex/EventLog)
┌─────────────────────┐         ┌──────────────────────────┐
│ 论文/网页/代码      │         │ Sessions / Events        │
│ 向量索引 (HNSW)      │         │ Relations / Profiles     │
│ 聚类 (k-means)      │         │ SHA256 链 EventLog       │
│                     │         │                          │
│ cluster → LLM压缩    │ ──单向──▶ 压缩成规则 → EventLog    │
│   "从这个簇提炼规则"  │         │ Meta 验证规则准确率       │
│   provenance: url    │         │ 规则融入 Behavior 选择    │
└─────────────────────┘         └──────────────────────────┘
```

**单向流动**: ChromaDB → 凝练 → 规则 → EventLog。不双向, 不复杂 ETL。

### 4.2 ChromaDB 集群/压缩管线

```python
# 聚类
store = ChromaStore()
clusters = store.cluster(n_clusters=5, query_text="agent orchestration")
# → [{cluster_id, size, top_terms, centroid, docs}]

# 凝练 — 每个簇提炼一条规则
for cluster in clusters:
    docs_text = "\n".join(d["text"] for d in cluster["docs"])
    prompt = f"基于以下{cluster['size']}篇文献, 提炼一条可复用的规则或最佳实践:\n{docs_text}"
    rule = llm.generate(prompt)
    # 存入 EventLog, provenance = [d["doc_id"] for d in cluster["docs"]]
```

### 4.3 存储路由

| 内容类型 | 存储 | 用途 |
|---------|------|------|
| 外部网页/论文/代码 | ChromaDB | 语义搜索 + 聚类 + 凝练 |
| 内部 sessions | HybridIndex | 会话历史查询 |
| 执行事件 | EventLog | 审计 + Meta 评分 |
| 关系图谱 | GraphStore | 实体关联查询 |

---

## 五、来源可信度评估 — SelfCheckGPT 三层

### 5.1 三层架构

```
L1 快速层: domain_authority (查表, 0ms)
  → arxiv.org=0.95, github.com=0.85, medium.com=0.50

L2 计算层: freshness + citations (计算, ~1ms)
  → freshness = e^(-days/365)
  → citations = min(1.0, 0.3 + count/50)

L3 LLM层: SelfCheck (LLM 自我一致性检查, ~500ms)
  → 内容 → LLM 判断: 内部是否一致? 引用是否可信? 0-10分
  → 权重: domain 25% + freshness 20% + citations 15% + selfcheck 40%
```

### 5.2 SelfCheck 原理

```
输入: 网页/论文全文(≤1500 chars)
LLM 评估:
  1. 该内容是否有明显矛盾? (是/否)
  2. 其数据或引用是否可信? (是/否/不确定)
  3. 整体可靠性 0-10 分
→ 解析 → 归一化 0-1

LLM不可用时: 默认中性 0.5, 不回退到旧 consistency 字段
```

### 5.3 权重设计

```python
W_AUTHORITY  = 0.25  # 域名权威(快速, 缓存)
W_FRESHNESS  = 0.20  # 时效性(计算)
W_CITATIONS  = 0.15  # 引用数(归一化)
W_SELFCHECK  = 0.40  # SelfCheck LLM(核心决策)

credibility = W_AUTHORITY*authority + W_FRESHNESS*freshness
            + W_CITATIONS*citations + W_SELFCHECK*selfcheck
```

### 5.4 与传统 consistency 的区别

| 之前 | 现在 |
|------|------|
| consistency = EventLog 中已知事实匹配 | 去掉, 合并到 SelfCheck |
| 静态 0.5 默认值 | LLM 主动判断 |
| 依赖历史数据积累 | 即时可用, 历史数据作为 Meta 验证 |

---

## 六、与 Blueprint learn() 的接法

```python
# 现有 learn() 改造为完整摄入管线
def learn(self, hypotheses, intent) -> LearningResult:
    result = LearningResult()

    # 1. 并行搜索(多源)
    arxiv_hits = self._search_arxiv(intent)
    web_hits = self._search_web(intent)       # DuckDuckGo
    scholar_hits = self._search_scholar(intent)  # Semantic Scholar

    # 2. 去重 + 排序(按 credibility)
    all_hits = arxiv_hits + web_hits + scholar_hits
    all_hits.sort(key=lambda h: h.get("credibility", 0), reverse=True)

    # 3. 抓取 top-3 完整内容
    for hit in all_hits[:3]:
        content = self._fetch_and_extract(hit["url"])
        if content:
            # 4. 评估可信度
            hit["credibility"] = evaluate_credibility(hit)
            # 5. 存入持久化 RAG
            self._ingest_to_rag(content, hit)

    result.arxiv_matches = arxiv_hits
    result.web_matches = web_hits
    result.scholar_matches = scholar_hits
    return result
```

---

## 七、宏任务考虑

| 维度 | 之前 | 现在 | 
|------|------|------|
| 搜索源 | arxiv only | 5源 (arxiv/DDG/Scholar/GitHub/Tavily) ✅ |
| DuckDuckGo | 正则解析 HTML | `duckduckgo_search` 官方库 ✅ |
| 正文提取 | `re.sub()` | trafilatura → newspaper3k → bs4 ✅ |
| 持久化 | 无 | ChromaDB(外部) + HybridIndex(内部) ✅ |
| 可信度 | 静态域名表 | SelfCheckGPT(L1 域名 + L2 计算 + L3 LLM) ✅ |
| 聚类 | 无 | ChromaDB HNSW + k-means ✅ |
| 规则凝练 | 无 | cluster → LLM compress → EventLog ✅ |
| OCR | 无 | pymupdf(可选) |
| 多模态 | 无 | 未来 |

### 宏切换

```
宏 1(仅元数据):  搜索 → 标题+摘要 → 不抓取全文           ✅ 已实现
宏 2(文本提取):  搜索 → 抓取 → trafilatura 提取文本        ✅ 已实现
宏 3(OCR):      宏2 + PDF扫描件 OCR → pymupdf             ⬜ 可选
宏 4(多模态):   宏3 + 将图像直接喂多模态模型理解             ⬜ 未来
```

---

## 八、实施状态

| 步骤 | 内容 | 状态 |
|------|------|:---:|
| P0 | 5源搜索 (arxiv/DDG/Scholar/GitHub/Tavily) | ✅ |
| P1 | trafilatura → newspaper3k → bs4 提取 | ✅ |
| P2 | SelfCheckGPT 三层可信度 | ✅ |
| P3 | ChromaDB 存储 + HNSW 聚类 | ✅ |
| P4 | 凝练管线 (cluster → LLM → rule → EventLog) | ✅ |
| P5 | OCR 可选开关 | ⬜ |
| P6 | 多模态模型可选开关 | ⬜ |
| P7 | credibility 学习闭环 (Meta → 修正 domain_authority) | ⬜ |
