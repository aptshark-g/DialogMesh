"""BGE embedder with async support, LRU cache, GPU toggle."""
import asyncio
from functools import lru_cache
from typing import Union
import numpy as np

from .models import EmbeddingConfig


class BgeEmbedder:
    """BGE-small embedder: dimension=384, LRU cache=1000, optional GPU."""

    def __init__(self, config: EmbeddingConfig = None):
        self.cfg = config or EmbeddingConfig()
        self._model = None
        self._lock = asyncio.Lock()

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            try:
                self._model = SentenceTransformer(
                    self.cfg.model_path or r"C:\Users\APTShark\PycharmProjects\DialogMesh\models\BAAI\bge-small-zh",
                    model_kwargs={"local_files_only": True},
                )
            except Exception:
                self._model = SentenceTransformer(
                    self.cfg.model_path or r"C:\Users\APTShark\PycharmProjects\DialogMesh\models\BAAI\bge-small-zh"
                )
            if self.cfg.use_gpu:
                import torch
                self._model = self._model.to(torch.device("cuda" if torch.cuda.is_available() else "cpu"))
        return self._model

    @lru_cache(maxsize=1000)
    def _cached_encode(self, text: str) -> tuple:
        model = self._load()
        vec = model.encode(text)
        return tuple(vec.tolist())

    def encode(self, text: Union[str, list]) -> np.ndarray:
        if isinstance(text, list):
            model = self._load()
            return model.encode(text)
        vec_tuple = self._cached_encode(text)
        return np.array(vec_tuple, dtype=np.float32)

    async def encode_async(self, text: Union[str, list]) -> np.ndarray:
        async with self._lock:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.encode, text)

    @property
    def dimension(self) -> int:
        return self.cfg.dimension
