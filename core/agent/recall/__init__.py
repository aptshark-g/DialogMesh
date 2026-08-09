# -*- coding: utf-8 -*-
"""统一召回能力接口（B2-3 P1 落地, 2026-08-08）。

混合锚点（BGE 向量 + BM25 + HyDE 扩展）→ 溯源置信度加权 →
对话树块图 k-hop 扩散 → 融合排序。所有模块（子图/多 agent/执行层）统一消费。
"""
from .recall_service import RecallService, RecallHit, RecallResult

__all__ = ["RecallService", "RecallHit", "RecallResult"]
