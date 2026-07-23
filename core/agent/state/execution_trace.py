"""ExecutionTraceV3 — State → Transition → State sequence.

Replaces ExecutionTrace(v1) which only tracked PERCEIVE/REASON/REFLECT.
V3 records full state snapshots with their causal Transitions.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent.state.state_object import (
    StateObject, Transition, TransitionReason, Lifespan,
)


@dataclass
class ExecutionTraceV3:
    """A reasoning session recorded as State → Transition → State."""

    session_id: str = ""
    states: List[StateObject] = field(default_factory=list)
    transitions: List[Transition] = field(default_factory=list)

    # ── Summary ──
    final_answer: str = ""
    final_confidence: float = 0.0
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0

    def snapshot(self, state: StateObject):
        """Record a state snapshot."""
        snap = state.snapshot()
        self.states.append(snap)
        return snap

    def record_transition(
        self,
        reason: TransitionReason,
        from_state: StateObject,
        to_state: StateObject,
        evidence: List[str] = None,
        effects: List = None,
        confidence: float = 0.5,
    ) -> Transition:
        """Record a transition between states."""
        t = Transition(
            reason=reason,
            from_state_id=from_state.id,
            to_state_id=to_state.id,
            evidence=evidence or [],
            effects=effects or [],
            confidence=confidence,
        )
        self.transitions.append(t)
        return t

    def finish(self, answer: str = "", confidence: float = 0.0):
        self.final_answer = answer
        self.final_confidence = confidence
        self.finished_at = time.time()

    @property
    def reasoning_path(self) -> str:
        if not self.transitions:
            return "(empty trace)"
        return " → ".join(
            f"[{t.reason.value}]{t.evidence_summary[:40]}"
            for t in self.transitions
        )

    def why_did_state_change(self, index: int) -> Optional[Transition]:
        """Why did state at position `index` change?"""
        if index < len(self.transitions):
            return self.transitions[index]
        return None

    def transitions_of_type(self, reason: TransitionReason) -> List[Transition]:
        """Filter transitions by reason type."""
        return [t for t in self.transitions if t.reason == reason]

    def meta_analyze(self) -> Dict[str, Any]:
        """Analyze transition patterns for meta-cognition."""
        if not self.transitions:
            return {"empty": True}

        reason_counts = {}
        total_conf = 0.0
        for t in self.transitions:
            r = t.reason.value
            reason_counts[r] = reason_counts.get(r, 0) + 1
            total_conf += t.confidence

        dominant = max(reason_counts, key=reason_counts.get) if reason_counts else "none"

        # Detect patterns
        reasons = [t.reason for t in self.transitions]
        consecutive_rejects = 0
        max_rejects = 0
        for r in reasons:
            if r == TransitionReason.REJECT:
                consecutive_rejects += 1
                max_rejects = max(max_rejects, consecutive_rejects)
            else:
                consecutive_rejects = 0

        return {
            "total_transitions": len(self.transitions),
            "total_states": len(self.states),
            "reason_distribution": reason_counts,
            "dominant_reason": dominant,
            "avg_confidence": total_conf / len(self.transitions),
            "max_consecutive_rejects": max_rejects,
            "duration_ms": (self.finished_at - self.started_at) * 1000,
        }

    def diff(self, other: "ExecutionTraceV3") -> Dict[str, Any]:
        """Compare two traces to find behavioral differences."""
        return {
            "steps_diff": len(self.states) - len(other.states),
            "transitions_diff": len(self.transitions) - len(other.transitions),
            "confidence_diff": self.final_confidence - other.final_confidence,
            "reason_similarity": _jaccard(
                set(t.reason.value for t in self.transitions),
                set(t.reason.value for t in other.transitions),
            ),
        }


def _jaccard(a: set, b: set) -> float:
    u = a | b
    return len(a & b) / len(u) if u else 0.0
