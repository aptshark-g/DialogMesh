# -*- coding: utf-8 -*-
"""
core/agent/service/stores/redis.py
──────────────────────────────────
Redis 会话存储实现（生产优化）。

适合集群部署，支持 TTL 自动过期。

依赖: pip install redis
"""

from __future__ import annotations

import json
import time
from typing import List, Optional

from core.agent.service.stores.base import SessionStore
from core.agent.service.models import Session, TurnRecord


class RedisSessionStore(SessionStore):
    """
    Redis 会话存储。

    Key 设计:
      session:{session_id} -> HASH (JSON 序列化)
      session:{session_id}:history -> ZSET (score=sequence, member=JSON)
      tenant:{tenant_id}:sessions -> ZSET (score=last_activity, member=session_id)
      TTL: 3600s
    """

    def __init__(self, host: str = "localhost", port: int = 6379,
                 db: int = 0, password: Optional[str] = None,
                 ttl_seconds: int = 3600):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.ttl_seconds = ttl_seconds
        self._redis = None

    def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.Redis(
                    host=self.host, port=self.port, db=self.db,
                    password=self.password, decode_responses=True,
                )
            except ImportError:
                raise RuntimeError("redis library not installed. Install with: pip install redis")
        return self._redis

    async def save_session(self, session: Session) -> bool:
        try:
            r = self._get_redis()
            data = json.dumps(session.to_persistent_dict(), ensure_ascii=False)
            key = f"session:{session.session_id}"
            await r.hset(key, mapping={"data": data})
            await r.expire(key, self.ttl_seconds)

            # 更新租户索引
            tenant_key = f"tenant:{session.tenant_id}:sessions"
            await r.zadd(tenant_key, {session.session_id: session.last_activity_at})
            await r.expire(tenant_key, self.ttl_seconds)
            return True
        except Exception:
            return False

    async def load_session(self, session_id: str) -> Optional[Session]:
        try:
            r = self._get_redis()
            key = f"session:{session_id}"
            data = await r.hget(key, "data")
            if data is None:
                return None
            return Session.from_persistent_dict(json.loads(data))
        except Exception:
            return None

    async def save_turn(self, session_id: str, turn: TurnRecord) -> bool:
        try:
            r = self._get_redis()
            key = f"session:{session_id}:history"
            data = json.dumps(turn.to_dict(), ensure_ascii=False)
            await r.zadd(key, {data: turn.sequence})
            await r.expire(key, self.ttl_seconds)
            return True
        except Exception:
            return False

    async def get_history(
        self, session_id: str, limit: int = 50,
        before_sequence: Optional[int] = None,
    ) -> List[TurnRecord]:
        try:
            r = self._get_redis()
            key = f"session:{session_id}:history"
            if before_sequence is not None:
                # ZREVRANGEBYSCORE: score <= before_sequence-1
                max_score = before_sequence - 1 if before_sequence > 0 else -1
                raw = await r.zrevrangebyscore(key, max_score, 0, start=0, num=limit)
            else:
                raw = await r.zrevrange(key, 0, limit - 1)
            turns = []
            for item in raw:
                data = json.loads(item)
                turns.append(TurnRecord.from_dict(data))
            turns.reverse()
            return turns
        except Exception:
            return []

    async def delete_session(self, session_id: str) -> bool:
        try:
            r = self._get_redis()
            await r.delete(f"session:{session_id}")
            await r.delete(f"session:{session_id}:history")
            return True
        except Exception:
            return False

    async def list_active_sessions(self, tenant_id: str, limit: int = 100) -> List[str]:
        try:
            r = self._get_redis()
            tenant_key = f"tenant:{tenant_id}:sessions"
            raw = await r.zrevrange(tenant_key, 0, limit - 1)
            return list(raw)
        except Exception:
            return []

    async def health_check(self) -> bool:
        try:
            r = self._get_redis()
            await r.ping()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
