# -*- coding: utf-8 -*-
"""
core/agent/persistence/graph_store.py
───────────────────────────────────
Graph node / edge persistence layer.

设计要点：
  - 复用 topic_tree.models.TopicNode / TopicEdge
  - SQLite 存储：nodes 表 + edges 表 + node_edges 索引
  - 支持 BFS/DFS 遍历（出边查询）
  - 支持按实体搜索节点（JSON 字段 GIN 模拟）
  - 与 SessionStore 共用连接（通过传入 conn）
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from core.agent.topic_tree.models import TopicEdge, TopicEdgeType, TopicNode


class GraphStore:
    """
    图持久化存储。
    使用 SQLite 存储节点和边，支持话题树的持久化与图遍历。
    """

    def __init__(self, conn: sqlite3.Connection, lock: threading.Lock):
        self._conn = conn
        self._lock = lock
        self._initialized = False

    def _ensure_tables(self) -> None:
        """懒加载表创建。"""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS graph_nodes (
                    node_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    data JSON NOT NULL,
                    updated_at REAL
                );

                CREATE TABLE IF NOT EXISTS graph_edges (
                    edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    edge_type TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    data JSON,
                    created_at REAL,
                    UNIQUE(session_id, source_id, target_id, edge_type)
                );

                CREATE INDEX IF NOT EXISTS idx_gnodes_session
                    ON graph_nodes(session_id);
                CREATE INDEX IF NOT EXISTS idx_gedges_session
                    ON graph_edges(session_id);
                CREATE INDEX IF NOT EXISTS idx_gedges_source
                    ON graph_edges(source_id);
                CREATE INDEX IF NOT EXISTS idx_gedges_target
                    ON graph_edges(target_id);
                CREATE INDEX IF NOT EXISTS idx_gedges_type
                    ON graph_edges(edge_type);
                """
            )
            self._conn.commit()
            self._initialized = True

    # ── 节点操作 ───────────────────────────────────────────

    def save_node(self, session_id: str, node: TopicNode) -> bool:
        """保存或更新节点（UPSERT）。"""
        self._ensure_tables()
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO graph_nodes (node_id, session_id, data, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(node_id) DO UPDATE SET
                        session_id = excluded.session_id,
                        data = excluded.data,
                        updated_at = excluded.updated_at
                    """,
                    (
                        node.id,
                        session_id,
                        json.dumps(node.to_dict(), ensure_ascii=False, default=str),
                        time.time(),
                    ),
                )
                self._conn.commit()
                return True
            except sqlite3.Error as e:
                self._conn.rollback()
                print(f"[GraphStore] save_node failed: {e}")
                return False

    def load_node(self, node_id: str) -> Optional[TopicNode]:
        """加载单个节点。"""
        self._ensure_tables()
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM graph_nodes WHERE node_id = ?",
                (node_id,),
            ).fetchone()

        if row is None:
            return None

        try:
            data = json.loads(row["data"])
            return TopicNode.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[GraphStore] load_node decode failed: {e}")
            return None

    def load_nodes_by_session(
        self, session_id: str, limit: int = 1000
    ) -> List[TopicNode]:
        """加载某会话的所有节点。"""
        self._ensure_tables()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT data FROM graph_nodes
                WHERE session_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

        nodes = []
        for row in rows:
            try:
                data = json.loads(row["data"])
                nodes.append(TopicNode.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue
        return nodes

    def delete_node(self, node_id: str) -> bool:
        """删除节点及其关联边。"""
        self._ensure_tables()
        with self._lock:
            try:
                self._conn.execute(
                    "DELETE FROM graph_edges WHERE source_id = ? OR target_id = ?",
                    (node_id, node_id),
                )
                self._conn.execute(
                    "DELETE FROM graph_nodes WHERE node_id = ?",
                    (node_id,),
                )
                self._conn.commit()
                return True
            except sqlite3.Error as e:
                self._conn.rollback()
                print(f"[GraphStore] delete_node failed: {e}")
                return False

    def delete_session_nodes(self, session_id: str) -> bool:
        """删除某会话的所有节点和边。"""
        self._ensure_tables()
        with self._lock:
            try:
                self._conn.execute(
                    "DELETE FROM graph_edges WHERE session_id = ?",
                    (session_id,),
                )
                self._conn.execute(
                    "DELETE FROM graph_nodes WHERE session_id = ?",
                    (session_id,),
                )
                self._conn.commit()
                return True
            except sqlite3.Error as e:
                self._conn.rollback()
                print(f"[GraphStore] delete_session_nodes failed: {e}")
                return False

    # ── 边操作 ───────────────────────────────────────────

    def save_edge(self, session_id: str, edge: TopicEdge) -> bool:
        """保存或更新边。"""
        self._ensure_tables()
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO graph_edges
                        (session_id, source_id, target_id, edge_type, weight, data, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id, source_id, target_id, edge_type) DO UPDATE SET
                        weight = excluded.weight,
                        data = excluded.data
                    """,
                    (
                        session_id,
                        edge.source_id,
                        edge.target_id,
                        edge.edge_type.value,
                        edge.weight,
                        json.dumps(edge.to_dict(), ensure_ascii=False, default=str),
                        time.time(),
                    ),
                )
                self._conn.commit()
                return True
            except sqlite3.Error as e:
                self._conn.rollback()
                print(f"[GraphStore] save_edge failed: {e}")
                return False

    def load_edges_from(
        self, node_id: str, edge_type: Optional[TopicEdgeType] = None
    ) -> List[TopicEdge]:
        """加载某节点的所有出边。"""
        self._ensure_tables()
        if edge_type is not None:
            rows = self._conn.execute(
                """
                SELECT data FROM graph_edges
                WHERE source_id = ? AND edge_type = ?
                ORDER BY weight DESC
                """,
                (node_id, edge_type.value),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT data FROM graph_edges
                WHERE source_id = ?
                ORDER BY weight DESC
                """,
                (node_id,),
            ).fetchall()

        edges = []
        for row in rows:
            try:
                data = json.loads(row["data"])
                edges.append(TopicEdge.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue
        return edges

    def load_edges_to(
        self, node_id: str, edge_type: Optional[TopicEdgeType] = None
    ) -> List[TopicEdge]:
        """加载某节点的所有入边。"""
        self._ensure_tables()
        if edge_type is not None:
            rows = self._conn.execute(
                """
                SELECT data FROM graph_edges
                WHERE target_id = ? AND edge_type = ?
                ORDER BY weight DESC
                """,
                (node_id, edge_type.value),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT data FROM graph_edges
                WHERE target_id = ?
                ORDER BY weight DESC
                """,
                (node_id,),
            ).fetchall()

        edges = []
        for row in rows:
            try:
                data = json.loads(row["data"])
                edges.append(TopicEdge.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue
        return edges

    # ── 图遍历 ───────────────────────────────────────────

    def bfs_neighbors(
        self,
        start_node_id: str,
        max_depth: int = 3,
        min_weight: float = 0.0,
        edge_types: Optional[Set[TopicEdgeType]] = None,
    ) -> List[Tuple[str, int, float]]:
        """
        BFS 遍历邻居节点。
        :return: [(node_id, depth, accumulated_weight), ...]
        """
        self._ensure_tables()
        if edge_types is not None:
            type_filter = {e.value for e in edge_types}
        else:
            type_filter = None

        visited: Dict[str, Tuple[int, float]] = {start_node_id: (0, 1.0)}
        queue = [(start_node_id, 0, 1.0)]
        result = []

        while queue:
            current, depth, acc_weight = queue.pop(0)
            if depth > 0:
                result.append((current, depth, acc_weight))

            if depth >= max_depth:
                continue

            edges = self.load_edges_from(current)
            for edge in edges:
                if edge.weight < min_weight:
                    continue
                if type_filter is not None and edge.edge_type.value not in type_filter:
                    continue

                nid = edge.target_id
                new_weight = acc_weight * edge.weight
                if nid not in visited or new_weight > visited[nid][1]:
                    visited[nid] = (depth + 1, new_weight)
                    queue.append((nid, depth + 1, new_weight))

        return result

    def find_nodes_by_entity(
        self, session_id: str, entity_type: str, entity_value: str
    ) -> List[TopicNode]:
        """
        按实体搜索节点（JSON 子串匹配）。
        注意：非 GIN 索引，大数量时性能有限；适合 <10K 节点。
        """
        self._ensure_tables()
        # 构建子串搜索模式：{"type": "xxx", "value": "yyy"}
        # 由于 JSON 序列化顺序不确定，使用两个 LIKE 条件
        pattern_type = f'%"type": "{entity_type}"%'
        pattern_value = f'%"value": "{entity_value}"%'

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT data FROM graph_nodes
                WHERE session_id = ?
                  AND data LIKE ?
                  AND data LIKE ?
                """,
                (session_id, pattern_type, pattern_value),
            ).fetchall()

        nodes = []
        for row in rows:
            try:
                data = json.loads(row["data"])
                # 二次验证（避免 LIKE 误匹配）
                found = False
                for ent in data.get("entities", []):
                    if ent.get("type") == entity_type and ent.get("value") == entity_value:
                        found = True
                        break
                if found:
                    nodes.append(TopicNode.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue
        return nodes

    # ── 批量操作 ───────────────────────────────────────────

    def save_nodes_batch(self, session_id: str, nodes: List[TopicNode]) -> bool:
        """批量保存节点。"""
        self._ensure_tables()
        with self._lock:
            try:
                self._conn.execute("BEGIN")
                for node in nodes:
                    self._conn.execute(
                        """
                        INSERT INTO graph_nodes (node_id, session_id, data, updated_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(node_id) DO UPDATE SET
                            session_id = excluded.session_id,
                            data = excluded.data,
                            updated_at = excluded.updated_at
                        """,
                        (
                            node.id,
                            session_id,
                            json.dumps(node.to_dict(), ensure_ascii=False, default=str),
                            time.time(),
                        ),
                    )
                self._conn.commit()
                return True
            except sqlite3.Error as e:
                self._conn.rollback()
                print(f"[GraphStore] save_nodes_batch failed: {e}")
                return False

    def save_edges_batch(self, session_id: str, edges: List[TopicEdge]) -> bool:
        """批量保存边。"""
        self._ensure_tables()
        with self._lock:
            try:
                self._conn.execute("BEGIN")
                for edge in edges:
                    self._conn.execute(
                        """
                        INSERT INTO graph_edges
                            (session_id, source_id, target_id, edge_type, weight, data, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(session_id, source_id, target_id, edge_type) DO UPDATE SET
                            weight = excluded.weight,
                            data = excluded.data
                        """,
                        (
                            session_id,
                            edge.source_id,
                            edge.target_id,
                            edge.edge_type.value,
                            edge.weight,
                            json.dumps(edge.to_dict(), ensure_ascii=False, default=str),
                            time.time(),
                        ),
                    )
                self._conn.commit()
                return True
            except sqlite3.Error as e:
                self._conn.rollback()
                print(f"[GraphStore] save_edges_batch failed: {e}")
                return False

    # ── 统计 ───────────────────────────────────────────

    def count_nodes(self, session_id: Optional[str] = None) -> int:
        """统计节点数。"""
        self._ensure_tables()
        if session_id:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM graph_nodes WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM graph_nodes"
            ).fetchone()
        return row["cnt"] if row else 0

    def count_edges(self, session_id: Optional[str] = None) -> int:
        """统计边数。"""
        self._ensure_tables()
        if session_id:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM graph_edges WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM graph_edges"
            ).fetchone()
        return row["cnt"] if row else 0
