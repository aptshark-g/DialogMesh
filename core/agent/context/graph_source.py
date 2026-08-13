"""ConceptGraphSource: graph-based subgraph compilation for context retrieval.

Multi-tier concept matching:
  Tier 0: Regex concept extraction (built at ingest time, free at query)
  Tier 1: Keyword overlap scoring (fast, good recall)
  Tier 2: Semantic embedding similarity (requires embedder, high precision)
  Tier 3: Co-occurrence graph traversal (BFS subgraph expansion)

Uses existing infrastructure:
  - SemanticEncoder (BGE-small-zh) for Tier 2 embedding
  - VectorStore (SQLite) for embedding cache + fast cosine lookup
  - HybridIndex pattern for weighted merge (semantic × keyword)
"""
from __future__ import annotations
import logging
import math
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np

from core.agent.context.source import (
    ContextSource, ContextItem, _keyword_score, _extract_bundle_text,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Concept graph builder
# ============================================================================

class ConceptGraph:
    """In-memory concept graph with optional semantic embedding support.

    Built from ObservationPool document observations.
    Supports multi-tier seed finding: keyword (fast) → semantic (precise).
    """

    def __init__(self, embedder: Callable[[str], Any] = None):
        self._nodes: Dict[str, dict] = {}
        self._edges: List[dict] = []
        self._embeddings: Dict[str, np.ndarray] = {}  # concept_name -> vector
        self._embedder = embedder
        self._built = False
        self._communities: List[List[str]] = []
        self._community_summaries: Dict[tuple, str] = {}

    @property
    def has_embeddings(self) -> bool:
        return len(self._embeddings) > 0

    def _get_concepts_from_interp(self, interp) -> list:
        if isinstance(interp, dict):
            return interp.get("concepts", [])
        return getattr(interp, "concepts", [])

    def _get_relations_from_interp(self, interp) -> list:
        if isinstance(interp, dict):
            return interp.get("relations", [])
        return getattr(interp, "relations", [])

    def _get_summary_from_interp(self, interp) -> str:
        if isinstance(interp, dict):
            return interp.get("summary", "")
        return getattr(interp, "summary", "")

    def _encode(self, text: str) -> Optional[np.ndarray]:
        if self._embedder is None or not text.strip():
            return None
        try:
            vec = self._embedder.encode(text)
            if isinstance(vec, list):
                vec = np.asarray(vec, dtype=np.float32)
            elif not isinstance(vec, np.ndarray):
                return None
            # BGE returns (1,512) — flatten to (512,)
            if vec.ndim == 2 and vec.shape[0] == 1:
                vec = vec.flatten()
            norm = np.linalg.norm(vec)
            return vec / norm if norm > 0 else vec
        except Exception:
            return None

    def build_from_pool(self, pool) -> int:
        if pool is None:
            return 0
        document_bundles = pool.get_by_domain("document")
        if not document_bundles:
            return 0

        for bundle in document_bundles:
            dom_obs = getattr(bundle, "domain_observations", {}).get("document")
            if dom_obs is None:
                continue
            meta = getattr(dom_obs, "meta", {}) or {}
            source_path = getattr(bundle, "bundle_id", meta.get("source_path", "unknown"))

            # Phase 1: register nodes and explicit relation edges
            for interp in getattr(dom_obs, "interpretations", []):
                concepts = self._get_concepts_from_interp(interp)
                relations = self._get_relations_from_interp(interp)
                raw_text = self._get_summary_from_interp(interp)

                for concept in concepts:
                    c = concept.strip()
                    if not c or len(c) < 3:  # skip too-short tokens
                        continue
                    # Skip noise: code snippets, file paths, URLs, pure digits, CLI commands
                    if any(ch in c for ch in ('/', '\\\\', '://', ':', '|', '{', '}')):
                        continue
                    if c.replace('.', '').replace('-', '').replace('_', '').isdigit():
                        continue
                    if c not in self._nodes:
                        self._nodes[c] = {"relations": [], "observations": [], "docs": set()}
                    node = self._nodes[c]
                    node["observations"].append(raw_text)
                    node["docs"].add(source_path)

                for rel in relations:
                    src = rel.get("source", "") if isinstance(rel, dict) else getattr(rel, "source", "")
                    tgt = rel.get("target", "") if isinstance(rel, dict) else getattr(rel, "target", "")
                    rel_type = rel.get("relation_type", "related_to") if isinstance(rel, dict) else getattr(rel, "relation_type", "related_to")
                    conf = rel.get("confidence", 0.5) if isinstance(rel, dict) else getattr(rel, "confidence", 0.5)
                    if src and tgt:
                        self._edges.append({
                            "source": src, "target": tgt, "type": rel_type,
                            "confidence": conf, "source_doc": source_path,
                        })
                        if src in self._nodes:
                            self._nodes[src]["relations"].append({"target": tgt, "type": rel_type, "confidence": conf})
                        if tgt in self._nodes:
                            self._nodes[tgt]["relations"].append({"target": src, "type": f"rev_{rel_type}", "confidence": conf})

        # Phase 2: co-occurrence edges
        cooccur = set()
        for bundle in document_bundles:
            dom_obs = getattr(bundle, "domain_observations", {}).get("document")
            if dom_obs is None:
                continue
            for interp in getattr(dom_obs, "interpretations", []):
                concepts = self._get_concepts_from_interp(interp)
                cleaned = [c.strip() for c in concepts if c.strip() and len(c.strip()) >= 2]
                for i in range(len(cleaned)):
                    for j in range(i + 1, len(cleaned)):
                        pair = tuple(sorted([cleaned[i], cleaned[j]]))
                        if pair not in cooccur:
                            cooccur.add(pair)
                            for a, b in [(cleaned[i], cleaned[j]), (cleaned[j], cleaned[i])]:
                                if a in self._nodes and b in self._nodes:
                                    self._edges.append({
                                        "source": a, "target": b, "type": "co_occurs",
                                        "confidence": 0.3, "source_doc": source_path,
                                    })
                                    self._nodes[a]["relations"].append({"target": b, "type": "co_occurs", "confidence": 0.3})

        # Phase 3: pre-compute semantic embeddings (Tier 2)
        if self._embedder is not None:
            count = 0
            for name in list(self._nodes.keys()):
                vec = self._encode(name)
                if vec is not None:
                    self._embeddings[name] = vec
                    count += 1
            logger.info("ConceptGraph: %d/%d nodes embedded", count, len(self._nodes))

        self._built = True
        logger.info("ConceptGraph: %d nodes, %d edges (%d co-occurrence), %d embeddings",
                    len(self._nodes), len(self._edges), len(cooccur), len(self._embeddings))
        self.build_communities()
        return len(self._nodes)

    def build_from_graph_store(self, store, domain: str = "vault_docs",
                               embedder: Optional[Callable[[str], Any]] = None) -> int:
        """从 UnifiedGraphStore 加载图（CONTENT_TO_GRAPH 设计 2, 2026-08-11）。

        消费 vault 文档节点 + wikilink/cross_ref 边（含 source_kind 标签）;
        节点带 summary（INDEX 摘要）→ 后续召回可 Coarse scan。
        与 build_from_pool 可叠加（文档图 + 观测概念图共存）。
        """
        if embedder is not None:
            self._embedder = embedder
        import json as _json
        rows = store._conn.execute(
            "SELECT node_id, data, summary FROM unified_nodes WHERE domain=?",
            (domain,)).fetchall()
        for row in rows:
            node_id = row["node_id"]
            data = _json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
            if node_id in self._nodes:
                continue
            self._nodes[node_id] = {
                "relations": [],
                "observations": [row["summary"] or ""] if row["summary"] else [],
                "docs": {data.get("source", "")} if data.get("source") else set(),
            }
        edge_rows = store._conn.execute(
            "SELECT edge_type, source_id, target_id, data, weight "
            "FROM unified_edges WHERE domain=?", (domain,)).fetchall()
        for er in edge_rows:
            src, tgt = er["source_id"], er["target_id"]
            if src not in self._nodes or tgt not in self._nodes:
                continue
            edata = _json.loads(er["data"]) if isinstance(er["data"], str) else er["data"]
            kind = edata.get("source_kind", "inferred") if edata else "inferred"
            conf = 0.9 if kind == "extracted" else 0.5
            self._edges.append({
                "source": src, "target": tgt,
                "type": er["edge_type"], "confidence": conf,
                "source_kind": kind,
            })
            self._nodes[src]["relations"].append({
                "target": tgt, "type": er["edge_type"], "confidence": conf,
            })
        self._built = True
        self.build_communities()
        return len(self._nodes)

    # ---- Community layer (GraphRAG 对齐, 2026-08-11, 设计 3) ----

    def build_communities(self) -> int:
        """社区检测 + 摘要（GraphRAG 全局层, SUBGRAPH_EXPANSION_UPGRADE 设计 3）。

        networkx greedy_modularity（无新依赖）; 每社区聚合节点+观测做摘要;
        社区名 → 摘要文本存 _community_summaries, 查询期向量 top-k。
        小图（<4 节点）跳过, 返回 0。
        """
        if len(self._nodes) < 4 or not self._edges:
            self._communities = []
            self._community_summaries = {}
            return 0
        import networkx as nx
        from networkx.algorithms import community as nx_community
        G = nx.Graph()
        G.add_nodes_from(self._nodes.keys())
        for e in self._edges:
            G.add_edge(e["source"], e["target"])
        try:
            comps = nx_community.greedy_modularity_communities(G)
        except Exception:
            comps = []
        self._communities = [sorted(c) for c in comps if len(c) >= 2]
        self._community_summaries = {}
        for c in self._communities:
            parts = []
            for name in c[:8]:
                node = self._nodes.get(name)
                if not node:
                    continue
                parts.append("[%s]" % name)
                parts.extend(node["observations"][:2])
            self._community_summaries[tuple(c)] = " ".join(p for p in parts if p)[:600]
        return len(self._communities)

    def community_top_k(self, query: str, top_k: int = 3,
                        threshold: float = 0.1) -> List[Tuple[List[str], float]]:
        """查询期全局层: query → 社区摘要向量 top-k（轻量, 毫秒级）。

        返回 [(社区节点列表, 相关分)], 命中社区的节点可并入局部扩展 seed。
        """
        if not getattr(self, "_community_summaries", None):
            return []
        qvec = self._encode(query)
        scored = []
        for c, summary in self._community_summaries.items():
            if qvec is not None:
                svec = self._encode(summary)
                sim = float(np.dot(qvec, svec)) if svec is not None else 0.0
            else:
                sim = sum(1 for w in query.lower().split()
                          if w in summary.lower()) * 0.1
            if sim >= threshold:
                scored.append((list(c), sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    # ---- Multi-tier seed finding ----

    def find_seeds(self, query: str, top_k: int = 5,
                   semantic_weight: float = 0.7, keyword_weight: float = 0.3) -> List[Tuple[str, float]]:
        """Multi-tier seed finding: keyword (Tier 1) + semantic (Tier 2).

        Tier 1: keyword overlap — free, always runs.
        Tier 2: cosine similarity — requires embedder, runs if embeddings available.
        Both scores are weighted and merged.
        """
        query_words = query.lower().split()
        has_semantic = self.has_embeddings and self._embedder is not None

        query_vec = None
        if has_semantic:
            query_vec = self._encode(query)

        scored = []
        for name, node in self._nodes.items():
            # Tier 1: keyword score
            kw = _keyword_score(query_words, name.lower())

            # Tier 2: semantic score
            sem = 0.0
            if query_vec is not None and name in self._embeddings:
                sem = float(np.dot(query_vec, self._embeddings[name]))
                sem = max(0.0, sem)  # cosine ∈ [0, 1] for normalized vectors

            # Weighted merge
            if has_semantic and query_vec is not None:
                score = semantic_weight * sem + keyword_weight * kw
            else:
                score = kw  # pure keyword when no embedder

            # Structural boost: well-connected concepts are more important
            degree = len(node["relations"])
            struct_boost = min(0.3, degree * 0.03)
            score = min(1.0, score + struct_boost)

            if score > 0.01:
                scored.append((name, score))

        # Filter: only consider concepts with connections
        scored = [(n, s) for n, s in scored if len(self._nodes[n]["relations"]) > 0 or s > 0.7]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    # ---- Subgraph expansion ----

    def expand_subgraph(self, seeds: List[str], max_hops: int = 2,
                        max_nodes: int = 30) -> Tuple[Set[str], List[dict]]:
        """子图扩展: 默认旧 BFS; dag_layer_expand=True 时走分层扩展 +
        同步剪枝 + 跨锚点桥接（SUBGRAPH_EXPANSION_UPGRADE 设计 1, 2026-08-11）。"""
        if getattr(self, "dag_layer_expand", False):
            return self._expand_subgraph_layered(seeds, max_hops, max_nodes)
        visited: Set[str] = set()
        edges: List[dict] = []
        frontier = set(seeds)

        for hop in range(max_hops):
            next_frontier = set()
            for node_name in frontier:
                if node_name not in self._nodes:
                    continue
                visited.add(node_name)
                for rel in self._nodes[node_name]["relations"]:
                    target = rel["target"]
                    edges.append({
                        "source": node_name, "target": target,
                        "type": rel["type"], "confidence": rel.get("confidence", 0.5), "hop": hop,
                    })
                    if target not in visited and target not in frontier:
                        next_frontier.add(target)
                if len(visited) + len(next_frontier) >= max_nodes:
                    break
            frontier = next_frontier
            if not frontier or len(visited) >= max_nodes:
                break
        visited.update(frontier)
        return visited, edges

    def _expand_subgraph_layered(self, seeds: List[str], max_hops: int = 2,
                                 max_nodes: int = 30) -> Tuple[Set[str], List[dict]]:
        """DAG 分层局部扩展: 每层边界节点邻域 → confidence×relevance 剪枝 →
        预算截断 → 下一层。天然拓扑序, 无环 = 无重复访问, 不会爆。"""
        visited: Set[str] = set()
        edges: List[dict] = []
        # 节点 relevance 缓存（种子最高, 逐层衰减）
        relevance = {s: 1.0 for s in seeds if s in self._nodes}
        frontier = set(relevance)
        threshold = float(getattr(self, "dag_prune_threshold", 0.3))
        budget = int(getattr(self, "dag_budget_per_layer", 12))
        max_hops = int(getattr(self, "dag_max_hops", max_hops))

        for hop in range(max_hops):
            if not frontier or len(visited) >= max_nodes:
                break
            next_frontier = {}
            for node_name in frontier:
                if node_name not in self._nodes:
                    continue
                visited.add(node_name)
                base_rel = relevance.get(node_name, 0.3)
                for rel in self._nodes[node_name]["relations"]:
                    target = rel["target"]
                    conf = float(rel.get("confidence", 0.5))
                    prio = conf * base_rel
                    edges.append({
                        "source": node_name, "target": target,
                        "type": rel["type"], "confidence": conf, "hop": hop,
                        "prio": round(prio, 4),
                    })
                    if target in visited or target in next_frontier:
                        continue
                    if prio < threshold:      # 同步剪枝: 低置信边丢弃
                        continue
                    next_frontier[target] = max(
                        next_frontier.get(target, 0.0), prio)
            # 预算截断: 每层只保留最相关的 top-budget
            ranked = sorted(next_frontier.items(),
                            key=lambda kv: kv[1], reverse=True)[:budget]
            frontier = {n for n, _ in ranked}
            for n, p in ranked:
                relevance[n] = p
            if getattr(self, "dag_bridge_check", True):
                # 跨锚点桥接: 层结果间若有直接边, 优先纳入（防漏桥）
                for a in seeds:
                    if a in self._nodes and a not in visited and a not in frontier:
                        rels = {r["target"] for r in self._nodes[a]["relations"]}
                        if rels.intersection(visited):
                            frontier.add(a)
                            relevance[a] = 0.9
            if len(visited) >= max_nodes:
                break
        visited.update(frontier)
        return visited, edges

    def compile_context(self, query: str, top_k: int = 10,
                        max_hops: int = 2, max_nodes: int = 30) -> List[ContextItem]:
        if not self._built:
            return []

        seeds = self.find_seeds(query, top_k=3)
        if not seeds:
            return []

        seed_names = [s[0] for s in seeds]
        node_set, edge_list = self.expand_subgraph(seed_names, max_hops, max_nodes)

        items = []
        for node_name in node_set:
            if node_name not in self._nodes:
                continue
            node = self._nodes[node_name]
            parts = [f"[CONCEPT] {node_name}"]
            for i, obs_text in enumerate(node["observations"][:5]):
                parts.append(f"  {obs_text[:300]}")
            parts.append(f"  Sources: {', '.join(list(node['docs'])[:3])}")

            related = []
            for e in edge_list:
                if e["source"] == node_name:
                    related.append(f"→ {e['type']} {e['target']}")
                elif e["target"] == node_name:
                    related.append(f"← {e['type']} {e['source']}")
            if related:
                parts.append(f"  Relations: {'; '.join(related[:8])}")

            content = "\n".join(parts)
            seed_score = next((s[1] for s in seeds if s[0] == node_name), 0.3)
            degree = len(node["relations"])
            relevance = min(1.0, seed_score + min(0.5, degree * 0.1))

            items.append(ContextItem(
                source="graph",
                content={"concept": node_name, "observations": node["observations"]},
                text=content,
                relevance=relevance,
                metadata={"doc": sorted(node["docs"])[:3], "concept": node_name},
            ))

        items.sort(key=lambda x: x.relevance, reverse=True)
        return items[:top_k]

    def stats(self) -> dict:
        return {
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "embeddings": len(self._embeddings),
            "built": self._built,
        }

    # ── 图导航 API（CONTENT_TO_GRAPH 设计 4, 2026-08-11）──

    def neighbors(self, node_name: str, edge_type: str = None) -> List[str]:
        """返回节点的邻居（可选按边类型过滤）。"""
        node = self._nodes.get(node_name)
        if not node:
            return []
        out = []
        for rel in node["relations"]:
            if edge_type and rel["type"] != edge_type:
                continue
            out.append(rel["target"])
        return out

    def callers(self, node_name: str, edge_type: str = None) -> List[str]:
        """反向边: 谁引用了该节点（溯源）。"""
        out = []
        for src, node in self._nodes.items():
            for rel in node["relations"]:
                if rel["target"] != node_name:
                    continue
                if edge_type and rel["type"] != edge_type:
                    continue
                out.append(src)
        return out

    def path(self, a: str, b: str, max_hops: int = 4) -> Optional[List[str]]:
        """双链最短路径（BFS）: 文档间导航, 防"锚点孤立"。"""
        if a not in self._nodes or b not in self._nodes:
            return None
        from collections import deque
        visited = {a: None}
        queue = deque([a])
        while queue and max_hops >= 0:
            cur = queue.popleft()
            if cur == b:
                path = []
                node = b
                while node is not None:
                    path.append(node)
                    node = visited[node]
                return list(reversed(path))
            for nb in self.neighbors(cur):
                if nb not in visited:
                    visited[nb] = cur
                    queue.append(nb)
            max_hops -= 1
        return None



# ============================================================================
# ConceptGraphSource
# ============================================================================

class ConceptGraphSource(ContextSource):
    """Graph-based subgraph compilation source with multi-tier matching.

    name="knowledge" — DomainSelector's K domain finds this source.

    Matching tiers:
      Tier 0: Concept extraction (regex) — built at ingest time
      Tier 1: Keyword overlap — always available
      Tier 2: Semantic embedding (BGE) — active when embedder provided
      Tier 3: Co-occurrence graph traversal (BFS expansion)

    Falls back to DocumentSource (keyword) if graph isn't built.
    """

    def __init__(self, observation_pool=None, max_hops: int = 2, max_nodes: int = 30,
                 embedder: Callable[[str], Any] = None,
                 semantic_weight: float = 0.7, keyword_weight: float = 0.3):
        self._pool = observation_pool
        self._graph = ConceptGraph(embedder=embedder)
        self._max_hops = max_hops
        self._max_nodes = max_nodes
        self._semantic_weight = semantic_weight
        self._keyword_weight = keyword_weight

    @property
    def name(self) -> str:
        return "knowledge"

    def build_graph(self) -> int:
        if self._pool is None:
            return 0
        return self._graph.build_from_pool(self._pool)

    def retrieve(self, query: str, top_k: int = 10, **kwargs) -> List[ContextItem]:
        if not self._graph._built:
            self.build_graph()
        if self._graph._built and len(self._graph._nodes) > 0:
            items = self._graph.compile_context(query, top_k=top_k,
                                                max_hops=self._max_hops,
                                                max_nodes=self._max_nodes)
            if items:
                return items
        from core.agent.context.source import DocumentSource
        return DocumentSource(observation_pool=self._pool).retrieve(query, top_k=top_k, **kwargs)

    def stats(self) -> dict:
        return self._graph.stats()
