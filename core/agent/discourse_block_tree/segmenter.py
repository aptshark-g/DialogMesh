# core/agent/discourse_block_tree/segmenter.py
"""Segmenter — 轮内切分器。

将量化后的 EDU 列表按粘合度阈值切分为 DiscourseBlock。

切分规则:
1. Cohesion Cliff: 相邻 EDU 间融合粘合度 < threshold (0.5) → 切分
2. BDI (突发意图漂移): 相邻 EDU 意图标签突变 → 强制切分
3. 聚类: 连续非边界 EDU 聚类为一个 DiscourseBlock

输出: List[DiscourseBlock]
"""

from __future__ import annotations

import logging
import math
from typing import List, Optional, Tuple

try:
    from core.agent.config.discourse_config import get_discourse_config
except ImportError:
    get_discourse_config = None  # type: ignore

try:
    from core.agent.discourse_block_tree.models import (
        BlockState,
        BoundaryType,
        DiscourseBlock,
        EDU,
        MacroDimensions,
        MicroDimensions,
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
    BlockState = _models_module.BlockState
    BoundaryType = _models_module.BoundaryType
    DiscourseBlock = _models_module.DiscourseBlock
    EDU = _models_module.EDU
    MacroDimensions = _models_module.MacroDimensions
    MicroDimensions = _models_module.MicroDimensions

logger = logging.getLogger(__name__)

class Segmenter:
    """话语块切分器。"""

    def __init__(
        self,
        threshold: float = 0.5,
        macro_weight: float = 0.6,
        micro_weight: float = 0.4,
        bdi_enabled: bool = True,
    ):
        # 从配置读取默认值
        config = get_discourse_config() if get_discourse_config else None
        seg_cfg = config.segmenter if config else None

        self.threshold = threshold if (seg_cfg is None) else seg_cfg.threshold
        self.macro_weight = macro_weight if (seg_cfg is None) else seg_cfg.macro_weight
        self.micro_weight = micro_weight if (seg_cfg is None) else seg_cfg.micro_weight
        self.bdi_enabled = bdi_enabled if (seg_cfg is None) else seg_cfg.bdi_enabled

        logger.debug(
            f"Segmenter initialized (threshold={self.threshold}, "
            f"macro_w={self.macro_weight}, micro_w={self.micro_weight}, bdi={self.bdi_enabled})"
        )

    # ── 公共接口 ──────────────────────────────────────────────────

    def segment(self, edus: List[EDU]) -> List[DiscourseBlock]:
        """将 EDU 列表切分为 DiscourseBlock。

        Args:
            edus: 已量化的 EDU 列表（每个 EDU 有 macro_dimensions 和 micro_dimensions）

        Returns:
            List[DiscourseBlock]: 切分后的话语块列表
        """
        if not edus:
            return []

        if len(edus) == 1:
            block = self._create_block([edus[0]])
            return [block]

        # 1. 标记边界
        boundaries = self._mark_boundaries(edus)

        # 2. 聚类
        blocks = self._cluster_edus(edus, boundaries)

        return blocks

    # ── 边界检测 ────────────────────────────────────────────────────

    def _mark_boundaries(self, edus: List[EDU]) -> List[Tuple[int, BoundaryType]]:
        """标记所有边界位置（返回 (edu_index, boundary_type) 列表）。

        第一个 EDU 始终是边界（块起始）。
        """
        boundaries = [(0, BoundaryType.COHESION_CLIFF)]  # 第一个 EDU 总是块起始

        for i in range(len(edus) - 1):
            edu_i = edus[i]
            edu_j = edus[i + 1]

            # BDI 检测（优先）
            if self.bdi_enabled and self._detect_bdi(edu_i, edu_j):
                boundaries.append((i + 1, BoundaryType.BDI))
                edu_j.boundary_type = BoundaryType.BDI
                continue

            # Cohesion Cliff 检测
            if self._detect_cohesion_cliff(edu_i, edu_j):
                boundaries.append((i + 1, BoundaryType.COHESION_CLIFF))
                edu_j.boundary_type = BoundaryType.COHESION_CLIFF

        return boundaries

    def _detect_cohesion_cliff(self, edu_i: EDU, edu_j: EDU) -> bool:
        """检测粘合度悬崖。

        融合粘合度 = 0.6 × 宏观 + 0.4 × 微观
        如果 < threshold → 悬崖
        """
        cohesion = self._compute_cohesion(edu_i, edu_j)
        return cohesion < self.threshold

    def _detect_bdi(self, edu_i: EDU, edu_j: EDU) -> bool:
        """检测突发意图漂移（BDI）。

        条件:
        1. 两个 EDU 都有意图标签
        2. 意图标签不同
        3. 不是通用的 "statement" 或 "meta" 类型
        """
        intent_i = edu_i.intent_label
        intent_j = edu_j.intent_label
        if not intent_i or not intent_j:
            return False
        if intent_i == intent_j:
            return False
        # 排除通用意图（不视为漂移）
        generic_intents = {"statement", "meta", "general"}
        if intent_i in generic_intents and intent_j in generic_intents:
            return False
        return True

    # ── 聚类 ────────────────────────────────────────────────────────

    def _cluster_edus(
        self,
        edus: List[EDU],
        boundaries: List[Tuple[int, BoundaryType]],
    ) -> List[DiscourseBlock]:
        """将 EDU 按边界聚类为 DiscourseBlock。"""
        # 提取边界索引（去重，排序）
        boundary_indices = sorted(set(idx for idx, _ in boundaries))
        if not boundary_indices:
            # 无边界，所有 EDU 在一个块
            return [self._create_block(edus)]

        blocks = []
        # 按边界索引切分
        for i in range(len(boundary_indices)):
            start_idx = boundary_indices[i]
            end_idx = boundary_indices[i + 1] if i + 1 < len(boundary_indices) else len(edus)
            group = edus[start_idx:end_idx]
            if group:
                block = self._create_block(group)
                blocks.append(block)

        return blocks

    # ── 块创建 ──────────────────────────────────────────────────────

    def _create_block(self, edus: List[EDU]) -> DiscourseBlock:
        """从 EDU 组创建 DiscourseBlock。"""
        if not edus:
            raise ValueError("Cannot create block from empty EDU list")

        first_edu = edus[0]
        turn_index = first_edu.turn_index

        block_id = f"block:T{turn_index}:{first_edu.edu_index}"

        block = DiscourseBlock(
            id=block_id,
            edus=list(edus),  # 复制
            start_turn=turn_index,
            end_turn=edus[-1].turn_index,
            state=BlockState.ACTIVE,
        )

        # 聚合块级 embedding（EDU embedding 的平均）
        embeddings = [e.embedding for e in edus if e.embedding]
        if embeddings:
            block.macro_embedding = self._average_vectors(embeddings)

        # 聚合块级意图（主导意图：出现最多的）
        intent_counts = {}
        for e in edus:
            if e.intent_label:
                intent_counts[e.intent_label] = intent_counts.get(e.intent_label, 0) + 1
        if intent_counts:
            block.intent_label = max(intent_counts, key=intent_counts.get)

        # 聚合实体签名
        block._update_entity_signature()

        # 计算块与后继的粘合度悬崖（placeholder，在 manager 中更新）
        block.cohesion_boundary = None

        return block

    # ── 工具方法 ────────────────────────────────────────────────────

    def _compute_cohesion(self, edu_i: EDU, edu_j: EDU) -> float:
        """计算两个 EDU 间的融合粘合度。

        公式: λ × MacroComposite + (1-λ) × MicroComposite
        """
        macro = edu_j.macro_dimensions.composite() if edu_j.macro_dimensions else 0.0
        micro = edu_j.micro_dimensions.composite() if edu_j.micro_dimensions else 0.0
        return self.macro_weight * macro + self.micro_weight * micro

    @staticmethod
    def _average_vectors(vectors: List[List[float]]) -> List[float]:
        """计算向量列表的平均向量。"""
        if not vectors:
            return []
        dim = len(vectors[0])
        avg = [0.0] * dim
        for v in vectors:
            for i in range(dim):
                avg[i] += v[i]
        count = len(vectors)
        return [x / count for x in avg]

    # ── 块间粘合度（用于 manager 的话题决策）────────────────────────

    def compute_block_boundary_cohesion(
        self,
        block_a: DiscourseBlock,
        block_b: DiscourseBlock,
    ) -> float:
        """计算两个块之间的边界粘合度（用于话题决策）。

        使用块级 embedding 的余弦相似度 + 意图一致性 + 实体重叠。
        """
        # 1. embedding 相似度
        emb_sim = 0.0
        if block_a.macro_embedding and block_b.macro_embedding:
            emb_sim = self._cosine_similarity(block_a.macro_embedding, block_b.macro_embedding)

        # 2. 意图一致性
        intent_sim = 1.0 if (block_a.intent_label and block_b.intent_label and
                             block_a.intent_label == block_b.intent_label) else 0.0

        # 3. 实体重叠（Jaccard）
        set_a = set(block_a.entity_signature.split()) if block_a.entity_signature else set()
        set_b = set(block_b.entity_signature.split()) if block_b.entity_signature else set()
        entity_sim = self._jaccard(set_a, set_b)

        # 加权融合（M1=0.35, M2=0.25, M3=0.20, 简化为三维度）
        return emb_sim * 0.40 + intent_sim * 0.35 + entity_sim * 0.25

    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        """计算余弦相似度。"""
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    @staticmethod
    def _jaccard(set_a: set, set_b: set) -> float:
        """计算 Jaccard 相似度。"""
        if not set_a and not set_b:
            return 1.0
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0
