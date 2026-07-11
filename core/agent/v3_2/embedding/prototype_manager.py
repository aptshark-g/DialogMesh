"""Prototype manager with incremental add_prototype updates."""
import numpy as np
from typing import List

from .models import BehaviorEmbedding
from .bge_embedder import BgeEmbedder


class PrototypeManager:
    """Incremental prototype vector store."""

    DIM = 384

    def __init__(self, embedder: BgeEmbedder = None):
        self.prototypes: dict = {}
        self._embedder = embedder or BgeEmbedder()
        self._fallback = np.zeros(self.DIM, dtype=np.float32)

    def initialize(self, predicate_classes: List[str]):
        """Bulk init from predicate class list."""
        standard_texts = self._get_standard_texts
        for pc in predicate_classes:
            texts = standard_texts(pc)
            if texts:
                embs = self._embedder.encode(texts)
                self.prototypes[pc] = np.mean(embs, axis=0)
            else:
                self.prototypes[pc] = self._fallback.copy()

    def add_prototype(self, pred_class: str, texts: List[str]):
        """Incremental update: add or refresh a prototype class."""
        if not texts:
            return
        embs = self._embedder.encode(texts)
        new_proto = np.mean(embs, axis=0)
        if pred_class in self.prototypes:
            old = self.prototypes[pred_class]
            # Exponential moving average update
            self.prototypes[pred_class] = 0.7 * old + 0.3 * new_proto
        else:
            self.prototypes[pred_class] = new_proto

    def get(self, pred_class: str) -> np.ndarray:
        return self.prototypes.get(pred_class, self._fallback)

    @staticmethod
    def cosine_sim(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        if norm_a < 1e-10 or norm_b < 1e-10:
            return 0.0
        return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))

    @staticmethod
    def _get_standard_texts(pred_class: str) -> List[str]:
        texts = {
            "execute": ["execute program", "run script", "launch service"],
            "debug":   ["debug process", "trace execution"],
            "build":   ["build project", "compile source"],
            "deploy":  ["deploy service", "release version"],
            "restart": ["restart service", "reboot system"],
            "config":  ["configure settings", "initialize parameters"],
            "scan":    ["scan network", "enumerate devices"],
            "test":    ["test function", "validate output"],
            "check":   ["check status", "inspect logs"],
            "monitor": ["monitor performance", "track metrics"],
            "show":    ["show details", "display result"],
            "list":    ["list files", "catalog items"],
            "analyze": ["analyze data", "investigate issue"],
            "compare": ["compare versions", "benchmark performance"],
            "predict": ["predict outcome", "forecast trend"],
            "create":  ["create project", "generate code"],
            "modify":  ["modify config", "edit settings"],
            "delete":  ["delete file", "remove entry"],
            "fix":     ["fix bug", "repair error"],
            "disable": ["disable service", "deactivate module"],
            "enable":  ["enable feature", "activate plugin"],
            "stop":    ["stop process", "halt service"],
            "clean":   ["clean cache", "purge temp"],
            "backup":  ["backup data", "save state"],
            "restore": ["restore backup", "recover data"],
            "update":  ["update version", "upgrade system"],
            "query":   ["query database", "search records"],
            "explain": ["explain concept", "describe process"],
            "schedule": ["schedule task", "plan job"],
            "document": ["document changes", "record results"],
            "answer":  ["answer question", "respond query"],
            "affirm":  ["affirm action", "confirm choice"],
            "greet":   ["greet user", "say hello"],
            "connect": ["connect server", "attach device"],
        }
        return texts.get(pred_class, [])
