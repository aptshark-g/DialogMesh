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

## 四、RAG 存储 — 复用持久化层

### 4.1 现有存储适配

```python
# 学习内容摄入 → HybridIndex
from core.agent.persistence.hybrid_index import HybridIndex

index = HybridIndex(db_path="data/learning_index.db")

def ingest(content: str, metadata: dict, embedding: list[float]):
    """摄入一篇学习内容到持久化存储"""
    index.index(
        doc_id=hash(content) % 10**9,
        vector=embedding,
        content=content,  # 原始文本(FTS5 全文搜索)
        metadata={
            "source_url": metadata.get("url"),
            "domain": extract_domain(metadata.get("url")),
            "timestamp": time.time(),
            "content_type": metadata.get("type", "webpage"),
            "title": metadata.get("title", ""),
            "credibility": metadata.get("credibility", 0.5),
        },
    )
```

### 4.2 索引 schema

```
learning_index 表:
  doc_id        TEXT PRIMARY KEY
  content       TEXT          -- 原文(FTS5 全文索引)
  embedding     BLOB          -- 768d vector(VectorStore)
  metadata_json TEXT          -- JSON(domain, timestamp, credibility, ...)
  created_at    REAL
  last_accessed REAL
```

---

## 五、来源可信度评估 — L5 因果层第一步

### 5.1 四维评分

```python
def evaluate_credibility(source: dict) -> float:
    """
    来源可信度 = domain_authority × freshness × citations × consistency

    domain_authority:  域名权威(预置表, 可学习)
    freshness:         e^(-days/365) 时间衰减
    citations:         引用数归一化
    consistency:       与 EventLog 中已知事实的一致性
    """
    # 1. 域名权威
    authority = DOMAIN_AUTHORITY.get(source["domain"], 0.5)

    # 2. 时效性: 1年内=1.0, 2年=0.37, 3年=0.13
    days_old = (time.time() - source.get("timestamp", time.time())) / 86400
    freshness = max(0.1, 2.71828 ** (-days_old / 365))

    # 3. 引用数: 有引用=0.8+, 无引用=基线0.3
    citations = source.get("citations", 0)
    citation_score = min(1.0, 0.3 + citations / 50)

    # 4. 一致性: 与已有事实匹配度(需 EventLog 中已有评价)
    consistency = 0.5  # 默认中性, 学习后更新

    return 0.3 * authority + 0.25 * freshness + 0.2 * citation_score + 0.25 * consistency

# 预置域名权威表(后续可学习调整)
DOMAIN_AUTHORITY = {
    "arxiv.org": 0.95,
    "github.com": 0.85,
    "semanticscholar.org": 0.90,
    "docs.python.org": 0.95,
    "en.wikipedia.org": 0.80,
    "medium.com": 0.50,
    "reddit.com": 0.35,
    "stackoverflow.com": 0.70,
    "blog.csdn.net": 0.40,
    "zhihu.com": 0.45,
}
```

### 5.2 置信度学习

```
每次使用学习内容 → EventLog 记录 → Meta 异步审计:
  - 该来源的信息是否正确? (与执行结果对比)
  - 如连续3次正确 → consistency_score += 0.1
  - 如连续3次错误 → consistency_score -= 0.2
  - 权重更新: credibility 融入 domain_authority 修正

这 = L5 因果层第一步: "这个信息来源可信吗?"
```

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

| 维度 | 当前 | 宏任务后 |
|------|------|---------|
| 搜索源 | arxiv only | arxiv + DDG + Semantic Scholar + GitHub |
| 内容提取 | 不提取 | urllib + bs4 提取 + OCR 可选 |
| 持久化 | 无 | HybridIndex(FTS5+Vector) |
| 可信度 | 无 | 四维评分 + 学习更新 |
| 多模态 | 无 | OCR可选 / 多模态模型可选 |

### 宏切换

```
宏 1(仅元数据):  搜索 → 标题+摘要 → 不抓取全文   ← 当前(arxiv)
宏 2(文本提取):  搜索 → 抓取 → bs4 提取文本       ← 本次目标
宏 3(OCR):      宏2 + PDF扫描件 OCR               ← 可选
宏 4(多模态):   宏3 + 将图像直接喂多模态模型理解     ← 未来
```

---

## 八、实施优先级

| 步骤 | 内容 | 估时 |
|------|------|:---:|
| P0 | DuckDuckGo 搜索 + urllib 抓取 + bs4 提取 | 1天 |
| P1 | HybridIndex 摄入 + credibility 评估 | 0.5天 |
| P2 | Semantic Scholar + GitHub 搜索源 | 0.5天 |
| P3 | OCR 可选开关 + 多模态模型可选开关 | 1天 |
| P4 | credibility 学习闭环(EventLog→Meta→修正) | 0.5天 |
