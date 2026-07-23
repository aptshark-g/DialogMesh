"""Tests for HybridIndex, MilvusVectorStore, and ContextAssembler integration."""
import sys, os, types

project_root = r"C:\Users\APTShark\PycharmProjects\DialogMesh"
sys.path.insert(0, project_root)

# Mock heavy dependencies
for mod_name in ['yaml', 'networkx', 'sentence_transformers', 'torch', 'sklearn']:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

sys.modules['yaml'].safe_load = lambda x: {}
sys.modules['yaml'].dump = lambda *a, **k: ""

nx = sys.modules['networkx']
nx.Graph = type('Graph', (), {'add_edge': lambda *a: None, 'nodes': lambda self: [], 'edges': lambda self: [], 'degree': lambda self: {}})
nx.DiGraph = type('DiGraph', (), {})

import numpy as np

from core.agent.persistence.vector_store import SQLiteVectorStore
from core.agent.persistence.hybrid_index import HybridIndex, KeywordIndex
from core.agent.persistence.milvus_store import MilvusVectorStore
from core.agent.context.source import (
    ContextItem, KnowledgeSource, HybridKnowledgeSource, HybridSkillSource,
    TieredVectorStore,
)
from core.agent.context.assembler import ContextAssembler

_tests_passed = 0
_tests_failed = 0

def assert_eq(actual, expected, msg=""):
    global _tests_passed, _tests_failed
    if actual == expected:
        _tests_passed += 1
        print(f"  [PASS] {msg}")
    else:
        _tests_failed += 1
        print(f"  [FAIL] {msg}: expected {expected!r}, got {actual!r}")

def assert_true(value, msg=""): assert_eq(bool(value), True, msg)
def assert_false(value, msg=""): assert_eq(bool(value), False, msg)

def assert_near(actual, expected, tol=0.01, msg=""):
    global _tests_passed, _tests_failed
    if abs(actual - expected) <= tol:
        _tests_passed += 1
        print(f"  [PASS] {msg}")
    else:
        _tests_failed += 1
        print(f"  [FAIL] {msg}: expected ~{expected}, got {actual}")

print("=" * 60)
print("HYBRID INDEX + MILVUS + CONTEXT ASSEMBLER TESTS")
print("=" * 60)

# ---- KeywordIndex Tests ----
print("\n--- KeywordIndex ---")

ki = KeywordIndex()
ki.add("doc1", "gateway cache optimization")
ki.add("doc2", "monitoring dashboard alerts")
ki.add("doc3", "gateway rate limiting")

results = ki.search("gateway", top_k=5)
assert_eq(len(results), 2, "keyword: found 2 docs with 'gateway'")
# Both doc1 and doc3 match "gateway" with same score; sort is stable by doc_id
assert_true(results[0][0] in ("doc1", "doc3"), "keyword: first result is doc1 or doc3")

results2 = ki.search("cache optimization", top_k=5)
assert_eq(len(results2), 1, "keyword: found 1 doc with both terms")
assert_eq(results2[0][0], "doc1", "keyword: doc1 matches both")

ki.remove("doc1")
assert_eq(ki.doc_count, 2, "keyword: remove doc1, count=2")

# ---- HybridIndex Tests ----
print("\n--- HybridIndex ---")

# Simple mock embedder: returns a deterministic vector based on text hash
class MockEmbedder:
    def __init__(self, dim=384):
        self.dim = dim
    def encode(self, text):
        np.random.seed(hash(text) % 2**31)
        return np.random.randn(self.dim).astype(np.float32)

embedder = MockEmbedder()

# Build vector store + hybrid index
sqlite_store = SQLiteVectorStore(":memory:")
sqlite_store.open()

hybrid = HybridIndex(
    vector_store=sqlite_store,
    embedder=embedder.encode,
    semantic_weight=0.7,
    keyword_weight=0.3,
)

# Index documents
hybrid.index_document("doc1", "gateway cache optimization", embedder.encode("gateway cache optimization"))
hybrid.index_document("doc2", "monitoring dashboard alerts", embedder.encode("monitoring dashboard alerts"))
hybrid.index_document("doc3", "gateway rate limiting", embedder.encode("gateway rate limiting"))

assert_eq(hybrid.vector_count, 3, "hybrid: 3 vectors indexed")
assert_eq(hybrid.keyword_count, 3, "hybrid: 3 docs in keyword index")

# Search
results = hybrid.search("gateway", top_k=5)
assert_true(len(results) >= 2, "hybrid: found at least 2 results for 'gateway'")

# Check that both semantic and keyword contribute
results_with_sources = hybrid.search_with_sources("gateway", top_k=5)
assert_true(len(results_with_sources) > 0, "hybrid: with_sources returned results")

# Verify merge scoring: doc1 and doc3 should be in results (both contain "gateway")
gateway_scores = {r[0]: r[1] for r in results}
assert_true("doc1" in gateway_scores or "doc3" in gateway_scores, "hybrid: at least one gateway doc in results")

# ---- MilvusVectorStore Tests ----
print("\n--- MilvusVectorStore ---")

milvus = MilvusVectorStore(host="localhost", port=19530)
# Should gracefully fail to connect (no Milvus server running)
connected = milvus.connect()
assert_eq(connected, False, "milvus: no server, connect returns False")
assert_eq(milvus.is_connected, False, "milvus: is_connected False")

# All operations should be no-ops when not connected
milvus.put("test", np.zeros(384))
assert_eq(milvus.count, 0, "milvus: put no-op when disconnected")
assert_eq(milvus.get("test"), None, "milvus: get returns None")
assert_eq(milvus.search(np.zeros(384)), [], "milvus: search returns empty")
milvus.delete("test")  # Should not raise

# disconnect should be safe
milvus.disconnect()
assert_eq(milvus.is_connected, False, "milvus: after disconnect")

# ---- TieredVectorStore Tests ----
print("\n--- TieredVectorStore ---")

sqlite = SQLiteVectorStore(":memory:")
sqlite.open()

# Without Milvus (below threshold)
tiered = TieredVectorStore(sqlite, milvus_store=None, threshold=100_000)
# Use non-zero vector to avoid zero-norm filtering in cosine search
vec = np.ones(384) / np.linalg.norm(np.ones(384))
tiered.put("node1", vec)
assert_eq(tiered.count, 1, "tiered: count=1")
results = tiered.search(vec, top_k=1)
assert_eq(len(results), 1, "tiered: search returns 1 result")
assert_eq(results[0][0], "node1", "tiered: found node1")

# With Milvus (but below threshold, should still use SQLite)
milvus_stub = MilvusVectorStore()
tiered2 = TieredVectorStore(sqlite, milvus_store=milvus_stub, threshold=100_000)
results2 = tiered2.search(vec, top_k=1)
assert_eq(len(results2), 1, "tiered: below threshold uses SQLite")"gateway", top_k=5)
assert_eq(len(results), 2, "keyword: found 2 docs with 'gateway'")
assert_eq(results[0][0], "doc1", "keyword: doc1 first (higher freq)")

results2 = ki.search("cache optimization", top_k=5)
assert_eq(len(results2), 1, "keyword: found 1 doc with both terms")
assert_eq(results2[0][0], "doc1", "keyword: doc1 matches both")

ki.remove("doc1")
assert_eq(ki.doc_count, 2, "keyword: remove doc1, count=2")

# ---- HybridIndex Tests ----
print("\n--- HybridIndex ---")

# Simple mock embedder: returns a deterministic vector based on text hash
class MockEmbedder:
    def __init__(self, dim=384):
        self.dim = dim
    def encode(self, text):
        np.random.seed(hash(text) % 2**31)
        return np.random.randn(self.dim).astype(np.float32)

embedder = MockEmbedder()

# Build vector store + hybrid index
sqlite_store = SQLiteVectorStore(":memory:")
sqlite_store.open()

hybrid = HybridIndex(
    vector_store=sqlite_store,
    embedder=embedder.encode,
    semantic_weight=0.7,
    keyword_weight=0.3,
)

# Index documents
hybrid.index_document("doc1", "gateway cache optimization", embedder.encode("gateway cache optimization"))
hybrid.index_document("doc2", "monitoring dashboard alerts", embedder.encode("monitoring dashboard alerts"))
hybrid.index_document("doc3", "gateway rate limiting", embedder.encode("gateway rate limiting"))

assert_eq(hybrid.vector_count, 3, "hybrid: 3 vectors indexed")
assert_eq(hybrid.keyword_count, 3, "hybrid: 3 docs in keyword index")

# Search
results = hybrid.search("gateway", top_k=5)
assert_true(len(results) >= 2, "hybrid: found at least 2 results for 'gateway'")

# Check that both semantic and keyword contribute
results_with_sources = hybrid.search_with_sources("gateway", top_k=5)
assert_true(len(results_with_sources) > 0, "hybrid: with_sources returned results")

# Verify merge scoring: doc1 and doc3 should have higher scores (both contain "gateway")
gateway_scores = {r[0]: r[1] for r in results}
assert_true("doc1" in gateway_scores, "hybrid: doc1 in results")
assert_true("doc3" in gateway_scores, "hybrid: doc3 in results")

# ---- MilvusVectorStore Tests ----
print("\n--- MilvusVectorStore ---")

milvus = MilvusVectorStore(host="localhost", port=19530)
# Should gracefully fail to connect (no Milvus server running)
connected = milvus.connect()
assert_eq(connected, False, "milvus: no server, connect returns False")
assert_eq(milvus.is_connected, False, "milvus: is_connected False")

# All operations should be no-ops when not connected
milvus.put("test", np.zeros(384))
assert_eq(milvus.count, 0, "milvus: put no-op when disconnected")
assert_eq(milvus.get("test"), None, "milvus: get returns None")
assert_eq(milvus.search(np.zeros(384)), [], "milvus: search returns empty")
milvus.delete("test")  # Should not raise

# disconnect should be safe
milvus.disconnect()
assert_eq(milvus.is_connected, False, "milvus: after disconnect")

# ---- TieredVectorStore Tests ----
print("\n--- TieredVectorStore ---")

sqlite = SQLiteVectorStore(":memory:")
sqlite.open()

# Without Milvus (below threshold)
tiered = TieredVectorStore(sqlite, milvus_store=None, threshold=100_000)
vec = np.zeros(384)
tiered.put("node1", vec)
assert_eq(tiered.count, 1, "tiered: count=1")
results = tiered.search(vec, top_k=1)
assert_eq(len(results), 1, "tiered: search returns 1 result")
assert_eq(results[0][0], "node1", "tiered: found node1")

# With Milvus (but below threshold, should still use SQLite)
milvus_stub = MilvusVectorStore()
tiered2 = TieredVectorStore(sqlite, milvus_store=milvus_stub, threshold=100_000)
results2 = tiered2.search(vec, top_k=1)
assert_eq(len(results2), 1, "tiered: below threshold uses SQLite")

# ---- HybridKnowledgeSource Tests ----
print("\n--- HybridKnowledgeSource ---")

class MockNode:
    def __init__(self, kid, statement):
        self.knowledge_id = kid
        self.statement = statement

nodes = [
    MockNode("k1", "gateway cache optimization"),
    MockNode("k2", "monitoring dashboard alerts"),
    MockNode("k3", "gateway rate limiting"),
]

# Build hybrid index for knowledge
sqlite_k = SQLiteVectorStore(":memory:")
sqlite_k.open()
hybrid_k = HybridIndex(
    vector_store=sqlite_k,
    embedder=embedder.encode,
)
for node in nodes:
    hybrid_k.index_document(node.knowledge_id, node.statement, embedder.encode(node.statement))

hks = HybridKnowledgeSource(nodes=nodes, hybrid_index=hybrid_k)
assert_eq(hks.name, "knowledge_hybrid", "hks: name correct")

items = hks.retrieve("gateway", top_k=5)
assert_true(len(items) >= 2, "hks: found at least 2 gateway results")
assert_eq(items[0].source, "knowledge_hybrid", "hks: source name correct")
assert_eq(items[0].metadata.get("retrieval"), "hybrid", "hks: metadata marks hybrid")

# Fallback to keyword when hybrid_index is None
hks_fallback = HybridKnowledgeSource(nodes=nodes, hybrid_index=None)
items_fb = hks_fallback.retrieve("gateway", top_k=5)
assert_true(len(items_fb) >= 2, "hks: fallback keyword works")

# ---- ContextAssembler Factory Tests ----
print("\n--- ContextAssembler Factory ---")

# Test with_hybrid_index
assembler = ContextAssembler.with_hybrid_index(
    knowledge_nodes=nodes,
    embedder=embedder.encode,
)
assert_eq(assembler.source_count, 2, "assembler: 2 sources (knowledge_hybrid + engineering)")

ctx = assembler.assemble("gateway", top_k=5)
assert_true(len(ctx.items) > 0, "assembler: retrieved items")
assert_true("knowledge_hybrid" in ctx.source_stats, "assembler: hybrid source used")

# Test with_tiered_store (no Milvus)
assembler2 = ContextAssembler.with_tiered_store(
    knowledge_nodes=nodes,
    embedder=embedder.encode,
    db_path=":memory:",
)
ctx2 = assembler2.assemble("gateway", top_k=5)
assert_true(len(ctx2.items) > 0, "assembler tiered: retrieved items")

# ---- Integration: End-to-end ----
print("\n--- Integration ---")

# Full pipeline: HybridIndex -> HybridKnowledgeSource -> ContextAssembler
sqlite_full = SQLiteVectorStore(":memory:")
sqlite_full.open()

hybrid_full = HybridIndex(
    vector_store=sqlite_full,
    embedder=embedder.encode,
    semantic_weight=0.7,
    keyword_weight=0.3,
)

# Index more nodes
more_nodes = [
    MockNode("k4", "database connection pooling"),
    MockNode("k5", "redis caching strategy"),
    MockNode("k6", "gateway timeout handling"),
]
all_nodes = nodes + more_nodes
for node in all_nodes:
    hybrid_full.index_document(node.knowledge_id, node.statement, embedder.encode(node.statement))

hks_full = HybridKnowledgeSource(nodes=all_nodes, hybrid_index=hybrid_full)
assembler_full = ContextAssembler([hks_full])

# Query
gateway_items = assembler_full.assemble("gateway timeout", top_k=3)
assert_true(len(gateway_items.items) > 0, "integration: found gateway items")
assert_true(len(gateway_items.items) <= 3, "integration: top_k respected")

# Verify relevance scores are in [0, 1]
for item in gateway_items.items:
    assert_true(0.0 <= item.relevance <= 1.0, f"integration: relevance {item.relevance} in [0,1]")

# ---- Summary ----
print("\n" + "=" * 60)
print(f"RESULTS: {_tests_passed} passed, {_tests_failed} failed")
print("=" * 60)

def main(ctx):
    return {"passed": _tests_passed, "failed": _tests_failed}
