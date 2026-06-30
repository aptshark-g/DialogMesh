# core/infrastructure/model_service.py
"""ModelService — 进程级模型服务，确保 BGE 只加载一次。

架构设计：
- 单例模式：全局只有一个 ModelService 实例
- 预加载：启动时主动加载模型，避免首次请求时的延迟
- 状态监控：提供 warm/cold/loading/error 状态
- 隔离层：业务代码只依赖 ModelService，不直接依赖 SemanticEncoder

使用方式：
    from core.infrastructure.model_service import get_model_service

    service = get_model_service()
    service.warm_up()  # 预加载，阻塞直到就绪
    
    # 编码
    vector = service.encode("文本")
    
    # 状态查询
    print(service.status)  # "warm" | "cold" | "loading" | "error"
    print(service.latency_ms)  # 最后一次编码延迟
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Union

import numpy as np

logger = logging.getLogger(__name__)

try:
    from core.agent.compiler.semantic_encoder import SemanticEncoder
except ImportError:
    SemanticEncoder = None  # type: ignore


class _ModelServiceSingleton:
    """进程级单例：确保全局只有一个 ModelService 实例。"""

    _instance: Optional["ModelService"] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "ModelService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = ModelService()
        return cls._instance


class ModelService:
    """模型服务 — BGE 常驻内存，进程级单例。

    状态机：
        cold -> loading -> warm -> error
                 ^              |
                 |______________|
                 (reload on error)
    """

    def __init__(self):
        self._encoder: Optional[Any] = None
        self._status = "cold"  # cold | loading | warm | error
        self._error_msg: Optional[str] = None
        self._lock = threading.Lock()
        self._latency_ms = 0.0
        self._call_count = 0
        self._cache: Dict[str, np.ndarray] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    # ── 状态属性 ──────────────────────────────────────────────

    @property
    def status(self) -> str:
        return self._status

    @property
    def is_ready(self) -> bool:
        return self._status == "warm"

    @property
    def latency_ms(self) -> float:
        return self._latency_ms

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "status": self._status,
            "call_count": self._call_count,
            "latency_ms_avg": self._latency_ms,
            "cache_size": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate": (
                self._cache_hits / (self._cache_hits + self._cache_misses)
                if (self._cache_hits + self._cache_misses) > 0
                else 0.0
            ),
        }

    # ── 核心接口 ──────────────────────────────────────────────

    def warm_up(self, timeout: float = 60.0) -> bool:
        """预加载模型（阻塞直到就绪或超时）。

        Args:
            timeout: 最大等待秒数

        Returns:
            True: 模型已就绪
            False: 加载失败
        """
        if self._status == "warm":
            return True
        if self._status == "loading":
            # 等待其他线程完成加载
            return self._wait_for_warm(timeout)

        with self._lock:
            if self._status == "warm":
                return True

            self._status = "loading"
            self._error_msg = None
            start = time.time()

            try:
                if SemanticEncoder is None:
                    raise RuntimeError("SemanticEncoder not available")

                self._encoder = SemanticEncoder()
                # 触发首次加载（热身编码）
                _ = self._encoder.encode("warmup", use_cache=False)
                self._status = "warm"
                elapsed = (time.time() - start) * 1000
                logger.info(f"ModelService warm-up complete in {elapsed:.1f}ms")
                return True

            except Exception as e:
                self._status = "error"
                self._error_msg = str(e)
                logger.error(f"ModelService warm-up failed: {e}")
                return False

    def encode(self, text: str, use_cache: bool = True) -> Optional[np.ndarray]:
        """编码文本为语义向量。

        Args:
            text: 输入文本
            use_cache: 是否使用缓存

        Returns:
            512-dim 向量（归一化），失败返回 None
        """
        if not self.is_ready:
            # 自动尝试 warm-up
            if not self.warm_up():
                return None

        # 缓存检查
        cache_key = text[:200]  # 截断防止 key 过长
        if use_cache and cache_key in self._cache:
            self._cache_hits += 1
            return self._cache[cache_key]

        start = time.time()
        try:
            vector = self._encoder.encode(text, normalize=True, use_cache=False)
            if vector is not None and len(vector) > 0:
                # 压平为 1D
                vector = np.squeeze(vector)
                if vector.ndim == 1:
                    vector = vector.reshape(1, -1)

                self._latency_ms = (time.time() - start) * 1000
                self._call_count += 1

                # 写入缓存
                if use_cache:
                    self._cache[cache_key] = vector
                    self._cache_misses += 1

                return vector
        except Exception as e:
            logger.warning(f"ModelService encode failed: {e}")
        return None

    def encode_batch(self, texts: List[str], use_cache: bool = True) -> List[Optional[np.ndarray]]:
        """批量编码。

        过滤已缓存的文本，只编码未缓存的，然后合并结果。
        """
        if not self.is_ready:
            if not self.warm_up():
                return [None] * len(texts)

        # 分离缓存命中和未命中
        cached_indices = []
        uncached_texts = []
        uncached_indices = []

        for i, text in enumerate(texts):
            cache_key = text[:200]
            if use_cache and cache_key in self._cache:
                cached_indices.append((i, self._cache[cache_key]))
                self._cache_hits += 1
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)
                if use_cache:
                    self._cache_misses += 1

        # 批量编码未缓存
        results: List[Optional[np.ndarray]] = [None] * len(texts)

        # 填充缓存命中
        for idx, vec in cached_indices:
            results[idx] = vec

        if uncached_texts:
            start = time.time()
            try:
                batch_vectors = self._encoder.encode(
                    uncached_texts, batch_size=32, normalize=True, use_cache=False
                )
                self._latency_ms = (time.time() - start) * 1000
                self._call_count += len(uncached_texts)

                # 填充结果和缓存
                for local_idx, global_idx in enumerate(uncached_indices):
                    vec = np.squeeze(batch_vectors[local_idx])
                    if vec.ndim == 1:
                        vec = vec.reshape(1, -1)
                    results[global_idx] = vec
                    if use_cache:
                        self._cache[uncached_texts[local_idx][:200]] = vec

            except Exception as e:
                logger.warning(f"ModelService batch encode failed: {e}")

        return results

    def clear_cache(self):
        """清除编码缓存。"""
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

    # ── 内部 ──────────────────────────────────────────────────

    def _wait_for_warm(self, timeout: float) -> bool:
        """等待其他线程完成加载。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._status == "warm":
                return True
            if self._status == "error":
                return False
            time.sleep(0.1)
        return False


def get_model_service() -> ModelService:
    """获取全局 ModelService 单例。"""
    return _ModelServiceSingleton.get_instance()


# 便捷函数：直接编码（自动获取单例）
def encode_text(text: str, use_cache: bool = True) -> Optional[np.ndarray]:
    """快捷编码函数（自动 warm-up）。"""
    return get_model_service().encode(text, use_cache=use_cache)
