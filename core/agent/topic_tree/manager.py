# -*- coding: utf-8 -*-
"""
core/agent/topic_tree/manager.py
──────────────────────────────
Topic tree manager: routing, forking, attachment, and graph traversal.

设计要点：
  - 路由算法：利用 cohesion_score 快速决策（continue / fork / attach）
  - 树投影：当前活跃分支
  - 图关联：跨话题实体关联
  - 时间复杂度：路由 < 5ms（纯规则匹配）
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from core.agent.topic_tree.models import TopicNode, TopicEdge, TopicEdgeType


@dataclass
class RoutingDecision:
    """话题路由决策结果。"""
    action: str                      # "continue" | "fork" | "attach" | "new"
    target_node_id: Optional[str] = None
    cohesion_score: float = 0.0
    reason: str = ""


class TopicTreeManager:
    """
    话题树管理器。
    管理话题的创建、路由、分叉和回溯。
    增加：局部热区 + 深度阈值 + 路径压缩。
    """

    # 路由阈值
    COHESION_CONTINUE_THRESHOLD = 0.6
    COHESION_FORK_THRESHOLD = 0.3

    # 深度防御
    MAX_DEPTH = 6                      # 树深度阈值，超过触发路径压缩
    HOT_ZONE_DEPTH = 2                 # 局部热区：当前节点前后 2 层直系

    def __init__(self):
        # 节点存储
        self._nodes: Dict[str, TopicNode] = {}
        # 边存储
        self._edges: List[TopicEdge] = []
        # 当前活跃节点
        self._current_node_id: Optional[str] = None
        # 根节点
        self._root_id: Optional[str] = None
        # 实体到节点的索引
        self._entity_index: Dict[str, Set[str]] = {}
        # 局部热区（内存中只保留这些节点全量）
        self._hot_zone: Set[str] = set()

    # ── 热区管理 ───────────────────────────────────────────

    def _maintain_hot_zone(self, current_node_id: str) -> None:
        """维护局部热区：当前节点 + 前 2 层祖先 + 后 1 层后代。"""
        self._hot_zone.clear()
        self._hot_zone.add(current_node_id)
        # 前 2 层祖先
        ancestors = self._get_ancestors(current_node_id, depth=self.HOT_ZONE_DEPTH)
        for node in ancestors:
            self._hot_zone.add(node.id)
        # 后 1 层后代（直系子节点）
        current = self._nodes.get(current_node_id)
        if current:
            for child_id in current.children_ids:
                self._hot_zone.add(child_id)

    def _hot_zone_lookup(self, query: str, entities: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
        """在热区中快速匹配。返回匹配的节点 ID 或 None。"""
        if not entities:
            return None
        entity_values = set()
        for entity in (entities or []):
            if isinstance(entity, dict):
                val = str(entity.get("value", ""))
                if val:
                    entity_values.add(val)
        if not entity_values:
            return None

        # 优先在热区中匹配
        for node_id in self._hot_zone:
            node = self._nodes.get(node_id)
            if not node:
                continue
            node_values = set()
            for e in node.entities:
                if isinstance(e, dict):
                    val = str(e.get("value", ""))
                    if val:
                        node_values.add(val)
            if node_values & entity_values:
                return node_id
        return None

    # ── 深度防御 ───────────────────────────────────────────

    def _check_depth_and_compress(self, node_id: str) -> None:
        """检查深度，超过阈值时触发路径压缩。"""
        path = self._get_path_to_root(node_id)
        if len(path) <= self.MAX_DEPTH:
            return

        # 找到中间点，将前半段压缩为摘要节点
        mid = len(path) // 2
        summary_node = self._create_summary_node(path[:mid])
        # 将后半段挂载到 summary_node
        for node in path[mid:]:
            node.parent_id = summary_node.id
            summary_node.children_ids.append(node.id)
        # 更新根节点（如果根被压缩了）
        if path[0].parent_id is None:
            self._root_id = summary_node.id

        # 重新计算所有节点的 depth（从 summary_node 开始 BFS）
        self._update_depth_recursive(summary_node.id, 0)

    def _update_depth_recursive(self, node_id: str, depth: int) -> None:
        """递归更新节点及其后代的 depth。"""
        node = self._nodes.get(node_id)
        if not node:
            return
        node.depth = depth
        for child_id in node.children_ids:
            self._update_depth_recursive(child_id, depth + 1)

    def _create_summary_node(self, nodes_to_compress: List[TopicNode]) -> TopicNode:
        """创建摘要节点。"""
        if not nodes_to_compress:
            return self._create_node(name="summary", parent_id=None, entities=[])

        # 合并实体和名称
        all_entities = []
        name_parts = []
        for node in nodes_to_compress:
            all_entities.extend(node.entities)
            if node.name and node.name not in name_parts:
                name_parts.append(node.name)

        summary_name = " | ".join(name_parts[:3]) + "..." if len(name_parts) > 3 else " | ".join(name_parts)
        summary_node = self._create_node(
            name=f"[摘要] {summary_name}",
            parent_id=nodes_to_compress[0].parent_id,
            entities=all_entities,
        )
        # 标记为摘要节点
        summary_node.metadata["is_summary"] = True
        summary_node.metadata["compressed_count"] = len(nodes_to_compress)
        return summary_node

    def _get_path_to_root(self, node_id: str) -> List[TopicNode]:
        """获取从节点到根的路径。"""
        path = []
        current = self._nodes.get(node_id)
        while current:
            path.append(current)
            if current.parent_id and current.parent_id in self._nodes:
                current = self._nodes[current.parent_id]
            else:
                break
        return list(reversed(path))

    def _get_ancestors(self, node_id: str, depth: int = 2) -> List[TopicNode]:
        """获取最近 N 层祖先。"""
        ancestors = []
        current = self._nodes.get(node_id)
        count = 0
        while current and current.parent_id and count < depth:
            parent = self._nodes.get(current.parent_id)
            if parent:
                ancestors.append(parent)
                current = parent
                count += 1
            else:
                break
        return list(reversed(ancestors))

    def _get_descendants(self, node_id: str, depth: int = 1) -> List[TopicNode]:
        """获取最近 N 层后代。"""
        descendants = []
        queue = [(node_id, 0)]
        while queue:
            current_id, level = queue.pop(0)
            if level >= depth:
                continue
            node = self._nodes.get(current_id)
            if not node:
                continue
            for child_id in node.children_ids:
                child = self._nodes.get(child_id)
                if child:
                    descendants.append(child)
                    queue.append((child_id, level + 1))
        return descendants

    # ── 核心 API：路由 ───────────────────────────────────────────

    def route(
        self,
        query: str,
        turn_index: int,
        cohesion_score: Optional[float] = None,
        extracted_entities: Optional[List[Dict[str, Any]]] = None,
    ) -> RoutingDecision:
        """
        话题路由。
        利用 cohesion_score（如果提供）快速决策，否则基于实体匹配。
        """
        # 优先在热区中匹配（快速命中）
        hot_zone_hit = self._hot_zone_lookup(query, extracted_entities)
        if hot_zone_hit and hot_zone_hit != self._current_node_id:
            # 热区命中且不在当前节点 → attach（回溯旧话题）
            self._current_node_id = hot_zone_hit
            self._maintain_hot_zone(hot_zone_hit)
            return RoutingDecision(
                action="attach",
                target_node_id=hot_zone_hit,
                cohesion_score=0.5,
                reason="热区实体匹配命中，回溯旧话题",
            )

        if cohesion_score is not None:
            if cohesion_score >= self.COHESION_CONTINUE_THRESHOLD:
                decision = self._route_continue()
            elif cohesion_score < self.COHESION_FORK_THRESHOLD:
                decision = self._route_fork(query, extracted_entities)
            else:
                decision = self._route_attach(query, extracted_entities)
        else:
            decision = self._route_by_entity_match(query, extracted_entities)

        # 路由后维护热区
        if decision.target_node_id:
            self._maintain_hot_zone(decision.target_node_id)
            # 检查深度
            self._check_depth_and_compress(decision.target_node_id)
        return decision

    def _route_continue(self) -> RoutingDecision:
        """继续当前话题。"""
        if self._current_node_id is None:
            return self._route_new("continue 但无当前话题", entities=[])
        return RoutingDecision(
            action="continue",
            target_node_id=self._current_node_id,
            cohesion_score=1.0,
            reason="cohesion_score >= 0.6，继续当前话题",
        )

    def _route_fork(self, query: str, entities: Optional[List[Dict[str, Any]]]) -> RoutingDecision:
        """创建新话题（分叉）。"""
        if self._current_node_id is None:
            return self._route_new("fork 但无父话题", entities=entities)

        parent_node = self._nodes[self._current_node_id]
        new_node = self._create_node(
            name=self._extract_topic_name(query),
            parent_id=parent_node.id,
            entities=entities or [],
        )
        self._add_edge(
            parent_node.id, new_node.id, TopicEdgeType.PARENT_CHILD,
            metadata={"fork_reason": "cohesion_score < 0.3"}
        )
        self._current_node_id = new_node.id
        return RoutingDecision(
            action="fork",
            target_node_id=new_node.id,
            cohesion_score=0.0,
            reason="cohesion_score < 0.3，创建新话题分支",
        )

    def _route_attach(self, query: str, entities: Optional[List[Dict[str, Any]]]) -> RoutingDecision:
        """附着到最相似的历史话题。如果最佳匹配就是当前节点，直接继续。"""
        best_node = self._find_most_similar_node(query, entities)
        if best_node is None:
            # 如果当前节点有共享实体，也视为 continue
            current_node = self._nodes.get(self._current_node_id) if self._current_node_id else None
            if current_node and entities and self._has_shared_entities(current_node, entities):
                return self._route_continue()
            return self._route_fork(query, entities)
        if best_node.id == self._current_node_id:
            return self._route_continue()

        self._current_node_id = best_node.id
        return RoutingDecision(
            action="attach",
            target_node_id=best_node.id,
            cohesion_score=0.5,
            reason="cohesion_score 在 [0.3, 0.6) 之间，附着到相似话题",
        )

    def _route_new(self, reason: str, entities: Optional[List[Dict[str, Any]]] = None) -> RoutingDecision:
        """创建全新话题（无父节点）。"""
        new_node = self._create_node(
            name="root",
            parent_id=None,
            entities=entities or [],
        )
        self._root_id = new_node.id
        self._current_node_id = new_node.id
        return RoutingDecision(
            action="new",
            target_node_id=new_node.id,
            cohesion_score=0.0,
            reason=reason,
        )

    def _route_by_entity_match(
        self, query: str, entities: Optional[List[Dict[str, Any]]]
    ) -> RoutingDecision:
        """基于实体匹配的回退路由。"""
        if not entities or not self._current_node_id:
            return self._route_new("无实体且无当前话题", entities=entities)

        current_node = self._nodes.get(self._current_node_id)
        if current_node and self._has_shared_entities(current_node, entities):
            return self._route_continue()

        return self._route_attach(query, entities)

    # ── 节点管理 ───────────────────────────────────────────

    def _create_node(
        self, name: str, parent_id: Optional[str], entities: List[Dict[str, Any]]
    ) -> TopicNode:
        """创建新话题节点。"""
        node = TopicNode(
            name=name,
            parent_id=parent_id,
            entities=entities,
            depth=0 if parent_id is None else self._nodes[parent_id].depth + 1,
        )
        self._nodes[node.id] = node

        if parent_id and parent_id in self._nodes:
            self._nodes[parent_id].children_ids.append(node.id)

        for entity in entities:
            if isinstance(entity, dict):
                val = str(entity.get("value", ""))
                if val:
                    self._entity_index.setdefault(val, set()).add(node.id)

        return node

    def _add_edge(
        self, source_id: str, target_id: str,
        edge_type: TopicEdgeType, weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TopicEdge:
        """添加边。"""
        edge = TopicEdge(
            source_id=source_id, target_id=target_id,
            edge_type=edge_type, weight=weight,
            metadata=metadata or {},
        )
        self._edges.append(edge)
        return edge

    # ── 查询 ───────────────────────────────────────────

    def _find_most_similar_node(
        self, query: str, entities: Optional[List[Dict[str, Any]]]
    ) -> Optional[TopicNode]:
        """查找最相似的历史话题节点。"""
        if not entities:
            return None

        entity_values = set()
        for entity in (entities or []):
            if isinstance(entity, dict):
                val = str(entity.get("value", ""))
                if val:
                    entity_values.add(val)

        best_node = None
        best_score = 0.0

        for node in self._nodes.values():
            if node.id == self._current_node_id:
                continue

            node_entities = set()
            for e in node.entities:
                if isinstance(e, dict):
                    val = str(e.get("value", ""))
                    if val:
                        node_entities.add(val)

            if not node_entities or not entity_values:
                continue

            intersection = len(entity_values & node_entities)
            union = len(entity_values | node_entities)
            score = intersection / union if union > 0 else 0.0

            time_decay = 1.0 / (1.0 + (time.time() - node.last_active_at) / 3600)
            score *= time_decay

            if score > best_score:
                best_score = score
                best_node = node

        return best_node if best_score > 0.1 else None

    def _has_shared_entities(
        self, node: TopicNode, entities: List[Dict[str, Any]]
    ) -> bool:
        """检查节点与实体列表是否有共享实体。"""
        node_values = set()
        for e in node.entities:
            if isinstance(e, dict):
                val = str(e.get("value", ""))
                if val:
                    node_values.add(val)

        for entity in entities:
            if isinstance(entity, dict):
                val = str(entity.get("value", ""))
                if val and val in node_values:
                    return True
        return False

    def _extract_topic_name(self, query: str) -> str:
        """从查询中提取话题名称。"""
        query = query.strip()
        if len(query) <= 20:
            return query
        return query[:20] + "..."

    # ── 公共查询 API ───────────────────────────────────────────

    def get_current_node(self) -> Optional[TopicNode]:
        """获取当前活跃话题节点。"""
        if self._current_node_id is None:
            return None
        return self._nodes.get(self._current_node_id)

    def get_node(self, node_id: str) -> Optional[TopicNode]:
        """按 ID 获取节点。"""
        return self._nodes.get(node_id)

    def get_ancestors(self, node_id: str) -> List[TopicNode]:
        """获取节点的所有祖先。"""
        ancestors = []
        current = self._nodes.get(node_id)
        while current and current.parent_id:
            parent = self._nodes.get(current.parent_id)
            if parent:
                ancestors.append(parent)
                current = parent
            else:
                break
        return list(reversed(ancestors))

    def get_descendants(self, node_id: str) -> List[TopicNode]:
        """获取节点的所有后代。"""
        descendants = []
        queue = [node_id]
        while queue:
            current_id = queue.pop(0)
            node = self._nodes.get(current_id)
            if not node:
                continue
            for child_id in node.children_ids:
                child = self._nodes.get(child_id)
                if child:
                    descendants.append(child)
                    queue.append(child_id)
        return descendants

    def get_related_nodes(self, node_id: str, edge_type: Optional[TopicEdgeType] = None) -> List[TopicNode]:
        """通过图边获取相关节点。"""
        related_ids = set()
        for edge in self._edges:
            if edge.source_id == node_id:
                if edge_type is None or edge.edge_type == edge_type:
                    related_ids.add(edge.target_id)
            elif edge.target_id == node_id:
                if edge_type is None or edge.edge_type == edge_type:
                    related_ids.add(edge.source_id)

        return [self._nodes[rid] for rid in related_ids if rid in self._nodes]

    def find_nodes_by_entity(self, entity_value: str) -> List[TopicNode]:
        """通过实体值查找所有关联节点。"""
        node_ids = self._entity_index.get(entity_value, set())
        return [self._nodes[nid] for nid in node_ids if nid in self._nodes]

    def get_all_nodes(self) -> List[TopicNode]:
        """获取所有节点。"""
        return list(self._nodes.values())

    def get_tree_summary(self) -> Dict[str, Any]:
        """获取树结构摘要。"""
        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "current_node_id": self._current_node_id,
            "root_id": self._root_id,
            "max_depth": max((n.depth for n in self._nodes.values()), default=0),
            "hot_zone_size": len(self._hot_zone),
        }

    # ── 序列化 ───────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典。"""
        return {
            "nodes": {nid: n.to_dict() for nid, n in self._nodes.items()},
            "edges": [e.to_dict() for e in self._edges],
            "current_node_id": self._current_node_id,
            "root_id": self._root_id,
            "entity_index": {k: list(v) for k, v in self._entity_index.items()},
            "hot_zone": list(self._hot_zone),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TopicTreeManager":
        """从字典恢复。"""
        manager = cls()
        for nid, nd in d.get("nodes", {}).items():
            manager._nodes[nid] = TopicNode.from_dict(nd)
        for ed in d.get("edges", []):
            manager._edges.append(TopicEdge.from_dict(ed))
        manager._current_node_id = d.get("current_node_id")
        manager._root_id = d.get("root_id")
        manager._entity_index = {
            k: set(v) for k, v in d.get("entity_index", {}).items()
        }
        manager._hot_zone = set(d.get("hot_zone", []))
        return manager

    # ── GraphStore 持久化 ───────────────────────────────────────────

    def save_to_graph_store(self, graph_store: "GraphStore", session_id: str) -> bool:
        """
        将话题树保存到 GraphStore。
        
        策略：先清除旧数据，再写入当前所有节点和边。
        """
        try:
            # 清除旧数据
            graph_store.delete_session_nodes(session_id)
            # 写入所有节点
            for node in self._nodes.values():
                graph_store.save_node(session_id, node)
            # 写入所有边
            for edge in self._edges:
                graph_store.save_edge(session_id, edge)
            return True
        except Exception as e:
            print(f"[TopicTreeManager] save_to_graph_store failed: {e}")
            return False

    @classmethod
    def load_from_graph_store(cls, graph_store: "GraphStore", session_id: str) -> Optional["TopicTreeManager"]:
        """
        从 GraphStore 加载话题树。
        
        返回 TopicTreeManager 或 None（无数据）。
        """
        nodes = graph_store.load_nodes_by_session(session_id, limit=1000)
        if not nodes:
            return None

        manager = cls()
        # 重建节点
        for node in nodes:
            manager._nodes[node.id] = node
            # 重建实体索引
            for entity in node.entities:
                if isinstance(entity, dict):
                    val = str(entity.get("value", ""))
                    if val:
                        manager._entity_index.setdefault(val, set()).add(node.id)
                elif isinstance(entity, str):
                    manager._entity_index.setdefault(entity, set()).add(node.id)

        # 重建边（从每个节点加载出边）
        loaded_edge_ids = set()
        for node in nodes:
            edges = graph_store.load_edges_from(node.id)
            for edge in edges:
                if edge.id not in loaded_edge_ids:
                    manager._edges.append(edge)
                    loaded_edge_ids.add(edge.id)

        # 恢复 current_node_id 和 root_id（从节点数据中推断）
        # root = parent_id 为 None 的节点
        roots = [n for n in nodes if n.parent_id is None]
        if roots:
            manager._root_id = roots[0].id
            manager._current_node_id = roots[0].id
        else:
            # 无根节点时，取第一个节点作为当前
            manager._current_node_id = nodes[0].id if nodes else None

        # 恢复热区（从当前节点重建）
        if manager._current_node_id:
            manager._maintain_hot_zone(manager._current_node_id)

        return manager

    # ── 生命周期 ───────────────────────────────────────────

    def clear(self) -> None:
        """清空所有话题。"""
        self._nodes.clear()
        self._edges.clear()
        self._current_node_id = None
        self._root_id = None
        self._entity_index.clear()
        self._hot_zone.clear()
