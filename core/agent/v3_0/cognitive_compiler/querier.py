# -*- coding: utf-8 -*-
"""
core/agent/v3_0/cognitive_compiler/querier.py
──────────────────────────────────────────────
Cognitive Tree 查询与遍历引擎。

提供按属性查询（类型/LLM/状态）和图遍历（DFS/BFS/活跃分支/失效分支）能力。

对应工程文档: ENGINEERING_COGNITIVE_COMPILER.md §10
版本: 3.0.0
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any, List, Optional

from core.agent.v3_0.cognitive_tree.models import (
    CognitiveTreeNode,
    CogEdgeType,
    CogNodeStatus,
    CogType,
)

logger = logging.getLogger(__name__)


class Querier:
    """
    Cognitive Tree 查询与遍历引擎。

    职责:
      - 按认知类型 / LLM 来源 / 状态查询节点
      - 深度优先与广度优先遍历
      - 活跃分支与失效分支追踪
    """

    def __init__(self, store: Any) -> None:
        """
        Args:
            store: 存储层实例，提供 load_node / load_nodes / load_edges_from / load_edges_to 接口
        """
        self._store = store

    # ── 按属性查询 ─────────────────────────────────────────────

    def find_by_type(self, session_id: str, cog_type: CogType) -> List[CognitiveTreeNode]:
        """按认知类型查询节点。"""
        try:
            nodes = self._store.load_nodes(session_id)
            return [n for n in nodes if n.cog_type == cog_type]
        except Exception as e:
            logger.error("find_by_type failed (%s): %s", cog_type.value, e)
            return []

    def find_by_llm(self, session_id: str, llm_name: str) -> List[CognitiveTreeNode]:
        """按 LLM 来源查询节点。"""
        try:
            nodes = self._store.load_nodes(session_id)
            return [n for n in nodes if n.source_llm == llm_name]
        except Exception as e:
            logger.error("find_by_llm failed (%s): %s", llm_name, e)
            return []

    def find_by_status(self, session_id: str, status: CogNodeStatus) -> List[CognitiveTreeNode]:
        """按状态查询节点。"""
        try:
            nodes = self._store.load_nodes(session_id)
            return [n for n in nodes if n.status == status]
        except Exception as e:
            logger.error("find_by_status failed (%s): %s", status.value, e)
            return []

    def find_active(self, session_id: str) -> List[CognitiveTreeNode]:
        """查找所有 ACTIVE 节点。"""
        return self.find_by_status(session_id, CogNodeStatus.ACTIVE)

    # ── 遍历 ───────────────────────────────────────────────────

    def traverse_dfs(
        self, session_id: str, start_node_id: str
    ) -> List[CognitiveTreeNode]:
        """深度优先遍历。"""
        try:
            visited: set = set()
            result: List[CognitiveTreeNode] = []
            stack: List[str] = [start_node_id]

            while stack:
                node_id = stack.pop()
                if node_id in visited:
                    continue
                visited.add(node_id)

                node = self._store.load_node(session_id, node_id)
                if node:
                    result.append(node)
                    edges = self._store.load_edges_from(session_id, node_id)
                    for edge in edges:
                        if edge.target_id not in visited:
                            stack.append(edge.target_id)

            return result
        except Exception as e:
            logger.error("traverse_dfs failed from %s: %s", start_node_id, e)
            return []

    def traverse_bfs(
        self, session_id: str, start_node_id: str
    ) -> List[CognitiveTreeNode]:
        """广度优先遍历。"""
        try:
            visited: set = set()
            result: List[CognitiveTreeNode] = []
            queue: deque = deque([start_node_id])

            while queue:
                node_id = queue.popleft()
                if node_id in visited:
                    continue
                visited.add(node_id)

                node = self._store.load_node(session_id, node_id)
                if node:
                    result.append(node)
                    edges = self._store.load_edges_from(session_id, node_id)
                    for edge in edges:
                        if edge.target_id not in visited:
                            queue.append(edge.target_id)

            return result
        except Exception as e:
            logger.error("traverse_bfs failed from %s: %s", start_node_id, e)
            return []

    def find_active_branch(self, session_id: str) -> List[CognitiveTreeNode]:
        """
        查找当前活跃分支（从 root 到最新的 ACTIVE 节点）。

        选取最新 ACTIVE 节点，沿 DERIVES / SUPPORTS 边回溯到根。
        """
        try:
            active_nodes = self.find_active(session_id)
            if not active_nodes:
                return []

            latest = max(active_nodes, key=lambda n: n.timestamp)
            branch: List[CognitiveTreeNode] = [latest]
            current = latest

            for _ in range(10):  # 深度限制
                edges = self._store.load_edges_to(session_id, current.node_id)
                parent_edges = [
                    e for e in edges
                    if e.edge_type in (CogEdgeType.DERIVES, CogEdgeType.SUPPORTS)
                ]
                if not parent_edges:
                    break
                best = max(parent_edges, key=lambda e: e.weight)
                parent = self._store.load_node(session_id, best.source_id)
                if parent:
                    branch.insert(0, parent)
                    current = parent
                else:
                    break

            return branch
        except Exception as e:
            logger.error("find_active_branch failed: %s", e)
            return []

    def find_stale_branches(
        self, session_id: str, max_age_seconds: float = 3600
    ) -> List[List[CognitiveTreeNode]]:
        """
        查找失效分支（超过最大年龄未更新的 ACTIVE 节点）。

        Args:
            max_age_seconds: 最大保留时间，默认 3600 秒（1 小时）
        """
        try:
            cutoff = time.time() - max_age_seconds
            active_nodes = self.find_active(session_id)

            stale: List[List[CognitiveTreeNode]] = []
            for node in active_nodes:
                if node.timestamp < cutoff:
                    branch = self.find_active_branch(session_id)
                    if branch:
                        stale.append(branch)
            return stale
        except Exception as e:
            logger.error("find_stale_branches failed: %s", e)
            return []
