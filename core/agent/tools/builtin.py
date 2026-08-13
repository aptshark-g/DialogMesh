"""Built-in tools: arxiv_search, web_fetch, pdf_extract, file_read, file_write."""
from __future__ import annotations

import re

from core.agent.tools.registry import ToolAdapter, ToolResult, ToolRegistry


# ── Arxiv Search ──

def _arxiv_search(query: str = "", max_results: int = 5, category: str = "", **kwargs) -> ToolResult:
    try:
        import arxiv
    except ImportError:
        return ToolResult("arxiv_search", False, error="arxiv package not installed")
    try:
        search = arxiv.Search(query=query, max_results=max_results, sort_by=arxiv.SortCriterion.Relevance)
        papers = []
        for r in search.results():
            papers.append({
                "title": r.title,
                "abstract": (r.summary or "")[:500],
                "url": r.pdf_url,
                "authors": [a.name for a in r.authors],
                "published": str(r.published),
            })
        return ToolResult("arxiv_search", True, data={"query": query, "count": len(papers), "papers": papers})
    except Exception as e:
        return ToolResult("arxiv_search", False, error=str(e))


# ── Web Fetch ──

def _web_fetch(url: str = "", format: str = "markdown", **kwargs) -> ToolResult:
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return ToolResult("web_fetch", False, error="requests/bs4 not installed")
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "DialogMesh/1.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # Truncate
        if len(text) > 10000:
            text = text[:10000] + "...(truncated)"
        return ToolResult("web_fetch", True, data={"url": url, "text": text, "length": len(text)})
    except Exception as e:
        return ToolResult("web_fetch", False, error=str(e))


# ── PDF Extract ──

def _pdf_extract(url: str = "", pages: str = "", **kwargs) -> ToolResult:
    try:
        import fitz  # pymupdf
        import io
        import requests as req
    except ImportError:
        return ToolResult("pdf_extract", False, error="pymupdf not installed (pip install pymupdf)")
    try:
        if url.startswith("http"):
            resp = req.get(url, timeout=30)
            doc = fitz.open(stream=resp.content, filetype="pdf")
        else:
            doc = fitz.open(url)
        page_list = [int(p) for p in pages.split(",") if p.strip()] if pages else range(len(doc))
        texts = []
        for i in page_list:
            if 0 <= i < len(doc):
                texts.append(doc[i].get_text())
        doc.close()
        text = "\n---\n".join(texts)
        if len(text) > 10000:
            text = text[:10000] + "..."
        return ToolResult("pdf_extract", True, data={"pages": len(texts), "text": text})
    except Exception as e:
        return ToolResult("pdf_extract", False, error=str(e))


# ── File Read ──

def _file_read(path: str = "", **kwargs) -> ToolResult:
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        return ToolResult("file_read", True, data={"path": path, "content": content[:5000], "size": len(content)})
    except Exception as e:
        return ToolResult("file_read", False, error=str(e))


# ── File Write ──

def _file_write(path: str = "", content: str = "", **kwargs) -> ToolResult:
    import os
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        # P0 写即索引（RECALL_SUBGRAPH_BRIDGE §六）: 产出内容进 chunk_store,
        # 让刚写的文件可被召回（记忆闭环: 产出 → 索引 → 可查）。
        try:
            from core.agent.tools.registry import ToolRegistry
            cs = ToolRegistry._config.get("chunk_store")
            if cs is not None and content and len(content) > 20:
                cs.add_text(
                    content[:2000],
                    block_id=f"file:{path}",
                    chunkable=True,
                    tags=["produced", "file_write"])
        except Exception:
            pass
        return ToolResult("file_write", True, data={"path": path, "bytes": len(content)})
    except Exception as e:
        return ToolResult("file_write", False, error=str(e))


# ── Document Chunking（生产链路同源, 2026-08-11）──

def _chunk_document(text: str = "", max_chunk_size: int = 280,
                    strategy: str = "auto", **kwargs) -> ToolResult:
    """文本 → 结构化语义块（走生产注册链路, 与召回/文档管道同源）。

    链路: MarkdownParser（heading 层级树, 代码块/列表/表格节点完整）
          → ChunkStrategyRegistry（header/semantic/fixed_size 策略选择）
          → 叶节点文本收集 + 相邻段合并到 max_chunk_size。
    不再私有重写切分逻辑（此前 goldset 生成器绕过注册链路, 硬切导致
    markdown 结构被吞、块语义残缺 —— 2026-08-11 修复）。
    """
    try:
        # 2026-08-11: 结构预分割层（STRUCTURE_PRESPLITTER_DESIGN）——
        # 代码/JSON 整体保留, 标题+正文同块, 列表/引用成组, 噪音过滤。
        from core.agent.discourse_block_tree.structure_pre_splitter import (
            StructurePreSplitter)
        # 2026-08-11: 两级粒度（设计 12.2）— 每块带全文+摘要,
        # 召回走 Coarse scan(摘要) → Full recall(全文)。
        gran_chunks = StructurePreSplitter().split_with_granularity(
            text, maxlen=max_chunk_size)
        chunks = [c["text"] for c in gran_chunks]
        summaries = [c["summary"] for c in gran_chunks]
        pieces = [(c, "presplit") for c in chunks]
        root = None
        if not pieces and strategy != "auto":
            from core.agent.document.parsers import MarkdownParser
            root = MarkdownParser().parse(text, "chunk_document")
        if not pieces and strategy != "auto":
            # 无结构文本 → 策略层兜底（semantic/fixed_size）
            from core.agent.chunking.strategies import (
                default_registry, TaskContext, RuntimeConstraints)
            reg = default_registry()
            strat = reg.get(strategy) or reg.select(
                TaskContext(file_type="text"),
                RuntimeConstraints(llm_available=False))
            if root is not None:
                result = strat.apply(root)
                pieces = [(_clean_leaf(n), getattr(n, "node_type", "paragraph"))
                          for n in result.nodes]
                pieces = [(t, k) for t, k in pieces if t]
        if pieces:
            chunks = [c for c, _ in pieces]
        return ToolResult("chunk_document", True, data={
            "chunks": chunks, "count": len(chunks),
            "strategy": "presplit" if pieces else "fallback",
            "chunk_sizes": [len(c) for c in chunks],
            "summaries": summaries if pieces else [],
        })
    except Exception as e:
        return ToolResult("chunk_document", False, error=str(e)[:300])


def _tree_chunks(node) -> list:
    """树结构切块: heading 节点 = 标题 + 子内容成块; code/list/table 独立;
    paragraph 独立; 噪音过滤。返回 [(text, kind)]。"""
    out = []
    kids = getattr(node, "children", []) or []
    ntype = getattr(node, "node_type", "")
    raw = _clean_leaf(node)
    if ntype == "heading":
        # heading: 标题 + 子内容合并成一块（锚点语义）
        parts = [raw] if raw else []
        for c in kids:
            sub = _tree_chunks(c)
            for t, k in sub:
                if k == "paragraph":
                    parts.append(t)
        if parts:
            out.append((" ".join(p for p in parts if p), "heading"))
        for c in kids:
            for t, k in _tree_chunks(c):
                if k != "paragraph":
                    out.append((t, k))
    elif ntype in ("code", "list", "table"):
        if raw:
            out.append((raw, ntype))
    elif ntype == "paragraph" and raw:
        out.append((raw, "paragraph"))
    else:
        # root 或未识别 → 递归子节点
        for c in kids:
            out.extend(_tree_chunks(c))
    return out


def _collect_node_text(node) -> str:
    parts = [node.raw_text or ""]
    for c in getattr(node, "children", []) or []:
        parts.append(_collect_node_text(c))
    return " ".join(p for p in parts if p)


def _leaf_nodes(node):
    kids = getattr(node, "children", []) or []
    if not kids:
        return [node]
    out = []
    for c in kids:
        out.extend(_leaf_nodes(c))
    return out


def _clean_leaf(node) -> str:
    """叶 → 文本, 过滤噪音（纯符号分隔线/空壳）。"""
    t = (node.raw_text or "").strip()
    if not t:
        return ""
    # 噪音: 纯分隔线 / 纯符号行
    if re.fullmatch(r"[-*_=~]{3,}", t):
        return ""
    return t


def _assemble_chunks(pieces, max_chunk_size):
    """heading/code/list 独立; 相邻普通段落合并到 max_chunk_size。"""
    STRUCTURAL = {"heading", "code", "list", "table"}
    chunks = []
    buf = ""
    buf_kind = "paragraph"
    for p, kind in pieces:
        if kind in STRUCTURAL or len(p) >= max_chunk_size:
            if buf:
                chunks.append((buf, buf_kind))
                buf = ""
            chunks.append((p, kind))
        elif len(buf) + len(p) <= max_chunk_size:
            buf = (buf + "。" + p) if buf else p
            buf_kind = kind
        else:
            chunks.append((buf, buf_kind))
            buf = p
            buf_kind = kind
    if buf:
        chunks.append((buf, buf_kind))
    # 结构块（heading/code/list/table）不过滤; 普通段落去短噪音
    out = []
    for c, kind in chunks:
        c = c.strip()
        if not c:
            continue
        if kind in STRUCTURAL or len(c) >= 20:
            out.append(c)
    return out


# ═══════════════════════ Register ═══════════════════════

ToolRegistry.register(ToolAdapter(
    name="arxiv_search",
    description="Search arxiv for academic papers by keyword, author, or category. Returns title, abstract, PDF URL, authors.",
    category="search",
    keywords_zh=["论文", "文献", "学术", "arxiv", "paper"],
    dependencies=["arxiv"],
    handler=_arxiv_search,
    input_schema={"query": "search query", "max_results": "int (default 5)", "category": "string (optional, e.g. cs.AI)"},
))

ToolRegistry.register(ToolAdapter(
    name="web_fetch",
    description="Fetch and extract text content from a URL. Strips scripts/styles/nav. Returns clean text.",
    category="web",
    keywords_zh=["爬", "网页", "抓取", "下载", "url", "网址", "内容"],
    dependencies=["requests", "beautifulsoup4"],
    handler=_web_fetch,
    input_schema={"url": "full URL to fetch", "format": "\"markdown\" or \"text\" (default markdown)"},
))

ToolRegistry.register(ToolAdapter(
    name="pdf_extract",
    description="Extract text from PDF at URL or local path. Returns page text content.",
    category="parse",
    keywords_zh=["pdf", "文档", "提取", "解析"],
    dependencies=["pymupdf"],
    handler=_pdf_extract,
    input_schema={"url": "PDF URL or local path", "pages": "comma-separated page numbers (e.g. 0,1,2)"},
))

ToolRegistry.register(ToolAdapter(
    name="file_read",
    description="Read a text file from disk and return its contents.",
    category="file",
    keywords_zh=["读文件", "读取", "文件内容", "查看文件"],
    handler=_file_read,
    input_schema={"path": "absolute file path to read"},
))

ToolRegistry.register(ToolAdapter(
    name="file_write",
    description="Write text content to a file on disk. Creates parent directories if needed.",
    category="file",
    keywords_zh=["写文件", "写入", "保存", "生成文件", "创建文件"],
    handler=_file_write,
    input_schema={"path": "absolute file path", "content": "text content to write"},
))

ToolRegistry.register(ToolAdapter(
    name="chunk_document",
    description="Split a document/text into structured semantic chunks. Uses the production "
                "parsing+chunking pipeline (heading hierarchy, code blocks kept intact, "
                "noise filtered). Returns chunk list with sizes.",
    category="parse",
    keywords_zh=["切块", "分块", "切分", "文档解析", "chunk", "结构化"],
    handler=_chunk_document,
    input_schema={"text": "document text to chunk", "max_chunk_size": "int (default 280)",
                  "strategy": "\"auto\" | \"header\" | \"semantic\" | \"fixed_size\""},
))


def _recall_decompose(query: str = "", top_k: int = 5,
                      parallel: bool = False, sid: str = "") -> dict:
    """统一召回工具（蓝图/tool_loop 可调）: query → 四路锚点 + 可选并行分解。

    2026-08-11 注册（SUBGRAPH_EXPANSION_UPGRADE）: 走生产 RecallService,
    与 /v6/recall 同源。parallel=True 时启用 LLM 并行子问题分解
    （I/O 密集, threading）。返回 {hits, sources, miss, decompose_misses}。
    """
    from core.agent.recall.recall_service import RecallService, format_anchors
    try:
        from core.agent.cli.engine import get_engine
        engine = get_engine()
    except Exception:
        engine = None
    rs = RecallService(engine=engine)
    rs.parallel_decompose = bool(parallel)
    res = rs.recall(query, top_k=top_k, sid=sid or None, use_hyde=bool(parallel))
    return {
        "hits": [{"id": h.id, "source": h.source, "score": round(h.score, 4),
                  "text": (h.text or "")[:160]} for h in res.hits],
        "sources": sorted({h.source for h in res.hits}),
        "miss": len(res.hits) == 0,
        "decompose_misses": getattr(rs, "_decompose_misses", []),
        "anchors": format_anchors(res, max_chars=1200),
    }


ToolRegistry.register(ToolAdapter(
    name="recall_decompose",
    description="Unified memory recall: coarse anchors (vector+bm25+spo+assoc RRF) for a query. "
                "Optionally decomposes the query into sub-questions via LLM for broader coverage "
                "(parallel=True). Returns ranked candidate anchors for downstream agentic steps.",
    category="parse",
    keywords_zh=["召回", "记忆", "检索", "回忆", "锚点", "上下文", "recall"],
    handler=_recall_decompose,
    input_schema={"query": "user query", "top_k": "int (default 5)",
                  "parallel": "bool: enable LLM sub-question decomposition (default false)",
                  "sid": "session id (optional)"},
))
