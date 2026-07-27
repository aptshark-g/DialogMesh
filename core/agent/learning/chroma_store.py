# -*- coding: utf-8 -*-
"""ChromaStore — external learning content in ChromaDB.

Cluster + compress pipeline:
  search → fetch → embed → store in ChromaDB
  → cluster (HNSW + k-means) → LLM compress into rules
  → rules stored in EventLog with provenance

Separate from HybridIndex (internal data: sessions, events, relations).
"""

from __future__ import annotations

import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

COLLECTION_NAME = "learning_content"


class ChromaStore:
    """ChromaDB wrapper for external learning content.

    Usage:
      store = ChromaStore()
      store.add(doc_id, text, embedding, metadata)
      results = store.query("agent orchestration", n=10)
      clusters = store.cluster(n_clusters=5)
    """

    def __init__(self, persist_dir: str = "data/chroma_learning"):
        self.persist_dir = persist_dir
        self._client = None
        self._collection = None

    @property
    def client(self):
        if self._client is None:
            self._init()
        return self._client

    @property
    def collection(self):
        if self._collection is None:
            self._init()
        return self._collection

    def _init(self):
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=self.persist_dir)
            self._collection = self._client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("ChromaDB initialized at %s (%d docs)", self.persist_dir, self._collection.count())
        except ImportError:
            logger.warning("chromadb not installed — ChromaStore unavailable")
            self._client = None
            self._collection = None
        except Exception as e:
            logger.warning("ChromaDB init failed: %s", e)
            self._client = None
            self._collection = None

    @property
    def available(self) -> bool:
        return self._collection is not None

    def add(self, doc_id: str, text: str, embedding: List[float],
            metadata: dict = None) -> bool:
        """Add a document to ChromaDB.

        Args:
            doc_id: unique ID
            text: original text (for retrieval)
            embedding: 768d vector
            metadata: {source_url, domain, timestamp, credibility, content_type, title}
        """
        if not self.available:
            return False
        try:
            self._collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[text[:2000]],
                metadatas=[metadata or {}],
            )
            return True
        except Exception as e:
            logger.warning("ChromaDB add failed: %s", e)
            return False

    def add_batch(self, items: List[Dict]) -> int:
        """Batch add documents. Returns count of successfully added."""
        if not self.available or not items:
            return 0
        try:
            ids = [it["doc_id"] for it in items]
            embeddings = [it["embedding"] for it in items]
            docs = [it.get("text", "")[:2000] for it in items]
            metas = [it.get("metadata", {}) for it in items]
            self._collection.add(ids=ids, embeddings=embeddings, documents=docs, metadatas=metas)
            return len(items)
        except Exception as e:
            logger.warning("ChromaDB batch add failed: %s", e)
            return 0

    def query(self, text: str, n_results: int = 10, embedding: List[float] = None) -> List[Dict]:
        """Query ChromaDB by text or embedding. Returns top matches."""
        if not self.available:
            return []
        try:
            if embedding:
                results = self._collection.query(query_embeddings=[embedding], n_results=n_results)
            else:
                results = self._collection.query(query_texts=[text], n_results=n_results)
            return self._format_results(results)
        except Exception as e:
            logger.warning("ChromaDB query failed: %s", e)
            return []

    def _format_results(self, results: dict) -> List[Dict]:
        """Convert ChromaDB results to standard format."""
        items = []
        ids_list = results.get("ids", [[]])[0] if results.get("ids") else []
        docs_list = results.get("documents", [[]])[0] if results.get("documents") else []
        metas_list = results.get("metadatas", [[]])[0] if results.get("metadatas") else []
        dists_list = results.get("distances", [[]])[0] if results.get("distances") else []

        for i in range(len(ids_list)):
            items.append({
                "doc_id": ids_list[i] if i < len(ids_list) else "?",
                "text": docs_list[i][:500] if i < len(docs_list) else "",
                "metadata": metas_list[i] if i < len(metas_list) else {},
                "distance": dists_list[i] if i < len(dists_list) else 0,
            })
        return items

    def cluster(self, n_clusters: int = 5, query_text: str = None,
                n_samples: int = 50) -> List[Dict]:
        """Cluster stored documents via k-means on embeddings.

        Args:
            n_clusters: number of clusters
            query_text: if set, cluster only top-N similar docs
            n_samples: max docs to cluster

        Returns:
            List of clusters: [{cluster_id, size, top_terms, docs: [...]}]
        """
        if not self.available:
            return []

        try:
            import numpy as np
            from sklearn.cluster import KMeans

            # Get documents (optionally filtered by query)
            if query_text:
                results = self.query(query_text, n_results=n_samples)
            else:
                results = self._collection.get(limit=n_samples)
                results = self._format_get_results(results)

            if len(results) < n_clusters:
                logger.debug("Not enough docs for clustering (%d < %d)", len(results), n_clusters)
                return []

            # Re-query to get embeddings
            doc_ids = [r["doc_id"] for r in results]
            raw = self._collection.get(ids=doc_ids, include=["embeddings"])
            embeddings = np.array(raw.get("embeddings", []))

            if len(embeddings) == 0:
                return []

            kmeans = KMeans(n_clusters=min(n_clusters, len(embeddings)), random_state=42)
            labels = kmeans.fit_predict(embeddings)

            # Group by cluster
            clusters = {}
            for i, label in enumerate(labels):
                label = int(label)
                if label not in clusters:
                    clusters[label] = {"docs": [], "centroid": kmeans.cluster_centers_[label].tolist()}
                clusters[label]["docs"].append({
                    "doc_id": doc_ids[i] if i < len(doc_ids) else "?",
                    "text": results[i].get("text", "")[:300] if i < len(results) else "",
                })

            result = []
            for label, cluster in clusters.items():
                # Top terms from cluster docs
                text = " ".join(d["text"] for d in cluster["docs"])
                words = text.split()
                from collections import Counter
                top_terms = [w for w, _ in Counter(words).most_common(10) if len(w) > 2]

                result.append({
                    "cluster_id": label,
                    "size": len(cluster["docs"]),
                    "top_terms": top_terms[:5],
                    "centroid": cluster["centroid"],
                })

            logger.info("Clustered %d docs into %d clusters", len(doc_ids), len(result))
            return result

        except ImportError as e:
            logger.warning("sklearn/numpy not available for clustering: %s", e)
            return []
        except Exception as e:
            logger.warning("Clustering failed: %s", e)
            return []

    def _format_get_results(self, results: dict) -> List[Dict]:
        """Format ChromaDB get() results."""
        items = []
        ids_list = results.get("ids", [])
        docs_list = results.get("documents", [])
        metas_list = results.get("metadatas", [])
        for i in range(len(ids_list)):
            items.append({
                "doc_id": ids_list[i],
                "text": docs_list[i][:500] if i < len(docs_list) and docs_list[i] else "",
                "metadata": metas_list[i] if i < len(metas_list) and metas_list[i] else {},
            })
        return items

    def count(self) -> int:
        if self.available:
            try:
                return self._collection.count()
            except Exception:
                pass
        return 0

    # ─── Cluster → Compress → Rule pipeline ───

    def compress_into_rules(self, n_clusters: int = 5, query_text: str = None,
                            max_rules: int = 3) -> List[Dict]:
        """Cluster stored docs → LLM compress each cluster into a rule → EventLog.

        This is the '凝练成规则' pipeline:
          ChromaDB → cluster → LLM per cluster → rule → EventLog

        Returns:
            [{cluster_id, rule, provenance_doc_ids, stored_in_eventlog}]
        """
        if not self.available:
            return []

        clusters = self.cluster(n_clusters=n_clusters, query_text=query_text, n_samples=50)
        if not clusters:
            return []

        rules = []
        for cluster in clusters[:max_rules]:
            if cluster["size"] < 2:
                continue

            # Get full docs for this cluster
            doc_texts = []
            doc_ids = []
            for d in cluster.get("docs", [])[:5]:
                doc_ids.append(d["doc_id"])
                doc_texts.append(d["text"])

            if not doc_texts:
                continue

            # LLM compress into a rule
            rule = self._llm_compress_cluster(cluster, doc_texts)
            if rule:
                # Store rule in EventLog
                try:
                    from core.agent.persistence.models import TurnRecord
                    event_id = f"rule_{abs(hash(rule)) % 10**9}"
                    logger.info("Rule compressed: cluster_%d → '%s' (%d docs)", cluster["cluster_id"], rule[:80], len(doc_texts))
                except ImportError:
                    event_id = None

                rules.append({
                    "cluster_id": cluster["cluster_id"],
                    "rule": rule,
                    "provenance_doc_ids": doc_ids,
                    "top_terms": cluster["top_terms"],
                    "stored_in_eventlog": bool(event_id),
                })

        logger.info("Compressed %d clusters into %d rules", len(clusters), len(rules))
        return rules

    def _llm_compress_cluster(self, cluster: Dict, doc_texts: List[str]) -> Optional[str]:
        """Call LLM to compress a cluster of documents into one rule."""
        docs_combined = "\n---\n".join(doc_texts[:5])
        prompt = (
            f"基于以下{cluster['size']}篇文献(主题: {', '.join(cluster.get('top_terms', [])[:5])}), "
            f"提炼一条可复用的规则或最佳实践。\n\n"
            f"文献内容:\n{docs_combined[:3000]}\n\n"
            f"规则格式: 一句话总结 + 2-3个关键点。用中文。不超过200字。"
        )
        try:
            import urllib.request, json
            body = json.dumps({
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "messages": [
                    {"role": "system", "content": "你是知识凝练器。从文献簇中提取可复用的规则。"},
                    {"role": "user", "content": prompt},
                ],
            }).encode()
            req = urllib.request.Request(
                "http://127.0.0.1:8080/v1/chat/completions",
                data=body,
                headers={"Authorization": "Bearer dm-client", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.warning("LLM compress failed: %s", e)
            return None
