"""Built-in tools: arxiv_search, web_fetch, pdf_extract, file_read, file_write."""
from __future__ import annotations

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
        return ToolResult("file_write", True, data={"path": path, "bytes": len(content)})
    except Exception as e:
        return ToolResult("file_write", False, error=str(e))


# ═══════════════════════ Register ═══════════════════════

ToolRegistry.register(ToolAdapter(
    name="arxiv_search",
    description="Search arxiv for academic papers by keyword, author, or category. Returns title, abstract, PDF URL, authors.",
    category="search",
    dependencies=["arxiv"],
    handler=_arxiv_search,
    input_schema={"query": "search query", "max_results": "int (default 5)", "category": "string (optional, e.g. cs.AI)"},
))

ToolRegistry.register(ToolAdapter(
    name="web_fetch",
    description="Fetch and extract text content from a URL. Strips scripts/styles/nav. Returns clean text.",
    category="web",
    dependencies=["requests", "beautifulsoup4"],
    handler=_web_fetch,
    input_schema={"url": "full URL to fetch", "format": "\"markdown\" or \"text\" (default markdown)"},
))

ToolRegistry.register(ToolAdapter(
    name="pdf_extract",
    description="Extract text from PDF at URL or local path. Returns page text content.",
    category="parse",
    dependencies=["pymupdf"],
    handler=_pdf_extract,
    input_schema={"url": "PDF URL or local path", "pages": "comma-separated page numbers (e.g. 0,1,2)"},
))

ToolRegistry.register(ToolAdapter(
    name="file_read",
    description="Read a text file from disk and return its contents.",
    category="file",
    handler=_file_read,
    input_schema={"path": "absolute file path to read"},
))

ToolRegistry.register(ToolAdapter(
    name="file_write",
    description="Write text content to a file on disk. Creates parent directories if needed.",
    category="file",
    handler=_file_write,
    input_schema={"path": "absolute file path", "content": "text content to write"},
))
