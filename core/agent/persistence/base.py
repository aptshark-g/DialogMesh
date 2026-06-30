# -*- coding: utf-8 -*-
"""
core/agent/persistence/base.py
────────────────────────────
SessionStore abstract base class.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

from core.agent.persistence.models import Session, TurnRecord


class SessionStore(ABC):
    """
    抽象基类：会话存储后端。
    所有实现必须支持异步操作（通过线程池或 asyncio 桥接）。
    """

    @abstractmethod
    def save_session(self, session: Session) -> bool:
        """保存或更新会话（不含 history）。"""
        ...

    @abstractmethod
    def load_session(self, session_id: str) -> Optional[Session]:
        """加载会话（不含 history，history 需单独加载）。"""
        ...

    @abstractmethod
    def save_turn(self, session_id: str, turn: TurnRecord) -> bool:
        """保存单轮对话记录。"""
        ...

    @abstractmethod
    def load_turns(self, session_id: str, limit: int = 50) -> List[TurnRecord]:
        """加载最近 N 轮对话记录。"""
        ...

    @abstractmethod
    def list_active_sessions(self, limit: int = 20, tenant_id: str = "default") -> List[str]:
        """列出最近活跃的会话 ID。"""
        ...

    @abstractmethod
    def delete_session(self, session_id: str) -> bool:
        """删除会话及其所有轮次。"""
        ...

    @abstractmethod
    def close(self) -> None:
        """关闭存储连接。"""
        ...
