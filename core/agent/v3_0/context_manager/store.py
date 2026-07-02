# -*- coding: utf-8 -*-
"""
core/agent/v3_0/context_manager/store.py
────────────────────────────────────────
DialogMesh Agent v3.0 — 上下文存储抽象与实现

用途：
- 定义上下文存储的抽象接口（ContextStore），便于接入 SQLite、Redis、文件系统等。
- 提供内存版（InMemoryContextStore）与 SQLite 版（SQLiteContextStore）实现。
- 所有操作支持异步，避免阻塞服务层事件循环。

版本: 3.0.0
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from core.agent.v3_0.context_manager.models import ContextSnapshot

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 抽象基类
# ═══════════════════════════════════════════════════════════════════════════

class ContextStore(ABC):
    """上下文存储抽象基类 — 定义会话快照的读写接口。

    实现者应保证：
    - ``save`` 与 ``load`` 的幂等性（同一 session_id 覆盖写入）。
    - 异步接口不阻塞事件循环。
    """

    @abstractmethod
    async def save(self, snapshot: ContextSnapshot) -> None:
        """保存会话快照（覆盖写入）。"""
        raise NotImplementedError

    @abstractmethod
    async def load(self, session_id: str) -> Optional[ContextSnapshot]:
        """加载会话快照。"""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """删除会话快照。"""
        raise NotImplementedError

    @abstractmethod
    async def list_sessions(self) -> List[str]:
        """列出所有已存储的 session_id。"""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """关闭存储连接，释放资源。"""
        raise NotImplementedError


# ═══════════════════════════════════════════════════════════════════════════
# 内存存储实现
# ═══════════════════════════════════════════════════════════════════════════

class InMemoryContextStore(ContextStore):
    """内存上下文存储 — 适用于单进程、开发测试或短期缓存场景。

    数据仅保存在进程内存中，进程退出即丢失。
    """

    def __init__(self) -> None:
        self._data: Dict[str, ContextSnapshot] = {}
        self._lock = asyncio.Lock()

    async def save(self, snapshot: ContextSnapshot) -> None:
        """异步保存快照到内存字典。"""
        try:
            await asyncio.sleep(0)
            async with self._lock:
                self._data[snapshot.session_id] = snapshot
                logger.debug("InMemory save: session=%s", snapshot.session_id)
        except Exception as exc:
            logger.error(f"InMemoryContextStore save failed: {exc}")
            raise

    async def load(self, session_id: str) -> Optional[ContextSnapshot]:
        """异步加载快照。"""
        try:
            await asyncio.sleep(0)
            async with self._lock:
                return self._data.get(session_id)
        except Exception as exc:
            logger.error(f"InMemoryContextStore load failed: {exc}")
            raise

    async def delete(self, session_id: str) -> bool:
        """异步删除快照。"""
        try:
            await asyncio.sleep(0)
            async with self._lock:
                existed = session_id in self._data
                self._data.pop(session_id, None)
                return existed
        except Exception as exc:
            logger.error(f"InMemoryContextStore delete failed: {exc}")
            raise

    async def list_sessions(self) -> List[str]:
        """异步列出所有 session_id。"""
        try:
            await asyncio.sleep(0)
            async with self._lock:
                return list(self._data.keys())
        except Exception as exc:
            logger.error(f"InMemoryContextStore list_sessions failed: {exc}")
            raise

    async def close(self) -> None:
        """清空内存数据。"""
        try:
            async with self._lock:
                self._data.clear()
                logger.info("InMemoryContextStore closed and cleared")
        except Exception as exc:
            logger.error(f"InMemoryContextStore close failed: {exc}")
            raise


# ═══════════════════════════════════════════════════════════════════════════
# SQLite 持久化实现
# ═══════════════════════════════════════════════════════════════════════════

class SQLiteContextStore(ContextStore):
    """SQLite 上下文存储 — 单文件持久化，适合单机部署。

    特性：
    - 自动建表（session_id 唯一索引）。
    - 使用标准库 sqlite3，无需额外依赖。
    - 写操作加 asyncio.Lock 防止并发写冲突。
    """

    def __init__(self, db_path: Union[str, Path]) -> None:
        import sqlite3
        self._sqlite3 = sqlite3
        self.db_path = Path(db_path)
        self._lock = asyncio.Lock()
        self._connection: Optional[Any] = None
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库连接与表结构。"""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = self._sqlite3.connect(
                str(self.db_path), check_same_thread=False
            )
            self._connection.execute("PRAGMA journal_mode=WAL;")
            self._create_tables()
            logger.info("SQLiteContextStore initialized: %s", self.db_path)
        except Exception as exc:
            logger.error(f"SQLiteContextStore init failed: {exc}")
            raise

    def _create_tables(self) -> None:
        """创建会话快照表。"""
        if self._connection is None:
            return
        try:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS context_snapshots (
                    session_id TEXT PRIMARY KEY,
                    snapshot_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_updated_at ON context_snapshots(updated_at)"
            )
            self._connection.commit()
        except Exception as exc:
            logger.error(f"SQLiteContextStore _create_tables failed: {exc}")
            raise

    async def save(self, snapshot: ContextSnapshot) -> None:
        """异步保存快照到 SQLite。"""
        try:
            await asyncio.sleep(0)
            json_str = snapshot.model_dump_json()
            now = time.time()
            async with self._lock:
                if self._connection is None:
                    raise RuntimeError("SQLite connection is closed")
                self._connection.execute(
                    """
                    INSERT INTO context_snapshots (session_id, snapshot_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        snapshot_json = excluded.snapshot_json,
                        updated_at = excluded.updated_at
                    """,
                    (snapshot.session_id, json_str, snapshot.created_at, now),
                )
                self._connection.commit()
                logger.debug("SQLite save: session=%s", snapshot.session_id)
        except Exception as exc:
            logger.error(f"SQLiteContextStore save failed: {exc}")
            raise

    async def load(self, session_id: str) -> Optional[ContextSnapshot]:
        """异步从 SQLite 加载快照。"""
        try:
            await asyncio.sleep(0)
            async with self._lock:
                if self._connection is None:
                    raise RuntimeError("SQLite connection is closed")
                cursor = self._connection.execute(
                    "SELECT snapshot_json FROM context_snapshots WHERE session_id = ?",
                    (session_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return ContextSnapshot.model_validate_json(row[0])
        except Exception as exc:
            logger.error(f"SQLiteContextStore load failed: {exc}")
            raise

    async def delete(self, session_id: str) -> bool:
        """异步删除快照。"""
        try:
            await asyncio.sleep(0)
            async with self._lock:
                if self._connection is None:
                    raise RuntimeError("SQLite connection is closed")
                cursor = self._connection.execute(
                    "DELETE FROM context_snapshots WHERE session_id = ?",
                    (session_id,),
                )
                self._connection.commit()
                return cursor.rowcount > 0
        except Exception as exc:
            logger.error(f"SQLiteContextStore delete failed: {exc}")
            raise

    async def list_sessions(self) -> List[str]:
        """异步列出所有 session_id。"""
        try:
            await asyncio.sleep(0)
            async with self._lock:
                if self._connection is None:
                    raise RuntimeError("SQLite connection is closed")
                cursor = self._connection.execute(
                    "SELECT session_id FROM context_snapshots ORDER BY updated_at DESC"
                )
                return [row[0] for row in cursor.fetchall()]
        except Exception as exc:
            logger.error(f"SQLiteContextStore list_sessions failed: {exc}")
            raise

    async def close(self) -> None:
        """异步关闭数据库连接。"""
        try:
            async with self._lock:
                if self._connection:
                    self._connection.close()
                    self._connection = None
                    logger.info("SQLiteContextStore closed: %s", self.db_path)
        except Exception as exc:
            logger.error(f"SQLiteContextStore close failed: {exc}")
            raise


# ═══════════════════════════════════════════════════════════════════════════
# 跨轮次实体缓存（EntityCache）
# ═══════════════════════════════════════════════════════════════════════════

class EntityCache:
    """跨轮次实体缓存 — 供后续轮次参照消解使用。

    设计文档 §3.3.7 要求：上下文合并器在完成继承后，将当前轮次的高置信度实体
    写入跨轮实体缓存，供下一轮 Pre-Stage 3.5 参照消解使用。

    写入策略：
    - 筛选条件：confidence >= 0.8 的实体（排除 inherited 标记的实体）
    - 键：按 session_id 索引
    - 值：Entity 对象列表（保留原始置信度、类型、值）
    - 淘汰策略：超过 max_rounds（默认 5）时移除最旧的轮次
    - 话题切换检测：如检测到话题切换短语，主动清空缓存

    版本: 3.0.0
    """

    def __init__(
        self,
        max_rounds: int = 5,
        max_entities_per_round: int = 20,
    ) -> None:
        self._data: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = asyncio.Lock()
        self.max_rounds = max(max_rounds, 1)
        self.max_entities_per_round = max(max_entities_per_round, 1)

    # ── 写入 ─────────────────────────────────────────────────

    async def add(
        self,
        session_id: str,
        entities: List[Any],
    ) -> None:
        """异步将高置信度实体写入缓存。

        Args:
            session_id: 会话 ID。
            entities: 实体列表（通常来自 Intent_v3.entities）。
        """
        try:
            await asyncio.sleep(0)
            high_conf = [
                {
                    "type": getattr(e, "type", None),
                    "type_value": getattr(getattr(e, "type", None), "value", None),
                    "value": getattr(e, "value", None),
                    "confidence": getattr(e, "confidence", 0.0),
                    "raw_text": getattr(e, "raw_text", ""),
                    "metadata": dict(getattr(e, "metadata", {})),
                    "timestamp": time.time(),
                }
                for e in entities
                if getattr(e, "confidence", 0.0) >= 0.8
                and not getattr(e, "metadata", {}).get("inherited")
            ]
            if not high_conf:
                return

            async with self._lock:
                if session_id not in self._data:
                    self._data[session_id] = []
                self._data[session_id].extend(high_conf)
                # 按数量截断（简化实现：每轮最多保留 max_entities_per_round * max_rounds 个）
                max_cached = self.max_entities_per_round * self.max_rounds
                if len(self._data[session_id]) > max_cached:
                    self._data[session_id] = self._data[session_id][-max_cached:]
                logger.debug(
                    "EntityCache add: session=%s added=%d total=%d",
                    session_id, len(high_conf), len(self._data[session_id]),
                )
        except Exception as exc:
            logger.error(f"EntityCache add failed: {exc}")
            raise

    # ── 读取 ─────────────────────────────────────────────────

    async def get(self, session_id: str) -> List[Dict[str, Any]]:
        """异步获取指定会话的缓存实体列表（按置信度降序）。"""
        try:
            await asyncio.sleep(0)
            async with self._lock:
                items = list(self._data.get(session_id, []))
            items.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)
            return items
        except Exception as exc:
            logger.error(f"EntityCache get failed: {exc}")
            raise

    async def search_by_type(
        self,
        session_id: str,
        entity_type: str,
    ) -> List[Dict[str, Any]]:
        """异步按实体类型搜索缓存。

        Args:
            session_id: 会话 ID。
            entity_type: 实体类型字符串（如 "memory_address"）。

        Returns:
            匹配的实体列表，按置信度降序排列。
        """
        try:
            await asyncio.sleep(0)
            all_items = await self.get(session_id)
            return [
                item for item in all_items
                if item.get("type_value") == entity_type or item.get("type") == entity_type
            ]
        except Exception as exc:
            logger.error(f"EntityCache search_by_type failed: {exc}")
            raise

    async def search_last(self, session_id: str) -> Optional[Dict[str, Any]]:
        """异步获取最近写入的高置信度实体（按时间）。"""
        try:
            await asyncio.sleep(0)
            async with self._lock:
                items = self._data.get(session_id, [])
                if not items:
                    return None
                return max(items, key=lambda x: x.get("timestamp", 0.0))
        except Exception as exc:
            logger.error(f"EntityCache search_last failed: {exc}")
            raise

    # ── 淘汰与清理 ───────────────────────────────────────────

    async def clear(self, session_id: str) -> None:
        """异步清空指定会话的缓存（话题切换时调用）。"""
        try:
            await asyncio.sleep(0)
            async with self._lock:
                self._data.pop(session_id, None)
            logger.debug("EntityCache cleared: session=%s", session_id)
        except Exception as exc:
            logger.error(f"EntityCache clear failed: {exc}")
            raise

    async def prune(self, session_id: str) -> None:
        """异步手动淘汰：只保留最近 N 轮的实体。

        默认淘汰策略在 add 时已按数量截断，此方法用于强制整理。
        """
        try:
            await asyncio.sleep(0)
            async with self._lock:
                items = self._data.get(session_id, [])
                max_cached = self.max_entities_per_round * self.max_rounds
                if len(items) > max_cached:
                    self._data[session_id] = items[-max_cached:]
        except Exception as exc:
            logger.error(f"EntityCache prune failed: {exc}")
            raise

    async def clear_all(self) -> None:
        """异步清空所有会话缓存。"""
        try:
            async with self._lock:
                self._data.clear()
            logger.info("EntityCache cleared all sessions")
        except Exception as exc:
            logger.error(f"EntityCache clear_all failed: {exc}")
            raise
