# core/infrastructure/graph_store.py
"""GraphStore — NetworkX 图数据库封装（话题树 + 对话关系）。

设计原则：
- 零额外依赖：Python 内置 NetworkX 3.4.2
- 图模型：有向图（DiGraph），节点 = 话题/轮次，边 = 关系（continuation/switch/backtrack/sub-topic）
- 持久化：GraphML 序列化到 SQLite BLOB，或独立 .graphml 文件
- 查询：话题路径、最短路径、相似话题聚类

节点类型：
    topic — 话题节点（聚合多轮）
    turn  — 单轮节点（属于某个话题）
    entity — 实体节点（NER 提取，跨话题链接）

边类型：
    continuation — 话题延续（同一话题内轮次间）
    switch       — 话题切换（旧话题 → 新话题）
    backtrack    — 话题回溯（回到历史话题）
    sub-topic    — 子话题关系（父话题 → 子话题）
    causal       — 因果/条件关系（假设 → 结论）
    contains     — 话题包含轮次（topic → turn）
    relates_to   — 话题间语义关联（相似度高）

使用方式：
    from core.infrastructure.graph_store import get_graph_store

    g = get_graph_store(session_id="demo")
    g.add_topic(topic_id=0, name="Python", turns=[0,1], domains={"Python"})
    g.add_topic(topic_id=1, name="天气", turns=[2], domains={"赣州"})
    g.add_edge(0, 1, relation="switch", weight=0.3)
    
    # 查询
    path = g.get_topic_path(1)  # [0, 1] 从根到该话题的路径
    related = g.get_related_topics(0, min_weight=0.5)  # 语义关联话题
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

logger = logging.getLogger(__name__)

GRAPH_DIR = "data/graphs"


class _GraphStoreSingleton:
    """按 session_id 隔离的图存储。"""

    _instances: Dict[str, "GraphStore"] = {}
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, session_id: str) -> "GraphStore":
        if session_id not in cls._instances:
            with cls._lock:
                if session_id not in cls._instances:
                    cls._instances[session_id] = GraphStore(session_id)
        return cls._instances[session_id]


class GraphStore:
    """NetworkX 图数据库封装。"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.graph = nx.DiGraph()
        self._lock = threading.Lock()
        self._path = os.path.join(GRAPH_DIR, f"{session_id}.graphml")
        self._ensure_dir()
        self._load()

    def _ensure_dir(self):
        os.makedirs(GRAPH_DIR, exist_ok=True)

    def _load(self):
        """从 GraphML 文件加载。"""
        if os.path.exists(self._path):
            try:
                self.graph = nx.read_graphml(self._path)
                logger.info(f"Graph loaded: {self._path}, {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
            except Exception as e:
                logger.warning(f"Graph load failed: {e}, starting fresh")
                self.graph = nx.DiGraph()

    def save(self) -> bool:
        """保存到 GraphML 文件。"""
        try:
            nx.write_graphml(self.graph, self._path)
            return True
        except Exception as e:
            logger.warning(f"Graph save failed: {e}")
            return False

    # ── 节点操作 ─────────────────────────────────────────────────

    def add_topic(self, topic_id: int, name: str, turns: Optional[List[int]] = None,
                  domains: Optional[List[str]] = None, intent: Optional[str] = None,
                  start_idx: Optional[int] = None, end_idx: Optional[int] = None,
                  parent_topic: Optional[int] = None, semantic_summary: Optional[str] = None) -> bool:
        """添加/更新话题节点。"""
        node_id = f"topic_{topic_id}"
        with self._lock:
            self.graph.add_node(
                node_id,
                type="topic",
                topic_id=topic_id,
                name=name,
                turns=json.dumps(turns or []),
                domains=json.dumps(list(domains or []), ensure_ascii=False),
                intent=intent or "unknown",
                start_idx=start_idx or 0,
                end_idx=end_idx or 0,
                semantic_summary=semantic_summary or "",
            )
            if parent_topic is not None:
                parent_id = f"topic_{parent_topic}"
                if parent_id in self.graph:
                    self.graph.add_edge(parent_id, node_id, relation="sub-topic", weight=1.0)
        return True

    def add_turn(self, turn_index: int, topic_id: int, raw_query: str,
                 intent: Optional[str] = None, router_mode: Optional[str] = None) -> bool:
        """添加轮次节点，并建立话题包含关系。"""
        node_id = f"turn_{turn_index}"
        topic_node_id = f"topic_{topic_id}"
        with self._lock:
            self.graph.add_node(
                node_id,
                type="turn",
                turn_index=turn_index,
                topic_id=topic_id,
                raw_query=raw_query,
                intent=intent or "unknown",
                router_mode=router_mode or "unknown",
            )
            if topic_node_id in self.graph:
                self.graph.add_edge(topic_node_id, node_id, relation="contains", weight=1.0)
        return True

    def add_entity(self, entity_id: str, name: str, entity_type: str,
                   mentions: Optional[List[int]] = None) -> bool:
        """添加实体节点（跨话题链接）。"""
        with self._lock:
            self.graph.add_node(
                entity_id,
                type="entity",
                name=name,
                entity_type=entity_type,
                mentions=json.dumps(mentions or []),
            )
        return True

    def link_entity_to_topic(self, entity_id: str, topic_id: int, weight: float = 1.0) -> bool:
        """实体 → 话题关联。"""
        topic_node_id = f"topic_{topic_id}"
        with self._lock:
            if topic_node_id in self.graph and entity_id in self.graph:
                self.graph.add_edge(entity_id, topic_node_id, relation="mentioned_in", weight=weight)
        return True

    # ── 边操作 ─────────────────────────────────────────────────

    def add_edge(self, source_topic_id: int, target_topic_id: int,
                 relation: str = "switch", weight: float = 0.5,
                 metadata: Optional[Dict[str, Any]] = None) -> bool:
        """添加话题间关系边。"""
        source_id = f"topic_{source_topic_id}"
        target_id = f"topic_{target_topic_id}"
        with self._lock:
            if source_id in self.graph and target_id in self.graph:
                data = {"relation": relation, "weight": weight}
                if metadata:
                    data.update({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in metadata.items()})
                self.graph.add_edge(source_id, target_id, **data)
                return True
        return False

    def add_turn_relation(self, turn_a: int, turn_b: int, relation: str = "continuation") -> bool:
        """轮次间关系（同一话题内）。"""
        a_id = f"turn_{turn_a}"
        b_id = f"turn_{turn_b}"
        with self._lock:
            if a_id in self.graph and b_id in self.graph:
                self.graph.add_edge(a_id, b_id, relation=relation, weight=1.0)
                return True
        return False

    # ── 查询 ───────────────────────────────────────────────────

    def get_topic(self, topic_id: int) -> Optional[Dict[str, Any]]:
        """获取话题节点数据。"""
        node_id = f"topic_{topic_id}"
        if node_id not in self.graph:
            return None
        data = dict(self.graph.nodes[node_id])
        # 解析 JSON 字段
        for field in ["turns", "domains"]:
            if field in data and isinstance(data[field], str):
                try:
                    data[field] = json.loads(data[field])
                except Exception:
                    data[field] = []
        return data

    def get_topic_path(self, topic_id: int) -> List[int]:
        """从根话题到目标话题的路径（通过 sub-topic 边）。"""
        node_id = f"topic_{topic_id}"
        if node_id not in self.graph:
            return []

        # 找所有 root 节点（无 sub-topic 入边的话题）
        roots = [n for n in self.graph.nodes()
                 if self.graph.nodes[n].get("type") == "topic"
                 and not any(self.graph.edges[e].get("relation") == "sub-topic"
                            for e in self.graph.in_edges(n))]

        if not roots:
            return [topic_id]

        # 从第一个 root 到目标的最短路径
        root_id = roots[0]
        try:
            path = nx.shortest_path(self.graph, source=root_id, target=node_id)
            return [int(self.graph.nodes[n]["topic_id"]) for n in path
                    if self.graph.nodes[n].get("type") == "topic"]
        except nx.NetworkXNoPath:
            return [topic_id]

    def get_related_topics(self, topic_id: int, min_weight: float = 0.5,
                          relation_filter: Optional[List[str]] = None) -> List[Tuple[int, float, str]]:
        """获取语义关联话题（通过 relates_to 或 continuation 边）。"""
        node_id = f"topic_{topic_id}"
        if node_id not in self.graph:
            return []

        results = []
        for neighbor in self.graph.neighbors(node_id):
            edge_data = self.graph.edges[node_id, neighbor]
            rel = edge_data.get("relation", "unknown")
            weight = edge_data.get("weight", 0.0)
            if weight >= min_weight and (relation_filter is None or rel in relation_filter):
                tid = self.graph.nodes[neighbor].get("topic_id")
                if tid is not None:
                    results.append((int(tid), weight, rel))

        # 也查反向边
        for neighbor in self.graph.predecessors(node_id):
            edge_data = self.graph.edges[neighbor, node_id]
            rel = edge_data.get("relation", "unknown")
            weight = edge_data.get("weight", 0.0)
            if weight >= min_weight and (relation_filter is None or rel in relation_filter):
                tid = self.graph.nodes[neighbor].get("topic_id")
                if tid is not None:
                    results.append((int(tid), weight, rel))

        # 去重按 weight 降序
        seen = set()
        unique = []
        for tid, weight, rel in sorted(results, key=lambda x: x[1], reverse=True):
            if tid not in seen:
                seen.add(tid)
                unique.append((tid, weight, rel))
        return unique

    def get_topic_turns(self, topic_id: int) -> List[Dict[str, Any]]:
        """获取话题下的所有轮次。"""
        topic_node_id = f"topic_{topic_id}"
        if topic_node_id not in self.graph:
            return []

        turns = []
        for neighbor in self.graph.neighbors(topic_node_id):
            if self.graph.nodes[neighbor].get("type") == "turn":
                data = dict(self.graph.nodes[neighbor])
                turns.append(data)
        turns.sort(key=lambda x: x.get("turn_index", 0))
        return turns

    def get_all_topics(self) -> List[Dict[str, Any]]:
        """获取所有话题。"""
        topics = []
        for node_id, data in self.graph.nodes(data=True):
            if data.get("type") == "topic":
                d = dict(data)
                for field in ["turns", "domains"]:
                    if field in d and isinstance(d[field], str):
                        try:
                            d[field] = json.loads(d[field])
                        except Exception:
                            d[field] = []
                topics.append(d)
        topics.sort(key=lambda x: x.get("topic_id", 0))
        return topics

    def get_stats(self) -> Dict[str, Any]:
        """图统计。"""
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "topics": sum(1 for _, d in self.graph.nodes(data=True) if d.get("type") == "topic"),
            "turns": sum(1 for _, d in self.graph.nodes(data=True) if d.get("type") == "turn"),
            "entities": sum(1 for _, d in self.graph.nodes(data=True) if d.get("type") == "entity"),
            "is_connected": nx.is_weakly_connected(self.graph) if self.graph.number_of_nodes() > 0 else False,
            "diameter": nx.diameter(self.graph.to_undirected()) if self.graph.number_of_nodes() > 0 and nx.is_connected(self.graph.to_undirected()) else None,
        }

    def clear(self):
        """清空图。"""
        with self._lock:
            self.graph.clear()
        if os.path.exists(self._path):
            os.remove(self._path)


def get_graph_store(session_id: str) -> GraphStore:
    """获取指定会话的图存储。"""
    return _GraphStoreSingleton.get_instance(session_id)
