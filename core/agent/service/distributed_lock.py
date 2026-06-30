# -*- coding: utf-8 -*-
"""
分布式锁抽象接口（P2 修复）。

当前实现：ThreadingLockAdapter（单机 threading.RLock 包装）
未来实现：RedisLockAdapter（基于 Redis Redlock）

设计原则：
  - 接口兼容 threading.Lock（acquire/release/__enter__/__exit__）
  - 可无缝替换，无需修改 AgentService 代码
"""

from abc import ABC, abstractmethod
import threading
import asyncio

class DistributedLock(ABC):
    @abstractmethod
    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool: ...
    @abstractmethod
    def release(self) -> None: ...
    @abstractmethod
    def __enter__(self): ...
    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb): ...

class ThreadingLockAdapter(DistributedLock):
    """单机版：包装 threading.RLock。"""
    def __init__(self):
        self._lock = threading.RLock()
    def acquire(self, blocking=True, timeout=-1):
        return self._lock.acquire(blocking=blocking, timeout=timeout if timeout > 0 else -1)
    def release(self):
        self._lock.release()
    def __enter__(self):
        self._lock.__enter__()
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._lock.__exit__(exc_type, exc_val, exc_tb)

class RedisLockAdapter(DistributedLock):
    """Redis 分布式锁实现（基于 SET NX EX 的单实例 Redlock）。

    依赖: pip install redis
    """
    def __init__(self, redis_client, lock_key: str, ttl_seconds: int = 10, lock_value: str = None):
        self._redis = redis_client
        self._lock_key = lock_key
        self._ttl = ttl_seconds
        self._value = lock_value or str(id(self))
        self._owned = False

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        import time as _time
        end = _time.time() + timeout if timeout > 0 else float('inf')
        while True:
            ok = self._redis.set(self._lock_key, self._value, nx=True, ex=self._ttl)
            if ok:
                self._owned = True
                return True
            if not blocking:
                return False
            if _time.time() >= end:
                return False
            _time.sleep(0.05)

    def release(self) -> None:
        if not self._owned:
            return
        # 使用 Lua 脚本确保原子性检查-删除
        lua = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        self._redis.eval(lua, 1, self._lock_key, self._value)
        self._owned = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


class AsyncRedisLockAdapter(DistributedLock):
    """异步 Redis 分布式锁。"""
    def __init__(self, redis_client, lock_key: str, ttl_seconds: int = 10, lock_value: str = None):
        self._redis = redis_client
        self._lock_key = lock_key
        self._ttl = ttl_seconds
        self._value = lock_value or str(id(self))
        self._owned = False

    async def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        import asyncio, time as _time
        end = _time.time() + timeout if timeout > 0 else float('inf')
        while True:
            ok = await self._redis.set(self._lock_key, self._value, nx=True, ex=self._ttl)
            if ok:
                self._owned = True
                return True
            if not blocking:
                return False
            if _time.time() >= end:
                return False
            await asyncio.sleep(0.05)

    def release(self) -> None:
        raise RuntimeError("AsyncRedisLockAdapter is async-only; use 'async with'")

    def __enter__(self):
        raise RuntimeError("AsyncRedisLockAdapter is async-only; use 'async with' instead of 'with'")

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._owned:
            lua = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            await self._redis.eval(lua, 1, self._lock_key, self._value)
            self._owned = False
        return False
class AsyncLockAdapter(DistributedLock):
    """通用异步锁：包装 asyncio.Lock（单机版，用于 AsyncAgentService 默认）。"""
    def __init__(self):
        self._lock = asyncio.Lock()

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        raise RuntimeError("AsyncLockAdapter is async-only; use 'await acquire_async()' or 'async with'")

    def release(self) -> None:
        raise RuntimeError("AsyncLockAdapter is async-only; use 'async with' or 'await release_async()'")

    def __enter__(self):
        raise RuntimeError("AsyncLockAdapter is async-only; use 'async with' instead of 'with'")

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    async def acquire_async(self, blocking: bool = True, timeout: float = -1) -> bool:
        if not blocking:
            if self._lock.locked():
                return False
            await self._lock.acquire()
            return True
        if timeout > 0:
            try:
                await asyncio.wait_for(self._lock.acquire(), timeout=timeout)
                return True
            except asyncio.TimeoutError:
                return False
        await self._lock.acquire()
        return True

    async def release_async(self) -> None:
        self._lock.release()

    async def __aenter__(self):
        await self._lock.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._lock.release()
        return False
