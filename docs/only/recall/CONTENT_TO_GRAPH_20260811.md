# 内容→图转化设计 — Obsidian 双链 + 知识图谱（2026-08-11）

> 触发: 用户 "我们没有转化图的模块？" + "Obsidian Vault 天然带图关系" +
> "文档本身就存在图关系"
> 原料: `C:\Users\APTShark\Documents\Obsidian Vault\dialogmesh-design\`
> （35 篇 md, 12 个 INDEX + MOC + frontmatter + `[[双链]]` + source 映射到项目 docs）
> 参考: SwarmVault（649★, Karpathy LLM Wiki 生产版）— 三层层架构 + 边类型标签 +
> 候选审核流 + 图导航; Kwipu（266★, 本地 Graph RAG）

---

## 一、现状核查（代码实测）

### 已有的（"内容→图"的 60%）

```
DocumentIngestionPipeline.ingest_file
  → MarkdownParser（标题层级树, 不解析 [[双链]]/frontmatter）
  → ObservationExtractor（提炼概念/关系 → 观测池）
  → ConceptGraph.build_from_pool（概念节点 + 关系边 + 向量）
  → SemanticIndex / RelationSubstrate / ContentProvider / ObjectRuntime
```

### 缺失的（40%）

| # | 缺口 | 证据 |
|---|------|------|
| G1 | **Obsidian 双链 `[[...]]` 未解析** — 显式图边被丢弃 | MarkdownParser 只处理标题层级, 无 wikilink 节点 |
| G2 | **frontmatter 未利用** — title/tags/source 元数据丢失 | vault 35 篇全带 frontmatter, 解析器不读 |
| G3 | **INDEX 索引/MOC 的"焦点"摘要未复用** — 现成文档级摘要浪费 | 12 个 00-INDEX-* 表格带一句话核心内容 |
| G4 | **图边无类型标签** — 无法区分 extracted/inferred | build_from_pool 只存 confidence, 无边来源类型 |
| G5 | **图导航 API 缺失** — 只有 compile_context, 无 graph query/path/callers | 召回无法"沿图走" |
| G6 | **文档↔代码映射断** — vault frontmatter 有 source 路径, 未接执行层 | source: docs/v3.0/xxx.md 在, 无 file_read 桥 |

---

## 二、设计（借鉴 SwarmVault + 复用现有）

### 设计 1: WikilinkParser（G1/G2/G3）— 零依赖, 解析层扩展

```python
# core/agent/document/wikilink_parser.py
class WikilinkParser(MarkdownParser):
    """MarkdownParser 超集: 额外解析 frontmatter + [[双链]]。
    产出节点带 meta: {title, tags, source, links: [target...]}。"""

    def parse(self, text, source_path=""):
        node = super().parse(text, source_path)
        node.meta["frontmatter"] = parse_frontmatter(text)   # title/tags/source
        node.meta["wikilinks"] = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", text)
        node.meta["has_index_summary"] = "00-INDEX" in source_path or "MOC" in source_path
        return node
```

- 解析 `[[target]]`（含别名 `[[target|显示名]]`）→ 图边原料
- 解析 frontmatter → 节点元数据（title/tags/source）
- INDEX/MOC 文档标记 → "焦点"摘要候选

### 设计 1b: 图持久化归属（2026-08-11 修正 — 走 UnifiedGraphStore, 不造新文件）

```
归属分层:
  解析层  core/agent/document/wikilink_parser.py   （非持久化）
  图构建  core/agent/context/graph_source.py        （非持久化, 内存图）
  持久化  core/agent/persistence/unified_graph_store.py （✅ 现成, 通用图存储）

vault 图落盘（unified_edges 已支持, 零 DDL 改动）:
  node: node_type="document", domain="vault_docs",
        data={title, tags, source, summary(INDEX焦点)}
  edge: edge_type="wikilink" | "indexed" | "inferred",
        data={"source_kind": "extracted"|"inferred"}, weight=0.9|0.5

不再自造 vault_graph.json — UnifiedGraphStore 已有 tier/importance/
activation_count/snapshots, 与对话树/工程链同库, 检索/维护统一。
```

### 设计 2: 图构建扩展（G4）— 边类型标签

```python
# ConceptGraph.build_from_pool 扩展: 双链边 + 类型标签
edges.append({
    "source": doc_a, "target": doc_b,
    "type": "wikilink",          # 显式人工边
    "confidence": 0.9,
    "source_kind": "extracted",  # extracted=文档显式 | inferred=LLM/规则提炼
})
```

- `[[双链]]` → `type=wikilink, source_kind=extracted`（高可信）
- LLM/规则提炼的关系 → `source_kind=inferred`（低可信, 防幻觉）
- INDEX 归属 → `type=indexed, source_kind=extracted`
- 对齐 SwarmVault: 边类型可审计, 幻觉不累积

### 设计 3: 文档级摘要复用（G3）— INDEX 焦点 + 懒加载

```
文档级摘要（Coarse scan 层）:
  - INDEX/MOC 表格的"焦点"列 → 直接作摘要（人工已写好）
  - 其余文档 → frontmatter.title + 首段（规则兜底）→ 后续 LLM 提炼
章节级摘要 → LLM 生成, 落盘 data/recall_docs_index.json（一次性, 增量更新）
全文 → path 懒加载（file_read, 不索引全文）
```

### 设计 4: 图导航 API（G5）— 召回沿图走

```python
graph.query(q)    # 现有 find_seeds + compile_context
graph.path(a, b)  # 双链最短路径（文档间导航, 防"锚点孤立"）
graph.callers(x)  # 谁引用了 x（反向边, 溯源）
graph.neighbors(x, edge_type="wikilink")
```

- `path` 用于"跨文档桥接"（query 命中 A 文档 → 沿双链到 B 文档）
- `callers` 用于溯源（"这段设计被谁引用"）
- 对齐 SwarmVault graph query/path/explain/callers

### 设计 5: 文档↔代码桥（G6）— source 映射执行层

```
vault frontmatter.source = docs/v3.0/xxx.md
  → 文档节点带 path
  → 命中后执行层 file_read(path) 读全文
  → 代码节点（tree-sitter AST, 后续）同图
```

---

## 三、与 SwarmVault 对照

| SwarmVault | 我们设计 |
|---|---|
| raw/ 不可变源 | docs + vault 只读 ✓ |
| wiki/ 摘要页+实体页+交叉引用 | 设计 3（INDEX 焦点 + LLM 章节摘要） |
| schema.md 领域约定 | 设计 1（frontmatter tags 即 schema 雏形） |
| 边类型 extracted/inferred/ambiguous | 设计 2（extracted/inferred） |
| candidates/ 审核流 | 沿用现有 LEARNED_TEMPLATES 审核模式 |
| SQLite FTS + embeddings 混合 | 已有 bm25 + vector RRF ✓ |
| graph query/path/callers | 设计 4 |
| tree-sitter AST 代码感知 | 后续（GAP 记录） |

---

## 四、实施顺序

1. **设计 1（WikilinkParser）**: 解析 vault 35 篇 → frontmatter + 双链
   落 UnifiedGraphStore（unified_nodes/edges, domain="vault_docs"）,
   可立即验证图规模（35 节点 + 双链边数）
2. **设计 2（边类型）**: ConceptGraph 消费 vault_graph, 双链边入图
3. **设计 4（图导航）**: graph path/callers 补 API + 测试
4. **设计 5（文档↔代码桥）**: source 映射 file_read
5. **设计 3（LLM 章节摘要）**: 最后（成本高, 9750 章分批）

> 关联: RECALL_MAINSTREAM_GAP（G5 图检索进主链路）;
> SUBGRAPH_EXPANSION_UPGRADE（设计 3 全局社区层）;
> ConceptGraph 已有 compile_context/expand_subgraph

---

## 五、施工记录（2026-08-11 完成 设计 1/1b/2/4）

### 已实现（全部实测）

1. **WikilinkParser**（core/agent/document/wikilink_parser.py）:
   MarkdownParser 超集 — frontmatter（title/tags/source）+ `[[双链]]`（含别名）
   + INDEX/MOC 检测; 标题层级树不破坏。6 测试。
2. **delete_domain**（UnifiedGraphStore）: 按域清理节点/边, 幂等重建用。
   1 测试。
3. **build_vault_graph**（scripts/build_vault_graph.py）: Obsidian vault
   35 篇 → UnifiedGraphStore: 35 vault 节点 + 30 wikilink 边 + 117 cross_ref
   跨库边（vault ↔ docs 75 文件映射）= 110 节点 / 147 边; 8 真未解析
   （MOC 别名/任务文件, 2.5%）。
4. **build_from_graph_store**（ConceptGraph）: 从 UnifiedGraphStore 加载
   节点+边（source_kind: extracted=0.9 / inferred=0.5）, summary 进
   observations（Coarse scan 原料）, 自动社区检测。1 测试。
5. **图导航 API**（ConceptGraph）: neighbors(edge_type 过滤) / callers(反向
   溯源) / path(BFS 最短路径, 防锚点孤立)。3 测试。

### 端到端验证（真实数据）
```
Obsidian Vault 35 篇 → WikilinkParser → UnifiedGraphStore(110 节点/147 边)
  → ConceptGraph(110/147/7 社区) → 导航: INDEX 节点 8 邻居(跨库),
    callers 溯源正常, path BFS 可用
```

### 测试
- wikilink 6 + unified graph 12（含 delete_domain）+ graph 扩展 9
- context+persistence 全套: 110 passed

### 遗留（设计 3/5 未施工）
- 设计 3: LLM 章节摘要（9750 章, 成本高, 排后）
- ~~设计 5: source 映射 → 执行层 file_read 桥~~ ✅ 已施工（见下）
- 图检索进主链路（RecallService 融合 domain "G"）— 待图评测集

### 2026-08-11 追加施工（设计 5 文档↔代码桥）

**实现**:
- `compile_context` 的 ContextItem 加 `metadata={"doc": [...], "concept": ...}`
  （图节点 docs 集 → 检索项路径索引）
- `expand_from_graph` 读 metadata.doc → DomainEntry cross_refs
  （target_domain="file", note=文档相对路径）— 执行层 file_read 桥
- 端到端: 真实图查询 "Behavior Chain/Intent Parser/Topic Tree" →
  命中 doc 节点 file 桥存在（1/1 真实文件）

**测试**: +1（test_graph_entry_doc_bridge）; subgraph+graph 19 passed
