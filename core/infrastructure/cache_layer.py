# core/infrastructure/cache_layer.py
"""ResponseCache — LLM 响应与语义搜索缓存层。

设计原则：
- 双级缓存：内存 L1（lru_cache，快速）+ SQLite L2（持久化，重启不丢）
- TTL 过期：默认 1 小时，避免缓存污染
- 缓存 key：基于 prompt 内容 hash（SHA-256）
- 选择性缓存：简单任务缓存，复杂任务不缓存（如 code_generation）

使用方式：
    from core.infrastructure.cache_layer import get_response_cache

    cache = get_response_cache()
    
    # 检查缓存
    key = cache.make_key(prompt, system_prompt, task_type)
    cached = cache.get(key)
    if cached:
        return cached
    
    # 调用 LLM 后存入缓存
    result = invoke_llm(...)
    cache.set(key, result, ttl=3600)
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 不缓存的任务类型（每次结果应不同）
NO_CACHE_TASKS = {"code_generation", "creative_writing", "debug"}

DEFAULT_TTL = 3600  # 1 小时


class _CacheLayerSingleton:
    _instance: Optional["ResponseCache"] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, ttl: int = DEFAULT_TTL) -> "ResponseCache":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = ResponseCache(ttl=ttl)
        return cls._instance


class ResponseCache:
    """响应缓存：内存 L1 + SQLite L2。"""

    def __init__(self, ttl: int = DEFAULT_TTL):
        self.ttl = ttl
        self._memory: Dict[str, Dict[str, Any]] = {}  # key -> {"value": str, "expires": float}
        self._lock = threading.Lock()
        self._sqlite_store = None

    def _get_store(self):
        """延迟初始化 SQLiteStore。"""
        if self._sqlite_store is None:
            try:
                from core.infrastructure.sqlite_store import get_sqlite_store
                self._sqlite_store = get_sqlite_store()
            except Exception as e:
                logger.debug(f"SQLite store not available for cache: {e}")
        return self._sqlite_store

    @staticmethod
    def make_key(prompt: str, system_prompt: Optional[str] = None, task_type: str = "default", **kwargs) -> str:
        """生成缓存 key（SHA-256）。"""
        content = f"{task_type}:{system_prompt or ''}:{prompt}:{json.dumps(kwargs, sort_keys=True)}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]

    def should_cache(self, task_type: str) -> bool:
        """判断任务类型是否应该缓存。"""
        return task_type not in NO_CACHE_TASKS

    def get(self, key: str) -> Optional[str]:
        """获取缓存（先查内存，再查 SQLite）。"""
        now = time.time()

        # L1: 内存
        with self._lock:
            entry = self._memory.get(key)
            if entry and entry["expires"] > now:
                logger.debug(f"Cache L1 hit: {key[:8]}...")
                return entry["value"]
            if entry:
                del self._memory[key]  # 过期清理

        # L2: SQLite
        store = self._get_store()
        if store:
            try:
                # 使用自定义表（不在 SQLiteStore 的 schema 中，这里直接查询）
                row = store._execute(
                    "SELECT value, expires FROM response_cache WHERE key = ?",
                    (key,),
                ).fetchone()
                if row and row["expires"] > now:
                    # 回填内存
                    with self._lock:
                        self._memory[key] = {"value": row["value"], "expires": row["expires"]}
                    logger.debug(f"Cache L2 hit: {key[:8]}...")
                    return row["value"]
                if row:
                    # 过期，删除
                    store._execute("DELETE FROM response_cache WHERE key = ?", (key,))
                    store._commit()
            except Exception as e:
                logger.debug(f"Cache L2 read failed: {e}")

        return None

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """设置缓存（写入内存 + SQLite）。"""
        if value is None or len(value) < 3:
            return False

        expires = time.time() + (ttl or self.ttl)

        # L1: 内存
        with self._lock:
            self._memory[key] = {"value": value, "expires": expires}

        # L2: SQLite
        store = self._get_store()
        if store:
            try:
                # 确保表存在
                store._execute(
                    """CREATE TABLE IF NOT EXISTS response_cache (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        expires REAL NOT NULL,
                        created_at REAL NOT NULL
                    )"""
                )
                store._execute(
                    """INSERT INTO response_cache (key, value, expires, created_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(key) DO UPDATE SET
                       value=excluded.value, expires=excluded.expires, created_at=excluded.created_at""",
                    (key, value, expires, time.time()),
                )
                store._commit()
                return True
            except Exception as e:
                logger.debug(f"Cache L2 write failed: {e}")

        return True

    def clear(self):
        """清空内存缓存。"""
        with self._lock:
            self._memory.clear()
        store = self._get_store()
        if store:
            try:
                store._execute("DELETE FROM response_cache")
                store._commit()
            except Exception as e:
                logger.debug(f"Cache clear failed: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计。"""
        now = time.time()
        with self._lock:
            total = len(self._memory)
            valid = sum(1 for e in self._memory.values() if e["expires"] > now)
        return {
            "memory_entries": total,
            "memory_valid": valid,
            "ttl_seconds": self.ttl,
        }


def get_response_cache(ttl: int = DEFAULT_TTL) -> ResponseCache:
    """获取全局响应缓存。"""
    return _CacheLayerSingleton.get_instance(ttl)
