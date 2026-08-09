# core/agent/compiler/semantic_encoder.py
"""SemanticEncoder — 轻量级语义编码器封装。

基于 BGE-small-zh (BAAI)，512-dim，中文语义质量优秀，13MB 轻量。
支持延迟加载（首次 encode 时初始化），避免启动时加载开销。

接口兼容 sentence-transformers，但内部使用 transformers + torch 直接实现，
无额外依赖（torch 和 transformers 已安装）。
"""

from __future__ import annotations

import logging
import math
import os
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

try:
    from core.agent.config.discourse_config import get_discourse_config
except ImportError:
    get_discourse_config = None  # type: ignore

logger = logging.getLogger(__name__)


import threading


class SemanticEncoder:
    """语义编码器：BGE-small-zh (512-dim)。"""

    # 备选模型 ID（用于错误提示）
    MODEL_ID = "BAAI/bge-small-zh"
    # Multilingual model for non-Chinese text (50+ languages, 384-dim)
    MULTILINGUAL_MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    MULTILINGUAL_MODEL_PATH = "models/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    # 向量维度（BGE-small-zh 固定为 512，multilingual 固定为 384）
    EMBEDDING_DIM = 512
    MULTILINGUAL_DIM = 384

    def __init__(self, model_path: Optional[str] = None, device: Optional[str] = None):
        # 从配置读取默认值（如果未显式传入）
        config = get_discourse_config() if get_discourse_config else None
        enc_cfg = config.encoder if config else None

        self.model_path = model_path or (enc_cfg.model_path if enc_cfg else "models/BAAI/bge-small-zh")
        self.device = device or (enc_cfg.resolved_device if enc_cfg else ("cuda" if torch.cuda.is_available() else "cpu"))
        self.max_length = enc_cfg.max_length if enc_cfg else 512

        # Lazy-loaded multilingual model for non-Chinese text
        self._multilingual_model = None
        self._multilingual_tokenizer = None
        self._multilingual_loaded = False
        self._cache_size = enc_cfg.cache_size if enc_cfg else 10000

        # 延迟加载
        self._tokenizer = None
        self._model = None
        self._initialized = False

        # 缓存（避免重复编码）
        self._cache: Dict[str, np.ndarray] = {}

        logger.debug(f"SemanticEncoder initialized (model_path={self.model_path}, device={self.device})")

    def _init(self):
        """延迟初始化模型。"""
        if self._initialized:
            return

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                f"Model not found at {self.model_path}. "
                f"Please download with: "
                f"python -m modelscope download {self.MODEL_ID}"
            )

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_path)
        self._model = AutoModel.from_pretrained(self.model_path)
        self._model.to(self.device)
        self._model.eval()
        self._initialized = True
        logger.info(f"SemanticEncoder loaded: {self.model_path} on {self.device}")

    def _is_chinese(self, text: str) -> bool:
        """Detect if text is primarily Chinese (>=1 CJK char).

        2026-08-08 修复: 原阈值 >30% 导致中英混合文本(如 "pi agent 怎么做")
        被判为 "other" → 走 384 维 n-gram 分支, 与 512 维 BGE 向量维度
        不一致, 余弦恒 0, vector 召回路全线失效。BGE-zh 支持中英混合
        token, 含任一 CJK 字符即走 zh 模型, 统一 512 维。
        """
        cjk = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff' or '\u3040' <= ch <= '\u30ff')
        return cjk > 0

    def _load_multilingual(self):
        """Lazy-load multilingual/English encoder for non-Chinese text.
        
        Falls back to word-overlap features if model unavailable.
        """
        if self._multilingual_loaded:
            return
        self._multilingual_loaded = True
        try:
            # Try loading multilingual model from local cache or modelscope
            import sentence_transformers
            # Check modelscope first (HF blocked in China)
            try:
                from modelscope import snapshot_download
                path = snapshot_download('iic/nlp_corom_sentence-embedding_english-base')
                self._multilingual_model = sentence_transformers.SentenceTransformer(path)
                self._multilingual_tokenizer = self._multilingual_model.tokenizer
                logger.info(f"English model loaded via ModelScope: {path}")
                return
            except Exception:
                pass
            # Try local path
            for local_path in [self.MULTILINGUAL_MODEL_PATH, "models/all-MiniLM-L6-v2"]:
                if os.path.exists(local_path):
                    self._multilingual_model = sentence_transformers.SentenceTransformer(local_path)
                    self._multilingual_tokenizer = self._multilingual_model.tokenizer
                    logger.info(f"Multilingual model loaded locally: {local_path}")
                    return
        except Exception as e:
            logger.warning(f"Multilingual model unavailable: {e}")

    def _detect_language(self, texts) -> str:
        """Detect primary language of input. Returns 'zh' or 'other'."""
        sample = texts[0] if isinstance(texts, list) else texts
        return "zh" if self._is_chinese(sample) else "other"

    def encode(
        self,
        texts: Union[str, List[str]],
        batch_size: int = 32,
        normalize: bool = True,
        use_cache: bool = True,
    ) -> np.ndarray:
        """编码文本为语义向量。

        Args:
            texts: 单个文本或文本列表
            batch_size: 批处理大小
            normalize: 是否 L2 归一化
            use_cache: 是否使用缓存

        Returns:
            numpy array: (N, 512) 向量矩阵
        """
        self._init()

        if isinstance(texts, str):
            texts = [texts]

        # Language detection: use multilingual model for non-Chinese
        lang = self._detect_language(texts)
        if lang != "zh":
            self._load_multilingual()

        # 1. 检查缓存
        if use_cache:
            uncached_texts = []
            uncached_indices = []
            cached_results = {}
            for i, text in enumerate(texts):
                if text in self._cache:
                    cached_results[i] = self._cache[text]
                else:
                    uncached_texts.append(text)
                    uncached_indices.append(i)
            if not uncached_texts:
                return np.vstack([cached_results[i] for i in range(len(texts))])
        else:
            uncached_texts = texts
            uncached_indices = list(range(len(texts)))
            cached_results = {}

        # 2. 批量编码 — use multilingual model for non-Chinese text
        all_vectors = []
        for i in range(0, len(uncached_texts), batch_size):
            batch = uncached_texts[i:i + batch_size]
            if lang != "zh" and self._multilingual_model:
                tokenizer = self._multilingual_tokenizer
                model = self._multilingual_model
                encoded = tokenizer(
                    batch, return_tensors="pt", padding=True,
                    truncation=True, max_length=self.max_length,
                )
                encoded = {k: v.to(self.device) for k, v in encoded.items()}
                with torch.no_grad():
                    output = model(**encoded)
                    vecs = output.last_hidden_state[:, 0].cpu().numpy()
                all_vectors.extend(vecs)
            elif lang != "zh" and not self._multilingual_model:
                # No multilingual model: use n-gram overlap features
                import re
                dim = self.MULTILINGUAL_DIM
                for text in batch:
                    # Character n-grams (3-gram) — captures subword similarity
                    clean = re.sub(r'\s+', ' ', text.lower().strip())
                    ngrams = set()
                    for j in range(len(clean) - 2):
                        ngrams.add(clean[j:j+3])
                    words = set(re.findall(r'\w+', clean))
                    v = np.zeros(dim, dtype=np.float32)
                    # Hash n-grams into vector (sparse encoding)
                    for j, ng in enumerate(sorted(ngrams)[:dim * 2]):
                        v[hash(ng) % dim] += 0.5
                    for j, w in enumerate(sorted(words)[:dim]):
                        v[hash(w) % dim] += 1.0
                    norm = np.linalg.norm(v)
                    all_vectors.append(v / norm if norm > 0 else v)
            else:
                encoded = self._tokenizer(
                    batch,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                )
                encoded = {k: v.to(self.device) for k, v in encoded.items()}
                with torch.no_grad():
                    output = self._model(**encoded)
                    vecs = output.last_hidden_state[:, 0].cpu().numpy()
                all_vectors.extend(vecs)

        # 3. 归一化
        if normalize:
            all_vectors = [self._l2_normalize(v) for v in all_vectors]

        # 4. 更新缓存（LRU：超出容量时清理）
        for text, vec in zip(uncached_texts, all_vectors):
            if len(self._cache) >= self._cache_size:
                # 简单 FIFO：移除最早的一个
                try:
                    self._cache.pop(next(iter(self._cache)))
                except StopIteration:
                    pass
            self._cache[text] = vec

        # 5. 组装结果
        result_map = dict(zip(uncached_indices, all_vectors))
        result_map.update(cached_results)
        return np.vstack([result_map[i] for i in range(len(texts))])

    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """计算两个向量的余弦相似度。"""
        if a.ndim == 1:
            a = a.reshape(1, -1)
        if b.ndim == 1:
            b = b.reshape(1, -1)
        dot = np.dot(a, b.T)
        norm_a = np.linalg.norm(a, axis=1, keepdims=True)
        norm_b = np.linalg.norm(b, axis=1, keepdims=True)
        return float(dot / (norm_a * norm_b.T + 1e-8))

    def batch_cosine_similarity(
        self,
        queries: Union[str, List[str]],
        candidates: Union[str, List[str]],
    ) -> np.ndarray:
        """批量计算查询与候选的相似度矩阵。

        Returns:
            (len(queries), len(candidates)) 的相似度矩阵
        """
        q_vecs = self.encode(queries)
        c_vecs = self.encode(candidates)
        # 归一化后点积即余弦相似度
        return np.dot(q_vecs, c_vecs.T)

    def find_most_similar(
        self,
        query: str,
        candidates: List[str],
        threshold: float = 0.0,
    ) -> Optional[Tuple[str, float]]:
        """查找与 query 最相似的候选。

        Returns:
            (best_candidate, similarity_score) 或 None
        """
        if not candidates:
            return None
        sims = self.batch_cosine_similarity([query], candidates)[0]
        best_idx = int(np.argmax(sims))
        best_score = float(sims[best_idx])
        if best_score < threshold:
            return None
        return candidates[best_idx], best_score

    def clear_cache(self):
        """清空编码缓存。"""
        self._cache.clear()

    @staticmethod
    def _l2_normalize(vec: np.ndarray) -> np.ndarray:
        """L2 归一化。"""
        norm = np.linalg.norm(vec)
        if norm > 0:
            return vec / norm
        return vec

    @property
    def embedding_dim(self) -> int:
        return self.EMBEDDING_DIM

# 全局单例锁（避免多线程重复创建实例）
_encoder_lock = threading.Lock()
_global_encoder: Optional[SemanticEncoder] = None


def get_encoder(model_path: Optional[str] = None, device: Optional[str] = None) -> SemanticEncoder:
    """返回全局共享的 SemanticEncoder 实例（线程安全）。"""
    global _global_encoder
    if _global_encoder is None:
        with _encoder_lock:
            # 双重检查（DCL）
            if _global_encoder is None:
                _global_encoder = SemanticEncoder(model_path, device)
    return _global_encoder


def preload(blocking: bool = False, timeout: float = 120.0) -> bool:
    """预加载语义编码器模型（在后台线程或阻塞模式）。

    Args:
        blocking: 是否阻塞等待加载完成（默认后台线程）
        timeout: 阻塞模式下的超时秒数

    Returns:
        True 如果加载成功或已在加载中
    """
    global _global_encoder
    if _global_encoder is not None and _global_encoder._initialized:
        logger.info("SemanticEncoder already preloaded")
        return True

    if blocking:
        try:
            encoder = get_encoder()
            encoder._init()
            logger.info("SemanticEncoder preloaded (blocking)")
            return True
        except Exception as e:
            logger.error(f"SemanticEncoder preload failed: {e}")
            return False
    else:
        def _preload_thread():
            try:
                encoder = get_encoder()
                encoder._init()
                logger.info("SemanticEncoder preloaded (background)")
            except Exception as e:
                logger.error(f"SemanticEncoder background preload failed: {e}")
        t = threading.Thread(target=_preload_thread, daemon=True, name="bge-preload")
        t.start()
        logger.info("SemanticEncoder preload started (background thread)")
        return True


def reset_encoder():
    """重置全局单例（测试/内存回收用）。"""
    global _global_encoder
    _global_encoder = None
