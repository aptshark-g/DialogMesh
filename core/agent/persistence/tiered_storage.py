# -*- coding: utf-8 -*-
"""
core/agent/persistence/tiered_storage.py
────────────────────────────────────────
Hot / Warm / Cold tiered storage strategy.

设计要点：
  - Hot: 内存缓存（SessionManager 已有的 OrderedDict）
  - Warm: SQLite 本地持久化（SQLiteSessionStore + GraphStore + EntityIndex）
  - Cold: 归档文件（压缩 JSONL，超过 TTL 的会话/图/实体）
  - 自动迁移：Hot -> Warm（缓存淘汰）、Warm -> Cold（TTL 过期）
  - 回热：Cold -> Warm（按需加载）
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.agent.persistence.base import SessionStore
from core.agent.persistence.models import Session, TurnRecord
from core.agent.persistence.sqlite_store import SQLiteSessionStore
from core.agent.persistence.graph_store import GraphStore
from core.agent.persistence.entity_index import EntityIndex
from core.agent.topic_tree.models import TopicNode, TopicEdge


class TierLevel:
    """存储层级枚举。"""
    HOT = "hot"      # 内存
    WARM = "warm"    # SQLite 本地
    COLD = "cold"    # 归档文件


@dataclass
class TierPolicy:
    """分层策略配置。"""
    hot_ttl_seconds: float = 3600            # 1 小时未访问则从 hot 淘汰到 warm
    warm_ttl_seconds: float = 7 * 24 * 3600  # 7 天未访问则从 warm 归档到 cold
    cold_retention_days: int = 90            # 归档保留 90 天
    cold_compression: bool = True            # 是否 gzip 压缩
    max_hot_sessions: int = 100
    max_warm_db_size_mb: int = 500           # warm 层最大 500MB


class TieredStorageManager:
    """
    分层存储管理器。
    协调 Hot / Warm / Cold 三层存储的自动迁移。
    """

    def __init__(
        self,
        warm_store: SQLiteSessionStore,
        cold_dir: str = "~/.memorygraph/archive",
        policy: Optional[TierPolicy] = None,
    ):
        self._warm = warm_store
        self._cold_dir = Path(cold_dir).expanduser()
        self._cold_dir.mkdir(parents=True, exist_ok=True)
        self._policy = policy or TierPolicy()

        # 连接 graph_store 和 entity_index（复用 warm 的连接）
        self._graph = GraphStore(warm_store._conn, warm_store._lock)
        self._entity_index = EntityIndex(warm_store._conn, warm_store._lock)

        self._lock = threading.Lock()
        self._hot_sessions: Dict[str, Tuple[Session, float]] = {}  # sid -> (session, last_access)

    # ── Hot 层管理 ───────────────────────────────────────────

    def get_hot(self, session_id: str) -> Optional[Session]:
        """从 Hot 层获取会话（更新访问时间）。"""
        with self._lock:
            if session_id in self._hot_sessions:
                session, _ = self._hot_sessions[session_id]
                self._hot_sessions[session_id] = (session, time.time())
                return session
        return None

    def put_hot(self, session: Session) -> None:
        """放入 Hot 层。"""
        with self._lock:
            self._hot_sessions[session.session_id] = (session, time.time())
            self._evict_hot_if_needed()

    def _evict_hot_if_needed(self) -> None:
        """如果 Hot 层超过上限，淘汰最久未访问的会话到 Warm。"""
        while len(self._hot_sessions) > self._policy.max_hot_sessions:
            oldest_sid = min(
                self._hot_sessions, key=lambda k: self._hot_sessions[k][1]
            )
            session, _ = self._hot_sessions.pop(oldest_sid)
            # 保存到 warm
            self._warm.save_session(session)
            # 保存历史
            for turn in session.history:
                self._warm.save_turn(session.session_id, turn)

    def evict_hot_to_warm(self, session_id: str) -> bool:
        """手动将某会话从 Hot 驱逐到 Warm。"""
        with self._lock:
            if session_id not in self._hot_sessions:
                return False
            session, _ = self._hot_sessions.pop(session_id)

        self._warm.save_session(session)
        for turn in session.history:
            self._warm.save_turn(session.session_id, turn)
        return True

    # ── Warm -> Cold 归档 ───────────────────────────────────────────

    def archive_warm_to_cold(self, dry_run: bool = False) -> Tuple[int, int]:
        """
        将 Warm 层过期会话归档到 Cold 层。
        :return: (archived_sessions, archived_turns)
        """
        cutoff = time.time() - self._policy.warm_ttl_seconds

        # 找出过期会话
        conn = self._warm._ensure_connection()
        with self._warm._lock:
            rows = conn.execute(
                """
                SELECT session_id, data FROM sessions
                WHERE updated_at < ?
                """,
                (cutoff,),
            ).fetchall()

        archived_sessions = 0
        archived_turns = 0

        for row in rows:
            sid = row["session_id"]
            try:
                session_data = json.loads(row["data"])
            except json.JSONDecodeError:
                continue

            # 加载完整会话（含历史、图、实体）
            full_record = self._load_full_session_record(sid)
            if full_record is None:
                continue

            if not dry_run:
                # 写入归档
                self._write_cold_archive(sid, full_record)
                # 从 warm 删除
                self._warm.delete_session(sid)
                self._graph.delete_session_nodes(sid)
                self._entity_index.delete_by_session(sid)

            archived_sessions += 1
            archived_turns += full_record.get("turn_count", 0)

        return archived_sessions, archived_turns

    def _load_full_session_record(self, session_id: str) -> Optional[Dict[str, Any]]:
        """加载会话的完整记录（会话 + 历史 + 图 + 实体）。"""
        session = self._warm.load_session(session_id)
        if session is None:
            return None

        turns = self._warm.load_turns(session_id, limit=10000)
        nodes = self._graph.load_nodes_by_session(session_id, limit=10000)
        # 边加载较复杂，这里简化：只存节点（边可重建）
        entities = self._entity_index.search_by_session(session_id, limit=10000)

        return {
            "session": session.to_persistent_dict(),
            "turns": [t.to_dict() for t in turns],
            "nodes": [n.to_dict() for n in nodes],
            "entities": entities,
            "turn_count": len(turns),
            "archived_at": time.time(),
        }

    def _write_cold_archive(self, session_id: str, record: Dict[str, Any]) -> None:
        """写入冷归档文件。"""
        date_str = time.strftime("%Y-%m-%d")
        filename = f"{session_id}_{date_str}.jsonl"
        filepath = self._cold_dir / filename

        if self._policy.cold_compression:
            filepath = filepath.with_suffix(filepath.suffix + ".gz")
            with gzip.open(filepath, "wt", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        else:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    # ── Cold -> Warm 回热 ───────────────────────────────────────────

    def rehydrate_cold_to_warm(self, session_id: str) -> Optional[Session]:
        """
        从 Cold 层回热会话到 Warm 层。
        扫描 cold_dir 查找匹配 session_id 的文件。
        """
        # 查找归档文件
        pattern = f"{session_id}_*.jsonl*"
        files = list(self._cold_dir.glob(pattern))
        if not files:
            return None

        # 取最新文件
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        latest = files[0]

        try:
            if latest.suffix == ".gz":
                with gzip.open(latest, "rt", encoding="utf-8") as f:
                    lines = f.readlines()
            else:
                with open(latest, "r", encoding="utf-8") as f:
                    lines = f.readlines()
        except Exception as e:
            print(f"[TieredStorage] rehydrate read failed: {e}")
            return None

        # 找到匹配的 session 记录
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if record.get("session", {}).get("session_id") == session_id:
                    return self._restore_record_to_warm(record)
            except json.JSONDecodeError:
                continue

        return None

    def _restore_record_to_warm(self, record: Dict[str, Any]) -> Optional[Session]:
        """将归档记录恢复到 Warm 层。"""
        session_data = record.get("session")
        if session_data is None:
            return None

        session = Session.from_persistent_dict(session_data)
        # 恢复历史
        for turn_data in record.get("turns", []):
            turn = TurnRecord.from_dict(turn_data)
            session.history.append(turn)
        session.turn_count = len(session.history)

        # 保存到 warm
        self._warm.save_session(session)
        for turn in session.history:
            self._warm.save_turn(session.session_id, turn)

        # 恢复图节点
        for node_data in record.get("nodes", []):
            node = TopicNode.from_dict(node_data)
            self._graph.save_node(session.session_id, node)

        # 恢复实体索引
        for ent_data in record.get("entities", []):
            self._entity_index.index_entity(
                entity_type=ent_data.get("entity_type", "unknown"),
                entity_value=ent_data.get("entity_value", ""),
                session_id=session.session_id,
                node_id=ent_data.get("node_id"),
                turn_seq=ent_data.get("turn_seq"),
                context_snippet=ent_data.get("context_snippet", ""),
            )

        return session

    # ── 维护 ───────────────────────────────────────────

    def cleanup_cold(self, dry_run: bool = False) -> int:
        """清理超过保留期的冷归档。"""
        cutoff = time.time() - self._policy.cold_retention_days * 24 * 3600
        count = 0

        for filepath in self._cold_dir.glob("*.jsonl*"):
            try:
                mtime = filepath.stat().st_mtime
                if mtime < cutoff:
                    if not dry_run:
                        filepath.unlink()
                    count += 1
            except Exception:
                continue

        return count

    def get_storage_stats(self) -> Dict[str, Any]:
        """获取三层存储统计。"""
        hot_count = len(self._hot_sessions)

        # Warm 统计
        conn = self._warm._ensure_connection()
        with self._warm._lock:
            warm_session_row = conn.execute(
                "SELECT COUNT(*) as cnt FROM sessions"
            ).fetchone()
            warm_turn_row = conn.execute(
                "SELECT COUNT(*) as cnt FROM turns"
            ).fetchone()

        warm_count = warm_session_row["cnt"] if warm_session_row else 0
        warm_turns = warm_turn_row["cnt"] if warm_turn_row else 0

        # Cold 统计
        cold_files = list(self._cold_dir.glob("*.jsonl*"))
        cold_size = sum(f.stat().st_size for f in cold_files)

        return {
            "hot": {"sessions": hot_count, "max": self._policy.max_hot_sessions},
            "warm": {
                "sessions": warm_count,
                "turns": warm_turns,
                "db_path": str(self._warm._db_path),
            },
            "cold": {
                "files": len(cold_files),
                "size_bytes": cold_size,
                "size_mb": round(cold_size / (1024 * 1024), 2),
                "dir": str(self._cold_dir),
            },
        }

    def shutdown(self) -> None:
        """优雅关闭：flush hot 到 warm。"""
        with self._lock:
            hot_sessions = dict(self._hot_sessions)
            self._hot_sessions.clear()

        for sid, (session, _) in hot_sessions.items():
            self._warm.save_session(session)
            for turn in session.history:
                self._warm.save_turn(sid, turn)
