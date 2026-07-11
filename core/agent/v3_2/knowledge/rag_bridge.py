# RAG Bridge - heterogeneous knowledge retrieval
import time, asyncio
from .models import KnowledgeEntry, QueryResult, SourceScorer, LRUCache
from .knowledge_source import KnowledgeSource
class RAGBridge:
    def __init__(self, cache_size=500, cache_ttl=3600):
        self.sources = {}
        self.scorer = SourceScorer()
        self.cache = LRUCache(maxsize=cache_size, ttl=cache_ttl)
        self._entry_cache = {}

    def batch_import(self, entries):
        for e in entries:
            key = f"{e.slot_name}:{e.value}:{e.domain}"
            self._entry_cache[key] = e

    def load_from_file(self, filepath):
        import json
        from .models import KnowledgeEntry
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        entries = [KnowledgeEntry(**i) for i in data]
        self.batch_import(entries)
        return len(entries)

    def register_source(self, source):
        self.sources[source.source_name] = source
    async def query(self, slot_name, value, domain='general'):
        start = time.time()
        cache_key = f'{slot_name}:{value}:{domain}'
        # Check entry cache first
        if cache_key in getattr(self, '_entry_cache', {}):
            return QueryResult([self._entry_cache[cache_key]], 0.0, 0, False)
        # Check LRU cache
        cached = self.cache.get(cache_key)
        if cached is not None:
            return QueryResult(cached, 0.0, 0, True)
        all_entries = []
        for name, source in self.sources.items():
            try:
                entries = await source.query(slot_name, value, domain)
                all_entries.extend(entries)
            except Exception as e:
                pass
        scored = sorted(all_entries, key=lambda e: self.scorer.score(e, {'domain': domain}), reverse=True)
        self.cache.set(cache_key, scored)
        elapsed = (time.time() - start) * 1000
        return QueryResult(scored, elapsed, len(self.sources), False)
    async def batch_query(self, queries):
        return await asyncio.gather(*[self.query(s, v, d) for s, v, d in queries])
