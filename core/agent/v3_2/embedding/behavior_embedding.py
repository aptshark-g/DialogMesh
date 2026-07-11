"""DialogMesh v3.2 Behavior Semantic Embedding Layer (DEPRECATED)

This module is a compatibility shim. All functionality has been split into:
- models.py
- predicate_splitter.py
- predicate_classifier.py
- bge_embedder.py
- prototype_manager.py
- composite_embedder.py
- three_tier_query.py
- index_builder.py

Import from core.agent.v3_2.embedding directly instead.
"""
import warnings

warnings.warn(
    "behavior_embedding.py is deprecated; import from core.agent.v3_2.embedding instead",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export for backward compatibility
from .models import BehaviorEmbedding, NeighborResult, EmbeddingConfig
from .predicate_classifier import PredicateClassifier as PredicateMapper
from .bge_embedder import BgeEmbedder
from .prototype_manager import PrototypeManager as PrototypeVectorStore
from .composite_embedder import CompositeEmbedder as SemanticQuery
from .three_tier_query import ThreeTierWeightQuery
from .index_builder import IndexBuilder

# Legacy module-level constants
BGE_MODEL_PATH = r"C:\Users\APTShark\PycharmProjects\DialogMesh\models\BAAI\bge-small-zh"

# Legacy weights dict (moved from old behavior_embedding.py)
weights = {
    "execute": (0.7, 0.3), "debug": (0.3, 0.7),
    "build": (0.7, 0.3), "deploy": (0.7, 0.3),
    "restart": (0.7, 0.3), "config": (0.5, 0.5),
    "scan": (0.7, 0.3), "test": (0.7, 0.3),
    "check": (0.4, 0.6), "monitor": (0.4, 0.6),
    "enable": (0.5, 0.5), "disable": (0.5, 0.5),
    "schedule": (0.7, 0.3), "backup": (0.7, 0.3),
    "restore": (0.7, 0.3), "update": (0.5, 0.5),
    "show": (0.3, 0.7), "list": (0.3, 0.7),
    "analyze": (0.3, 0.7), "compare": (0.3, 0.7),
    "predict": (0.3, 0.7), "document": (0.3, 0.7),
    "query": (0.3, 0.7), "create": (0.7, 0.3),
    "modify": (0.7, 0.3), "delete": (0.7, 0.3),
    "explain": (0.2, 0.8), "fix": (0.7, 0.3),
    "connect": (0.5, 0.5), "stop": (0.7, 0.3),
    "clean": (0.7, 0.3), "greet": (0.2, 0.8),
    "affirm": (0.2, 0.8), "answer": (0.2, 0.8),
    "trace": (0.3, 0.7), "search": (0.3, 0.7),
    "find": (0.3, 0.7), "locate": (0.3, 0.7),
    "install": (0.7, 0.3),
}

# Legacy module-level singletons (deprecated)
_bge_model = None


def get_bge_model():
    """Lazy-load BGE-small-zh model (deprecated, use BgeEmbedder)."""
    global _bge_model
    if _bge_model is None:
        from sentence_transformers import SentenceTransformer
        try:
            _bge_model = SentenceTransformer(BGE_MODEL_PATH, model_kwargs={"local_files_only": True})
        except Exception:
            _bge_model = SentenceTransformer(BGE_MODEL_PATH)
    return _bge_model


# Legacy singletons
PROTOTYPES = PrototypeVectorStore()
EMBEDDER = SemanticQuery()
HARD_BOUNDARY = ThreeTierWeightQuery(EMBEDDER)


def init_embeddings(mapper=None):
    """Initialize prototypes and warm up BGE model (deprecated)."""
    m = mapper or PredicateMapper()
    PROTOTYPES.initialize(m.classes)
    threshold = HARD_BOUNDARY.cfg.cosine_threshold
    dim = PROTOTYPES.DIM
    print(f"[Embedding] Initialized: {m.class_count} classes, {dim}d, threshold={threshold:.3f} (adaptive)")


def get_embedding_stats():
    """Return current embedding system state (deprecated)."""
    thr = HARD_BOUNDARY.cfg.cosine_threshold
    return {
        "classes": PredicateMapper().class_count,
        "dim": PROTOTYPES.DIM,
        "threshold": thr,
        "bge_loaded": _bge_model is not None,
    }
