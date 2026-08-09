"""Topic Tree — 话题树（V2 唯一内核，一内核多门面）。

归一（T4，2026-08-05）:
  - 内核: manager_v2.TopicTreeManagerV2（路由/分叉/合并/压缩/导出）
  - 门面: manager.TopicTreeManager = V2 别名（兼容旧消费方）
  - V1 原始包装类归档: un_use/manager_v1.py（A17 记录不删）
  - 组件资产保留: heat_model（A15 温度）/ fact_store / context（画像·上下文接线素材）
"""
from core.agent.topic_tree.fact_store import FactBlock, FactStore, RelationMetadataStore
from core.agent.topic_tree.heat_model import AdaptiveHeatModel
from core.agent.topic_tree.context import DualPerspectiveContext, MultiPerspectiveBranchView, BehaviorDrivenRefresh
from core.agent.topic_tree.manager import (
    EmbeddingEngine,
    RoutingDecision,
    TopicTreeManager,
)
from core.agent.topic_tree.manager_v2 import TopicTreeManagerV2, RoutingDecisionV2

__all__ = [
    "TopicTreeManager",        # 门面 → V2 内核
    "TopicTreeManagerV2",      # V2 内核（主路径）
    "EmbeddingEngine",
    "RoutingDecision",
    "RoutingDecisionV2",
    # 组件资产
    "FactBlock", "FactStore", "RelationMetadataStore",
    "AdaptiveHeatModel",
    "DualPerspectiveContext", "MultiPerspectiveBranchView", "BehaviorDrivenRefresh",
]
