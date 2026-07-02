# -*- coding: utf-8 -*-
"""
service/stores/base.py
──────────────────────
Session storage abstract base class.

Defines the contract that all persistence backends must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from service.models import Session, TurnRecord, UserProfile


class SessionStore(ABC):
    """Abstract base class for session persistence backends."""

    @abstractmethod
    async def save_session(self, session: Session) -> bool:
        """Persist a session. Returns True on success."""
        raise NotImplementedError

    @abstractmethod
    async def load_session(self, session_id: str) -> Optional[Session]:
        """Load a session by ID. Returns None if not found."""
        raise NotImplementedError

    @abstractmethod
    async def save_turn(self, session_id: str, turn: TurnRecord) -> bool:
        """Persist a single turn. Returns True on success."""
        raise NotImplementedError

    @abstractmethod
    async def get_history(
        self,
        session_id: str,
        limit: int = 50,
        before_sequence: Optional[int] = None,
    ) -> List[TurnRecord]:
        """Retrieve turn history for a session."""
        raise NotImplementedError

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its turns. Returns True on success."""
        raise NotImplementedError

    @abstractmethod
    async def list_active_sessions(self, tenant_id: str, limit: int = 100) -> List[str]:
        """List active session IDs for a tenant, ordered by most recent update."""
        raise NotImplementedError

    @abstractmethod
    async def save_user_profile(self, user_id: str, tenant_id: str, profile: UserProfile) -> bool:
        """Persist a user profile. Returns True on success."""
        raise NotImplementedError

    @abstractmethod
    async def load_user_profile(self, user_id: str, tenant_id: str) -> Optional[UserProfile]:
        """Load a user profile. Returns None if not found."""
        raise NotImplementedError
