# -*- coding: utf-8 -*-
"""
core/agent/persistence/window_snapshot.py
─────────────────────────────────────────
Window snapshot persistence layer.

设计要点：
  - 保存 PCR 链当前状态（话题节点、历史、缓存、画像）
  - 支持 checkpoint 和 restore
  - 用于会话恢复和跨进程迁移
  - 轻量级：只存引用 ID 和可序列化数据，不存图节点本身（图节点由 GraphStore 管理）
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from core.agent.persistence.models import TurnRecord
from core.agent.pcr.datacontract import HistoryEntry


class WindowSnapshot:
    """
    窗口快照数据。
    记录某一时刻 PCR 链的状态。
    """

    def __init__(
        self,
        session_id: str,
        current_node_id: Optional[str] = None,
        history: Optional[List[HistoryEntry]] = None,
        entity_cache_entries: Optional[List[Dict[str, Any]]] = None,
        cognitive_profile: Optional[Dict[str, Any]] = None,
        adaptive_thresholds: Optional[Dict[str, float]] = None,
        window_metadata: Optional[Dict[str, Any]] = None,
        timestamp: float = 0.0,
    ):
        self.session_id = session_id
        self.current_node_id = current_node_id
        self.history = history or []
        self.entity_cache_entries = entity_cache_entries or []
        self.cognitive_profile = cognitive_profile or {}
        self.adaptive_thresholds = adaptive_thresholds or {}
        self.window_metadata = window_metadata or {}
        self.timestamp = timestamp if timestamp else time.time()

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典。"""
        return {
            "session_id": self.session_id,
            "current_node_id": self.current_node_id,
            "history": [h.to_dict() if hasattr(h, "to_dict") else dict(h) for h in self.history],
            "entity_cache_entries": self.entity_cache_entries,
            "cognitive_profile": self.cognitive_profile,
            "adaptive_thresholds": self.adaptive_thresholds,
            "window_metadata": self.window_metadata,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WindowSnapshot":
        """从字典恢复。"""
        history_raw = d.get("history", [])
        history = []
        for h in history_raw:
            if isinstance(h, dict):
                history.append(HistoryEntry(
                    role=h.get("role", ""),
                    content=h.get("content", ""),
                    expectation=h.get("expectation", ""),
                    timestamp=h.get("timestamp", 0.0),
                    metadata=h.get("metadata", {}),
                ))

        return cls(
            session_id=d.get("session_id", ""),
            current_node_id=d.get("current_node_id"),
            history=history,
            entity_cache_entries=d.get("entity_cache_entries", []),
            cognitive_profile=d.get("cognitive_profile", {}),
            adaptive_thresholds=d.get("adaptive_thresholds", {}),
            window_metadata=d.get("window_metadata", {}),
            timestamp=d.get("timestamp", 0.0),
        )

    def __repr__(self) -> str:
        return (
            f"WindowSnapshot({self.session_id[:8]}..., node={self.current_node_id}, "
            f"history={len(self.history)}, ts={self.timestamp:.0f})"
        )


class WindowSnapshotStore:
    """
    窗口快照持久化存储。
    支持 checkpoint（保存快照）和 restore（恢复最近快照）。
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
                CREATE TABLE IF NOT EXISTS window_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    data JSON NOT NULL,
                    timestamp REAL,
                    UNIQUE(session_id)
                );

                CREATE TABLE IF NOT EXISTS window_snapshots_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    data JSON NOT NULL,
                    timestamp REAL
                );

                CREATE INDEX IF NOT EXISTS idx_ws_session
                    ON window_snapshots(session_id);
                CREATE INDEX IF NOT EXISTS idx_ws_timestamp
                    ON window_snapshots(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_ws_history_session
                    ON window_snapshots_history(session_id);
                """
            )
            self._conn.commit()
            self._initialized = True

    # ── Checkpoint / Restore ───────────────────────────────────────────

    def checkpoint(self, snapshot: WindowSnapshot) -> bool:
        """保存或更新快照（UPSERT）。"""
        self._ensure_tables()
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO window_snapshots (session_id, data, timestamp)
                    VALUES (?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        data = excluded.data,
                        timestamp = excluded.timestamp
                    """,
                    (
                        snapshot.session_id,
                        json.dumps(snapshot.to_dict(), ensure_ascii=False, default=str),
                        snapshot.timestamp,
                    ),
                )
                self._conn.commit()
                return True
            except sqlite3.Error as e:
                self._conn.rollback()
                print(f"[WindowSnapshotStore] checkpoint failed: {e}")
                return False

    def restore(self, session_id: str) -> Optional[WindowSnapshot]:
        """恢复最近快照。"""
        self._ensure_tables()
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM window_snapshots WHERE session_id = ?",
                (session_id,),
            ).fetchone()

        if row is None:
            return None

        try:
            data = json.loads(row["data"])
            return WindowSnapshot.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[WindowSnapshotStore] restore decode failed: {e}")
            return None

    # ── 历史版本（可选）──────────────────────────────────────────

    def checkpoint_with_history(
        self, snapshot: WindowSnapshot, keep_versions: int = 3
    ) -> bool:
        """
        保存快照并保留历史版本（keep_versions 个）。
        使用单独的历史表。
        """
        self._ensure_tables()
        with self._lock:
            try:
                # 先保存到历史表
                self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS window_snapshots_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        data JSON NOT NULL,
                        timestamp REAL
                    )
                    """
                )
                self._conn.execute(
                    """
                    INSERT INTO window_snapshots_history (session_id, data, timestamp)
                    VALUES (?, ?, ?)
                    """,
                    (
                        snapshot.session_id,
                        json.dumps(snapshot.to_dict(), ensure_ascii=False, default=str),
                        snapshot.timestamp,
                    ),
                )

                # 清理旧版本
                self._conn.execute(
                    """
                    DELETE FROM window_snapshots_history
                    WHERE id NOT IN (
                        SELECT id FROM window_snapshots_history
                        WHERE session_id = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    )
                    """,
                    (snapshot.session_id, keep_versions),
                )

                # 再保存到当前快照
                self._conn.execute(
                    """
                    INSERT INTO window_snapshots (session_id, data, timestamp)
                    VALUES (?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        data = excluded.data,
                        timestamp = excluded.timestamp
                    """,
                    (
                        snapshot.session_id,
                        json.dumps(snapshot.to_dict(), ensure_ascii=False, default=str),
                        snapshot.timestamp,
                    ),
                )
                self._conn.commit()
                return True
            except sqlite3.Error as e:
                self._conn.rollback()
                print(f"[WindowSnapshotStore] checkpoint_with_history failed: {e}")
                return False

    def list_versions(self, session_id: str, limit: int = 10) -> List[float]:
        """列出某会话的历史版本时间戳。"""
        self._ensure_tables()
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT timestamp FROM window_snapshots_history
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

        return [r["timestamp"] for r in rows]

    # ── 清理 ───────────────────────────────────────────

    def delete(self, session_id: str) -> bool:
        """删除快照。"""
        self._ensure_tables()
        with self._lock:
            try:
                self._conn.execute(
                    "DELETE FROM window_snapshots WHERE session_id = ?",
                    (session_id,),
                )
                self._conn.execute(
                    "DELETE FROM window_snapshots_history WHERE session_id = ?",
                    (session_id,),
                )
                self._conn.commit()
                return True
            except sqlite3.Error as e:
                self._conn.rollback()
                print(f"[WindowSnapshotStore] delete failed: {e}")
                return False

    def cleanup_old(self, ttl_seconds: float, dry_run: bool = False) -> int:
        """清理过期快照。"""
        self._ensure_tables()
        cutoff = time.time() - ttl_seconds

        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM window_snapshots WHERE timestamp < ?",
                (cutoff,),
            ).fetchone()
            count = row["cnt"] if row else 0

            if not dry_run and count > 0:
                try:
                    self._conn.execute(
                        "DELETE FROM window_snapshots WHERE timestamp < ?",
                        (cutoff,),
                    )
                    self._conn.execute(
                        """
                        DELETE FROM window_snapshots_history
                        WHERE timestamp < ?
                        """,
                        (cutoff,),
                    )
                    self._conn.commit()
                except sqlite3.Error as e:
                    self._conn.rollback()
                    print(f"[WindowSnapshotStore] cleanup_old failed: {e}")
                    return 0

        return count

    # ── 统计 ───────────────────────────────────────────

    def count(self) -> int:
        """统计快照数。"""
        self._ensure_tables()
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM window_snapshots"
            ).fetchone()
            return row["cnt"] if row else 0
