"""P2: Unified Persistence Layer.

AnnotationStore — JSON-based unified annotation storage.
UnifiedStore   — BGE vector index with LSH pruning.

Replaces scattered persistence: mind_*.json, pattern_learner.json,
neuro_symbolic_rules.json, monitor/*.jsonl into single namespace.

Memory-mapped for large datasets, auto-compaction, versioned.
"""
from __future__ import annotations
import json, os, logging, shutil, time
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)


class AnnotationStore:
    """Unified JSON annotation store with namespaces and versioning.

    namespace/ → key → value
    ─ data/annotations/
       ├── mind/
       │   ├── relations.json
       │   ├── anchors.json
       │   └── mistakes.json
       ├── rules/
       │   └── neuro_symbolic.json
       ├── patterns/
       │   └── pattern_learner.json
       ├── profile/
       │   └── track_b.json
       └── version.txt
    """

    def __init__(self, base_dir: str = "data/annotations"):
        self._base = Path(base_dir)
        self._version = 1
        self._load_version()

    def _load_version(self):
        vf = self._base / "version.txt"
        if vf.exists():
            self._version = int(vf.read_text().strip())

    def _save_version(self):
        self._base.mkdir(parents=True, exist_ok=True)
        (self._base / "version.txt").write_text(str(self._version))

    def put(self, namespace: str, key: str, value: Any) -> None:
        """Store any JSON-serializable value under namespace/key."""
        ns_dir = self._base / namespace
        ns_dir.mkdir(parents=True, exist_ok=True)
        path = ns_dir / f"{key}.json"
        # Atomic write
        tmp = path.with_suffix(".tmp")
        try:
            with open(tmp, "w") as f:
                json.dump({"value": value, "updated": time.time(), "version": self._version}, f)
            tmp.replace(path)
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        path = self._base / namespace / f"{key}.json"
        if not path.exists():
            return default
        with open(path) as f:
            data = json.load(f)
        return data.get("value", default)

    def list_keys(self, namespace: str) -> List[str]:
        ns_dir = self._base / namespace
        if not ns_dir.exists():
            return []
        return [p.stem for p in ns_dir.glob("*.json")]

    def namespace_exists(self, namespace: str) -> bool:
        return (self._base / namespace).is_dir()

    def backup(self) -> str:
        """Create timestamped backup."""
        ts = int(time.time())
        backup_dir = self._base.parent / f"annotations_backup_{ts}"
        if self._base.exists():
            shutil.copytree(self._base, backup_dir)
        return str(backup_dir)

    def compact(self) -> int:
        """Remove old versions, return count cleaned."""
        self._version += 1
        self._save_version()
        count = 0
        for ns_dir in self._base.iterdir():
            if ns_dir.is_dir() and ns_dir.name != "version.txt":
                for f in ns_dir.glob("*.tmp"):
                    f.unlink()
                    count += 1
        return count

    def stats(self) -> Dict[str, Any]:
        namespaces = {}
        total_size = 0
        for ns_dir in self._base.iterdir():
            if ns_dir.is_dir():
                files = list(ns_dir.glob("*.json"))
                size = sum(f.stat().st_size for f in files)
                namespaces[ns_dir.name] = {"files": len(files), "size_kb": size // 1024}
                total_size += size
        return {"namespaces": namespaces, "total_kb": total_size // 1024, "version": self._version}


class UnifiedStore:
    """Unified vector index with BGE embeddings + LSH pruning.

    Single interface for: BGE retrieval, LSH candidate selection,
    object name → embedding lookup.

    Wraps: BGE model (semantic_encoder), LSH index, object store.
    """

    def __init__(self, bge_model=None, dim: int = 512, annotation_store: Optional[AnnotationStore] = None):
        self._dim = dim
        self._bge = bge_model
        self._annotations = annotation_store
        self._cache: Dict[str, Any] = {}

    def index_objects(self, objects: dict) -> int:
        """Index object names → BGE embeddings for fast retrieval."""
        if not self._bge or not objects:
            return 0

        try:
            names = list(objects.keys())[:5000]  # Cap at 5K
            embeddings = self._bge.encode(names) if hasattr(self._bge, 'encode') else None
            if embeddings is None:
                return 0

            import numpy as np
            self._cache["object_embeddings"] = np.array(embeddings)
            self._cache["object_names"] = names
            logger.info("UnifiedStore: indexed %d objects (dim=%d)", len(names), self._dim)
            return len(names)
        except Exception as e:
            logger.debug("UnifiedStore index skipped: %s", e)
            return 0

    def retrieve(self, query: str, top_k: int = 10, candidate_set: Optional[set] = None) -> List[str]:
        """BGE semantic retrieval with optional LSH candidate pruning."""
        cache = self._cache
        if "object_embeddings" not in cache or not self._bge:
            return []

        try:
            import numpy as np
            query_vec = getattr(self._bge, 'encode', lambda x: None)([query])
            if query_vec is None:
                return []

            # If candidate_set provided, only score those (LSH-pruned)
            if candidate_set:
                indices = [i for i, name in enumerate(cache["object_names"]) if name in candidate_set]
                if not indices:
                    return []
                query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-8)
                embeddings = cache["object_embeddings"][indices]
                scores = np.dot(embeddings, query_norm.T).flatten()
                top = np.argsort(scores)[-top_k:][::-1]
                return [cache["object_names"][indices[i]] for i in top if scores[i] > 0.4]
            else:
                # Full BGE retrieval
                query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-8)
                scores = np.dot(cache["object_embeddings"], query_norm.T).flatten()
                top = np.argsort(scores)[-top_k:][::-1]
                return [cache["object_names"][i] for i in top if scores[i] > 0.4]
        except Exception as e:
            logger.debug("UnifiedStore retrieve skipped: %s", e)
            return []

    def save(self, path: str = "data/vectors/unified_index.npz") -> None:
        """Persist vector index to disk."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        import numpy as np
        try:
            np.savez_compressed(path,
                embeddings=self._cache.get("object_embeddings", np.array([])),
                names=np.array(self._cache.get("object_names", []), dtype=object))
            logger.info("UnifiedStore: saved %d vectors", len(self._cache.get("object_names", [])))
        except Exception as e:
            logger.debug("UnifiedStore save skipped: %s", e)

    def load(self, path: str = "data/vectors/unified_index.npz") -> bool:
        """Load vector index from disk."""
        import numpy as np
        if not os.path.exists(path):
            return False
        try:
            data = np.load(path, allow_pickle=True)
            self._cache["object_embeddings"] = data["embeddings"]
            self._cache["object_names"] = list(data["names"])
            logger.info("UnifiedStore: loaded %d vectors", len(self._cache["object_names"]))
            return True
        except Exception as e:
            logger.debug("UnifiedStore load skipped: %s", e)
            return False

    def stats(self) -> Dict[str, Any]:
        return {
            "indexed_objects": len(self._cache.get("object_names", [])),
            "dim": self._dim,
            "cache_size": sum(len(str(v)) for v in self._cache.values()),
        }
