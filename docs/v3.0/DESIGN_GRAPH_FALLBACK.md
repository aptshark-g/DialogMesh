# Graph Fallback Strategy — Large-Scale Retrieval

## Problem

当前 `_build_bge_index` 对 10,477 个对象做全量点积 → O(N×512) = 5M 次浮点运算。
图扩展到百万节点时不可行。

## Solution: Anchor-First, Graph-Second

```
Query
  │
  ├─ Tier 1: LSH bucket hash (O(k×bands) ≈ 64ops)
  │          → 100 candidates from 10K
  │
  ├─ Tier 2: HNSW approximate NN (O(log N) ≈ 14 hops)
  │          → 50 candidates when BGE vectors available
  │
  ├─ Tier 3: BFS graph expansion (O(branch^depth))
  │          → from anchors, walk RelationSubstrate 2 hops
  │          → adds ~200 related nodes
  │
  └─ Tier 4: BGE precise scoring (O(300 × 512) ≈ 0.15M ops)
             → only on ~300 subgraph nodes, not all 10K
```

Complexity: **O(N) → O(log N + k×branch^depth)**

## Implementation

### Existing modules to wire:

| Module | Role | Status |
|--------|------|--------|
| `compiler/lsh_index.py` (114行) | MinHash LSH → 候选桶 | 已存在，未接入 |
| `persistence/hnsw_index.py` (396行) | HNSW 近似最近邻 | 已存在，未接入 |
| `persistence/hybrid_index.py` (196行) | 混合索引编排 | 已存在，未接入 |
| `persistence/faiss_store.py` (205行) | FAISS 精确向量搜索 | 已存在，未接入 |
| `compiler/relation_substrate.py` | BFS 图扩展 | 已接入 engine ✅ |

### Fallback degradation chain:

```
BGE available + vectors cached:
  → HNSW (O(log N)) → Graph BFS → BGE precise

BGE available, no cache:
  → LSH (O(k)) → Graph BFS → BGE precise on subgraph

No BGE:
  → LSH (O(k)) → Jieba keyword → Graph BFS → substring match

No graph:
  → LSH → Jieba → substring (current fallback)
```

### Engine integration (`_find_targets_semantic`):

```python
def _find_targets_semantic(self, query: str):
    # Tier 1: LSH fast anchor discovery
    if self._lsh_index:
        candidates = self._lsh_index.query(query, top_k=100)
    else:
        candidates = list(self._world_objects.keys())[:200]  # degraded

    # Tier 2: HNSW approximate NN (if BGE vectors cached)
    if self._hnsw_index and self._bge_encoder:
        vec = self._bge_encoder.encode(query)
        hnsw_candidates = self._hnsw_index.search(vec, k=50)
        candidates = list(set(candidates) | set(hnsw_candidates))

    # Tier 3: Graph BFS from anchors
    if self._relation_substrate:
        expanded = set(candidates)
        for anchor in candidates[:10]:  # expand top-10 anchors
            neighbors = self._relation_substrate.get_neighbors(anchor, max_depth=2)
            expanded.update(neighbors)
        candidates = list(expanded)[:300]

    # Tier 4: BGE precise scoring on subgraph only
    if self._bge_encoder:
        return self._bge_find(query, candidates)  # O(|candidates| × 512)
    else:
        return self._keyword_find(query, candidates)  # jieba fallback
```
