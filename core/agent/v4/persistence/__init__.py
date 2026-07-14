"""DialogMesh v4 Persistence — Vector + Keyword + Hybrid indices."""
from __future__ import annotations

# Lazy imports to avoid loading heavy dependencies at import time
def _lazy_import(name):
    import importlib
    return importlib.import_module(f"core.agent.v4.persistence.{name}")

# Core indices (lightweight)
from core.agent.v4.persistence.hnsw_index import HNSWIndex

# Heavy indices (lazy-loaded via functions)
def get_vector_store():
    from core.agent.v4.persistence.vector_store import VectorStore, SQLiteVectorStore, MilvusVectorStore
    return VectorStore, SQLiteVectorStore, MilvusVectorStore

def get_faiss_store():
    from core.agent.v4.persistence.faiss_store import FaissVectorStore
    return FaissVectorStore

def get_fts5_index():
    from core.agent.v4.persistence.fts5_index import FTS5Index
    return FTS5Index

def get_hybrid_index():
    from core.agent.v4.persistence.hybrid_index import HybridIndex
    return HybridIndex

def get_unified_store():
    from core.agent.v4.persistence.unified_store import UnifiedGraphStore
    return UnifiedGraphStore

__all__ = [
    "HNSWIndex",
    "get_vector_store",
    "get_faiss_store",
    "get_fts5_index",
    "get_hybrid_index",
    "get_unified_store",
]
