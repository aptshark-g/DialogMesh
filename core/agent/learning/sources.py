# -*- coding: utf-8 -*-
"""SearchSource — abstract base + 4 built-in sources.

Implement SearchSource → register → search_all parallel.
Each source defines its own search() method and authority score.
"""

from __future__ import annotations

import abc
import logging
import time
import urllib.request
import urllib.parse
import urllib.error
import json
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class SearchSource(abc.ABC):
    """Abstract search source — implement search() + authority()."""

    name: str = "base"

    @abc.abstractmethod
    def search(self, query: str, max_results: int = 5) -> List[Dict]:
        """Execute search. Returns [{title, url, snippet, timestamp}]."""
        ...

    @abc.abstractmethod
    def authority(self) -> float:
        """Domain authority score 0.0-1.0. Used for credibility ranking."""
        ...

    @property
    def enabled(self) -> bool:
        return True

    def __repr__(self):
        return f"{self.name}(authority={self.authority():.2f})"


# ═══════════════════════════════════════════════
# Built-in sources
# ═══════════════════════════════════════════════

class ArxivSource(SearchSource):
    """arXiv API — academic papers by relevance."""

    name = "arxiv"

    def authority(self) -> float:
        return 0.95

    def search(self, query: str, max_results: int = 3) -> List[Dict]:
        try:
            q = urllib.parse.quote(query)
            url = f"http://export.arxiv.org/api/query?search_query=all:{q}&max_results={max_results}&sortBy=relevance"
            req = urllib.request.Request(url, headers={"User-Agent": "DialogMesh/6.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                root = ET.fromstring(resp.read())
            results = []
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns)
                summary = entry.find("atom:summary", ns)
                link = entry.find("atom:id", ns)
                results.append({
                    "title": title.text.strip() if title is not None and title.text else "?",
                    "url": link.text.strip() if link is not None and link.text else "",
                    "snippet": (summary.text or "")[:300] if summary is not None else "",
                    "source": "arxiv",
                    "timestamp": time.time(),
                })
            logger.info("Arxiv: %d results for '%s'", len(results), query[:50])
            return results[:max_results]
        except Exception as e:
            logger.warning("Arxiv search failed: %s", e)
            return []


class DuckDuckGoSource(SearchSource):
    """DuckDuckGo HTML search — webpage results."""

    name = "duckduckgo"

    def authority(self) -> float:
        return 0.55  # 聚合搜索, 权威性取决于链接到的页面

    def search(self, query: str, max_results: int = 5) -> List[Dict]:
        try:
            q = urllib.parse.quote(query)
            url = f"https://html.duckduckgo.com/html/?q={q}"
            req = urllib.request.Request(url, headers={"User-Agent": "DialogMesh/6.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                html = resp.read().decode(errors="replace")
            # Parse DuckDuckGo HTML results
            results = []
            import re
            # Extract result blocks: <a class="result__a" href="...">title</a> + <a class="result__snippet">...</a>
            links = re.findall(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html)
            snippets = re.findall(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', html)
            for i, (href, title) in enumerate(links[:max_results]):
                snippet = snippets[i].strip() if i < len(snippets) else ""
                results.append({
                    "title": re.sub(r'<[^>]+>', '', title).strip(),
                    "url": href,
                    "snippet": re.sub(r'<[^>]+>', '', snippet)[:300],
                    "source": "duckduckgo",
                    "timestamp": time.time(),
                })
            logger.info("DuckDuckGo: %d results for '%s'", len(results), query[:50])
            return results
        except Exception as e:
            logger.warning("DuckDuckGo search failed: %s", e)
            return []


class ScholarSource(SearchSource):
    """Semantic Scholar API — academic papers with citation counts."""

    name = "scholar"

    def authority(self) -> float:
        return 0.90

    def search(self, query: str, max_results: int = 3) -> List[Dict]:
        try:
            q = urllib.parse.quote(query)
            url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={q}&limit={max_results}&fields=title,url,abstract,citationCount"
            req = urllib.request.Request(url, headers={"User-Agent": "DialogMesh/6.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            results = []
            for paper in data.get("data", []):
                results.append({
                    "title": paper.get("title", "?"),
                    "url": paper.get("url", ""),
                    "snippet": (paper.get("abstract") or "")[:300],
                    "source": "semantic_scholar",
                    "timestamp": time.time(),
                    "citations": paper.get("citationCount", 0),
                })
            logger.info("Scholar: %d results for '%s'", len(results), query[:50])
            return results[:max_results]
        except Exception as e:
            logger.warning("Scholar search failed: %s", e)
            return []


class GitHubSource(SearchSource):
    """GitHub repository search — code + README."""

    name = "github"

    def authority(self) -> float:
        return 0.85

    def search(self, query: str, max_results: int = 3) -> List[Dict]:
        try:
            q = urllib.parse.quote(query)
            url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page={max_results}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "DialogMesh/6.0",
                "Accept": "application/vnd.github.v3+json",
            })
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            results = []
            for repo in data.get("items", []):
                results.append({
                    "title": repo.get("full_name", "?"),
                    "url": repo.get("html_url", ""),
                    "snippet": (repo.get("description") or "")[:300],
                    "source": "github",
                    "timestamp": time.time(),
                    "stars": repo.get("stargazers_count", 0),
                })
            logger.info("GitHub: %d results for '%s'", len(results), query[:50])
            return results[:max_results]
        except Exception as e:
            logger.warning("GitHub search failed: %s", e)
            return []
