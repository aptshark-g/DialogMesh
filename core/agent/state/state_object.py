"""StateObject — unified state abstraction for DialogMesh v6.

All persistent entities are StateObjects with different lifespans:
  Snapshot  (seconds)  → Workspace  (conversation) → Mind (months) → Knowledge (forever)

Design: makes Transition observable — every state change has a reason, evidence, and effects.
"""
from __future__ import annotations

import time, copy, hashlib, json, logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Callable

logger = logging.getLogger(__name__)


# ═══════════════════════ Lifespan ═══════════════════════

class Lifespan(Enum):
    SNAPSHOT = 1       # 瞬态 (seconds)
    WORKSPACE = 2      # 一次推理 (conversation)
    MIND = 3           # 长期心智 (months)
    KNOWLEDGE = 4      # 永久知识 (forever)

    def __lt__(self, other):
        return self.value < other.value


# ═══════════════════════ StateObject ═══════════════════════

@dataclass
class StateObject:
    """Base class for all objects with observable state evolution.

    Every state change is tracked via a Transition, making the system
    explainable at every step.
    """

    id: str = field(default_factory=lambda: hashlib.md5(str(time.time()).encode()).hexdigest()[:12])
    lifespan: Lifespan = Lifespan.SNAPSHOT
    data: Dict[str, Any] = field(default_factory=dict)

    created_at: float = field(default_factory=time.time)
    last_modified: float = field(default_factory=time.time)

    # ── State tracking ──
    _previous_state: Optional[Dict[str, Any]] = field(default=None, repr=False)
    _transitions: List[Transition] = field(default_factory=list, repr=False)

    def snapshot(self) -> StateObject:
        """Create a snapshot copy (short-lifetime sibling)."""
        snap = copy.deepcopy(self)
        snap.id = hashlib.md5(f"{self.id}_{time.time()}".encode()).hexdigest()[:12]
        snap.lifespan = Lifespan.SNAPSHOT
        snap.created_at = time.time()
        snap._transitions = []
        return snap

    def evolve(self, transition: Transition) -> StateObject:
        """Apply a Transition, returning a new StateObject with updated state."""
        self._previous_state = copy.deepcopy(self.data)
        self._transitions.append(transition)
        self.last_modified = time.time()

        # Apply deltas
        for delta in transition.effects:
            self._apply_delta(delta)
        self.data.update(transition.to_state_data or {})

        return self

    def _apply_delta(self, delta: StateDelta):
        """Apply a StateDelta to this object's data (nested key support)."""
        target = self.data
        keys = delta.key.split(".")
        for k in keys[:-1]:
            target = target.setdefault(k, {})
        if delta.operation == "set":
            target[keys[-1]] = delta.value
        elif delta.operation == "inc":
            target[keys[-1]] = target.get(keys[-1], 0) + delta.value
        elif delta.operation == "append":
            target.setdefault(keys[-1], []).append(delta.value)

    def freeze(self) -> StateObject:
        """Freeze to next-longer lifespan.

        Snapshot → Workspace → Mind → Knowledge
        """
        order = [Lifespan.SNAPSHOT, Lifespan.WORKSPACE, Lifespan.MIND, Lifespan.KNOWLEDGE]
        try:
            idx = order.index(self.lifespan)
            if idx < len(order) - 1:
                self.lifespan = order[idx + 1]
                logger.info("StateObject %s frozen: %s → %s", self.id[:8], order[idx], self.lifespan)
        except ValueError:
            pass
        return self

    def diff_from_previous(self) -> Dict[str, Any]:
        """Return what changed since last evolve()."""
        if self._previous_state is None:
            return {}
        return _deep_diff(self._previous_state, self.data)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "lifespan": self.lifespan.value,
            "data": self.data,
            "created_at": self.created_at,
            "last_modified": self.last_modified,
            "transition_count": len(self._transitions),
        }


# ═══════════════════════ Transition ═══════════════════════

class TransitionReason(Enum):
    # ── 观察驱动 ──
    OBSERVE = "observe"
    NEW_EVIDENCE = "new_evidence"

    # ── 推理驱动 ──
    INFER = "infer"
    COMPARE = "compare"
    ANALOGIZE = "analogize"

    # ── 冲突驱动 ──
    CONTRADICT = "contradict"
    REJECT = "reject"
    RESOLVE = "resolve"

    # ── 整合驱动 ──
    MERGE = "merge"
    FREEZE = "freeze"
    GENERALIZE = "generalize"

    # ── 反思驱动 ──
    REFLECT = "reflect"
    REVISE = "revise"
    STRENGTHEN = "strengthen"
    WEAKEN = "weaken"

    # ── 视角驱动 ──
    CHANGE_PERSPECTIVE = "change_perspective"
    SHIFT_ATTENTION = "shift_attention"
    ACTIVATE = "activate"           # block/concept/node activated


@dataclass
class StateDelta:
    """One specific change within a Transition."""
    key: str                    # 改变的字段路径，如 "confidence" 或 "attention.Runtime"
    operation: str              # "set" | "inc" | "append"
    value: Any


@dataclass
class Transition:
    """A state change from one State to another, with reason and evidence."""

    id: str = field(default_factory=lambda: hashlib.md5(str(time.time()).encode()).hexdigest()[:12])
    reason: TransitionReason = TransitionReason.OBSERVE
    from_state_id: str = ""
    to_state_id: str = ""
    to_state_data: Dict[str, Any] = field(default_factory=dict)

    evidence: List[str] = field(default_factory=list)
    effects: List[StateDelta] = field(default_factory=list)

    confidence: float = 0.5
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def evidence_summary(self) -> str:
        return "; ".join(self.evidence[:2]) if self.evidence else "(no evidence)"


# ═══════════════════════ Helpers ═══════════════════════

def _deep_diff(old: dict, new: dict) -> dict:
    """Compute nested diff between two state dicts."""
    diff = {}
    all_keys = set(old) | set(new)
    for key in all_keys:
        if key not in old:
            diff[key] = ("+", new[key])
        elif key not in new:
            diff[key] = ("-", old[key])
        elif isinstance(old[key], dict) and isinstance(new[key], dict):
            nested = _deep_diff(old[key], new[key])
            if nested:
                diff[key] = nested
        elif old[key] != new[key]:
            diff[key] = (old[key], "→", new[key])
    return diff
