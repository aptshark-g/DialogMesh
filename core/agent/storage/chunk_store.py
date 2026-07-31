"""ChunkStore — semantic atom storage backed by ChromaDB.

Design: OPENSOURCE_DEEP_READ.md → GraphRAG + LangChain patterns.
  - Atom: smallest retrievable unit, with block_id back-reference.
  - Non-chunkable marker: code/quote/exact match → not split, not embedded.
  - Hash-based dedup: sha256(text) → skip if already processed.
  - Pluggable: defaults to ChromaDB, swap via backend= param.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("dm.chunk_store")


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
    """Semantic atom store with ChromaDB backend and hash-based dedup."""

    def __init__(self, backend: str = "in_memory", collection: str = "discourse_atoms"):
        self._atoms: List[Atom] = []
        self._store = None
        self._backend = backend
        self._collection_name = collection
        self._dedup_cache: set = set()  # fallback if ChromaDB unavailable

    # ── Write ──

    def add(self, atoms: List[Atom]) -> int:
        """Add atoms to store. Returns count of newly added (skips duplicates)."""
        new_count = 0
        for atom in atoms:
            if not self._should_process(atom.text):
                continue
            self._atoms.append(atom)
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
        self._try_chromadb_add(atom)
        return atom

    # ── Read ──

    def search(self, query: str, top_k: int = 10) -> List[Atom]:
        """Vector search. Falls back to keyword search if ChromaDB unavailable."""
        if self._store:
            try:
                results = self._store.query(query_texts=[query], n_results=top_k)
                ids = results.get("ids", [[]])[0]
                return [a for a in self._atoms if a.atom_id in ids][:top_k]
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
        }

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
            self._store.add(
                ids=[atom.atom_id],
                documents=[atom.text],
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
        """Lazy init ChromaDB — optional dependency."""
        try:
            import chromadb
            client = chromadb.Client()
            self._store = client.get_or_create_collection(self._collection_name)
            logger.info("ChunkStore: ChromaDB connected (%s)", self._collection_name)
        except ImportError:
            logger.info("ChunkStore: ChromaDB not installed, using in-memory only")
        except Exception as e:
            logger.warning("ChunkStore: ChromaDB init failed (%s), using in-memory", e)
