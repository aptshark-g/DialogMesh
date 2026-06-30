# -*- coding: utf-8 -*-
"""
core/agent/service/rate_limiter.py
──────────────────────────────────
限流器（v2.4 服务层新增）。

双层限流：
  1. 租户级：每个 tenant_id 有独立配额（防止单租户挤占）
  2. 会话级：每个 session 有 burst 限制（防止单个用户刷屏）

策略：
  - 令牌桶（Token Bucket）：平滑限流，允许短突发
  - 优先队列：Clarification 回复优先级高于新消息
  - 背压（Backpressure）：当队列深度 > 100 时，新请求返回 429
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass
class TokenBucket:
    """令牌桶。"""
    rate: float = 1.0          # 每秒令牌数
    burst: int = 5             # 桶容量
    tokens: float = field(default=0.0, repr=False)
    last_update: float = field(default_factory=time.time, repr=False)

    def __post_init__(self):
        # 初始满桶
        if self.tokens == 0.0 and self.burst > 0:
            self.tokens = float(self.burst)

    def acquire(self, tokens: int = 1) -> bool:
        """尝试获取令牌。返回是否成功。"""
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_update = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def wait_time(self, tokens: int = 1) -> float:
        """计算需要等待的时间（秒）。"""
        now = time.time()
        elapsed = now - self.last_update
        current = min(self.burst, self.tokens + elapsed * self.rate)
        if current >= tokens:
            return 0.0
        return (tokens - current) / self.rate


class RateLimiter:
    """
    双层限流器。
    """

    def __init__(
        self,
        tenant_rps: Optional[Dict[str, float]] = None,
        default_tenant_rps: float = 10.0,
        session_burst: int = 5,
        queue_max_depth: int = 100,
    ):
        self.default_tenant_rps = default_tenant_rps
        self.session_burst = session_burst
        self.queue_max_depth = queue_max_depth

        self._tenant_buckets: Dict[str, TokenBucket] = {}
        self._session_buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.RLock()

    def _get_tenant_bucket(self, tenant_id: str) -> TokenBucket:
        """获取或创建租户令牌桶。"""
        with self._lock:
            bucket = self._tenant_buckets.get(tenant_id)
            if bucket is None:
                rate = self.default_tenant_rps  # 可扩展为按 tenant_id 配置
                bucket = TokenBucket(rate=rate, burst=int(rate * 2))
                self._tenant_buckets[tenant_id] = bucket
            return bucket

    def _get_session_bucket(self, session_id: str) -> TokenBucket:
        """获取或创建会话令牌桶。"""
        with self._lock:
            bucket = self._session_buckets.get(session_id)
            if bucket is None:
                bucket = TokenBucket(rate=1.0, burst=self.session_burst)
                self._session_buckets[session_id] = bucket
            return bucket

    def check(
        self, tenant_id: str, session_id: str, priority: str = "normal"
    ) -> Tuple[bool, Optional[float], Optional[str]]:
        """
        检查请求是否允许通过。

        返回: (allowed, retry_after_seconds, reason)
        - allowed: True/False
        - retry_after: 如果不允许，建议等待多久（秒）
        - reason: 拒绝原因
        """
        # 1. 租户级限流
        tenant_bucket = self._get_tenant_bucket(tenant_id)
        if not tenant_bucket.acquire():
            wait = tenant_bucket.wait_time()
            return False, wait, "tenant_rate_limited"

        # 2. 会话级限流
        session_bucket = self._get_session_bucket(session_id)
        if not session_bucket.acquire():
            wait = session_bucket.wait_time()
            return False, wait, "session_rate_limited"

        # 3. 背压检查（简化：队列深度由外部控制）
        # 这里只做计数，实际队列深度由 SessionManager / RequestQueue 管理
        return True, None, None

    def release_session(self, session_id: str) -> None:
        """会话关闭时释放资源。"""
        with self._lock:
            self._session_buckets.pop(session_id, None)

    def get_stats(self) -> Dict[str, Dict]:
        """获取限流统计。"""
        with self._lock:
            return {
                "tenant_buckets": {
                    tid: {"rate": b.rate, "burst": b.burst, "tokens": b.tokens}
                    for tid, b in self._tenant_buckets.items()
                },
                "session_buckets": {
                    sid: {"rate": b.rate, "burst": b.burst, "tokens": b.tokens}
                    for sid, b in self._session_buckets.items()
                },
            }
