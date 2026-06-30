# core/agent/context_manager/semantic_index.py
"""语义索引 —— 基于 BGE 向量的话语块搜索。

Phase 3 能力：
- 实时编码：所有话语块自动编码为 512-dim 向量
- 相似度搜索：余弦相似度 + top-k 返回
- 跨会话索引：支持加载多个会话的块到同一索引
- 批量编码：通过 ModelService 批量优化
- 预加载：启动时主动 warm-up，避免首次请求延迟

使用方式：
    index = SemanticIndex()
    index.warm_up()  # 预加载模型（阻塞直到就绪）
    
    index.add_block(block_id="block:T0:0", text="Python 列表推导式")
    index.add_block(block_id="block:T1:0", text="FastAPI 对比 Flask")
    
    results = index.search("Flask 的优缺点", top_k=3)
    # → [("block:T1:0", 0.92), ("block:T0:0", 0.34), ...]
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


try:
    from core.agent.compiler.semantic_encoder import SemanticEncoder, get_encoder
except ImportError:
    SemanticEncoder = None  # type: ignore
    get_encoder = None  # type: ignore


class SemanticIndex:
    """语义索引 —— 基于 BGE 向量的块搜索。"""

    def __init__(self, encoder: Optional[Any] = None):
        self._encoder = encoder  # 如果外部传入，优先使用
        self._vectors: Dict[str, np.ndarray] = {}  # block_id → 512-dim vector
        self._texts: Dict[str, str] = {}           # block_id → raw text
        self._index_count = 0

    def _get_encoder(self) -> Optional[Any]:
        """获取语义编码器（通过 ModelService 单例，确保 BGE 只加载一次）。"""
        if self._encoder is not None:
            return self._encoder

        try:
            from core.infrastructure.model_service import get_model_service
            service = get_model_service()
            if service.warm_up():
                self._encoder = service
                logger.info("SemanticIndex using ModelService (singleton)")
                return self._encoder
            else:
                logger.warning("ModelService warm-up failed, falling back to direct encoder")
        except Exception as e:
            logger.warning(f"Failed to initialize via ModelService: {e}")

        # 回退：直接创建 SemanticEncoder（旧行为，仅当 ModelService 不可用时）
        try:
            if get_encoder is not None:
                self._encoder = get_encoder()
            elif SemanticEncoder is not None:
                self._encoder = SemanticEncoder()
        except Exception as e:
            logger.warning(f"Failed to initialize encoder: {e}")

        return self._encoder

    def _get_model_service(self) -> Optional[Any]:
        """获取底层 ModelService（用于状态查询）。"""
        try:
            from core.infrastructure.model_service import get_model_service
            return get_model_service()
        except Exception:
            return None

    def warm_up(self) -> bool:
        """预加载模型（阻塞直到就绪）。

        Returns:
            True: 模型已就绪
            False: 加载失败
        """
        encoder = self._get_encoder()
        return encoder is not None

    def add_block(self, block_id: str, text: str) -> bool:
        """添加话语块到索引。

        Returns:
            是否成功编码并添加
        """
        encoder = self._get_encoder()
        if encoder is None:
            return False

        try:
            # ModelService.encode 返回 (1, 512) 的 2D 数组
            vector = encoder.encode(text)
            if vector is not None and len(vector) > 0:
                vector = np.squeeze(vector)
                # 确保是 1D
                if vector.ndim == 0:
                    vector = vector.reshape(-1)
                self._vectors[block_id] = vector
                self._texts[block_id] = text
                self._index_count += 1
                return True
        except Exception as e:
            logger.warning(f"Failed to encode block {block_id}: {e}")
        return False

    def add_blocks(self, blocks: List[Tuple[str, str]]) -> int:
        """批量添加话语块（使用 ModelService 批量编码优化）。

        Returns:
            成功添加的数量
        """
        encoder = self._get_encoder()
        if encoder is None:
            return 0

        # 尝试批量编码（ModelService 支持 encode_batch）
        try:
            if hasattr(encoder, 'encode_batch'):
                texts = [text for _, text in blocks]
                vectors = encoder.encode_batch(texts)
                count = 0
                for i, (block_id, text) in enumerate(blocks):
                    vec = vectors[i]
                    if vec is not None:
                        vec = np.squeeze(vec)
                        if vec.ndim == 0:
                            vec = vec.reshape(-1)
                        self._vectors[block_id] = vec
                        self._texts[block_id] = text
                        self._index_count += 1
                        count += 1
                return count
        except Exception as e:
            logger.warning(f"Batch encode failed: {e}, falling back to single")

        # 回退：逐个编码
        count = 0
        for block_id, text in blocks:
            if self.add_block(block_id, text):
                count += 1
        return count

    def search(self, query: str, top_k: int = 5, min_score: float = 0.3) -> List[Tuple[str, float, str]]:
        """语义搜索。

        Args:
            query: 搜索查询文本
            top_k: 返回结果数量
            min_score: 最小相似度阈值（0-1）

        Returns:
            [(block_id, similarity_score, text), ...]，按相似度降序
        """
        encoder = self._get_encoder()
        if encoder is None or not self._vectors:
            return []

        try:
            query_vec = encoder.encode(query)
            if query_vec is None or len(query_vec) == 0:
                return []

            query_vec = np.squeeze(query_vec)
            if query_vec.ndim == 0:
                query_vec = query_vec.reshape(-1)

            # 归一化查询向量
            query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-8)

            results = []
            for block_id, vec in self._vectors.items():
                # 余弦相似度 = 归一化向量的点积
                vec_norm = vec / (np.linalg.norm(vec) + 1e-8)
                score = float(np.dot(query_norm, vec_norm))
                if score >= min_score:
                    results.append((block_id, score, self._texts.get(block_id, "")))

            # 按相似度降序排序
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]

        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")
            return []

    def get_block_text(self, block_id: str) -> Optional[str]:
        """获取 block 的原始文本。"""
        return self._texts.get(block_id)

    def get_block_vector(self, block_id: str) -> Optional[np.ndarray]:
        """获取 block 的向量。"""
        return self._vectors.get(block_id)

    def get_all_blocks(self) -> List[Tuple[str, str, np.ndarray]]:
        """获取所有索引的 block。"""
        return [
            (bid, self._texts[bid], self._vectors[bid])
            for bid in self._vectors
        ]

    def remove_block(self, block_id: str) -> bool:
        """移除 block。"""
        if block_id in self._vectors:
            del self._vectors[block_id]
            del self._texts[block_id]
            return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计（含 ModelService 状态）。"""
        stats = {
            "indexed_blocks": len(self._vectors),
            "total_added": self._index_count,
        }
        service = self._get_model_service()
        if service:
            stats["model_service"] = service.stats
        else:
            stats["encoder_ready"] = self._encoder is not None
        return stats

    def clear(self):
        """清空索引。"""
        self._vectors.clear()
        self._texts.clear()
        self._index_count = 0
