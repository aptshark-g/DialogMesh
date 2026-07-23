# -*- coding: utf-8 -*-
"""
core/agent/v3_0/cognitive_compiler/lifecycle.py
────────────────────────────────────────────────
认知节点生命周期管理器。

管理 CognitiveTreeNode 的完整生命周期状态机:
  CREATED → ACTIVE → VALIDATED / INVALIDATED → SUPERSEDED / ARCHIVED

对应工程文档: ENGINEERING_COGNITIVE_COMPILER.md §6
版本: 3.0.0
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

from core.agent.v3_0.cognitive_tree.models import (
    CognitiveTreeEdge,
    CognitiveTreeNode,
    CogEdgeType,
    CogNodeStatus,
)

logger = logging.getLogger(__name__)


class NodeLifecycleManager:
    """
    节点生命周期管理器 — 管理 CognitiveTreeNode 的完整生命周期。

    状态机:
        CREATED → ACTIVE → VALIDATED / INVALIDATED
                → SUPERSEDED / ARCHIVED

    权限检查委托给底层存储层，生命周期管理器只负责状态转换逻辑。
    """

    def __init__(self, store: Any) -> None:
        """
        Args:
            store: 存储层实例，提供 load_node / update_node / add_edge 接口
        """
        self._store = store

    def activate(self, session_id: str, node_id: str, requesting_llm: str) -> bool:
        """
        将节点从 CREATED 激活为 ACTIVE。

        触发场景:
          - Planning-LLM 采纳某个推理作为执行计划
          - Answer-LLM 确认某个假设作为回复依据
        """
        return self._transition(
            session_id, node_id, requesting_llm,
            from_status=CogNodeStatus.CREATED,
            to_status=CogNodeStatus.ACTIVE,
        )

    def validate(
        self,
        session_id: str,
        node_id: str,
        requesting_llm: str,
        validation_result: str,
    ) -> bool:
        """
        验证节点（Meta-Cognitive-LLM 调用）。

        结果:
          - 验证通过 → VALIDATED
          - 验证失败 → INVALIDATED
        """
        try:
            node = self._store.load_node(session_id, node_id)
            if not node:
                logger.warning("validate: node %s not found", node_id)
                return False

            node.add_validation(validation_result)

            if "PASS" in validation_result or "VALID" in validation_result:
                new_status = CogNodeStatus.VALIDATED
            else:
                new_status = CogNodeStatus.INVALIDATED

            return self._transition(
                session_id, node_id, requesting_llm,
                from_status=node.status,
                to_status=new_status,
            )
        except Exception as e:
            logger.error("validate failed for node %s: %s", node_id, e)
            return False

    def supersede(
        self,
        session_id: str,
        node_id: str,
        requesting_llm: str,
        new_node_id: str,
    ) -> bool:
        """
        将节点标记为 SUPERSEDED（被新版本替代）。

        触发场景:
          - 同一 LLM 产生了新的、更准确的推理
          - Meta-Cognitive-LLM 发现旧版本存在错误
        """
        try:
            self._store.add_edge(
                session_id,
                CognitiveTreeEdge(
                    source_id=node_id,
                    target_id=new_node_id,
                    edge_type=CogEdgeType.REFINES,
                ),
            )
            return self._transition(
                session_id, node_id, requesting_llm,
                from_status=CogNodeStatus.ACTIVE,
                to_status=CogNodeStatus.SUPERSEDED,
            )
        except Exception as e:
            logger.error("supersede failed for node %s: %s", node_id, e)
            return False

    def archive(self, session_id: str, node_id: str, requesting_llm: str) -> bool:
        """
        将节点归档（Reflective-LLM 调用）。

        触发场景:
          - 节点超过保留期（如 30 天）
          - Reflective-LLM 的定期清理任务
        """
        return self._transition(
            session_id, node_id, requesting_llm,
            from_status=CogNodeStatus.VALIDATED,
            to_status=CogNodeStatus.ARCHIVED,
        )

    def _transition(
        self,
        session_id: str,
        node_id: str,
        requesting_llm: str,
        from_status: CogNodeStatus,
        to_status: CogNodeStatus,
    ) -> bool:
        """通用状态转换方法。"""
        try:
            node = self._store.load_node(session_id, node_id)
            if not node:
                logger.warning("_transition: node %s not found", node_id)
                return False

            if node.status != from_status:
                logger.warning(
                    "_transition: node %s status mismatch (expected %s, got %s)",
                    node_id, from_status.value, node.status.value,
                )
                return False

            node.status = to_status
            node.version_history.append(
                json.dumps(
                    {
                        "time": time.time(),
                        "from": from_status.value,
                        "to": to_status.value,
                        "by": requesting_llm,
                    }
                )
            )

            return self._store.update_node(
                session_id, node_id, {"status": to_status}, requesting_llm
            )
        except Exception as e:
            logger.error(
                "_transition failed for node %s (%s → %s): %s",
                node_id, from_status.value, to_status.value, e,
            )
            return False
