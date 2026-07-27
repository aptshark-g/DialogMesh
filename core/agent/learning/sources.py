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
    """DuckDuckGo search via duckduckgo_search library.

    Uses the official library — no fragile HTML regex parsing.
    Falls back to direct API if library unavailable.
    """

    name = "duckduckgo"

    def authority(self) -> float:
        return 0.55

    def search(self, query: str, max_results: int = 5) -> List[Dict]:
        # Try official library first
        try:
            from duckduckgo_search import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": (r.get("body", "") or "")[:300],
                        "source": "duckduckgo",
                        "timestamp": time.time(),
                    })
            logger.info("DuckDuckGo: %d results for '%s'", len(results), query[:50])
            return results
        except ImportError:
            logger.debug("duckduckgo_search not installed — using HTML fallback")
        except Exception as e:
            logger.warning("DDGS library failed: %s — trying HTML fallback", e)

        # HTML fallback (fragile — only used when library unavailable)
        try:
            q = urllib.parse.quote(query)
            url = f"https://html.duckduckgo.com/html/?q={q}"
            req = urllib.request.Request(url, headers={"User-Agent": "DialogMesh/6.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                html = resp.read().decode(errors="replace")
            results = []
            import re
            links = re.findall(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html)
            snippets = re.findall(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', html)
            for i, (href, title) in enumerate(links[:max_results]):
                s = re.sub(r'<[^>]+>', '', snippets[i])[:300] if i < len(snippets) else ""
                results.append({
                    "title": re.sub(r'<[^>]+>', '', title).strip(),
                    "url": href,
                    "snippet": s,
                    "source": "duckduckgo",
                    "timestamp": time.time(),
                })
            logger.info("DuckDuckGo(fallback): %d results", len(results))
            return results
        except Exception as e:
            logger.warning("DuckDuckGo search failed: %s", e)
            return []


class TavilySource(SearchSource):
    """Tavily Search API — purpose-built for AI agents.

    Returns structured summaries + full content + relevance scores.
    Free tier: 1000 queries/month. https://tavily.com
    """

    name = "tavily"

    def authority(self) -> float:
        return 0.92

    def search(self, query: str, max_results: int = 5) -> List[Dict]:
        try:
            import os
            api_key = os.environ.get("TAVILY_API_KEY", "")
            if not api_key:
                logger.debug("TAVILY_API_KEY not set — skipping Tavily")
                return []

            import urllib.request, json
            body = json.dumps({
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
                "include_answer": False,
                "include_raw_content": True,
            }).encode()
            req = urllib.request.Request(
                "https://api.tavily.com/search",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            results = []
            for r in data.get("results", [])[:max_results]:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", "")[:500],
                    "raw_content": r.get("raw_content", ""),
                    "source": "tavily",
                    "timestamp": time.time(),
                    "relevance_score": r.get("score", 0.5),
                })
            logger.info("Tavily: %d results for '%s'", len(results), query[:50])
            return results
        except Exception as e:
            logger.warning("Tavily search failed: %s", e)
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
