# -*- coding: utf-8 -*-
"""
service/__init__.py (B4-1-P2 精简版)
────────────────────────────────────
服务层"整层"已归档（agent_service/orchestrator/api → un_use/），
本包保留为**协议资产 + 组件资产**，供前端契约与既有测试消费：
  - service/protocol/   : Clarification UI / TaskGraph / FSM / WS 事件契约
  - service/models.py   : 服务层数据契约（Session/TurnRecord/...）
  - service/async_session_manager.py + service/stores/ : 会话组件

生产入口的缓冲能力由 core/agent/api/service_middleware.py（v6_app 薄中间件层）
承接；本包不再提供完整服务层，仅保留资产。
"""

from __future__ import annotations

from service.models import (
    AdaptiveThresholds,
    CognitiveProfile,
    Session,
    SessionSummary,
    TurnRecord,
    UserProfile,
)
from service.stores.base import SessionStore
from service.async_session_manager import AsyncSessionManager
from service import protocol

__all__ = [
    "AdaptiveThresholds",
    "AsyncSessionManager",
    "CognitiveProfile",
    "Session",
    "SessionStore",
    "SessionSummary",
    "TurnRecord",
    "UserProfile",
    "protocol",
]
