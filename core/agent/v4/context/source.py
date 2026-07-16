"""ContextSource: abstract interface for context retrieval from knowledge domains.

Design: Source -> Rank -> Assemble pipeline.
Each source independently retrieves from its domain.
The ContextAssembler aggregates and ranks results.

Key design: ContextItem.content is the original object (for uniformity).
ContextItem.text is the pre-extracted searchable text (for assembler).
Sources are responsible for populating .text at retrieval time.
"""
from __future__ import annotations
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ContextItem:
    """A single context item from a knowledge source.

    content: Original object (ObservationBundle, KnowledgeNode, etc.) — kept for uniformity.
    text: Pre-extracted searchable text — populated by source at retrieval time.
    relevance: Ranking score [0, 1].
    """
    source: str
    content: Any
    text: str = ""
    relevance: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class CrossDomainContext:
    """Aggregated context from multiple sources."""
    intent: str
    items: List[ContextItem] = field(default_factory=list)
    source_stats: Dict[str, int] = field(default_factory=dict)
    total_items: int = 0

    def by_source(self, source_name: str) -> List[ContextItem]:
        return [i for i in self.items if i.source == source_name]

    def top_k(self, k: int) -> List[ContextItem]:
        return sorted(self.items, key=lambda x: x.relevance, reverse=True)[:k]


class ContextSource(ABC):
    """Abstract interface for context retrieval.

    Each source represents one knowledge domain:
    Observation, Knowledge, Skill, World, Engineering, Document, etc.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable source name."""

    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        """Retrieve relevant context items for a query."""


# ============================================================================
# Helpers
# ============================================================================

def _keyword_score(query_words: List[str], text: str) -> float:
    """Weighted keyword overlap score with stop-word filtering.

    Long/specific terms get higher weight; common short words (stop words)
    contribute less. This prevents generic words from inflating all scores.
    """
    if not query_words or not text:
        return 0.0
    text_lower = text.lower()
    total_weight = 0.0
    matched_weight = 0.0
    
    # Stop words: common Chinese/English particles that don't carry topic signal
    _stop_words = {
        '的', '是', '了', '在', '和', '也', '就', '都', '而', '及', '与',
        'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been',
        'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
        '什么', '怎么', '如何', '为什么', '哪个', '哪里', '谁', '哪',
        '给我', '讲一下', '具体', '详细', '细节', '一下', '我', '你', '他',
        '这个', '那个', '这些', '那些', '一个', '可以', '会', '要',
    }
    
    for kw in query_words:
        if not kw or kw in _stop_words:
            continue
        # Weight: longer = more specific = higher weight
        weight = min(1.0, len(kw) / 6.0)
        total_weight += weight
        if kw in text_lower:
            matched_weight += weight
    
    if total_weight == 0:
        return 0.0
    return min(1.0, matched_weight / total_weight)


def _extract_bundle_text(bundle) -> str:
    """Extract searchable text from an ObservationBundle.

    Pulls from all domain_observations: summary + interpretation summaries
    (which contain actual document paragraph text, NOT observation_type labels).
    Objects/actions are excluded because they contain classification labels,
    not content useful for retrieval or LLM consumption.
    """
    parts: List[str] = []
    for dom_obs in getattr(bundle, "domain_observations", {}).values():
        s = getattr(dom_obs, "summary", "")
        if s and s != "Document ingestion" and not s.startswith("Document ingestion"):
            parts.append(s)
        # Extract actual content from interpretations (this is where
        # DocumentObservation.raw_text ends up after to_observation_bundle())
        for interp in getattr(dom_obs, "interpretations", []):
            if isinstance(interp, dict):
                summary = interp.get("summary", "")
                # Filter out headings that are too short to be useful
                if len(summary) > 15:  # actual paragraph text, not just a heading
                    parts.append(summary)
                elif not any(len(p) > 50 for p in parts):  # keep short text only if no long text yet
                    parts.append(summary)
            else:
                summary = getattr(interp, "summary", "")
                if len(summary) > 15:
                    parts.append(summary)
                elif not any(len(p) > 50 for p in parts):
                    parts.append(summary)
    return " ".join(p for p in parts if p)


# ============================================================================
# Observation source
# ============================================================================

class ObservationSource(ContextSource):
    """Retrieves from ObservationPool with keyword matching.

    Returns ContextItem with content=ObservationBundle (object, for uniformity)
    and text=extracted searchable text (for assembler).
    """

    def __init__(self, pool=None):
        self._pool = pool

    @property
    def name(self) -> str:
        return "observation"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        if self._pool is None:
            return []
        try:
            query_words = query.lower().split()
            seen_ids: set = set()
            items: List[ContextItem] = []

            for domain in self._pool.stats().get("by_domain", {}):
                bundles = self._pool.get_by_domain(domain)
                for bundle in bundles:
                    if bundle.bundle_id in seen_ids:
                        continue
                    seen_ids.add(bundle.bundle_id)

                    # Per-interpretation scoring: each paragraph scored individually.
                    # Only the best-matching paragraphs contribute to the document's
                    # relevance. This prevents documents about CLI from matching
                    # "Context Compiler" just because one sentence mentions "Context".
                    best_score = 0.0
                    best_text = ""
                    for dom_obs in getattr(bundle, "domain_observations", {}).values():
                        for interp in getattr(dom_obs, "interpretations", []):
                            if isinstance(interp, dict):
                                summary = interp.get("summary", "")
                            else:
                                summary = getattr(interp, "summary", "")
                            if not summary or len(summary) < 15:
                                continue
                            score = _keyword_score(query_words, summary)
                            if score > best_score:
                                best_score = score
                                best_text = summary

                    if best_score == 0:
                        continue

                    # Assemble top-3 matching paragraphs as context text
                    scored_paras = []
                    for dom_obs in getattr(bundle, "domain_observations", {}).values():
                        for interp in getattr(dom_obs, "interpretations", []):
                            if isinstance(interp, dict):
                                summary = interp.get("summary", "")
                            else:
                                summary = getattr(interp, "summary", "")
                            if not summary or len(summary) < 15:
                                continue
                            s = _keyword_score(query_words, summary)
                            if s > 0:
                                scored_paras.append((s, summary))
                    scored_paras.sort(key=lambda x: x[0], reverse=True)
                    context_text = " | ".join(p[1][:300] for p in scored_paras[:3])

                    items.append(ContextItem(
                        source=self.name,
                        content=bundle,
                        text=context_text,
                        relevance=best_score,
                        metadata={
                            "bundle_id": bundle.bundle_id,
                            "event_id": getattr(bundle, "event_id", ""),
                            "domain": domain,
                            "best_paragraph_score": round(best_score, 3),
                            "matching_paragraphs": len(scored_paras),
                        },
                    ))

            items.sort(key=lambda x: x.relevance, reverse=True)
            return [i for i in items if i.relevance > 0][:top_k]
        except Exception as e:
            logger.warning("ObservationSource retrieval failed: %s", e)
            return []


# ============================================================================
# Document source (keyword-based)
# ============================================================================

class DocumentSource(ContextSource):
    """Retrieves from DocumentObservationBundle via keyword matching.

    Searches against raw_text + concepts + heading_path of each
    DocumentObservation inside the bundle. This is the v4 DIL adapter
    that makes ingested documents reachable by ContextAssembler.

    name="knowledge" so DomainSelector's K domain can find this source
    via _find_source().
    """

    def __init__(self, observation_pool=None):
        self._pool = observation_pool

    @property
    def name(self) -> str:
        return "document"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        if self._pool is None:
            return []
        try:
            bundles = self._pool.get_by_domain("document")
            if not bundles:
                return []

            query_words = query.lower().split()
            items: List[ContextItem] = []

            for bundle in bundles:
                dom_obs = getattr(bundle, "domain_observations", {}).get("document")
                if dom_obs is None:
                    continue

                # Build searchable text from the document domain observation
                text_parts: List[str] = []
                text_parts.append(getattr(dom_obs, "summary", ""))

                # Each interpretation carries the actual document content
                for interp in getattr(dom_obs, "interpretations", []):
                    if isinstance(interp, dict):
                        text_parts.append(interp.get("summary", ""))
                    else:
                        text_parts.append(getattr(interp, "summary", ""))

                text_parts.extend(getattr(dom_obs, "objects", []))
                full_text = " ".join(t for t in text_parts if t)
                if not full_text:
                    continue

                score = _keyword_score(query_words, full_text)
                if score == 0:
                    continue

                # Boost by observation type distribution (definitions/constraints are high-value)
                meta_dict = getattr(dom_obs, "meta", {}) or {}
                obs_types = meta_dict.get("observation_types", [])
                type_boost = 0.05 if obs_types else 0.0

                items.append(ContextItem(
                    source=self.name,
                    content=bundle,
                    text=full_text,
                    relevance=min(1.0, score + type_boost),
                    metadata={
                        "bundle_id": getattr(bundle, "bundle_id", ""),
                        "event_id": getattr(bundle, "event_id", ""),
                        "source_path": meta_dict.get("source_path", ""),
                        "observation_types": obs_types,
                    },
                ))

            items.sort(key=lambda x: x.relevance, reverse=True)
            return items[:top_k]
        except Exception as e:
            logger.warning("DocumentSource retrieval failed: %s", e)
            return []


# ============================================================================
# Hybrid document source (semantic + keyword dual-path)
# ============================================================================

class HybridDocumentSource(DocumentSource):
    """Hybrid retrieval for documents: semantic embedding + keyword matching.

    Uses an embedder to compute query/document embeddings and cosine similarity,
    then merges with keyword score. Falls back to pure keyword matching
    if no embedder is available.

    This is the RAG-style retrieval that maximizes recall on the 88 ingested
    design documents by leveraging semantic similarity, not just keyword overlap.
    """

    def __init__(self, observation_pool=None, embedder: Callable[[str], Any] = None,
                 semantic_weight: float = 0.7, keyword_weight: float = 0.3):
        super().__init__(observation_pool)
        self._embedder = embedder
        self._semantic_weight = semantic_weight
        self._keyword_weight = keyword_weight
        self._doc_cache: Dict[str, Tuple[str, Any]] = {}  # bundle_id -> (text, embedding)

    @property
    def name(self) -> str:
        return "document"

    def _get_or_compute_embedding(self, bundle_id: str, text: str) -> Optional[Any]:
        """Cache document embeddings to avoid recomputation on every query."""
        if self._embedder is None:
            return None
        if bundle_id in self._doc_cache:
            cached_text, cached_vec = self._doc_cache[bundle_id]
            if cached_text == text:
                return cached_vec
        try:
            vec = self._embedder(text)
            self._doc_cache[bundle_id] = (text, vec)
            return vec
        except Exception:
            return None

    @staticmethod
    def _cosine_similarity(vec_a, vec_b) -> float:
        """Compute cosine similarity between two vectors (list or ndarray)."""
        try:
            import numpy as np
            a = np.asarray(vec_a, dtype=np.float64)
            b = np.asarray(vec_b, dtype=np.float64)
            if a.shape != b.shape:
                return 0.0
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return float(np.dot(a, b) / (norm_a * norm_b))
        except Exception:
            return 0.0

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        if self._pool is None:
            return []
        if self._embedder is None:
            # No embedder — fall back to pure keyword matching
            return super().retrieve(query, top_k, **kwargs)

        try:
            bundles = self._pool.get_by_domain("document")
            if not bundles:
                return []

            query_words = query.lower().split()
            query_vec = self._get_or_compute_embedding("__query__", query)
            items: List[ContextItem] = []

            for bundle in bundles:
                dom_obs = getattr(bundle, "domain_observations", {}).get("document")
                if dom_obs is None:
                    continue

                # Build searchable text (same logic as parent)
                text_parts: List[str] = [getattr(dom_obs, "summary", "")]
                for interp in getattr(dom_obs, "interpretations", []):
                    if isinstance(interp, dict):
                        text_parts.append(interp.get("summary", ""))
                    else:
                        text_parts.append(getattr(interp, "summary", ""))
                text_parts.extend(getattr(dom_obs, "objects", []))
                full_text = " ".join(t for t in text_parts if t)
                if not full_text:
                    continue

                # Dual-path scoring
                kw_score = _keyword_score(query_words, full_text)

                sem_score = 0.0
                bundle_id = getattr(bundle, "bundle_id", "")
                doc_vec = self._get_or_compute_embedding(bundle_id, full_text)
                if query_vec is not None and doc_vec is not None:
                    sem_score = max(0.0, self._cosine_similarity(query_vec, doc_vec))

                # Weighted merge
                relevance = self._semantic_weight * sem_score + self._keyword_weight * kw_score
                if relevance < 0.01:
                    continue

                meta_dict = getattr(dom_obs, "meta", {}) or {}
                items.append(ContextItem(
                    source=self.name,
                    content=bundle,
                    text=full_text,
                    relevance=min(1.0, relevance),
                    metadata={
                        "bundle_id": bundle_id,
                        "event_id": getattr(bundle, "event_id", ""),
                        "source_path": meta_dict.get("source_path", ""),
                        "semantic_score": round(sem_score, 4),
                        "keyword_score": round(kw_score, 4),
                        "observation_types": meta_dict.get("observation_types", []),
                    },
                ))

            items.sort(key=lambda x: x.relevance, reverse=True)
            return items[:top_k]
        except Exception as e:
            logger.warning("HybridDocumentSource retrieval failed: %s", e)
            return super().retrieve(query, top_k, **kwargs)


# ============================================================================
# Knowledge / Skill / World / Engineering sources
# ============================================================================

class KnowledgeSource(ContextSource):
    """Retrieves from frozen Knowledge nodes via O(n) keyword matching."""

    def __init__(self, knowledge_nodes: List[Any] = None):
        self._nodes = knowledge_nodes or []

    @property
    def name(self) -> str:
        return "knowledge"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        query_words = query.lower().split()
        scored = []
        for node in self._nodes:
            text = getattr(node, 'statement', str(node)).lower()
            score = sum(1 for kw in query_words if kw in text)
            if score > 0:
                scored.append(ContextItem(
                    source=self.name,
                    content=node,
                    text=getattr(node, 'statement', str(node)),
                    relevance=min(1.0, score / len(query_words)),
                ))
        scored.sort(key=lambda x: x.relevance, reverse=True)
        return scored[:top_k]


class SkillSource(ContextSource):
    """Retrieves from SkillPool via O(n) keyword matching."""

    def __init__(self, skill_pool=None):
        self._pool = skill_pool

    @property
    def name(self) -> str:
        return "skill"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        if self._pool is None:
            return []
        try:
            skills = getattr(self._pool, 'list_all', lambda: [])()
            query_words = query.lower().split()
            items = []
            for skill in skills:
                name = getattr(skill, 'name', str(skill)).lower()
                score = sum(1 for kw in query_words if kw in name)
                if score > 0:
                    items.append(ContextItem(
                        source=self.name,
                        content=skill,
                        text=getattr(skill, 'name', str(skill)),
                        relevance=min(1.0, score / max(1, len(query_words))),
                    ))
            items.sort(key=lambda x: x.relevance, reverse=True)
            return items[:top_k]
        except Exception:
            return []


class WorldSource(ContextSource):
    """Retrieves from StructuralWorldGraph via ContextCompiler."""

    def __init__(self, world_graph=None):
        self._graph = world_graph

    @property
    def name(self) -> str:
        return "world"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        if self._graph is None:
            return []
        try:
            from core.agent.v4.world.compiler import StructuralContextCompiler
            compiler = StructuralContextCompiler()
            subgraph = compiler.compile_subgraph(self._graph, intent=query, max_nodes=top_k * 2)
            items = []
            for node in subgraph.nodes[:top_k]:
                text = getattr(node, 'name', str(node))
                items.append(ContextItem(
                    source=self.name,
                    content=node,
                    text=text,
                    relevance=node.backbone_score if node.backbone_score > 0 else 0.3,
                ))
            return items
        except Exception:
            return []


class EngineeringSource(ContextSource):
    """Retrieves from Engineering chain (stub)."""

    @property
    def name(self) -> str:
        return "engineering"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        return []


# ============================================================================
# Vector-based sources (v4)
# ============================================================================

class VectorKnowledgeSource(KnowledgeSource):
    """Retrieves from Knowledge nodes using vector similarity.

    Requires a VectorStore with pre-computed embeddings.
    Falls back to keyword matching if no embedding for a node.
    """

    def __init__(self, nodes=None, vector_store=None, embedder=None):
        super().__init__(nodes)
        self._vector_store = vector_store
        self._embedder = embedder

    @property
    def name(self) -> str:
        return "knowledge"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        if self._vector_store is None or self._embedder is None:
            return super().retrieve(query, top_k, **kwargs)
        try:
            query_vec = self._embedder.encode(query) if hasattr(self._embedder, 'encode') else self._embedder(query)
            if isinstance(query_vec, list):
                __import__('numpy')
                import numpy as np
                query_vec = np.array(query_vec)
            results = self._vector_store.search(query_vec, top_k)
            items = []
            for node_id, score in results:
                for node in self._nodes:
                    if hasattr(node, 'knowledge_id') and node.knowledge_id == node_id:
                        items.append(ContextItem(
                            source=self.name,
                            content=node,
                            text=getattr(node, 'statement', str(node)),
                            relevance=float(score),
                        ))
                        break
            return items
        except Exception:
            return super().retrieve(query, top_k, **kwargs)


# ============================================================================
# Hybrid sources (v4) — semantic + keyword dual-path
# ============================================================================

class HybridKnowledgeSource(KnowledgeSource):
    """Hybrid retrieval: semantic + keyword with weighted merge."""

    def __init__(self, nodes=None, hybrid_index=None):
        super().__init__(nodes)
        self._hybrid_index = hybrid_index

    @property
    def name(self) -> str:
        return "knowledge"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        if self._hybrid_index is None:
            return super().retrieve(query, top_k, **kwargs)
        try:
            results = self._hybrid_index.search(query, top_k)
            items = []
            for node_id, score in results:
                for node in self._nodes:
                    node_id_attr = getattr(node, 'knowledge_id', None)
                    if node_id_attr and node_id_attr == node_id:
                        items.append(ContextItem(
                            source=self.name,
                            content=node,
                            text=getattr(node, 'statement', str(node)),
                            relevance=float(score),
                            metadata={"retrieval": "hybrid"},
                        ))
                        break
            return items
        except Exception:
            return super().retrieve(query, top_k, **kwargs)


class HybridSkillSource(SkillSource):
    """Hybrid retrieval for SkillPool: semantic + keyword."""

    def __init__(self, skill_pool=None, hybrid_index=None):
        super().__init__(skill_pool)
        self._hybrid_index = hybrid_index

    @property
    def name(self) -> str:
        return "skill_hybrid"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        if self._hybrid_index is None:
            return super().retrieve(query, top_k, **kwargs)
        try:
            results = self._hybrid_index.search(query, top_k)
            items = []
            for skill_id, score in results:
                skills = getattr(self._pool, 'list_all', lambda: [])()
                for skill in skills:
                    sid = getattr(skill, 'skill_id', getattr(skill, 'name', str(skill)))
                    if sid == skill_id:
                        items.append(ContextItem(
                            source=self.name,
                            content=skill,
                            text=getattr(skill, 'name', str(skill)),
                            relevance=float(score),
                            metadata={"retrieval": "hybrid"},
                        ))
                        break
            return items
        except Exception:
            return super().retrieve(query, top_k, **kwargs)


# ============================================================================
# TieredVectorStore (backward compatibility)
# ============================================================================

class TieredVectorStore:
    """Auto-switches between SQLite and Milvus based on vector count."""

    def __init__(self, sqlite_store, milvus_store=None, threshold: int = 100_000):
        self._sqlite = sqlite_store
        self._milvus = milvus_store
        self._threshold = threshold

    def put(self, node_id: str, vector, metadata=None):
        self._sqlite.put(node_id, vector, metadata)
        if self._milvus and self._sqlite.count > self._threshold:
            self._milvus.put(node_id, vector, metadata)

    def search(self, query_vector, top_k=10):
        if self._milvus and self._sqlite.count > self._threshold:
            return self._milvus.search(query_vector, top_k)
        return self._sqlite.search(query_vector, top_k)

    @property
    def count(self):
        return self._sqlite.count


# ============================================================================
# Causal retrieval source (v3_2 BehaviorGraph + CausalSubstrate adapter)
# ============================================================================

class CausalSource(ContextSource):
    """Retrieves causal context from v3_2 BehaviorGraph via CausalSubstrate."""

    def __init__(
        self,
        behavior_graph=None,
        causal_substrate=None,
        max_chain_depth: int = 5,
        min_causal_score: float = 0.0,
    ):
        self._graph = behavior_graph
        self._substrate = causal_substrate
        self._max_depth = max_chain_depth
        self._min_score = min_causal_score

    @property
    def name(self) -> str:
        return "causal"

    def retrieve(self, query: str, top_k: int = 5, **kwargs) -> List[ContextItem]:
        if self._graph is None:
            return []
        try:
            keywords = query.lower().split()
            matched_steps = []
            for step in getattr(self._graph, "nodes", {}).values():
                summary = getattr(step, "action_summary", "").lower()
                score = sum(1 for kw in keywords if kw in summary)
                if score > 0:
                    matched_steps.append((step, score))

            if not matched_steps:
                return []

            matched_steps.sort(key=lambda x: x[1], reverse=True)
            seed_steps = matched_steps[:top_k]

            items: List[ContextItem] = []
            visited_chains = set()

            for seed_step, _ in seed_steps:
                step_id = getattr(seed_step, "step_id", None)
                if not step_id:
                    continue

                chain = []
                if hasattr(self._graph, "get_chain"):
                    chain = self._graph.get_chain(step_id, max_depth=self._max_depth)
                if not chain:
                    continue

                chain_sig = step_id + ":" + ",".join(
                    getattr(s, "step_id", "") for s, _ in chain
                )
                if chain_sig in visited_chains:
                    continue
                visited_chains.add(chain_sig)

                causal_results = []
                if self._substrate is not None and hasattr(self._substrate, "process_chain"):
                    step_list = [seed_step] + [s for s, _ in chain]
                    causal_results = self._substrate.process_chain(step_list)

                for result in causal_results:
                    edge_key = result.get("edge_key", "")
                    prior = result.get("structural_prior", 0.0)
                    if prior < self._min_score:
                        continue

                    edge = None
                    if hasattr(self._graph, "edges"):
                        edge = self._graph.edges.get(edge_key)

                    from_step = None
                    to_step = None
                    if edge and hasattr(self._graph, "nodes"):
                        from_step = self._graph.nodes.get(getattr(edge, "from_step_id", ""))
                        to_step = self._graph.nodes.get(getattr(edge, "to_step_id", ""))

                    content_str = self._format_causal_entry(edge, from_step, to_step, prior)
                    items.append(ContextItem(
                        source=self.name,
                        content=content_str,
                        text=content_str,
                        relevance=prior,
                        metadata={
                            "edge_key": edge_key,
                            "structural_prior": prior,
                            "from_summary": getattr(from_step, "action_summary", "") if from_step else "",
                            "to_summary": getattr(to_step, "action_summary", "") if to_step else "",
                            "seed_step_id": step_id,
                            "chain_depth": len(chain),
                        },
                    ))

            seen_edges = set()
            unique_items = []
            for item in sorted(items, key=lambda x: x.relevance, reverse=True):
                ek = item.metadata.get("edge_key", "")
                if ek not in seen_edges:
                    seen_edges.add(ek)
                    unique_items.append(item)
            return unique_items[:top_k]
        except Exception as e:
            logger.warning("CausalSource retrieval failed: %s", e)
            return []

    @staticmethod
    def _format_causal_entry(edge, from_step, to_step, prior: float) -> str:
        fs = getattr(from_step, "action_summary", "?") if from_step else "?"
        ts = getattr(to_step, "action_summary", "?") if to_step else "?"
        ft = getattr(from_step, "action_type", "") if from_step else ""
        tt = getattr(to_step, "action_type", "") if to_step else ""
        sc = getattr(edge, "success_rate", 0.5) if edge else 0.5
        return (
            f"Causal: [{ft}] {fs} -> [{tt}] {ts} "
            f"(prior={prior:.2f}, success_rate={sc:.2f})"
        )


class CausalSubstrateAdapter:
    """Lazy initializer for CausalSubstrate from BehaviorGraph."""

    def __init__(self, behavior_graph):
        self._graph = behavior_graph
        self._substrate = None

    @property
    def substrate(self):
        if self._substrate is None and self._graph is not None:
            try:
                from core.agent.v3_2.causal_substrate.causal_substrate import CausalSubstrate
                self._substrate = CausalSubstrate(self._graph)
            except Exception as e:
                logger.warning("Failed to create CausalSubstrate: %s", e)
        return self._substrate
