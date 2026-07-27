# Learning Ingestion — 实施计划

> **Design doc:** `docs/DESIGN_LEARNING_INGESTION.md`
> **环境:** Windows, LM Studio(nomic-embed-text 768d), switch gateway(LLM), persistence(data/)

**目标:** 实现完整学习摄入管线——多源搜索→抓取提取→可信度评估→RAG 持久化→接入 Blueprint learn()。

---

## Phase 0: 基础层 — 搜索 + 提取

### Task 0.1: WebSearcher — 多源搜索

**文件:** 创建 `core/agent/learning/__init__.py` + `core/agent/learning/web_search.py`

四源并行搜索:
- `search_arxiv(query, max=3)` — 已有, 保持一致
- `search_duckduckgo(query, max=5)` — `duckduckgo.com/html?q=` GET → parse HTML
- `search_semantic_scholar(query, max=3)` — `api.semanticscholar.org/graph/v1/paper/search`
- `search_github(query, max=3)` — `api.github.com/search/repositories`

返回统一格式: `[{title, url, snippet, source, timestamp}]`

### Task 0.2: ContentFetcher — 网页抓取 + 文本提取

**文件:** `core/agent/learning/content_fetcher.py`

- `fetch(url) → (content_type, raw_bytes)` — urllib GET, 检测 Content-Type
- `extract_text(raw_bytes, content_type) → str`
  - HTML → BeautifulSoup(main/article/body 优先)
  - PDF → marker-pdf 提取 (如扫描件标记 "ocr_needed")
  - Markdown → 直读
  - Unknown → 原样返回前 5000 字符
- `chunk_text(text, chunk=512, overlap=128) → list[str]`

### Task 0.3: 嵌入 — LM Studio nomic-embed-text

**文件:** `core/agent/learning/embedder.py`

- 调 LM Studio `localhost:1234/v1/embeddings`
- nomic-embed-text → 768d
- 批量嵌入(每批 10 chunks)
- 失败 fallback: 返回零向量, 标记 `embedding_failed`

---

## Phase 1: 评估 + 存储

### Task 1.1: CredibilityEvaluator — 四维可信度

**文件:** `core/agent/learning/credibility.py`

对齐 DESIGN_LEARNING_INGESTION.md §五:
- `evaluate(source) → float` — 四维加权
- `DOMAIN_AUTHORITY` 预置表(25+ 域名)
- `update_consistency(source_url, was_correct: bool)` — Meta 回写
- `get_domain_authority(domain) → float` — 查询+学习更新

### Task 1.2: IngestionPipeline — 摄入到 HybridIndex

**文件:** `core/agent/learning/ingestion.py`

- `ingest(content, metadata, embedding) → doc_id` — 写入 HybridIndex
- 去重: FTS5 检查 URL → 已有则更新 accessed_at
- metadata: {source_url, domain, timestamp, content_type, title, credibility}
- 失败回退: FTS5-only (无 embedding 时)

---

## Phase 2: 接入 Blueprint

### Task 2.1: learn() 升级 — 完整摄入管线

**文件:** 改造 `core/agent/blueprint/llm_dag_builder.py`

替换现有 `learn()` 为:
```python
def learn(self, hypotheses, intent) -> LearningResult:
    # 1. 多源并行搜索
    arxiv = search_arxiv(intent)
    web = search_duckduckgo(intent)
    scholar = search_semantic_scholar(intent)
    
    # 2. 去重 + 按 credibility 排序(无完整内容先用 domain authority)
    all_hits = deduplicate(arxiv + web + scholar)
    all_hits.sort(key=lambda h: domain_authority(h["url"]), reverse=True)
    
    # 3. 抓取 top-3 完整内容 + 嵌入 + 摄入
    for hit in all_hits[:3]:
        content = fetch_and_extract(hit["url"])
        if content:
            credibility = evaluate(hit)
            embedding = embed(content[:2000])
            ingest(content, {**hit, "credibility": credibility}, embedding)
            result.ingested.append({...})
    
    return result
```

---

## Phase 3: 文档 + E2E

### Task 3.1: E2E 测试

**文件:** `tests/test_learning_e2e.py`

- 搜索测试: DuckDuckGo "agent orchestration" 有结果
- 抓取测试: GitHub README 提取成功
- 嵌入测试: LM Studio nomic-embed-text → 768d
- 摄入测试: HybridIndex.index → FTS5 可查
- 可信度测试: arxiv.org=0.95, medium.com=0.50

### Task 3.2: 文档

**文件:** `docs/BUSINESS_CHAIN_12_LEARNING.md`

---

## 文件清单

```
core/agent/learning/          (~500L 新增)
  __init__.py
  web_search.py     (4源并行搜索)
  content_fetcher.py(抓取+bs4提取+分块)
  embedder.py       (LM Studio 768d)
  credibility.py    (四维评分+学习更新)
  ingestion.py      (HybridIndex 摄入)

core/agent/blueprint/llm_dag_builder.py  (改造 learn())
tests/test_learning_e2e.py              (E2E)

docs/BUSINESS_CHAIN_12_LEARNING.md       (业务链文档)
```

## 环境适配

| 组件 | 本地 | 备注 |
|------|------|------|
| 嵌入模型 | LM Studio nomic-embed-text:1234 | 768d, 已配置 |
| LLM | switch gateway:8080 deepseek-v4-flash | 已配置 |
| 持久化 | data/learning_index.db | HybridIndex(FTS5+Vector) |
| 网络 | 直连(arxiv/SemanticScholar/GitHub不需要代理) | DuckDuckGo 也不需要 |

## 预估

| Phase | 文件 | 时间 |
|-------|:---:|:---:|
| 0 搜索+提取 | 3新 | 1.5天 |
| 1 评估+存储 | 2新 | 1天 |
| 2 接入 Blueprint | 1改 | 0.5天 |
| 3 文档+E2E | 2新 | 0.5天 |

**总计: 3.5天**
