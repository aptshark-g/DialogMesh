"""P1: EventScheduler + CausalTracker + GradedDegradation + SelfRepair.

EventScheduler: passive Tick + active timer (delayed events).
CausalTracker: tracks cause→effect chains for UI optimistic updates.
GradedDegradation: 4-level automatic fallback under load.
SelfRepair: meta-cognition adjusts own thresholds when accuracy < 0.7.
"""
from __future__ import annotations
import time, threading, logging
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ══════════ Event Scheduler ══════════

@dataclass
class DelayedEvent:
    event_id: str
    event_type: str
    data: Dict[str, Any]
    fire_at: float
    fired: bool = False


class EventScheduler:
    """Passive Tick + active timer events.

    Passive: user messages trigger tick()
    Active: 5min silence → TimeoutEvent, 30s → CheckpointEvent
    """

    def __init__(self):
        self._delayed: List[DelayedEvent] = []
        self._counter = 0
        self._silence_seconds = 0
        self._silence_threshold = 300  # 5min
        self._checkpoint_interval = 30  # 30s

    def schedule(self, event_type: str, data: Dict, delay_s: float) -> str:
        self._counter += 1
        eid = f"delayed_{self._counter}"
        self._delayed.append(DelayedEvent(
            event_id=eid, event_type=event_type, data=data,
            fire_at=time.time() + delay_s,
        ))
        return eid

    def tick(self, is_silent: bool = False) -> List[DelayedEvent]:
        """Return ready events, update silence timer."""
        now = time.time()
        
        # Silence detection
        if is_silent:
            self._silence_seconds += 1
            if self._silence_seconds >= self._silence_threshold:
                self._silence_seconds = 0
                # Inject TimeoutEvent
                ready = [DelayedEvent(
                    event_id="timeout", event_type="SilenceTimeout",
                    data={"seconds": self._silence_threshold},
                    fire_at=now, fired=False,
                )]
        else:
            self._silence_seconds = 0
        
        # Check delayed events
        ready = [d for d in self._delayed if d.fire_at <= now and not d.fired]
        for d in ready:
            d.fired = True
        
        # Cleanup old fired events
        self._delayed = [d for d in self._delayed if not d.fired or now - d.fire_at < 60]
        
        return ready + ([ready[0]] if is_silent and self._silence_seconds >= self._silence_threshold else [])

    def auto_schedule_checkpoint(self):
        """Schedule periodic checkpoint events."""
        self.schedule("CheckpointEvent", {}, self._checkpoint_interval)

    def auto_schedule_scans(self):
        """Schedule periodic scans (inertia, stale annotations)."""
        self.schedule("InertiaScanEvent", {}, 3600)     # 1h
        self.schedule("StaleScanEvent", {}, 7200)       # 2h


# ══════════ Causal Tracker ══════════

@dataclass
class CausalLink:
    parent_event: str       # root cause
    child_event: str        # effect
    depth: int
    ts: float


class CausalTracker:
    """Tracks cause→effect chains for UI optimistic updates.

    User edits → NodeEdited(depth=0) → PatternDiscovered(1) → ProfileDrifted(2) → MetaReviewed(3)
    Frontend polls /v6/causal-chain?event=XXX to show progress.
    """

    def __init__(self):
        self._links: Dict[str, CausalLink] = {}  # child_id → link
        self._history: List[int] = [3, 4, 5, 4, 6, 3, 7, 4, 5]  # sample chain lengths

    def link(self, parent: str, child: str):
        depth = 0
        if parent in self._links:
            depth = self._links[parent].depth + 1
        self._links[child] = CausalLink(parent_event=parent, child_event=child,
                                        depth=depth, ts=time.time())

    def get_chain(self, root_event: str) -> List[Dict]:
        """Trace full causal chain from root."""
        chain = [{"event": root_event, "depth": 0}]
        current = root_event
        visited = {root_event}
        while True:
            children = [cl for eid, cl in self._links.items() 
                       if cl.parent_event == current and eid not in visited]
            if not children: break
            child = children[0]
            visited.add(child.child_event)
            chain.append({"event": child.child_event, "depth": child.depth})
            current = child.child_event
        return chain

    def estimate_remaining(self, current_depth: int) -> int:
        """P90 estimate of remaining chain length from history."""
        p90 = sorted(self._history)[int(len(self._history) * 0.9)]
        return max(0, p90 - current_depth)

    def record_chain_length(self, length: int):
        self._history.append(length)
        if len(self._history) > 100:
            self._history = self._history[-100:]

    def stats(self) -> Dict:
        return {
            "tracked_chains": len(self._links),
            "avg_chain_length": sum(self._history) / max(len(self._history), 1),
            "p90_chain_length": sorted(self._history)[int(len(self._history) * 0.9)] if self._history else 0,
        }


# ══════════ Graded Degradation ══════════

class DegradationLevel(Enum):
    NORMAL = 0    # all systems go
    WARNING = 1   # queue 50-200: pause Deep Path
    DEGRADED = 2  # queue 200-500: pause meta review, behavior discovery
    EMERGENCY = 3 # queue > 500: only core chat + user edits


class GradedDegradation:
    """4-level automatic degradation under load. Never drops events.

    Level 0 (NORMAL):   all chains active
    Level 1 (WARNING):  pause Deep Path (causal promotion, deep scans)
    Level 2 (DEGRADED): pause meta review, behavior discovery, L5
    Level 3 (EMERGENCY): only chain 01-03 (core chat + user edits)
    """

    def __init__(self):
        self._level = DegradationLevel.NORMAL
        self._queue_depth = 0

    def assess(self, queue_depth: int) -> DegradationLevel:
        self._queue_depth = queue_depth
        
        if queue_depth > 500:
            self._level = DegradationLevel.EMERGENCY
        elif queue_depth > 200:
            self._level = DegradationLevel.DEGRADED
        elif queue_depth > 50:
            self._level = DegradationLevel.WARNING
        else:
            self._level = DegradationLevel.NORMAL
        
        return self._level

    def is_active(self, chain: str) -> bool:
        """Check if a chain should be active at current level."""
        if self._level == DegradationLevel.NORMAL:
            return True
        
        if self._level == DegradationLevel.WARNING:
            return chain not in ("deep_path", "causal_promotion", "deep_scan")
        
        if self._level == DegradationLevel.DEGRADED:
            return chain in ("core_chat", "user_edit", "behavior_predict", "slow_path")
        
        # EMERGENCY
        return chain in ("core_chat", "user_edit")

    @property
    def level(self) -> DegradationLevel:
        return self._level


# ══════════ Meta Self-Repair ══════════

class MetaSelfRepair:
    """Auto-adjusts meta-cognition thresholds based on accuracy.

    Accuracy < 0.7 → raise review threshold (be more conservative)
    Accuracy > 0.9 → lower review threshold (be more aggressive)
    """

    def __init__(self):
        self._base_threshold = 0.6    # default review confidence threshold
        self._current_threshold = 0.6
        self._accuracy_history: List[float] = []
        self._adjustment_count = 0

    def record_accuracy(self, accuracy: float):
        """Record meta-cognition accuracy for self-repair."""
        self._accuracy_history.append(accuracy)
        if len(self._accuracy_history) > 50:
            self._accuracy_history = self._accuracy_history[-50:]
        
        if len(self._accuracy_history) < 10:
            return  # not enough data
        
        avg = sum(self._accuracy_history[-10:]) / 10
        
        if avg < 0.7:
            # Raise threshold → be more conservative
            adjustment = min(0.15, (0.7 - avg) * 0.3)
            self._current_threshold = min(0.85, self._base_threshold + adjustment)
            self._adjustment_count += 1
            logger.info("Meta self-repair: accuracy=%.2f, threshold raised to %.2f", avg, self._current_threshold)
        
        elif avg > 0.9:
            # Lower threshold → be more aggressive
            self._current_threshold = max(0.5, self._current_threshold - 0.02)
            logger.info("Meta self-repair: accuracy=%.2f, threshold lowered to %.2f", avg, self._current_threshold)

    @property
    def threshold(self) -> float:
        return self._current_threshold

    def stats(self) -> Dict:
        return {
            "base_threshold": self._base_threshold,
            "current_threshold": self._current_threshold,
            "adjustments": self._adjustment_count,
            "avg_accuracy": sum(self._accuracy_history[-10:]) / max(len(self._accuracy_history[-10:]), 1),
        }
