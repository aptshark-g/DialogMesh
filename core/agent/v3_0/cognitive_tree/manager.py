# -*- coding: utf-8 -*-
"""
core/agent/v3_0/cognitive_tree/manager.py
────────────────────────────────────────
Cognitive Tree Manager v3.0 — 认知树核心管理器

职责:
  - 认知节点与边的生命周期管理
  - 树结构遍历（DFS / BFS）
  - 活跃分支与失效分支追踪
  - 索引维护（按类型 / LLM / 状态）
  - 异步批量写入与事务性 Flush
  - 序列化与反序列化

对应工程文档: ENGINEERING_DATA_MODEL.md §12
对应设计文档: DESIGN_MULTILAYER_LLM_COGNITIVE.md §4.2

版本: 3.0.0
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from core.agent.v3_0.cognitive_tree.models import (
    AccessControlMatrix,
    CognitiveTreeEdge,
    CognitiveTreeNode,
    CogEdgeType,
    CogNodeStatus,
    CogType,
    LLMPermissions,
)

logger = logging.getLogger(__name__)


class CognitiveTree:
    """认知树 — LLM 的共享心智空间

    对应设计文档: DESIGN_MULTILAYER_LLM_COGNITIVE.md §2.2.2
    """

    def __init__(self, session_id: Optional[str] = None, depth_limit: int = 10):
        self.session_id: Optional[str] = session_id

        # 核心存储
        self.nodes: Dict[str, CognitiveTreeNode] = {}  # node_id -> node
        self.edges: List[CognitiveTreeEdge] = []         # 边列表

        # 索引（加速查询）
        self._by_type: Dict[CogType, Set[str]] = {}       # 类型 -> 节点 ID 集合
        self._by_llm: Dict[str, Set[str]] = {}            # LLM -> 节点 ID 集合
        self._by_status: Dict[CogNodeStatus, Set[str]] = {}  # 状态 -> 节点 ID 集合
        self._adjacency: Dict[str, Set[str]] = {}         # source_id -> {target_id, ...}
        self._reverse_adj: Dict[str, Set[str]] = {}       # target_id -> {source_id, ...}

        # 树结构管理
        self.root: Optional[str] = None                   # 根节点 ID
        self.active_branch: List[str] = []                # 当前活跃分支节点 ID 列表
        self.stale_branches: List[List[str]] = []        # 失效分支列表
        self.depth_limit: int = depth_limit

        # 访问控制
        self.access_control = AccessControlMatrix()

        # 事务性写入（v3.0 新增）
        self._pending_writes: Dict[str, CognitiveTreeNode] = {}  # node_id -> node
        self._pending_edges: List[CognitiveTreeEdge] = []         # 待写入边
        self._write_lock: Optional[asyncio.Lock] = None

    def _ensure_write_lock(self) -> asyncio.Lock:
        if self._write_lock is None:
            self._write_lock = asyncio.Lock()
        return self._write_lock

    # ═══════════════════════════════════════════════════════════════════
    # 节点管理
    # ═══════════════════════════════════════════════════════════════════

    def add_node(
        self,
        node: CognitiveTreeNode,
        parent_id: Optional[str] = None,
        check_permission: bool = True,
        requester_llm: str = "",
    ) -> None:
        """添加认知节点到树

        Args:
            node: 要添加的认知节点
            parent_id: 逻辑父节点 ID（可选）
            check_permission: 是否检查访问权限
            requester_llm: 请求者 LLM 名称（用于权限检查）
        """
        try:
            if check_permission and requester_llm:
                if not self.access_control.check_create(requester_llm, node.cog_type):
                    raise PermissionError(
                        f"LLM '{requester_llm}' 无权限创建类型为 {node.cog_type.value} 的节点"
                    )

            # 设置父子关系与深度
            if parent_id and parent_id in self.nodes:
                node.parent_id = parent_id
                node.depth = self.nodes[parent_id].depth + 1
                # 如果深度超限，标记并记录
                if node.depth > self.depth_limit:
                    logger.warning(
                        "节点 %s 深度 %d 超过限制 %d",
                        node.node_id, node.depth, self.depth_limit
                    )
                    node.metadata["depth_exceeded"] = True
            elif not self.root and not parent_id:
                # 首个节点作为根
                self.root = node.node_id
                node.depth = 0

            # 存入节点表
            self.nodes[node.node_id] = node

            # 更新索引
            self._index_node(node)

            # 标记待写入
            self._mark_dirty(node)

            logger.debug("添加节点: %s (type=%s)", node.node_id, node.cog_type.value)

        except PermissionError:
            raise
        except Exception as e:
            logger.error("add_node 失败: %s", e)
            raise

    def get_node(self, node_id: str) -> Optional[CognitiveTreeNode]:
        """按 ID 获取认知节点"""
        return self.nodes.get(node_id)

    def update_node(
        self,
        node_id: str,
        requester_llm: str = "",
        **kwargs: Any,
    ) -> bool:
        """更新认知节点属性

        Args:
            node_id: 目标节点 ID
            requester_llm: 请求者 LLM 名称
            **kwargs: 要更新的字段及其新值
        """
        try:
            node = self.nodes.get(node_id)
            if not node:
                logger.warning("update_node: 节点 %s 不存在", node_id)
                return False

            # 权限检查
            if requester_llm:
                if not self.access_control.check_update(
                    requester_llm, node_id, node.source_llm
                ):
                    raise PermissionError(
                        f"LLM '{requester_llm}' 无权限更新节点 {node_id}"
                    )

            # 更新字段
            for key, value in kwargs.items():
                if hasattr(node, key):
                    old_value = getattr(node, key)
                    setattr(node, key, value)
                    # 若状态变更，更新状态索引
                    if key == "status" and old_value != value:
                        self._reindex_status(node_id, old_value, value)
                else:
                    logger.warning("节点 %s 无属性 '%s'，跳过", node_id, key)

            # 标记待写入
            self._mark_dirty(node)
            return True

        except PermissionError:
            raise
        except Exception as e:
            logger.error("update_node 失败: %s", e)
            raise

    def update_node_status(
        self,
        node_id: str,
        status: CogNodeStatus,
        requester_llm: str = "",
    ) -> bool:
        """更新节点状态（便捷方法）"""
        return self.update_node(node_id, requester_llm, status=status)

    def remove_node(self, node_id: str, requester_llm: str = "") -> bool:
        """移除认知节点及其关联边

        Args:
            node_id: 要移除的节点 ID
            requester_llm: 请求者 LLM 名称
        """
        try:
            node = self.nodes.get(node_id)
            if not node:
                return False

            if requester_llm:
                if not self.access_control.check_delete(
                    requester_llm, node_id, node.source_llm
                ):
                    raise PermissionError(
                        f"LLM '{requester_llm}' 无权限删除节点 {node_id}"
                    )

            # 从索引中移除
            self._unindex_node(node_id)

            # 移除关联边
            self.edges = [
                e for e in self.edges
                if e.source_id != node_id and e.target_id != node_id
            ]
            self._rebuild_adjacency()

            # 从节点表移除
            del self.nodes[node_id]

            # 从待写入中移除（如果存在）
            self._pending_writes.pop(node_id, None)

            logger.debug("移除节点: %s", node_id)
            return True

        except PermissionError:
            raise
        except Exception as e:
            logger.error("remove_node 失败: %s", e)
            raise

    # ═══════════════════════════════════════════════════════════════════
    # 边管理
    # ═══════════════════════════════════════════════════════════════════

    def add_edge(
        self,
        edge: CognitiveTreeEdge,
        check_nodes_exist: bool = True,
    ) -> None:
        """添加认知边

        Args:
            edge: 要添加的边
            check_nodes_exist: 是否校验 source/target 节点存在
        """
        try:
            if check_nodes_exist:
                if edge.source_id not in self.nodes:
                    raise ValueError(f"source 节点 {edge.source_id} 不存在")
                if edge.target_id not in self.nodes:
                    raise ValueError(f"target 节点 {edge.target_id} 不存在")

            # 防重边（同 source + target + type）
            for existing in self.edges:
                if (
                    existing.source_id == edge.source_id
                    and existing.target_id == edge.target_id
                    and existing.edge_type == edge.edge_type
                ):
                    logger.debug(
                        "重复边已存在: %s -> %s (%s)",
                        edge.source_id, edge.target_id, edge.edge_type.value
                    )
                    return

            self.edges.append(edge)
            self._index_edge(edge)
            self._pending_edges.append(edge)

            logger.debug(
                "添加边: %s -> %s (%s)",
                edge.source_id, edge.target_id, edge.edge_type.value
            )

        except Exception as e:
            logger.error("add_edge 失败: %s", e)
            raise

    def get_outgoing(self, node_id: str) -> List[CognitiveTreeEdge]:
        """获取从某节点出发的所有边"""
        return [e for e in self.edges if e.source_id == node_id]

    def get_incoming(self, node_id: str) -> List[CognitiveTreeEdge]:
        """获取指向某节点的所有边"""
        return [e for e in self.edges if e.target_id == node_id]

    def get_neighbors(self, node_id: str) -> List[str]:
        """获取相邻节点 ID（出边 + 入边）"""
        neighbors: Set[str] = set()
        for e in self.edges:
            if e.source_id == node_id:
                neighbors.add(e.target_id)
            if e.target_id == node_id:
                neighbors.add(e.source_id)
        return list(neighbors)

    def remove_edge(self, edge_id: str) -> bool:
        """按 edge_id 移除边"""
        try:
            for idx, e in enumerate(self.edges):
                if e.edge_id == edge_id:
                    self.edges.pop(idx)
                    self._rebuild_adjacency()
                    return True
            return False
        except Exception as e:
            logger.error("remove_edge 失败: %s", e)
            raise

    # ═══════════════════════════════════════════════════════════════════
    # 索引维护
    # ═══════════════════════════════════════════════════════════════════

    def _index_node(self, node: CognitiveTreeNode) -> None:
        """将节点加入各索引"""
        self._by_type.setdefault(node.cog_type, set()).add(node.node_id)
        self._by_llm.setdefault(node.source_llm, set()).add(node.node_id)
        self._by_status.setdefault(node.status, set()).add(node.node_id)

    def _unindex_node(self, node_id: str) -> None:
        """从各索引中移除节点"""
        for idx_map in (self._by_type, self._by_llm, self._by_status):
            for key, id_set in list(idx_map.items()):
                id_set.discard(node_id)
                if not id_set:
                    del idx_map[key]

    def _reindex_status(
        self,
        node_id: str,
        old_status: CogNodeStatus,
        new_status: CogNodeStatus,
    ) -> None:
        """状态变更后重建状态索引"""
        self._by_status.setdefault(old_status, set()).discard(node_id)
        self._by_status.setdefault(new_status, set()).add(node_id)
        # 清理空集合
        if old_status in self._by_status and not self._by_status[old_status]:
            del self._by_status[old_status]

    def _index_edge(self, edge: CognitiveTreeEdge) -> None:
        """将边加入邻接表"""
        self._adjacency.setdefault(edge.source_id, set()).add(edge.target_id)
        self._reverse_adj.setdefault(edge.target_id, set()).add(edge.source_id)

    def _rebuild_adjacency(self) -> None:
        """重建邻接表（批量操作后）"""
        self._adjacency.clear()
        self._reverse_adj.clear()
        for e in self.edges:
            self._adjacency.setdefault(e.source_id, set()).add(e.target_id)
            self._reverse_adj.setdefault(e.target_id, set()).add(e.source_id)

    # ═══════════════════════════════════════════════════════════════════
    # 查询 API
    # ═══════════════════════════════════════════════════════════════════

    def find_by_type(self, cog_type: CogType) -> List[CognitiveTreeNode]:
        """按类型查询认知节点"""
        node_ids = self._by_type.get(cog_type, set())
        return [self.nodes[nid] for nid in node_ids if nid in self.nodes]

    def find_by_llm(self, llm_name: str) -> List[CognitiveTreeNode]:
        """按 LLM 来源查询认知节点"""
        node_ids = self._by_llm.get(llm_name, set())
        return [self.nodes[nid] for nid in node_ids if nid in self.nodes]

    def find_by_status(self, status: CogNodeStatus) -> List[CognitiveTreeNode]:
        """按状态查询认知节点"""
        node_ids = self._by_status.get(status, set())
        return [self.nodes[nid] for nid in node_ids if nid in self.nodes]

    def find_active_branch(self) -> List[CognitiveTreeNode]:
        """获取当前活跃分支的节点列表"""
        return [self.nodes[nid] for nid in self.active_branch if nid in self.nodes]

    def find_stale_branches(self) -> List[List[CognitiveTreeNode]]:
        """获取所有失效分支的节点列表"""
        result: List[List[CognitiveTreeNode]] = []
        for branch in self.stale_branches:
            nodes = [self.nodes[nid] for nid in branch if nid in self.nodes]
            if nodes:
                result.append(nodes)
        return result

    def find_roots(self) -> List[CognitiveTreeNode]:
        """查找所有无入边的根节点"""
        root_ids = [nid for nid in self.nodes if nid not in self._reverse_adj]
        return [self.nodes[nid] for nid in root_ids]

    def find_leaves(self) -> List[CognitiveTreeNode]:
        """查找所有无出边的叶节点"""
        leaf_ids = [nid for nid in self.nodes if nid not in self._adjacency]
        return [self.nodes[nid] for nid in leaf_ids]

    def search_content(self, keyword: str) -> List[CognitiveTreeNode]:
        """按关键词搜索节点内容（简单子串匹配）"""
        keyword_lower = keyword.lower()
        return [
            node for node in self.nodes.values()
            if keyword_lower in node.content.lower()
        ]

    # ═══════════════════════════════════════════════════════════════════
    # 树遍历
    # ═══════════════════════════════════════════════════════════════════

    def traverse_dfs(
        self,
        start_node: str,
        max_depth: Optional[int] = None,
    ) -> List[CognitiveTreeNode]:
        """深度优先遍历

        Args:
            start_node: 起始节点 ID
            max_depth: 最大遍历深度（None 表示无限制）
        """
        if start_node not in self.nodes:
            logger.warning("traverse_dfs: 起始节点 %s 不存在", start_node)
            return []

        result: List[CognitiveTreeNode] = []
        visited: Set[str] = set()
        stack: List[Tuple[str, int]] = [(start_node, 0)]

        while stack:
            node_id, depth = stack.pop()
            if node_id in visited:
                continue
            if max_depth is not None and depth > max_depth:
                continue

            visited.add(node_id)
            node = self.nodes.get(node_id)
            if node:
                result.append(node)

            # 将子节点按创建时间倒序入栈（保持时序）
            children = sorted(
                self._adjacency.get(node_id, set()),
                key=lambda nid: self.nodes.get(nid, CognitiveTreeNode()).timestamp,
                reverse=True,
            )
            for child_id in children:
                if child_id not in visited:
                    stack.append((child_id, depth + 1))

        return result

    def traverse_bfs(
        self,
        start_node: str,
        max_depth: Optional[int] = None,
    ) -> List[CognitiveTreeNode]:
        """广度优先遍历

        Args:
            start_node: 起始节点 ID
            max_depth: 最大遍历深度（None 表示无限制）
        """
        if start_node not in self.nodes:
            logger.warning("traverse_bfs: 起始节点 %s 不存在", start_node)
            return []

        result: List[CognitiveTreeNode] = []
        visited: Set[str] = set()
        queue: List[Tuple[str, int]] = [(start_node, 0)]
        idx = 0

        while idx < len(queue):
            node_id, depth = queue[idx]
            idx += 1
            if node_id in visited:
                continue
            if max_depth is not None and depth > max_depth:
                continue

            visited.add(node_id)
            node = self.nodes.get(node_id)
            if node:
                result.append(node)

            for child_id in self._adjacency.get(node_id, set()):
                if child_id not in visited:
                    queue.append((child_id, depth + 1))

        return result

    def get_path_to_root(self, node_id: str) -> List[CognitiveTreeNode]:
        """获取从某节点到根节点的路径（自底向上）"""
        path: List[CognitiveTreeNode] = []
        current = self.nodes.get(node_id)
        visited: Set[str] = set()

        while current and current.node_id not in visited:
            path.append(current)
            visited.add(current.node_id)
            # 使用 _reverse_adj 查找父节点（树结构中通常只有一个）
            parents = self._reverse_adj.get(current.node_id, set())
            parent_id = next(iter(parents)) if parents else None
            current = self.nodes.get(parent_id) if parent_id else None

        return list(reversed(path))

    # ═══════════════════════════════════════════════════════════════════
    # 活跃分支管理
    # ═══════════════════════════════════════════════════════════════════

    def set_active_branch(self, node_ids: List[str]) -> None:
        """设置当前活跃分支

        旧活跃分支若与当前无交集，则移入 stale_branches
        """
        try:
            # 验证节点存在
            valid_ids = [nid for nid in node_ids if nid in self.nodes]
            if len(valid_ids) != len(node_ids):
                missing = set(node_ids) - set(valid_ids)
                logger.warning("活跃分支包含不存在的节点: %s", missing)

            # 旧分支保存为失效分支（如果有节点不再在新分支中）
            if self.active_branch:
                old_set = set(self.active_branch)
                new_set = set(valid_ids)
                stale = old_set - new_set
                if stale:
                    stale_list = [nid for nid in self.active_branch if nid in stale]
                    self.stale_branches.append(stale_list)
                    # 清理过长的 stale_branches 列表（保留最近 10 条）
                    if len(self.stale_branches) > 10:
                        self.stale_branches = self.stale_branches[-10:]

            self.active_branch = valid_ids
            logger.debug("活跃分支已更新: %d 个节点", len(self.active_branch))

        except Exception as e:
            logger.error("set_active_branch 失败: %s", e)
            raise

    def append_to_active_branch(self, node_id: str) -> None:
        """将节点追加到活跃分支末尾"""
        if node_id not in self.nodes:
            raise ValueError(f"节点 {node_id} 不存在")
        if node_id in self.active_branch:
            # 若已存在，先移除再追加（移至末尾）
            self.active_branch.remove(node_id)
        self.active_branch.append(node_id)

    # ═══════════════════════════════════════════════════════════════════
    # 事务性写入（v3.0 新增）
    # ═══════════════════════════════════════════════════════════════════

    def _mark_dirty(self, node: CognitiveTreeNode) -> None:
        """标记节点为待写入（内存更新，不立即持久化）"""
        self._pending_writes[node.node_id] = node

    def _mark_edge_dirty(self, edge: CognitiveTreeEdge) -> None:
        """标记边为待写入"""
        self._pending_edges.append(edge)

    async def flush(self) -> Tuple[int, int]:
        """批量持久化所有待写入的节点和边

        Returns:
            (flushed_nodes, flushed_edges)
        """
        async with self._ensure_write_lock():
            node_count = len(self._pending_writes)
            edge_count = len(self._pending_edges)

            if node_count == 0 and edge_count == 0:
                return 0, 0

            try:
                # TODO: 在此接入实际持久化层（如 GraphStore / SQLite）
                # 当前阶段仅清空内存队列，并记录日志
                logger.info(
                    "Flush: %d 节点, %d 边 (session=%s)",
                    node_count, edge_count, self.session_id
                )

                self._pending_writes.clear()
                self._pending_edges.clear()
                return node_count, edge_count

            except Exception as e:
                logger.error("flush 失败: %s", e)
                raise

    async def emergency_flush(self) -> Tuple[int, int]:
        """异常时紧急 flush — 保证已处理状态不丢失"""
        try:
            return await self.flush()
        except Exception as e:
            logger.error("Emergency flush 失败: %s", e)
            return 0, 0

    # ═══════════════════════════════════════════════════════════════════
    # 序列化与反序列化
    # ═══════════════════════════════════════════════════════════════════

    def to_dict(self) -> Dict[str, Any]:
        """将整棵树序列化为字典"""
        return {
            "session_id": self.session_id,
            "root": self.root,
            "active_branch": list(self.active_branch),
            "stale_branches": [list(b) for b in self.stale_branches],
            "depth_limit": self.depth_limit,
            "nodes": {
                nid: node.to_dict() for nid, node in self.nodes.items()
            },
            "edges": [e.to_dict() for e in self.edges],
            "access_control": self.access_control.to_dict(),
            "__version__": "3.0",
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CognitiveTree":
        """从字典反序列化整棵树"""
        try:
            tree = cls(session_id=d.get("session_id"))
            tree.root = d.get("root")
            tree.active_branch = list(d.get("active_branch", []))
            tree.stale_branches = [
                list(b) for b in d.get("stale_branches", [])
            ]
            tree.depth_limit = d.get("depth_limit", 10)

            # 反序列化节点
            for nid, node_dict in d.get("nodes", {}).items():
                try:
                    node = CognitiveTreeNode.from_dict(node_dict)
                    tree.nodes[nid] = node
                    tree._index_node(node)
                except Exception as e:
                    logger.warning("节点 %s 反序列化失败: %s", nid, e)

            # 反序列化边
            for edge_dict in d.get("edges", []):
                try:
                    edge = CognitiveTreeEdge.from_dict(edge_dict)
                    tree.edges.append(edge)
                    tree._index_edge(edge)
                except Exception as e:
                    logger.warning("边反序列化失败: %s", e)

            # 反序列化访问控制
            ac_dict = d.get("access_control")
            if ac_dict:
                try:
                    tree.access_control = AccessControlMatrix.from_dict(ac_dict)
                except Exception as e:
                    logger.warning("访问控制反序列化失败: %s", e)

            return tree

        except Exception as e:
            logger.error("CognitiveTree.from_dict 失败: %s", e)
            raise

    def __repr__(self) -> str:
        return (
            f"CognitiveTree(session={self.session_id!r}, "
            f"nodes={len(self.nodes)}, edges={len(self.edges)}, "
            f"active={len(self.active_branch)})"
        )
