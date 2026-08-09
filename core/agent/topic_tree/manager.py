"""Topic Tree Manager — 兼容门面（一内核多门面，红线 7）。

T4 归一（2026-08-05）:
  V2（manager_v2.TopicTreeManagerV2）= 唯一话题树内核。
  本模块保留旧名 `TopicTreeManager` 以兼容旧消费方
  （cli registry / v3_common.integration_bridge / inspect_v3_cmd），
  实际指向 V2 内核，不再维护并行实现。

  V1 原始包装类已归档: core/agent/topic_tree/un_use/manager_v1.py（A17 记录不删）。
  V1 独特组件资产（heat_model / fact_store / context）保留原位，供后续接线
  （A15 温度系统 / 画像·上下文）。
"""

from core.agent.topic_tree.manager_v2 import (
    EmbeddingEngine,           # noqa: F401
    RoutingDecisionV2,         # noqa: F401
    TopicTreeManagerV2,
)

# 兼容门面: 旧名 → V2 内核（route/get_node/get_current_branch 等 V2 API）
TopicTreeManager = TopicTreeManagerV2
RoutingDecision = RoutingDecisionV2

__all__ = ["TopicTreeManager", "RoutingDecision", "EmbeddingEngine", "TopicTreeManagerV2"]
