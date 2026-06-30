# -*- coding: utf-8 -*-
"""
core/agent/service — 服务层（Layer 2）
"""

from __future__ import annotations

from core.agent.service.models import (
    Session, TurnRecord, SessionSummary,
    IntentResult, ClarificationPayload,
    ParseProgressEvent, ErrorPayload,
)
from core.agent.service.session_manager import SessionManager
from core.agent.service.rate_limiter import RateLimiter
from core.agent.service.agent_service import AgentService
from core.agent.service.distributed_lock import (
    DistributedLock,
    ThreadingLockAdapter,
    RedisLockAdapter,
    AsyncRedisLockAdapter,
)
from core.agent.service.stores.base import SessionStore

try:
    from core.agent.service.stores.sqlite import SQLiteSessionStore
except ImportError:
    SQLiteSessionStore = None

try:
    from core.agent.service.api import create_app, HAS_FASTAPI
except ImportError:
    HAS_FASTAPI = False
    create_app = None

__all__ = [
    "Session", "TurnRecord", "SessionSummary",
    "IntentResult", "ClarificationPayload",
    "ParseProgressEvent", "ErrorPayload",
    "SessionManager", "RateLimiter", "AgentService",
    "DistributedLock", "ThreadingLockAdapter",
    "RedisLockAdapter", "AsyncRedisLockAdapter",
    "SessionStore", "SQLiteSessionStore",
    "create_app", "HAS_FASTAPI",
]
