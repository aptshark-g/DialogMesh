# -*- coding: utf-8 -*-
from __future__ import annotations
import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class DistributedLock(ABC):
    @abstractmethod
    async def acquire(self, key: str, ttl_ms: int = 5000) -> bool:
        ...
    @abstractmethod
    async def release(self, key: str) -> None:
        ...
    @abstractmethod
    async def is_locked(self, key: str) -> bool:
        ...

class ThreadingLockAdapter(DistributedLock):
    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._owners: Dict[str, str] = {}

    async def acquire(self, key: str, ttl_ms: int = 5000) -> bool:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        try:
            await asyncio.wait_for(self._locks[key].acquire(), timeout=ttl_ms / 1000.0)
            self._owners[key] = str(id(asyncio.current_task()))
            return True
        except asyncio.TimeoutError:
            return False

    async def release(self, key: str) -> None:
        lock = self._locks.get(key)
        if lock and lock.locked():
            lock.release()
            self._owners.pop(key, None)

    async def is_locked(self, key: str) -> bool:
        lock = self._locks.get(key)
        return lock is not None and lock.locked()

    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for key in list(self._locks.keys()):
            await self.release(key)

class RedisLockAdapter(DistributedLock):
    def __init__(self, redis_client: Any = None, prefix: str = "lock:"):
        self._client = redis_client
        self._prefix = prefix
        self._local_fallback = ThreadingLockAdapter()
        self._has_redis = redis_client is not None

    async def acquire(self, key: str, ttl_ms: int = 5000) -> bool:
        if self._has_redis:
            try:
                import aioredis
                return await self._client.set(self._prefix + key, "1", expire=ttl_ms // 1000, exist=aioredis.SET_IF_NOT_EXIST)
            except Exception:
                self._has_redis = False
        return await self._local_fallback.acquire(key, ttl_ms)

    async def release(self, key: str) -> None:
        if self._has_redis:
            try:
                await self._client.delete(self._prefix + key)
                return
            except Exception:
                pass
        await self._local_fallback.release(key)

    async def is_locked(self, key: str) -> bool:
        if self._has_redis:
            try:
                return await self._client.exists(self._prefix + key)
            except Exception:
                pass
        return await self._local_fallback.is_locked(key)

__all__ = ["DistributedLock", "ThreadingLockAdapter", "RedisLockAdapter"]
