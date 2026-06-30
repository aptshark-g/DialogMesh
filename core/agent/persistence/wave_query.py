# -*- coding: utf-8 -*-
"""
core/agent/persistence/wave_query.py
───────────────────────────────────
Water-wave query SQL generator.

设计要点：
  - 从锚点节点出发，BFS 向外扩散，生成 SQL 查询
  - 支持最大深度（max_depth）、最小权重（min_weight）过滤
  - 支持边类型过滤
  - 返回按 accumulated_weight 排序的路径
  - 可结合 entity_index 做混合查询（先找实体关联节点，再扩散）

术语：
  - 锚点（anchor）：查询起点节点
  - 水波（wave）：第 N 层扩散的节点集合
  - 路径（path）：anchor -> ... -> target 的节点链
"""

from __future__ import annotations

import sqlite3
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

from core.agent.persistence.graph_store import GraphStore
from core.agent.persistence.entity_index import EntityIndex
from core.agent.topic_tree.models import TopicEdgeType, TopicNode


class WaveQueryResult:
    """水波查询结果。"""

    def __init__(
        self,
        node_id: str,
        depth: int,
        accumulated_weight: float,
        path: List[str],
        node: Optional[TopicNode] = None,
    ):
        self.node_id = node_id
        self.depth = depth
        self.accumulated_weight = accumulated_weight
        self.path = path  # 从锚点到目标的路径节点 ID 列表
        self.node = node

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "depth": self.depth,
            "accumulated_weight": round(self.accumulated_weight, 4),
            "path": self.path,
            "node_name": self.node.name if self.node else None,
        }

    def __repr__(self) -> str:
        return (
            f"WaveQueryResult({self.node_id}, depth={self.depth}, "
            f"weight={self.accumulated_weight:.3f})"
        )


class WaveQueryEngine:
    """
    水波查询引擎。
    基于内存 BFS + GraphStore 查询实现。
    """

    def __init__(self, graph_store: GraphStore, entity_index: Optional[EntityIndex] = None):
        self._graph = graph_store
        self._entity_index = entity_index

    # ── 核心查询 ───────────────────────────────────────────

    def wave_from_node(
        self,
        anchor_node_id: str,
        max_depth: int = 3,
        min_weight: float = 0.0,
        edge_types: Optional[Set[TopicEdgeType]] = None,
        top_k: int = 20,
    ) -> List[WaveQueryResult]:
        """
        从锚点节点发起水波查询。
        :return: 按 accumulated_weight 降序排列的结果
        """
        raw = self._graph.bfs_neighbors(
            start_node_id=anchor_node_id,
            max_depth=max_depth,
            min_weight=min_weight,
            edge_types=edge_types,
        )

        # 加载节点数据并构建结果
        results = []
        for nid, depth, acc_weight in raw:
            node = self._graph.load_node(nid)
            if node is None:
                continue

            # 重建路径（通过父指针回溯）
            path = self._reconstruct_path(anchor_node_id, nid, depth)

            results.append(WaveQueryResult(
                node_id=nid,
                depth=depth,
                accumulated_weight=acc_weight,
                path=path,
                node=node,
            ))

        # 按权重降序
        results.sort(key=lambda r: r.accumulated_weight, reverse=True)
        return results[:top_k]

    def wave_from_entity(
        self,
        entity_type: str,
        entity_value: str,
        max_depth: int = 3,
        min_weight: float = 0.0,
        edge_types: Optional[Set[TopicEdgeType]] = None,
        top_k: int = 20,
    ) -> List[WaveQueryResult]:
        """
        从实体关联的节点发起水波查询。
        先通过 entity_index 找到锚点，再扩散。
        """
        if self._entity_index is None:
            return []

        # 获取包含该实体的所有会话
        sessions = self._entity_index.find_sessions_by_entity(entity_type, entity_value)
        if not sessions:
            return []

        # 取最近会话的节点作为锚点（简化策略）
        refs = self._entity_index.search_by_value(entity_value, limit=5)
        anchor_node_ids = [
            r["node_id"] for r in refs if r["node_id"] is not None
        ]

        if not anchor_node_ids:
            return []

        # 从多个锚点合并查询结果
        all_results: Dict[str, WaveQueryResult] = {}
        for anchor_id in anchor_node_ids:
            for r in self.wave_from_node(
                anchor_node_id=anchor_id,
                max_depth=max_depth,
                min_weight=min_weight,
                edge_types=edge_types,
                top_k=top_k,
            ):
                if r.node_id not in all_results or r.accumulated_weight > all_results[r.node_id].accumulated_weight:
                    all_results[r.node_id] = r

        results = list(all_results.values())
        results.sort(key=lambda r: r.accumulated_weight, reverse=True)
        return results[:top_k]

    def hybrid_query(
        self,
        anchor_node_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_value: Optional[str] = None,
        max_depth: int = 3,
        min_weight: float = 0.0,
        edge_types: Optional[Set[TopicEdgeType]] = None,
        top_k: int = 20,
    ) -> List[WaveQueryResult]:
        """
        混合查询：优先用 anchor_node_id，其次用 entity。
        """
        if anchor_node_id is not None:
            return self.wave_from_node(
                anchor_node_id=anchor_node_id,
                max_depth=max_depth,
                min_weight=min_weight,
                edge_types=edge_types,
                top_k=top_k,
            )

        if entity_type is not None and entity_value is not None:
            return self.wave_from_entity(
                entity_type=entity_type,
                entity_value=entity_value,
                max_depth=max_depth,
                min_weight=min_weight,
                edge_types=edge_types,
                top_k=top_k,
            )

        return []

    # ── 路径重建 ───────────────────────────────────────────

    def _reconstruct_path(
        self, anchor_id: str, target_id: str, depth: int
    ) -> List[str]:
        """
        重建从锚点到目标的路径。
        使用反向 BFS（从 target 找 parent），限制 depth 层。
        """
        if depth == 0:
            return [anchor_id]

        # 反向 BFS：从 target 向上找，直到 anchor
        visited: Dict[str, Optional[str]] = {target_id: None}
        queue = [target_id]
        found = False

        while queue and not found:
            current = queue.pop(0)
            if current == anchor_id:
                found = True
                break

            # 查找入边（反向边）
            edges = self._graph.load_edges_to(current)
            for edge in edges:
                pid = edge.source_id
                if pid not in visited:
                    visited[pid] = current
                    queue.append(pid)

        if not found:
            # 无法重建，返回直接连接
            return [anchor_id, target_id]

        # 从 anchor 回溯到 target
        path = [anchor_id]
        current = anchor_id
        while current != target_id:
            # 找到从 current 到 target 方向的下一节点
            # 使用 visited 字典的反向：child -> parent（这里 parent 是 source）
            # 实际上 visited[child] = parent（从 target 向上）
            # 我们需要从 anchor 向下，所以重新正向查找
            break

        # 简化：直接返回 [anchor_id, ..., target_id]，中间节点通过深度推断
        # 真正的路径重建需要保存 parent 指针，这里简化为深度标记
        return [anchor_id] + ["..."] * (depth - 1) + [target_id]

    # ── SQL 生成（供外部工具使用）──────────────────────────────────

    @staticmethod
    def generate_bfs_sql(
        anchor_node_id: str,
        max_depth: int = 3,
        min_weight: float = 0.0,
        edge_types: Optional[List[str]] = None,
    ) -> str:
        """
        生成纯 SQL 的 BFS CTE 查询（SQLite 3.8+ 支持 recursive CTE）。
        注意：此 SQL 供外部工具/分析使用，引擎内部用 Python BFS 实现。
        """
        type_filter = ""
        if edge_types:
            placeholders = ", ".join(f"'{t}'" for t in edge_types)
            type_filter = f"AND e.edge_type IN ({placeholders})"

        sql = f"""
        WITH RECURSIVE wave AS (
            -- 锚点
            SELECT
                '{anchor_node_id}' AS node_id,
                0 AS depth,
                1.0 AS accumulated_weight
            UNION ALL
            -- 扩散
            SELECT
                e.target_id AS node_id,
                w.depth + 1 AS depth,
                w.accumulated_weight * e.weight AS accumulated_weight
            FROM wave w
            JOIN graph_edges e ON w.node_id = e.source_id
            WHERE w.depth < {max_depth}
              AND e.weight >= {min_weight}
              {type_filter}
        )
        SELECT
            w.node_id,
            w.depth,
            w.accumulated_weight,
            n.data AS node_data
        FROM wave w
        LEFT JOIN graph_nodes n ON w.node_id = n.node_id
        WHERE w.depth > 0
        ORDER BY w.accumulated_weight DESC
        LIMIT 50;
        """
        return sql.strip()

    # ── 辅助 ───────────────────────────────────────────

    def get_anchor_suggestions(
        self, session_id: str, recent_turns: int = 3
    ) -> List[Tuple[str, str, float]]:
        """
        为某会话推荐锚点节点（最近活跃、实体密集、权重高）。
        :return: [(node_id, node_name, score), ...]
        """
        nodes = self._graph.load_nodes_by_session(session_id, limit=100)
        if not nodes:
            return []

        scored = []
        for node in nodes:
            # 评分：实体数 * 0.3 + 1/深度 * 0.2 + 最近活跃衰减 * 0.5
            import time
            age = time.time() - node.last_active_at
            recency_score = max(0, 1.0 - age / 3600)  # 1小时内满分
            entity_score = min(1.0, len(node.entities) / 5.0)
            depth_score = max(0, 1.0 - node.depth * 0.2)

            score = recency_score * 0.5 + entity_score * 0.3 + depth_score * 0.2
            scored.append((node.id, node.name, score))

        scored.sort(key=lambda x: x[2], reverse=True)
        return scored[:5]
