"""InternalStateMonitor — records all engine internals for backpropagation-like debugging.

Captures every state change across all v6 components:
  - Transition sequence with reasoning
  - Policy generation and effects
  - Profile deltas (TrackA + TrackB)
  - Simulation predictions vs actual
  - ContextualStrategy selections
  - DiscourseTree events
  - InteractionGraph propagations

Output: structured JSONL log for analysis/replay.
"""
from __future__ import annotations
import json, time, os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent.v4.state.state_object import TransitionReason


@dataclass
class MonitorEvent:
    """One internal state change event."""
    timestamp: float
    event_type: str             # "transition" | "policy" | "profile" | "simulation" | "strategy" | "tree"
    turn: int
    data: Dict[str, Any]


class InternalStateMonitor:
    """Hooks into all v6 components to record internal state evolution.

    Usage:
        monitor = InternalStateMonitor(session_id="bench_001")
        monitor.record_transition(turn, transition, evidence)
        monitor.record_policy(turn, policy)
        monitor.record_profile_delta(turn, track_a, track_b)
        monitor.record_simulation(turn, predicted, actual, matched)
        monitor.save()  # writes to data/monitor_<session_id>.jsonl
    """

    def __init__(self, session_id: str = "", log_dir: str = "data/monitor"):
        self.session_id = session_id or f"monitor_{int(time.time())}"
        self.log_dir = log_dir
        self.events: List[MonitorEvent] = []
        os.makedirs(log_dir, exist_ok=True)
        self._log_path = os.path.join(log_dir, f"{self.session_id}.jsonl")
        self._start_time = time.time()

    # ── Recording ──

    def record_transition(self, turn: int, reason: str, evidence: str, effects: list = None):
        self.events.append(MonitorEvent(
            timestamp=time.time(),
            event_type="transition",
            turn=turn,
            data={
                "reason": reason,
                "evidence": evidence,
                "effects": effects or [],
            },
        ))

    def record_policy(self, turn: int, policy: Any):
        if policy is None:
            return
        self.events.append(MonitorEvent(
            timestamp=time.time(),
            event_type="policy",
            turn=turn,
            data={
                "perspective": getattr(policy, 'perspective', None),
                "explanation_mode": getattr(policy, 'explanation_mode', None),
                "depth_adjust": getattr(policy, 'depth_adjust', 0),
                "focus_objects": getattr(policy, 'focus_objects', []),
                "source": getattr(policy, 'source', 'unknown'),
                "reason": getattr(policy, 'reason', ''),
            },
        ))

    def record_profile(self, turn: int, track_a: Any, track_b: dict = None):
        ta_data = {}
        if track_a:
            for attr in ['cognitive_inertia','trust_score','emotional_entropy','attention_anchor','observation_count']:
                ta_data[attr] = getattr(track_a, attr, None)
        self.events.append(MonitorEvent(
            timestamp=time.time(),
            event_type="profile",
            turn=turn,
            data={"track_a": ta_data, "track_b_tags": list(track_b.keys())[:5] if track_b else []},
        ))

    def record_simulation(self, turn: int, predicted: str, actual: str, matched: bool, similarity: float):
        self.events.append(MonitorEvent(
            timestamp=time.time(),
            event_type="simulation",
            turn=turn,
            data={
                "predicted": predicted[:80],
                "actual": actual[:80],
                "matched": matched,
                "similarity": similarity,
            },
        ))

    def record_strategy(self, turn: int, strategy_name: str, context: dict, score: float):
        self.events.append(MonitorEvent(
            timestamp=time.time(),
            event_type="strategy",
            turn=turn,
            data={
                "strategy": strategy_name,
                "context": context,
                "score": score,
            },
        ))

    def record_tree(self, turn: int, blocks: int, active: int, forks: int):
        self.events.append(MonitorEvent(
            timestamp=time.time(),
            event_type="tree",
            turn=turn,
            data={"blocks": blocks, "active": active, "forks": forks},
        ))

    def record_error(self, turn: int, component: str, error: str):
        self.events.append(MonitorEvent(
            timestamp=time.time(),
            event_type="error",
            turn=turn,
            data={"component": component, "error": error[:200]},
        ))

    # ── Analysis ──

    def summary(self) -> Dict[str, Any]:
        """Aggregate statistics across all recorded events."""
        by_type = {}
        for e in self.events:
            by_type.setdefault(e.event_type, 0)
            by_type[e.event_type] += 1

        transitions = [e for e in self.events if e.event_type == "transition"]
        reason_counts = {}
        for t in transitions:
            r = t.data.get("reason", "unknown")
            reason_counts[r] = reason_counts.get(r, 0) + 1

        policies = [e for e in self.events if e.event_type == "policy"]
        sims = [e for e in self.events if e.event_type == "simulation"]
        matches = sum(1 for s in sims if s.data.get("matched"))

        return {
            "session_id": self.session_id,
            "total_events": len(self.events),
            "duration_s": time.time() - self._start_time,
            "event_types": by_type,
            "transition_reasons": reason_counts,
            "policies_generated": len(policies),
            "simulation_accuracy": f"{matches}/{len(sims)}" if sims else "N/A",
            "errors": len([e for e in self.events if e.event_type == "error"]),
        }

    def save(self):
        """Write all events to JSONL file."""
        with open(self._log_path, 'a', encoding='utf-8') as f:
            for e in self.events[-20:]:  # batch write last 20
                f.write(json.dumps({
                    "timestamp": e.timestamp,
                    "type": e.event_type,
                    "turn": e.turn,
                    "data": e.data,
                }, ensure_ascii=False) + "\n")
        # Truncate internal buffer
        if len(self.events) > 20:
            self.events = self.events[-10:]

    def flush(self):
        """Write ALL remaining events and clear."""
        with open(self._log_path, 'a', encoding='utf-8') as f:
            for e in self.events:
                f.write(json.dumps({
                    "timestamp": e.timestamp,
                    "type": e.event_type,
                    "turn": e.turn,
                    "data": e.data,
                }, ensure_ascii=False) + "\n")
        self.events.clear()
