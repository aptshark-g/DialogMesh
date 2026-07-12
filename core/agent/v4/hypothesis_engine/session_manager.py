"""SessionManager: ReasonSession lifecycle (open/close/archive)."""
from __future__ import annotations
import time
import uuid
from typing import Dict, List, Optional

from .models import ReasonSession, VoteRecord


class SessionManager:

    def __init__(self):
        self._sessions: Dict[str, ReasonSession] = {}

    def open(self, triggering_event: str, domain: str = "") -> ReasonSession:
        sid = f"rs_{uuid.uuid4().hex[:8]}"
        session = ReasonSession(
            session_id=sid,
            triggering_event=triggering_event,
            domain=domain,
        )
        self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> Optional[ReasonSession]:
        return self._sessions.get(session_id)

    def close(self, session_id: str, winner: str = None, knowledge_ref: str = None) -> bool:
        s = self._sessions.get(session_id)
        if s is None or s.status != "open":
            return False
        s.winner = winner
        s.knowledge_ref = knowledge_ref
        s.closed_at = time.time()
        s.status = "closed"
        return True

    def archive(self, session_id: str) -> bool:
        s = self._sessions.get(session_id)
        if s is None or s.status != "closed":
            return False
        s.status = "archived"
        return True

    def list_open(self) -> List[ReasonSession]:
        return [s for s in self._sessions.values() if s.status == "open"]

    def list_closed(self) -> List[ReasonSession]:
        return [s for s in self._sessions.values() if s.status == "closed"]

    def stats(self) -> dict:
        return {
            "total": len(self._sessions),
            "open": sum(1 for s in self._sessions.values() if s.status == "open"),
            "closed": sum(1 for s in self._sessions.values() if s.status == "closed"),
            "archived": sum(1 for s in self._sessions.values() if s.status == "archived"),
        }
