# -*- coding: utf-8 -*-
"""
core/agent/persistence/entity_index.py
─────────────────────────────────────
Entity index persistence layer.

设计要点：
  - 将 Jieba 分词提取的实体持久化到 SQLite
  - 支持按实体搜索关联的节点/轮次/会话
  - 全局索引，跨会话
  - 与 EntityCache 互补：EntityCache 是热缓存（5轮），此索引是全局温索引
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


class EntityIndex:
    """
    实体倒排索引。
    存储 (entity_type, entity_value) -> [(session_id, node_id, turn_seq, timestamp)]
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
                CREATE TABLE IF NOT EXISTS entity_index (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_value TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    node_id TEXT,           -- 可选：关联的图节点
                    turn_seq INTEGER,       -- 可选：关联的轮次序号
                    context_snippet TEXT,   -- 出现上下文片段（前50字）
                    timestamp REAL,
                    UNIQUE(entity_type, entity_value, session_id, node_id, turn_seq)
                );

                CREATE INDEX IF NOT EXISTS idx_entity_type_value
                    ON entity_index(entity_type, entity_value);
                CREATE INDEX IF NOT EXISTS idx_entity_session
                    ON entity_index(session_id);
                CREATE INDEX IF NOT EXISTS idx_entity_timestamp
                    ON entity_index(timestamp DESC);
                """
            )
            self._conn.commit()
            self._initialized = True

    # ── 写入 ───────────────────────────────────────────

    def index_entity(
        self,
        entity_type: str,
        entity_value: str,
        session_id: str,
        node_id: Optional[str] = None,
        turn_seq: Optional[int] = None,
        context_snippet: str = "",
    ) -> bool:
        """索引单个实体出现。"""
        self._ensure_tables()
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO entity_index
                        (entity_type, entity_value, session_id, node_id, turn_seq, context_snippet, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entity_type,
                        entity_value,
                        session_id,
                        node_id,
                        turn_seq,
                        context_snippet[:100],
                        time.time(),
                    ),
                )
                self._conn.commit()
                return True
            except sqlite3.Error as e:
                self._conn.rollback()
                print(f"[EntityIndex] index_entity failed: {e}")
                return False

    def index_entities_batch(
        self,
        session_id: str,
        entities: List[Dict[str, Any]],
        node_id: Optional[str] = None,
        turn_seq: Optional[int] = None,
    ) -> bool:
        """批量索引实体列表。"""
        self._ensure_tables()
        with self._lock:
            try:
                self._conn.execute("BEGIN")
                for ent in entities:
                    self._conn.execute(
                        """
                        INSERT OR IGNORE INTO entity_index
                            (entity_type, entity_value, session_id, node_id, turn_seq, context_snippet, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            ent.get("type", "unknown"),
                            str(ent.get("value", "")),
                            session_id,
                            node_id,
                            turn_seq,
                            str(ent.get("context", ""))[:100],
                            time.time(),
                        ),
                    )
                self._conn.commit()
                return True
            except sqlite3.Error as e:
                self._conn.rollback()
                print(f"[EntityIndex] index_entities_batch failed: {e}")
                return False

    # ── 查询 ───────────────────────────────────────────

    def search_by_value(
        self, entity_value: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """按实体值搜索（精确匹配）。"""
        self._ensure_tables()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT entity_type, session_id, node_id, turn_seq, context_snippet, timestamp
                FROM entity_index
                WHERE entity_value = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (entity_value, limit),
            ).fetchall()

        return [
            {
                "entity_type": r["entity_type"],
                "entity_value": entity_value,
                "session_id": r["session_id"],
                "node_id": r["node_id"],
                "turn_seq": r["turn_seq"],
                "context_snippet": r["context_snippet"],
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]

    def search_by_type(
        self, entity_type: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """按实体类型搜索。"""
        self._ensure_tables()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT entity_value, session_id, node_id, turn_seq, context_snippet, timestamp
                FROM entity_index
                WHERE entity_type = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (entity_type, limit),
            ).fetchall()

        return [
            {
                "entity_type": entity_type,
                "entity_value": r["entity_value"],
                "session_id": r["session_id"],
                "node_id": r["node_id"],
                "turn_seq": r["turn_seq"],
                "context_snippet": r["context_snippet"],
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]

    def search_by_session(
        self, session_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取某会话的所有索引实体。"""
        self._ensure_tables()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT entity_type, entity_value, node_id, turn_seq, context_snippet, timestamp
                FROM entity_index
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

        return [
            {
                "entity_type": r["entity_type"],
                "entity_value": r["entity_value"],
                "session_id": session_id,
                "node_id": r["node_id"],
                "turn_seq": r["turn_seq"],
                "context_snippet": r["context_snippet"],
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]

    def find_sessions_by_entity(
        self, entity_type: str, entity_value: str
    ) -> List[str]:
        """查找包含某实体的所有会话 ID（去重）。"""
        self._ensure_tables()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT DISTINCT session_id FROM entity_index
                WHERE entity_type = ? AND entity_value = ?
                ORDER BY timestamp DESC
                """,
                (entity_type, entity_value),
            ).fetchall()

        return [r["session_id"] for r in rows]

    def get_top_entities(
        self, session_id: Optional[str] = None, limit: int = 20
    ) -> List[Tuple[str, str, int]]:
        """
        获取高频实体。
        :return: [(entity_type, entity_value, count), ...]
        """
        self._ensure_tables()
        if session_id:
            rows = self._conn.execute(
                """
                SELECT entity_type, entity_value, COUNT(*) as cnt
                FROM entity_index
                WHERE session_id = ?
                GROUP BY entity_type, entity_value
                ORDER BY cnt DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT entity_type, entity_value, COUNT(*) as cnt
                FROM entity_index
                GROUP BY entity_type, entity_value
                ORDER BY cnt DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [(r["entity_type"], r["entity_value"], r["cnt"]) for r in rows]

    # ── 维护 ───────────────────────────────────────────

    def delete_by_session(self, session_id: str) -> bool:
        """删除某会话的所有索引。"""
        self._ensure_tables()
        with self._lock:
            try:
                self._conn.execute(
                    "DELETE FROM entity_index WHERE session_id = ?",
                    (session_id,),
                )
                self._conn.commit()
                return True
            except sqlite3.Error as e:
                self._conn.rollback()
                print(f"[EntityIndex] delete_by_session failed: {e}")
                return False

    def cleanup_old(self, ttl_seconds: float, dry_run: bool = False) -> int:
        """清理过期索引。"""
        self._ensure_tables()
        cutoff = time.time() - ttl_seconds

        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM entity_index WHERE timestamp < ?",
                (cutoff,),
            ).fetchone()
            count = row["cnt"] if row else 0

            if not dry_run and count > 0:
                try:
                    self._conn.execute(
                        "DELETE FROM entity_index WHERE timestamp < ?",
                        (cutoff,),
                    )
                    self._conn.commit()
                except sqlite3.Error as e:
                    self._conn.rollback()
                    print(f"[EntityIndex] cleanup_old failed: {e}")
                    return 0

        return count

    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计。"""
        self._ensure_tables()
        with self._lock:
            total_row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM entity_index"
            ).fetchone()
            type_row = self._conn.execute(
                "SELECT COUNT(DISTINCT entity_type) as cnt FROM entity_index"
            ).fetchone()
            value_row = self._conn.execute(
                "SELECT COUNT(DISTINCT entity_value) as cnt FROM entity_index"
            ).fetchone()
            session_row = self._conn.execute(
                "SELECT COUNT(DISTINCT session_id) as cnt FROM entity_index"
            ).fetchone()

        return {
            "total_entries": total_row["cnt"] if total_row else 0,
            "distinct_types": type_row["cnt"] if type_row else 0,
            "distinct_values": value_row["cnt"] if value_row else 0,
            "distinct_sessions": session_row["cnt"] if session_row else 0,
        }
