"""P0: Unified Event Log — single source of truth for all system events.

Merges:
  - NodeEditRecord (dialogue tree edits from chain 03)
  - CorrectionJournal (profile corrections from chain 08)
  - BehaviorPatterns (pattern discovery from chain 05)
  - ParameterChanges (parameter registry changes)
  - MetaDecisions (meta-cognition verdicts)

All events → ChainedEventLog (SHA256-chained, append-only).
State is derived by replaying events — not stored independently.
"""
from __future__ import annotations
import time, logging
from typing import Any, Dict, List, Optional

from core.agent.persistence.chained_event_log import ChainedEventLog, ChainedEvent

logger = logging.getLogger(__name__)


class UnifiedEventLog:
    """Single event stream — append from all subsystems.

    Usage:
      uel = UnifiedEventLog()
      uel.log_node_edit("n42", "changed text from A to B", author="user")
      uel.log_profile_correction("C", old=0.46, new=0.85)
      uel.log_pattern("write_code→add_test", confidence=0.85)
      uel.log_parameter("behavior.min_repeat_count", old="3", new="2")
      uel.log_meta_decision("rev_001", verdict="approved")
    """

    def __init__(self, path: str = "data/events/unified_log.jsonl"):
        self._log = ChainedEventLog(path)

    # ── Chain 03: Dialogue Tree Edits ──

    def log_node_edit(self, block_id: str, change: str, author: str = "user",
                      before: str = "", after: str = ""):
        return self._log.append("NodeEdited", {
            "block_id": block_id, "change": change, "author": author,
            "before": before[:200], "after": after[:200],
        })

    def log_node_create(self, block_id: str, parent_id: str = ""):
        return self._log.append("NodeCreated", {
            "block_id": block_id, "parent_id": parent_id,
        })

    def log_node_split(self, original_id: str, new_ids: List[str]):
        return self._log.append("NodeSplit", {
            "original_id": original_id, "new_ids": new_ids,
        })

    # ── Chain 08: Profile Corrections ──

    def log_profile_correction(self, dimension: str, old_value: float, 
                                new_value: float, reason: str = "user_edit"):
        return self._log.append("ProfileEdited", {
            "dimension": dimension, "old": old_value, "new": new_value,
            "reason": reason,
        })

    def log_profile_drift(self, dimension: str, drift: float):
        return self._log.append("ProfileDrifted", {
            "dimension": dimension, "drift": drift,
        })

    # ── Chain 05: Behavior Patterns ──

    def log_pattern(self, pattern_key: str, confidence: float, support: int = 0):
        return self._log.append("PatternDiscovered", {
            "pattern": pattern_key, "confidence": confidence, "support": support,
        })

    def log_pattern_feedback(self, pattern_key: str, accepted: bool):
        return self._log.append("PatternFeedback", {
            "pattern": pattern_key, "accepted": accepted,
        })

    # ── Parameters ──

    def log_parameter(self, param_key: str, old_value: str, new_value: str,
                      author: str = "engine"):
        return self._log.append("ParameterChanged", {
            "param": param_key, "old": old_value, "new": new_value,
            "author": author,
        })

    # ── Chain 09: Meta-Cognition ──

    def log_meta_decision(self, review_id: str, verdict: str, 
                          reason: str = ""):
        return self._log.append("MetaDecision", {
            "review_id": review_id, "verdict": verdict, "reason": reason[:200],
        })

    def log_meta_self_audit(self, accuracy: float, recommendation: str):
        return self._log.append("MetaSelfAudit", {
            "accuracy": accuracy, "recommendation": recommendation,
        })

    # ── Inertia ──

    def log_inertia_break(self, pattern_id: str, counter_count: int):
        return self._log.append("InertiaBroken", {
            "pattern": pattern_id, "counter_examples": counter_count,
        })

    # ── Engineering ──

    def log_constraint_added(self, module_name: str, constraint: str):
        return self._log.append("ConstraintAdded", {
            "module": module_name, "constraint": constraint,
        })

    # ── Queries ──

    def verify(self) -> Dict[str, Any]:
        return self._log.verify()

    def stats(self) -> Dict[str, Any]:
        return self._log.stats()

    def replay_all(self) -> List[ChainedEvent]:
        return self._log.replay()

    def recent_events(self, n: int = 20) -> List[ChainedEvent]:
        return self._log._events[-n:]

    def events_by_type(self, event_type: str, limit: int = 50) -> List[ChainedEvent]:
        return [e for e in self._log._events if e.event_type == event_type][-limit:]
