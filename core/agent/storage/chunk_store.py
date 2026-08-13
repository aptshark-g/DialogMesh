"""ChunkStore — semantic atom storage with pluggable vector backends.

Design: OPENSOURCE_DEEP_READ.md → GraphRAG + LangChain patterns.
  - Atom: smallest retrievable unit, with block_id back-reference.
  - Non-chunkable marker: code/quote/exact match → not split, not embedded.
  - Hash-based dedup: sha256(text) → skip if already processed.
  - Pluggable: backend= "in_memory" (default) | "chromadb" | "unified".
    "unified" wires UnifiedStore (BGE + LSH, lightweight stage-1 vector
    backend per G10); falls back to keyword when BGE unavailable.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("dm.chunk_store")


def _local_embed(texts) -> list:
    """Zero-download deterministic embedder (char-hash → 64d).

    Fallback when no BGE model is present — keeps the ChromaDB backend
    fully local (G10: no 79MB ONNX model download on first add).
    """
    import numpy as np
    if isinstance(texts, str):
        texts = [texts]
    out = []
    rng = np.random.RandomState(42)
    for t in texts:
        v = np.zeros(64, dtype=float)
        for i, ch in enumerate(t[:256]):
            v[i % 64] += (ord(ch) % 31) / 31.0
        v = v + rng.rand(64) * 1e-6
        n = np.linalg.norm(v)
        if n > 0:
            v = v / n
        out.append(v.tolist())
    return out


@dataclass
class Atom:
    """Smallest retrievable semantic unit."""
    atom_id: str = field(default_factory=lambda: f"a_{uuid.uuid4().hex[:8]}")
    text: str = ""
    embedding: Optional[List[float]] = None
    block_id: str = ""               # back-reference to DiscourseTree block
    chunkable: bool = True           # False for code/quote/exact match
    tags: List[str] = field(default_factory=list)
    priority: float = 0.5
    source: str = "granularity"      # which splitter created this


class ChunkStore:
    """Semantic atom store with pluggable vector backend and hash-based dedup."""

    def __init__(self, backend: str = "in_memory", collection: str = "discourse_atoms",
                 bge_model=None, unified_store=None, persist_dir: str = "data/chroma_discourse",
                 unified_persist: bool = False):
        self._atoms: List[Atom] = []
        self._store = None
        self._backend = backend
        self._collection_name = collection
        self._dedup_cache: set = set()  # fallback if ChromaDB unavailable
        self._persist_dir = persist_dir
        self._unified_persist = unified_persist
        self._unified_dirty = 0
        self._unified_save_every = 25  # throttle full npz serialization
        # G10-P1: UnifiedStore (BGE + LSH) lightweight vector backend
        self._bge = bge_model
        self._unified = unified_store
        if backend == "chromadb":
            self._init_chromadb()
        elif backend == "unified":
            self._init_unified()

    # ── Local deterministic embedding (zero-download fallback) ──────────

    def _embed(self, texts) -> Optional[list]:
        """Encode texts with BGE if available; else local char-hash vector.

        Used for ChromaDB backend — we never rely on chromadb's default
        ONNX MiniLM (would download a model; G10: lightweight backend).
        """
        try:
            if self._bge is not None and hasattr(self._bge, "encode"):
                emb = self._bge.encode(texts)
                import numpy as np
                arr = np.asarray(emb)
                if arr.ndim == 1:
                    arr = arr[None, :]
                return [v.tolist() for v in arr]
            return _local_embed(texts)
        except Exception:
            return None

    # ── Write ──

    def add(self, atoms: List[Atom]) -> int:
        """Add atoms to store. Returns count of newly added (skips duplicates)."""
        new_count = 0
        for atom in atoms:
            if not self._should_process(atom.text):
                continue
            self._atoms.append(atom)
            if self._backend == "unified":
                self._try_unified_add(atom)
            else:
                self._try_chromadb_add(atom)
            new_count += 1
        return new_count

    def add_text(self, text: str, block_id: str, chunkable: bool = True,
                 tags: List[str] = None) -> Optional[Atom]:
        """Quick add from raw text. Returns Atom or None if duplicate."""
        if not self._should_process(text):
            return None
        atom = Atom(text=text, block_id=block_id, chunkable=chunkable,
                    tags=tags or [])
        self._atoms.append(atom)
        if self._backend == "unified":
            self._try_unified_add(atom)
        else:
            self._try_chromadb_add(atom)
        return atom

    def atoms_by_tag(self, tag: str) -> List[Atom]:
        """按标签取原子（P0 写即索引: recall 冷路径合并 produced 块）。"""
        return [a for a in self._atoms if tag in (a.tags or [])]

    # ── Read ──

    def search(self, query: str, top_k: int = 10) -> List[Atom]:
        """Vector search. Falls back to keyword search if ChromaDB unavailable."""
        if self._backend == "unified" and self._unified is not None:
            try:
                hits = self._unified.search_texts(query, top_k=top_k)
            except Exception:
                hits = []
            if hits:
                atoms = []
                for h in hits:
                    md = h.get("metadata") or {}
                    atoms.append(Atom(
                        atom_id=h.get("id", ""),
                        text=h.get("text", ""),
                        block_id=md.get("block_id", ""),
                        chunkable=md.get("chunkable", True),
                        tags=md.get("tags", []) or [],
                        priority=md.get("priority", 0.5),
                    ))
                return atoms[:top_k]
        if self._store:
            try:
                qv = self._embed([query])
                if not qv:
                    results = self._store.query(query_texts=[query], n_results=top_k)
                else:
                    results = self._store.query(query_embeddings=qv, n_results=top_k)
                ids = results.get("ids", [[]])[0]
                atoms = [a for a in self._atoms if a.atom_id in ids]
                if not atoms:
                    # Cold reopen: rebuild from chromadb documents/metadatas
                    docs = results.get("documents", [[]])[0]
                    metas = results.get("metadatas", [[]])[0]
                    for i, aid in enumerate(ids):
                        md = metas[i] if i < len(metas) else {}
                        atoms.append(Atom(
                            atom_id=aid,
                            text=docs[i] if i < len(docs) else "",
                            block_id=md.get("block_id", ""),
                            chunkable=bool(md.get("chunkable", True)),
                            tags=(md.get("tags") or "").split(",") if md.get("tags") else [],
                            priority=float(md.get("priority", 0.5)),
                        ))
                return atoms[:top_k]
            except Exception:
                pass
        # Keyword fallback — multi-term OR matching (any term hits)
        terms = [t.lower() for t in query.split() if len(t.strip()) >= 2]
        matches = []
        for a in self._atoms:
            text_l = a.text.lower()
            if not terms:
                if query.lower() in text_l:
                    matches.append(a)
            elif any(t in text_l for t in terms):
                matches.append(a)
        return sorted(matches, key=lambda a: a.priority, reverse=True)[:top_k]

    def get_by_block(self, block_id: str) -> List[Atom]:
        """Get all atoms for a discourse block."""
        return [a for a in self._atoms if a.block_id == block_id]

    def stats(self) -> dict:
        return {
            "total_atoms": len(self._atoms),
            "chunkable": sum(1 for a in self._atoms if a.chunkable),
            "non_chunkable": sum(1 for a in self._atoms if not a.chunkable),
            "backend": self._backend,
            "unified_indexed": self._unified.stats().get("indexed_texts", 0)
            if self._unified is not None else 0,
        }

    def close(self) -> None:
        """Release backend file locks (chromadb sqlite) — Windows-safe."""
        if self._unified_persist and self._unified is not None and self._unified_dirty > 0:
            try:
                self._unified.save("data/recall_index/unified_text_index.npz")
            except Exception:
                pass
            self._unified_dirty = 0
        if self._backend == "chromadb" and self._store is not None:
            try:
                client = getattr(self._store, "_client", None)
                close = getattr(client, "close", None)
                if close is not None:
                    close()
            except Exception:
                pass
            self._store = None

    # ── Dedup ──

    def _should_process(self, text: str) -> bool:
        """Hash-based dedup (from LlamaIndex IngestionCache pattern)."""
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if h in self._dedup_cache:
            return False
        self._dedup_cache.add(h)
        return True

    # ── ChromaDB integration ──

    def _try_chromadb_add(self, atom: Atom) -> None:
        """Best-effort ChromaDB write. Falls back to in-memory only."""
        if self._backend != "chromadb" or self._store is None:
            return  # in-memory mode — no model download
        try:
            embeddings = None
            if atom.embedding is not None:
                embeddings = [list(atom.embedding)]
            else:
                embeddings = self._embed([atom.text])
            if not embeddings:
                return
            self._store.add(
                ids=[atom.atom_id],
                documents=[atom.text],
                embeddings=embeddings,
                metadatas=[{
                    "block_id": atom.block_id,
                    "chunkable": atom.chunkable,
                    "tags": ",".join(atom.tags),
                    "priority": atom.priority,
                }],
            )
        except Exception as e:
            logger.debug("ChromaDB add failed (in-memory only): %s", e)

    def _init_chromadb(self) -> None:
        """Lazy init ChromaDB — optional dependency (persistent local store)."""
        try:
            import chromadb
            import os
            persist_path = os.path.abspath(self._persist_dir)
            os.makedirs(persist_path, exist_ok=True)
            client = chromadb.PersistentClient(path=persist_path)
            self._store = client.get_or_create_collection(
                self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("ChunkStore: ChromaDB connected (%s)", self._collection_name)
        except ImportError:
            logger.info("ChunkStore: ChromaDB not installed, using in-memory only")
        except Exception as e:
            logger.warning("ChunkStore: ChromaDB init failed (%s), using in-memory", e)

    # ── UnifiedStore integration (G10-P1) ──

    def _init_unified(self) -> None:
        """Lazy init UnifiedStore (BGE + LSH) — lightweight vector backend."""
        try:
            from core.agent.persistence.unified_store import UnifiedStore
            self._unified = self._unified or UnifiedStore(bge_model=self._bge)
            if self._unified_persist:
                # G0: restore previously persisted text index (cross-restart recall)
                self._unified.load("data/recall_index/unified_text_index.npz")
            logger.info("ChunkStore: UnifiedStore backend wired (dim=%s)", self._unified._dim)
        except Exception as e:
            logger.warning("ChunkStore: UnifiedStore init failed (%s), using in-memory", e)
            self._unified = None

    def _try_unified_add(self, atom: Atom) -> None:
        """Best-effort UnifiedStore write. Falls back to in-memory only."""
        if self._unified is None:
            return
        try:
            self._unified.add_text(
                atom.text, atom.atom_id,
                {"block_id": atom.block_id, "chunkable": atom.chunkable,
                 "tags": atom.tags, "priority": atom.priority},
            )
            if self._unified_persist:
                self._unified_dirty += 1
                if self._unified_dirty >= self._unified_save_every:
                    self._unified.save("data/recall_index/unified_text_index.npz")
                    self._unified_dirty = 0
        except Exception as e:
            logger.debug("UnifiedStore add failed (in-memory only): %s", e)
