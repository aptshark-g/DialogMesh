"""P0: Decider Pattern — Command→Event validation + ShardedState.

Decider: sole entry point for state mutations. Validates commands,
produces Events, applies them to ShardedState.

ShardedState: keyed by discourse_block_id. Only modified via Decider.
"""
from __future__ import annotations
import time, logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ══════════ Command → Event ══════════

@dataclass
class Command:
    cmd_type: str
    target: str    # block_id / dimension / pattern_id
    payload: Dict[str, Any]
    author: str = "user"  # user | engine | meta_cognition
    ts: float = field(default_factory=time.time)


@dataclass 
class Event:
    event_type: str
    target: str
    data: Dict[str, Any]
    ts: float = field(default_factory=time.time)


class Decider:
    """P0: Command→Event decision engine.
    
    Only entry point for state mutation.
    Validates: conflicts, permissions, budgets.
    Produces 1 Event per tick (anti-broadcast-storm).
    """

    def __init__(self, state: ShardedState = None):
        self._state = state

    def decide(self, cmd: Command) -> Optional[Event]:
        """Validate command → produce event (or None if rejected)."""

        if cmd.cmd_type == "node_edit":
            return self._decide_node_edit(cmd)
        
        elif cmd.cmd_type == "profile_edit":
            return self._decide_profile_edit(cmd)
        
        elif cmd.cmd_type == "parameter_change":
            return self._decide_parameter_change(cmd)
        
        elif cmd.cmd_type == "pattern_discovered":
            return self._decide_pattern(cmd)
        
        return None  # unknown command → rejected

    def _decide_node_edit(self, cmd: Command) -> Optional[Event]:
        block_id = cmd.target
        change = cmd.payload.get("change", "")
        
        # Conflict check
        if self._state and self._state.is_locked(block_id):
            logger.warning("Decider: block %s locked, rejecting edit", block_id)
            return None
        
        # Budget check
        if len(change) > 10000:
            logger.warning("Decider: edit too large (%d chars)", len(change))
            return None
        
        return Event(event_type="NodeEdited", target=block_id,
                    data={"change": change, "author": cmd.author})

    def _decide_profile_edit(self, cmd: Command) -> Optional[Event]:
        dim = cmd.target
        value = cmd.payload.get("value", 0.5)
        
        # Range check
        if not (0 <= value <= 1):
            logger.warning("Decider: profile value out of range: %s=%s", dim, value)
            return None
        
        return Event(event_type="ProfileEdited", target=dim,
                    data={"from": cmd.payload.get("old_value"), "to": value,
                          "reason": cmd.payload.get("reason", "user_edit")})

    def _decide_parameter_change(self, cmd: Command) -> Optional[Event]:
        param = cmd.target
        new_val = cmd.payload.get("value")
        
        # Allowed parameters whitelist
        allowed = {"behavior.min_repeat_count", "behavior.min_confidence",
                   "behavior.window_size", "behavior.epsilon_initial",
                   "slow_path.event_threshold"}
        
        if param not in allowed:
            logger.warning("Decider: parameter %s not in allowed list", param)
            return None
        
        return Event(event_type="ParameterChanged", target=param,
                    data={"from": cmd.payload.get("old_value"), "to": new_val})

    def _decide_pattern(self, cmd: Command) -> Optional[Event]:
        pattern = cmd.target  # "write_code→add_test"
        conf = cmd.payload.get("confidence", 0)
        
        if conf < 0.5:  # too weak
            return None
        
        return Event(event_type="PatternDiscovered", target=pattern,
                    data={"confidence": conf, "support": cmd.payload.get("support", 0)})


# ══════════ Sharded State ══════════

@dataclass
class BlockState:
    text: str = ""
    locked: bool = False
    version: int = 0

    def apply(self, event: Event) -> 'BlockState':
        ns = BlockState(text=self.text, locked=self.locked, version=self.version + 1)
        if event.event_type == "NodeEdited":
            ns.text = event.data.get("change", ns.text)
        return ns


class ShardedState:
    """P0: State sharded by block_id. Only Decider can modify.
    
    Reference: Flink KeyedState — each key has independent state.
    Cold shards can be swapped to disk (future: RocksDB backend).
    """

    def __init__(self):
        self._shards: Dict[str, BlockState] = {}
        self._locks: Dict[str, bool] = {}

    def get(self, block_id: str) -> BlockState:
        return self._shards.get(block_id, BlockState())

    def is_locked(self, block_id: str) -> bool:
        return self._locks.get(block_id, False)

    def lock(self, block_id: str):
        self._locks[block_id] = True

    def unlock(self, block_id: str):
        self._locks.pop(block_id, None)

    def apply_event(self, event: Event):
        """Apply event to the target shard."""
        if not event.target: return
        
        current = self.get(event.target)
        evolved = current.apply(event)
        self._shards[event.target] = evolved

    def evolve(self, events: List[Event]) -> ShardedState:
        """Apply multiple events (only non-conflicting ones can be batched)."""
        targets = set()
        for e in events:
            if e.target in targets:
                continue  # skip conflicting events (same target)
            targets.add(e.target)
            self.apply_event(e)
        return self

    def stats(self) -> Dict[str, Any]:
        return {
            "total_shards": len(self._shards),
            "locked": sum(self._locks.values()),
            "total_version": sum(s.version for s in self._shards.values()),
        }
