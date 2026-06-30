# core/agent/compiler/macro_micro_quantizer.py
"""Stage 3: MacroMicroQuantizer — 宏观微观 9 维粘合度量化器。

输入：List[EDU]（来自 SyntacticDecomposer）
输出：为每个 EDU 填充 micro_dimensions + macro_dimensions，计算相邻 EDU 间 inter_edu_cohesion。

9 维体系:
- 宏观 (M1-M4): 语义相似度 0.35, 意图一致性 0.25, 实体重叠 0.20, 时间衰减 0.20
- 微观 (μ1-μ5): 实体重叠 0.30, 因果链 0.25, 指代消解 0.20, 时态连贯 0.15, 语态对齐 0.10

融合: 融合粘合度 = 0.6 × 宏观 + 0.4 × 微观 (TiMem 双通道)

约束:
- 零 LLM 依赖（embedding 用本地 BGE 模型或 SHA256 伪向量 fallback）
- 单轮 3 个 EDU 间 2 对相邻关系计算 < 5ms
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    from core.agent.config.discourse_config import get_discourse_config
except ImportError:
    get_discourse_config = None  # type: ignore

try:
    from core.agent.compiler.semantic_encoder import SemanticEncoder
    SEMANTIC_ENCODER_AVAILABLE = True
except ImportError:
    SEMANTIC_ENCODER_AVAILABLE = False

try:
    from core.agent.discourse_block_tree.models import (
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
    EDU = _models_module.EDU
    MacroDimensions = _models_module.MacroDimensions
    MicroDimensions = _models_module.MicroDimensions

logger = logging.getLogger(__name__)

# 因果链标记词典
CAUSAL_MARKERS = {
    "因为", "所以", "由于", "导致", "如果", "则", "因此", "从而",
    "既然", "假设", "条件", "结果", "后果",
    "because", "so", "since", "therefore", "thus", "if", "then", "hence",
    "consequently", "as a result", "assuming", "given that",
}

# 时间副词词典（用于 μ4 时态连贯）
TEMPORAL_MARKERS = {
    "现在", "刚才", "之前", "之后", "接着", "然后", "首先", "最后",
    "当前", "过去", "未来", "现在", "正在", "已经", "将要",
    "now", "then", "before", "after", "next", "first", "last", "currently",
    "previously", "recently", "later", "finally", "ongoing", "already", "will",
}

# 语态标记（用于 μ5 语态对齐）
VOICE_MARKERS = {
    "active", "passive", "被", "让", "使", "把",
}


class MacroMicroQuantizer:
    """宏观微观 9 维粘合度量化器。"""

    def __init__(
        self,
        embedding_model_name: Optional[str] = None,
        macro_weight: float = 0.6,
        micro_weight: float = 0.4,
    ):
        # 从配置读取默认值
        config = get_discourse_config() if get_discourse_config else None
        seg_cfg = config.segmenter if config else None

        self.macro_weight = macro_weight if (seg_cfg is None) else seg_cfg.macro_weight
        self.micro_weight = micro_weight if (seg_cfg is None) else seg_cfg.micro_weight
        self.temporal_decay_lambda = 0.6  # 时间衰减参数，来自 TiMem 论文

        # 加载语义编码器
        self._encoder: Optional[SemanticEncoder] = None
        self._embedding_cache: Dict[str, List[float]] = {}
        if SEMANTIC_ENCODER_AVAILABLE:
            try:
                from core.agent.compiler.semantic_encoder import get_encoder
                self._encoder = get_encoder()
                self._embedding_dim = self._encoder.embedding_dim
            except Exception as e:
                logger.warning(f"Encoder init failed in MacroMicroQuantizer: {e}")
                self._encoder = None

        if self._encoder is None:
            # Fallback: SHA256 伪向量（64 维，用于测试和无模型环境）
            self._embedding_dim = 64

        logger.debug(
            f"MacroMicroQuantizer initialized (macro={self.macro_weight}, "
            f"micro={self.micro_weight}, temporal_decay={self.temporal_decay_lambda})"
        )

    # ── 公共接口 ──────────────────────────────────────────────────

    def quantize(self, edus: List[EDU]) -> List[EDU]:
        """为 EDU 列表计算 9 维粘合度。

        步骤:
        1. 为每个 EDU 计算 embedding（缓存 + 批量编码优化）
        2. 计算每个 EDU 的微观维度（基于自身属性）
        3. 计算相邻 EDU 对的宏观维度（EDU_i ↔ EDU_j）
        4. 填充 EDU 的 dimensions 字段
        5. 计算相邻 EDU 间的融合粘合度

        Returns:
            更新后的 EDU 列表（每个 EDU 的 micro_dimensions 和 macro_dimensions 已填充）
        """
        if not edus:
            return edus

        # 1. 批量计算所有 EDU 的 embedding（减少多次 BGE encode 调用）
        uncached_edus = [
            edu for edu in edus
            if edu.embedding is None and edu.raw_text not in self._embedding_cache
        ]
        if uncached_edus and self._encoder is not None:
            try:
                texts = [edu.raw_text for edu in uncached_edus]
                vectors = self._encoder.encode(texts).tolist()
                for edu, vec in zip(uncached_edus, vectors):
                    edu.embedding = vec
                    self._embedding_cache[edu.raw_text] = vec
            except Exception as e:
                logger.warning(f"Batch embedding failed, falling back to single: {e}")

        # 对剩余未缓存的逐个计算
        for edu in edus:
            if edu.embedding is None:
                edu.embedding = self._compute_embedding(edu.raw_text)

        # 2. 计算每个 EDU 的微观维度（基于自身属性）
        for edu in edus:
            edu.micro_dimensions = self._compute_micro_dimensions(edu)

        # 3. 计算相邻 EDU 对的宏观维度（只计算相邻对，O(n)）
        for i in range(len(edus) - 1):
            edu_i = edus[i]
            edu_j = edus[i + 1]
            edu_j.macro_dimensions = self._compute_macro_dimensions(edu_i, edu_j)

        # 第一个 EDU 的宏观维度设为最大值（无前置 EDU）
        if edus:
            edus[0].macro_dimensions = MacroDimensions(M1=1.0, M2=1.0, M3=1.0, M4=1.0)

        return edus

    def compute_inter_edu_cohesion(self, edu_i: EDU, edu_j: EDU) -> float:
        """计算两个 EDU 之间的融合粘合度。

        公式: λ × MacroComposite + (1-λ) × MicroComposite
        """
        macro = edu_j.macro_dimensions.composite() if edu_j.macro_dimensions else 0.0
        micro = edu_j.micro_dimensions.composite() if edu_j.micro_dimensions else 0.0
        return self.macro_weight * macro + self.micro_weight * micro

    def compute_block_cohesion(self, block_edus: List[EDU]) -> float:
        """计算一个话语块内所有 EDU 的平均粘合度。"""
        if len(block_edus) <= 1:
            return 1.0
        cohesion_sum = 0.0
        count = 0
        for i in range(len(block_edus) - 1):
            c = self.compute_inter_edu_cohesion(block_edus[i], block_edus[i + 1])
            cohesion_sum += c
            count += 1
        return cohesion_sum / count if count > 0 else 1.0

    # ── 微观维度计算 (μ1-μ5) ───────────────────────────────────────

    def _compute_micro_dimensions(self, edu: EDU) -> MicroDimensions:
        """计算单个 EDU 的微观维度（基于自身文本特征）。

        注意：微观维度计算的是 EDU 内部的微观特征密度，
        不是相邻 EDU 间的对比。这些值用于后续与相邻 EDU 的微观测度对比。
        """
        text = edu.raw_text
        lower_text = text.lower()

        # μ1: 实体密度（实体数量 / 文本长度归一化）
        entity_count = len(edu.raw_entities)
        μ1 = min(1.0, entity_count / 5.0)  # 5 个实体视为满密度

        # μ2: 因果链标记密度
        causal_count = sum(1 for m in CAUSAL_MARKERS if m in lower_text)
        μ2 = min(1.0, causal_count / 2.0)

        # μ3: 指代消解密度（代词 + 省略信号）
        pronouns = ["这个", "那个", "它", "他", "这", "那", "其", "之",
                    "this", "that", "it", "they", "them", "these", "those"]
        ref_count = sum(1 for p in pronouns if p in text)
        μ3 = min(1.0, ref_count / 2.0)

        # μ4: 时态连贯密度
        temporal_count = sum(1 for m in TEMPORAL_MARKERS if m in lower_text)
        μ4 = min(1.0, temporal_count / 2.0)

        # μ5: 语态对齐密度（主动/被动标记）
        voice_count = sum(1 for m in VOICE_MARKERS if m in lower_text)
        μ5 = min(1.0, voice_count / 1.0)

        return MicroDimensions(μ1=μ1, μ2=μ2, μ3=μ3, μ4=μ4, μ5=μ5)

    # ── 宏观维度计算 (M1-M4) ───────────────────────────────────────

    def _compute_macro_dimensions(self, edu_i: EDU, edu_j: EDU) -> MacroDimensions:
        """计算相邻 EDU 间的宏观维度。

        M1: 语义相似度（embedding 余弦）
        M2: 意图一致性（相同意图标签得 1，否则 0）
        M3: 实体重叠（Jaccard 相似度）
        M4: 时间窗口内聚（时间衰减，连续轮次得 1）
        """
        # M1: 语义相似度
        M1 = self._cosine_similarity(edu_i.embedding, edu_j.embedding)

        # M2: 意图一致性
        M2 = 1.0 if (edu_i.intent_label and edu_j.intent_label and
                     edu_i.intent_label == edu_j.intent_label) else 0.0

        # M3: 实体重叠（Jaccard）
        set_i = set(edu_i.raw_entities)
        set_j = set(edu_j.raw_entities)
        M3 = self._jaccard(set_i, set_j)

        # M4: 时间窗口内聚
        # 假设相邻 EDU 在同一轮或相邻轮，时间差极小，直接给 1.0
        # 如果跨轮次，按轮次差衰减
        turn_diff = abs(edu_j.turn_index - edu_i.turn_index)
        if turn_diff == 0:
            M4 = 1.0
        else:
            M4 = math.exp(-self.temporal_decay_lambda * turn_diff)

        return MacroDimensions(M1=M1, M2=M2, M3=M3, M4=M4)

    # ── 嵌入计算 ──────────────────────────────────────────────────

    def _compute_embedding(self, text: str) -> List[float]:
        """计算文本 embedding（优先真实语义模型，退化为 SHA256 伪向量）。"""
        if text in self._embedding_cache:
            return self._embedding_cache[text]

        if self._encoder is not None:
            try:
                vec = self._encoder.encode(text).tolist()[0]
                self._embedding_cache[text] = vec
                return vec
            except Exception as e:
                logger.warning(f"Single embedding failed, using pseudo embedding: {e}")

        # Fallback: SHA256 伪向量（64 维，用于测试和无模型环境）
        vec = self._pseudo_embedding(text)
        self._embedding_cache[text] = vec
        return vec

    def _pseudo_embedding(self, text: str) -> List[float]:
        """SHA256 伪向量：确定性、快速、无需外部模型。"""
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # 取前 64 字节，每字节映射到 [-1, 1]
        dim = self._embedding_dim
        vec = []
        for i in range(dim):
            byte_val = h[i % len(h)]
            vec.append((byte_val / 128.0) - 1.0)  # 归一化到 [-1, 1]
        # L2 归一化
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    # ── 工具方法 ────────────────────────────────────────────────────

    @staticmethod
    def _cosine_similarity(v1: Optional[List[float]], v2: Optional[List[float]]) -> float:
        """计算余弦相似度（使用 numpy 加速）。"""
        if not v1 or not v2:
            return 0.0
        a = np.array(v1, dtype=np.float32)
        b = np.array(v2, dtype=np.float32)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    @staticmethod
    def _jaccard(set_a: set, set_b: set) -> float:
        """计算 Jaccard 相似度。"""
        if not set_a and not set_b:
            return 1.0  # 两个空集视为完全相似
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0
