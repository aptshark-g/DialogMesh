# -*- coding: utf-8 -*-
"""
core/agent/service/stores/base.py
──────────────────────────────────
会话存储抽象基类（v2.4 服务层新增）。

支持 SQLite（单机）、Redis（集群）、PostgreSQL（关系型）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from core.agent.service.models import Session, TurnRecord


class SessionStore(ABC):
    """会话存储抽象。"""

    @abstractmethod
    async def save_session(self, session: Session) -> bool:
        """保存完整会话。"""
        raise NotImplementedError

    @abstractmethod
    async def load_session(self, session_id: str) -> Optional[Session]:
        """加载会话。"""
        raise NotImplementedError

    @abstractmethod
    async def save_turn(self, session_id: str, turn: TurnRecord) -> bool:
        """保存单轮对话。"""
        raise NotImplementedError

    @abstractmethod
    async def get_history(
        self,
        session_id: str,
        limit: int = 50,
        before_sequence: Optional[int] = None,
    ) -> List[TurnRecord]:
        """获取历史记录。"""
        raise NotImplementedError

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """删除会话。"""
        raise NotImplementedError

    @abstractmethod
    async def list_active_sessions(
        self, tenant_id: str, limit: int = 100
    ) -> List[str]:
        """列出活跃会话 ID。"""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """存储健康检查。"""
        raise NotImplementedError
