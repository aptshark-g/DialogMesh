# core/agent/discourse_block_tree/adapter.py
"""DiscourseBlockAdapter — V2 集成适配器。

将 DiscourseBlock / EDU 输出映射为 TopicTreeManagerV2 路由所需的输入格式：
- query_embedding: block.macro_embedding (或 EDU embedding 平均)
- query_text: block.summary.latest (v3/v2/v1 fallback)
- extracted_entities: block.entity_signature 解析
- query_intent: block.intent_label

这样 manager_v2.py 的 route() 方法无需修改，只需通过 adapter 包装调用。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

try:
    from core.agent.discourse_block_tree.models import (
        DiscourseBlock,
        EDU,
    )
except ImportError:
    import importlib.util
    import os
    import sys
    _models_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "discourse_block_tree", "models.py"
    )
    _spec = importlib.util.spec_from_file_location("discourse_models", _models_path)
    _models_module = importlib.util.module_from_spec(_spec)
    sys.modules["discourse_models"] = _models_module
    _spec.loader.exec_module(_models_module)
    DiscourseBlock = _models_module.DiscourseBlock
    EDU = _models_module.EDU


class DiscourseBlockAdapter:
    """话语块 → V2 路由输入适配器。"""

    @staticmethod
    def to_route_input(block: DiscourseBlock) -> Dict[str, Any]:
        """将 DiscourseBlock 转换为 manager_v2.route() 的 kwargs。

        Returns:
            {
                "query": str,           # 摘要文本
                "query_embedding": List[float],  # 块级 embedding
                "query_intent": str,    # 意图标签
                "extracted_entities": List[Dict[str, str]],  # 实体列表
            }
        """
        # 1. 查询文本：v3 → v2 → v1 → raw_text fallback
        query_text = block.latest_summary or block.text or ""

        # 2. 块级 embedding
        embedding = block.macro_embedding or []

        # 3. 意图
        intent = block.intent_label or "general"

        # 4. 实体解析（entity_signature 字符串 → 结构化列表）
        entities = []
        if block.entity_signature:
            for entity_name in block.entity_signature.split():
                entities.append({
                    "name": entity_name,
                    "type": "entity",  # V2 不要求精确类型，用通用标签
                })

        return {
            "query": query_text,
            "query_embedding": embedding,
            "query_intent": intent,
            "extracted_entities": entities,
        }

    @staticmethod
    def to_node_summary(block: DiscourseBlock) -> str:
        """生成 TopicNode 的 summary 字段（替代 query[:80]）。

        优先级: v3 → v2 → v1 → entity_signature → id
        """
        if block.summary:
            if block.summary.v3:
                return block.summary.v3[:120]
            if block.summary.v2:
                return block.summary.v2[:120]
            if block.summary.v1:
                return block.summary.v1[:120]
        if block.entity_signature:
            return block.entity_signature[:120]
        return block.id

    @staticmethod
    def to_fork_input(block: DiscourseBlock) -> Dict[str, Any]:
        """ForkPointLocator 输入：使用 cohesion_boundary 作为分叉信号。"""
        return {
            "query_embedding": block.macro_embedding or [],
            "query_intent": block.intent_label or "",
            "cohesion_boundary": block.cohesion_boundary,
        }

    @staticmethod
    def to_merge_input(block_a: DiscourseBlock, block_b: DiscourseBlock) -> Dict[str, Any]:
        """MergeEngine 输入：三路语义合并的素材。"""
        return {
            "entity_signature_a": block_a.entity_signature,
            "summary_a": block_a.latest_summary or "",
            "entity_signature_b": block_b.entity_signature,
            "summary_b": block_b.latest_summary or "",
        }

    @staticmethod
    def embedding_from_edus(edus: List[EDU]) -> List[float]:
        """从 EDU embedding 计算平均向量（当 block.macro_embedding 为空时）。"""
        embeddings = [e.embedding for e in edus if e.embedding]
        if not embeddings:
            return []
        dim = len(embeddings[0])
        avg = [0.0] * dim
        for v in embeddings:
            for i in range(dim):
                avg[i] += v[i]
        count = len(embeddings)
        return [x / count for x in avg]

    @staticmethod
    def cosine_similarity(v1: List[float], v2: List[float]) -> float:
        """计算余弦相似度（用于与 V2 EmbeddingEngine 结果对齐）。"""
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)
