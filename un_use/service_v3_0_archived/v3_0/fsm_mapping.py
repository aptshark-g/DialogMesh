# -*- coding: utf-8 -*-
from __future__ import annotations
import time
from typing import Any, Dict, List, Optional, Tuple

_CLARIFICATION_STATES = {
    "START": "idle",
    "PARSING": "processing",
    "ACTIONABLE": "ready",
    "CLARIFYING": "needs_clarification",
    "RE_PARSING": "processing",
    "EXPIRED": "timed_out",
    "CLOSED": "completed",
}

_CLARIFICATION_REVERSE = {v: k for k, v in _CLARIFICATION_STATES.items()}

_ORCHESTRATOR_STATES = {
    "pcr_analysis": "analyzing",
    "intent_parsing": "analyzing",
    "planning": "planning",
    "execution": "executing",
    "answer_generation": "generating",
    "meta_cognitive": "validating",
    "reflective": "reviewing",
    "completed": "completed",
    "failed": "failed",
}

class StateTransitionLog:
    def __init__(self):
        self._entries: List[Dict[str, Any]] = []
    def record(self, internal: str, external: str, metadata: Optional[Dict] = None):
        self._entries.append({"timestamp": time.time(), "internal": internal, "external": external, "metadata": metadata or {}})
    def get_history(self) -> List[Dict[str, Any]]:
        return list(self._entries)
    def clear(self) -> None:
        self._entries.clear()

StateTransitionLogStore: Dict[str, StateTransitionLog] = {}

def to_external(internal_state: str, domain: str = "clarification") -> str:
    if domain == "clarification":
        return _CLARIFICATION_STATES.get(internal_state, "unknown")
    return _ORCHESTRATOR_STATES.get(internal_state, "unknown")

def from_external(external_state: str, domain: str = "clarification") -> Optional[str]:
    if domain == "clarification":
        return _CLARIFICATION_REVERSE.get(external_state)
    rev = {v: k for k, v in _ORCHESTRATOR_STATES.items()}
    return rev.get(external_state)

def record_transition(session_id: str, internal: str, domain: str = "clarification") -> None:
    if session_id not in StateTransitionLogStore:
        StateTransitionLogStore[session_id] = StateTransitionLog()
    external = to_external(internal, domain)
    StateTransitionLogStore[session_id].record(internal, external)

def get_transition_history(session_id: str) -> List[Dict[str, Any]]:
    log = StateTransitionLogStore.get(session_id)
    return log.get_history() if log else []

def clear_transition_history(session_id: str) -> None:
    StateTransitionLogStore.pop(session_id, None)

__all__ = ["to_external", "from_external", "record_transition", "get_transition_history", "clear_transition_history", "StateTransitionLog"]
