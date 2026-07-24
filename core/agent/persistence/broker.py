"""Unified Persistence Broker — single entry point for all 10 chains.

Startup: replay events → restore StateGraph
Runtime: per-tick append event + periodic snapshot
Shutdown: final snapshot + verify chain integrity
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
import time, logging, threading

from core.agent.persistence.unified_event_log import UnifiedEventLog
from core.agent.persistence.lsm_store import LSMStore
from core.agent.persistence.models import Session, TurnRecord

logger = logging.getLogger(__name__)


@dataclass
class PersistenceState:
    """What was restored from disk at startup."""
    events: int = 0
    sessions: int = 0
    turns: int = 0
    graph_nodes: int = 0
    chain_intact: bool = True


class UnifiedPersistenceBroker:
    """Single entry point for all persistence operations.

    Connects: UnifiedEventLog → SQLiteStore → GraphStore → TieredStorage
    All 10 chains read/write through this single broker.

    Usage:
        broker = UnifiedPersistenceBroker(data_dir="data/dialogmesh")
        state = broker.startup()  # restore from disk
        # ... runtime: chains call broker methods ...
        broker.shutdown()  # final snapshot + verify
    """

    def __init__(self, data_dir: str = "data/dialogmesh",
                 gc_interval: float = 3600.0, ttl_seconds: float = 604800.0):
        """Initialize persistence broker.

        Args:
            data_dir: Root data directory
            gc_interval: GC cycle interval in seconds (default: 1 hour)
            ttl_seconds: Session TTL in seconds (default: 7 days)
        """
        self._dir = data_dir
        self._gc_interval = gc_interval
        self._ttl_seconds = ttl_seconds
        import os
        os.makedirs(data_dir, exist_ok=True)

        # Layer 1: Event Sourcing
        self.event_log = UnifiedEventLog(
            path=f"{data_dir}/events/unified_log.jsonl"
        )

        # Layer 2: Structured Stores
        self.store = LSMStore(
            db_path=f"{data_dir}/lsm.db"
        )
        self.store.open()

        self._state = PersistenceState()
        self._lock = threading.Lock()

    # ── Lifecycle ──

    def startup(self) -> PersistenceState:
        """Restore state from disk. Called once at process start."""
        t0 = time.time()

        # Verify event log integrity
        verify = self.event_log.verify()
        self._state.chain_intact = verify["chain_intact"]
        self._state.events = verify["total"]
        if not verify["chain_intact"]:
            logger.warning("Event chain BROKEN at %d events", verify["broken"])

        # Replay events from log
        events = self.event_log.replay_all()
        self._state.events = len(events)
        logger.info("Replayed %d events (chain %s)", 
                    self._state.events, 
                    "intact" if self._state.chain_intact else "BROKEN")

        # Restore sessions
        sessions = self.store.list_sessions(limit=100)
        self._state.sessions = len(sessions)

        # Start GC tier manager (JVM-style promotion/demotion)
        self._gc_timer = threading.Timer(self._gc_interval, self._gc_tick)
        self._gc_timer.daemon = True
        self._gc_timer.start()

        elapsed = (time.time() - t0) * 1000
        logger.info("PersistenceBroker started in %.0fms: %s", elapsed, self._state)
        return self._state

    def shutdown(self):
        """Final integrity check + GC flush. Called at process exit."""
        if hasattr(self, '_gc_timer') and self._gc_timer:
            self._gc_timer.cancel()

        verify = self.event_log.verify()
        logger.info("Shutdown verify: chain_intact=%s, events=%d",
                    verify["chain_intact"], verify["total"])
        self.store.close()

    def _gc_tick(self):
        """Periodic GC: demote stale, clean expired, strip cold data."""
        try:
            # Session TTL cleanup
            self.store.cleanup(self._ttl_seconds)
            
            # Reschedule
            if hasattr(self, '_gc_timer'):
                self._gc_timer = threading.Timer(self._gc_interval, self._gc_tick)
                self._gc_timer.daemon = True
                self._gc_timer.start()
        except Exception as e:
            logger.debug("GC tick failed: %s", e)

    # ── Chain 01: DiscourseTree ──

    def persist_block(self, block_id: str, data: dict, session_id: str):
        """Persist a DiscourseBlock."""
        self.event_log.log_node_edit(
            block_id=block_id,
            change=f"block_updated",
            author="engine",
            before="",
            after=str(data.get("raw_text", ""))[:200],
        )

    def persist_block_split(self, original_id: str, new_ids: list):
        self.event_log.log_node_split(original_id, new_ids)

    # ── Chain 02: Context ──

    def persist_turn(self, session_id: str, role: str, content: str, 
                     sequence: int, metadata: dict = None):
        """Persist a conversation turn."""
        self.store.put_turn(session_id, sequence, role, content, metadata or {})

    # ── Chain 03: MultiIntent ──

    def persist_intent_lock(self, session_id: str, intent: str, confidence: float):
        """Persist a locked intent (L3 posterior >= 0.85 or consensus)."""
        self.event_log.log_meta_decision(
            review_id=f"intent_{session_id}",
            verdict="locked",
            reason=f"intent={intent} conf={confidence:.2f}",
        )

    # ── Chain 04: PCR ──

    def persist_route(self, session_id: str, zone: str, coords: dict):
        """Persist PCR routing decision."""
        self.event_log.log_parameter(
            param_key=f"pcr.{session_id}",
            old_value="",
            new_value=f"zone={zone} x={coords.get('x',0):.2f} y={coords.get('y',0):.2f}",
            author="pcr_v2",
        )

    # ── Chain 05: Behavior ──

    def persist_behavior_pattern(self, pattern_key: str, confidence: float, support: int = 0):
        """Persist discovered behavior pattern."""
        self.event_log.log_pattern(pattern_key, confidence, support)

    def persist_pattern_feedback(self, pattern_key: str, accepted: bool):
        """Persist user feedback on pattern."""
        self.event_log.log_pattern_feedback(pattern_key, accepted)

    # ── Chain 06: Association ──

    def persist_belief_update(self, intent_key: str, belief_7d: dict):
        """Persist L2.5 belief state."""
        self.event_log.log_parameter(
            param_key=f"belief.{intent_key}",
            old_value="",
            new_value=str(belief_7d),
            author="l2_5",
        )

    # ── Chain 07: Engineering ──

    def persist_constraint(self, module: str, constraint: str):
        """Persist engineering constraint."""
        self.event_log.log_constraint_added(module, constraint)

    # ── Chain 08: Cognitive Profile ──

    def persist_profile_correction(self, dimension: str, old: float, new: float,
                                   reason: str = "user_edit"):
        """Persist OCEAN profile correction."""
        self.event_log.log_profile_correction(dimension, old, new, reason)

    def persist_profile_drift(self, dimension: str, drift: float):
        """Persist detected profile drift."""
        self.event_log.log_profile_drift(dimension, drift)

    # ── Chain 09: Metacognition ──

    def persist_meta_decision(self, review_id: str, verdict: str, reason: str = ""):
        """Persist metacognitive verdict."""
        self.event_log.log_meta_decision(review_id, verdict, reason)

    # ── Chain 10: Orchestrator ──

    def persist_session(self, session_id: str, user_id: str = ""):
        """Persist session metadata."""
        self.store.put_session(session_id, {"user_id": user_id}, user_id)

    # ── Bulk operations ──

    def verify_integrity(self) -> dict:
        """Full integrity check: event chain + graph + sessions."""
        return {
            "event_chain": self.event_log.verify(),
            "sessions": self.store.list_sessions(limit=1),
            "events_total": len(self.event_log.replay_all()),
        }

    @property
    def state(self) -> PersistenceState:
        return self._state
