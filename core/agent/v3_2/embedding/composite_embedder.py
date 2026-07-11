"""Composite embedder with behavior-type-aware weights (design doc §7.3)."""
import numpy as np
from typing import Tuple

from .models import BehaviorEmbedding, EmbeddingConfig
from .predicate_classifier import PredicateClassifier
from .prototype_manager import PrototypeManager
from .bge_embedder import BgeEmbedder


class CompositeEmbedder:
    """Behavior-type-aware embedding with predicate-argument weighting."""

    # Design doc §7.3 WEIGHT_MAP: action_type -> (verb_weight, noun_weight)
    WEIGHT_MAP = {
        "TOOL_EXEC":      (0.7, 0.3),
        "CODE_RUN":       (0.7, 0.3),
        "LOG_CHECK":      (0.4, 0.6),
        "ENTITY_ANALYZE": (0.3, 0.7),
        "CONFIG_MODIFY":  (0.5, 0.5),
        "EXPLORATION":    (0.3, 0.7),
    }

    def __init__(self, config: EmbeddingConfig = None):
        self.cfg = config or EmbeddingConfig()
        self._classifier = PredicateClassifier()
        self._prototypes = PrototypeManager(BgeEmbedder(self.cfg))
        self._prototypes.initialize(self._classifier.classes)
        self._embedder = BgeEmbedder(self.cfg)

    def embed(self, action: str, action_type: str = "") -> BehaviorEmbedding:
        """Embed an action string with predicate-argument decomposition."""
        parts = action.strip().split(None, 1)
        verb = parts[0] if parts else ""
        arg = parts[1] if len(parts) > 1 else ""
        pred_class = self._classifier.classify(verb) or ""
        w_verb, w_noun = self.WEIGHT_MAP.get(action_type, (0.5, 0.5))
        # Prototype vector for predicate class
        pred_vec = self._prototypes.get(pred_class)
        # BGE embed for argument
        arg_vec = self._embedder.encode(arg) if arg else np.zeros(self.cfg.dimension, dtype=np.float32)
        # Composite
        composite = w_verb * pred_vec + w_noun * arg_vec
        return BehaviorEmbedding(
            vector=composite,
            action_type=action_type,
            predicate_class=pred_class,
            argument_class=arg,
            raw_text=action,
        )

    def embed_pair(self, from_action: str, to_action: str, action_type: str = "") -> np.ndarray:
        """Embed a behavior pair (from -> to) as concatenated vector."""
        v_from = self.embed(from_action, action_type).vector
        v_to = self.embed(to_action, action_type).vector
        return np.concatenate([v_from, v_to])

    def similarity(self, emb_a: BehaviorEmbedding, emb_b: BehaviorEmbedding) -> float:
        return PrototypeManager.cosine_sim(emb_a.vector, emb_b.vector)
