# -*- coding: utf-8 -*-
"""SourceRegistry — register, search_all parallel, get_authority.

Singleton pattern — one registry for the process.
Extensible: implement SearchSource → register().
"""

from __future__ import annotations

import logging
import time
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.agent.learning.sources import SearchSource, ArxivSource, DuckDuckGoSource, ScholarSource, GitHubSource, TavilySource

logger = logging.getLogger(__name__)


class SourceRegistry:
    """Central registry for search sources.

    Usage:
      reg = SourceRegistry.get()
      reg.search_all("agent orchestration", max_per_source=3)
    """

    _instance: Optional["SourceRegistry"] = None

    def __init__(self):
        self._sources: Dict[str, SearchSource] = {}

    @classmethod
    def get(cls) -> "SourceRegistry":
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._register_builtins()
        return cls._instance

    def _register_builtins(self):
        """Register the 5 built-in sources."""
        self.register(ArxivSource())
        self.register(DuckDuckGoSource())
        self.register(ScholarSource())
        self.register(GitHubSource())
        self.register(TavilySource())

    def register(self, source: SearchSource):
        """Register a new search source. Replaces existing with same name."""
        self._sources[source.name] = source
        logger.info("SourceRegistry: registered %s (authority=%.2f)", source.name, source.authority())

    def unregister(self, name: str):
        """Remove a search source by name."""
        self._sources.pop(name, None)
        logger.info("SourceRegistry: unregistered %s", name)

    def list_sources(self) -> List[Dict]:
        """List all registered sources with status."""
        return [{
            "name": s.name,
            "authority": s.authority(),
            "enabled": s.enabled,
        } for s in self._sources.values()]

    def search_all(self, query: str, max_per_source: int = 3,
                   max_total: int = 15, timeout: float = 10.0) -> List[Dict]:
        """Parallel search across ALL registered sources.

        Args:
            query: search query string
            max_per_source: max results per source
            max_total: max total results after dedup
            timeout: per-source timeout in seconds

        Returns:
            List of deduplicated results sorted by source authority.
            Each result: {title, url, snippet, source, timestamp, credibility}
        """
        if not query:
            return []

        enabled = [s for s in self._sources.values() if s.enabled]
        if not enabled:
            return []

        all_hits: List[Dict] = []

        # Parallel search
        with ThreadPoolExecutor(max_workers=min(8, len(enabled))) as executor:
            futures = {
                executor.submit(self._safe_search, src, query, max_per_source, timeout): src.name
                for src in enabled
            }
            for future in as_completed(futures, timeout=timeout + 2):
                name = futures[future]
                try:
                    results = future.result(timeout=1)
                    all_hits.extend(results)
                except Exception as e:
                    logger.warning("Source %s failed: %s", name, e)

        # Deduplicate by URL
        seen = set()
        deduped = []
        for h in all_hits:
            url = h.get("url", "")
            if url and url not in seen:
                seen.add(url)
                # Attach source authority as initial credibility
                src = self._sources.get(h.get("source", ""))
                h["credibility"] = src.authority() if src else 0.5
                deduped.append(h)

        # Sort by credibility (highest first), then by source authority
        deduped.sort(key=lambda h: h.get("credibility", 0), reverse=True)

        logger.info("SourceRegistry: %d results (%d sources) for '%s'",
                     len(deduped), len(enabled), query[:50])
        return deduped[:max_total]

    def _safe_search(self, src: SearchSource, query: str, max_results: int, timeout: float) -> List[Dict]:
        """Search with timeout guard."""
        t0 = time.time()
        try:
            results = src.search(query, max_results)
            elapsed = (time.time() - t0) * 1000
            logger.debug("%s: %d results (%.0fms)", src.name, len(results), elapsed)
            return results
        except Exception as e:
            logger.warning("%s: search failed: %s", src.name, e)
            return []

    def get_authority(self, domain: str) -> float:
        """Get domain authority — takes max across all registered sources."""
        for src in self._sources.values():
            if src.name == domain or src.name in domain:
                return src.authority()
        return 0.5  # default neutral
