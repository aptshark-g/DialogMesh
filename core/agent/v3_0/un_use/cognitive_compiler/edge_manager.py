# -*- coding: utf-8 -*-
"""
core/agent/v3_0/cognitive_compiler/edge_manager.py
──────────────────────────────────────────────────
认知边关系管理器。

管理 Cognitive Tree 节点间的推理关系，
支持 DERIVES / SUPPORTS / CONTRADICTS / CONDITIONAL / ALTERNATIVE / REFINES / SUMMARIZES / CROSS_REF 边类型。

对应工程文档: ENGINEERING_COGNITIVE_COMPILER.md §7
版本: 3.0.0
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.agent.v3_0.cognitive_tree.models import (
    CognitiveTreeEdge,
    CogEdgeType,
)

logger = logging.getLogger(__name__)


class EdgeManager:
    """
    边关系管理器 — 管理 Cognitive Tree 节点间的推理关系。

    职责:
      - 带权限检查的认知边创建
      - 矛盾边、支持边、推导链查询
      - 边类型权限矩阵（6 个 LLM 实例）
    """

    # 边类型权限限制矩阵 — 设计文档 §7
    # 空集合表示无限制，非空集合表示禁止的边类型
    _RESTRICTED_EDGES: Dict[str, set] = {
        "PCR-LLM": {CogEdgeType.CONTRADICTS, CogEdgeType.CONDITIONAL},
        "Intent-LLM": {CogEdgeType.CONTRADICTS},
        "Planning-LLM": {CogEdgeType.CONTRADICTS, CogEdgeType.REFINES},
        "Meta-Cognitive-LLM": set(),  # 无限制
        "Reflective-LLM": {
            CogEdgeType.DERIVES,
            CogEdgeType.SUPPORTS,
            CogEdgeType.CONTRADICTS,
            CogEdgeType.CONDITIONAL,
        },
        "Answer-LLM": {CogEdgeType.CONTRADICTS, CogEdgeType.REFINES},
    }

    def __init__(self, store: Any) -> None:
        """
        Args:
            store: 存储层实例，提供 save_edge / load_edges / load_edges_from 接口
        """
        self._store = store

    def create_edge(
        self,
        session_id: str,
        source_id: str,
        target_id: str,
        edge_type: CogEdgeType,
        weight: float = 1.0,
        condition: Optional[str] = None,
        requesting_llm: str = "",
    ) -> bool:
        """
        创建认知边。

        Args:
            session_id: 会话标识
            source_id: 源节点 ID
            target_id: 目标节点 ID
            edge_type: 边类型
            weight: 依赖强度 [0, 1]
            condition: 条件表达式
            requesting_llm: 请求者 LLM 名称

        Raises:
            PermissionError: 如果 LLM 无权限创建该边类型
        """
        try:
            if not self._check_edge_type_permission(requesting_llm, edge_type):
                raise PermissionError(
                    f"LLM '{requesting_llm}' cannot create {edge_type.value} edges"
                )

            edge = CognitiveTreeEdge(
                source_id=source_id,
                target_id=target_id,
                edge_type=edge_type,
                weight=weight,
                condition=condition,
            )
            self._store.save_edge(session_id, edge)
            logger.debug(
                "Edge created: %s -> %s (%s) by %s",
                source_id, target_id, edge_type.value, requesting_llm,
            )
            return True
        except PermissionError:
            raise
        except Exception as e:
            logger.error(
                "create_edge failed (%s -> %s): %s", source_id, target_id, e
            )
            raise

    def find_contradictions(self, session_id: str, node_id: str) -> List[CognitiveTreeEdge]:
        """查找与某节点存在 CONTRADICTS 关系的所有边。"""
        try:
            all_edges = self._store.load_edges(session_id)
            return [
                e for e in all_edges
                if (e.source_id == node_id or e.target_id == node_id)
                and e.edge_type == CogEdgeType.CONTRADICTS
            ]
        except Exception as e:
            logger.error("find_contradictions failed for %s: %s", node_id, e)
            return []

    def find_supports(self, session_id: str, node_id: str) -> List[CognitiveTreeEdge]:
        """查找支持某节点的所有 SUPPORTS 边（target_id 指向该节点）。"""
        try:
            all_edges = self._store.load_edges(session_id)
            return [
                e for e in all_edges
                if e.target_id == node_id and e.edge_type == CogEdgeType.SUPPORTS
            ]
        except Exception as e:
            logger.error("find_supports failed for %s: %s", node_id, e)
            return []

    def find_derived_chain(self, session_id: str, start_node_id: str) -> List[str]:
        """
        查找从起始节点出发的 DERIVES 推导链。

        沿着权重最高的 DERIVES 边逐层追踪，最大深度 10。

        Returns:
            节点 ID 列表，从 start_node_id 开始
        """
        try:
            chain: List[str] = [start_node_id]
            current = start_node_id

            for _ in range(10):  # 深度限制
                edges = self._store.load_edges_from(session_id, current)
                derive_edges = [
                    e for e in edges if e.edge_type == CogEdgeType.DERIVES
                ]
                if not derive_edges:
                    break
                best = max(derive_edges, key=lambda e: e.weight)
                chain.append(best.target_id)
                current = best.target_id

            return chain
        except Exception as e:
            logger.error(
                "find_derived_chain failed for %s: %s", start_node_id, e
            )
            return [start_node_id]

    def _check_edge_type_permission(
        self, llm_name: str, edge_type: CogEdgeType
    ) -> bool:
        """检查 LLM 是否有权限创建某类型的边。"""
        forbidden = self._RESTRICTED_EDGES.get(llm_name, set())
        return edge_type not in forbidden
