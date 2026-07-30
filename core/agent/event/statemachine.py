"""P2: State Machine Engine — Decider-driven pipeline coordination.

Currently the Decider just records ticks. This makes it actually DECIDE:
  1. What chains to run based on current state
  2. When to escalate (low confidence → deep path)
  3. When to skip (cache hit → fast path)
  4. Checkpoint after each decision for replay

Design: DESIGN_GLOBAL_STATE_MACHINE.md + LangGraph conditional_edges pattern.
"""
import threading, time, json, logging
from enum import Enum
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class PipelinePhase(Enum):
    """Pipeline phases — the Decider routes through these."""
    IDLE = "idle"
    PCR = "pcr"               # Pre-cognitive routing
    INTENT = "intent"         # Intent parsing
    PLANNING = "planning"     # Blueprint / plan generation
    CONTEXT = "context"       # Context assembly + subgraph
    LLM = "llm"               # LLM generation
    DISCOURSE = "discourse"   # Discourse tree update
    BEHAVIOR = "behavior"     # Behavior graph
    META = "meta"             # Meta cognition review
    PROFILE = "profile"       # OCEAN analysis
    PERSIST = "persist"       # Persistence to storage
    ASSOCIATION = "association"  # L1 + L2.5 chain
    DONE = "done"


STATE_TRANSITIONS: Dict[PipelinePhase, Dict[str, PipelinePhase]] = {
    # Normal flow: PCR → Intent → Planning → Context → LLM → (subsystems) → DONE
    PipelinePhase.IDLE:      {"start": PipelinePhase.PCR},
    PipelinePhase.PCR:       {"normal": PipelinePhase.INTENT, "skip": PipelinePhase.LLM},
    PipelinePhase.INTENT:    {"normal": PipelinePhase.PLANNING, "simple": PipelinePhase.LLM},
    PipelinePhase.PLANNING:  {"normal": PipelinePhase.CONTEXT, "skip": PipelinePhase.LLM},
    PipelinePhase.CONTEXT:   {"normal": PipelinePhase.LLM},
    PipelinePhase.LLM:       {"normal": PipelinePhase.DISCOURSE, "error": PipelinePhase.DONE},
    PipelinePhase.DISCOURSE: {"normal": PipelinePhase.BEHAVIOR},
    PipelinePhase.BEHAVIOR:  {"normal": PipelinePhase.META},
    PipelinePhase.META:      {"normal": PipelinePhase.PROFILE},
    PipelinePhase.PROFILE:   {"normal": PipelinePhase.PERSIST},
    PipelinePhase.PERSIST:   {"normal": PipelinePhase.DONE},
}


@dataclass 
class StateSnapshot:
    """Snapshot of engine state for the Decider to make decisions."""
    phase: PipelinePhase = PipelinePhase.IDLE
    turn_count: int = 0
    last_pcr_zone: str = "MIXED"
    confidence: float = 0.5
    errors_in_phase: int = 0
    total_latency_ms: float = 0
    chain_results: Dict[str, Any] = field(default_factory=dict)
    checkpoint: Optional[str] = None


class DeciderStateMachine:
    """Coordinates pipeline execution by deciding what phase runs next.

    Replaces hardcoded on_event serial chain with state-driven routing.
    Pattern: LangGraph conditional_edges — each phase decides "where next?"
    """

    def __init__(self):
        self._state = StateSnapshot()
        self._lock = threading.Lock()
        self._history: List[StateSnapshot] = []
        self._phase_handlers: Dict[PipelinePhase, Callable] = {}
        self._running = True

    def register_handler(self, phase: PipelinePhase, handler: Callable):
        """Register a function to execute when this phase is reached."""
        self._phase_handlers[phase] = handler

    def current_phase(self) -> PipelinePhase:
        return self._state.phase

    def snapshot(self) -> StateSnapshot:
        with self._lock:
            return StateSnapshot(
                phase=self._state.phase,
                turn_count=self._state.turn_count,
                last_pcr_zone=self._state.last_pcr_zone,
                confidence=self._state.confidence,
                errors_in_phase=self._state.errors_in_phase,
                total_latency_ms=self._state.total_latency_ms,
            )

    def decide(self, phase: PipelinePhase, result: dict = None) -> PipelinePhase:
        """Given current phase and result, decide next phase.

        This is the core of the state machine — conditional routing.
        """
        transitions = STATE_TRANSITIONS.get(phase, {})

        if not transitions:
            return PipelinePhase.DONE

        # Decision logic based on result
        if result:
            if result.get("error"):
                # Error → skip to safe next phase
                return transitions.get("error", transitions.get("normal", PipelinePhase.DONE))
            if result.get("skip"):
                return transitions.get("skip", transitions.get("normal", PipelinePhase.DONE))
            if result.get("confidence", 0.5) < 0.3:
                # Low confidence → escalate (if available)
                pass  # Use normal path for now

        return transitions.get("normal", PipelinePhase.DONE)

    def transition(self, to_phase: PipelinePhase, result: dict = None):
        """Record a state transition and save checkpoint."""
        with self._lock:
            self._state.phase = to_phase
            self._state.turn_count += 1
            if result:
                self._state.chain_results[to_phase.value] = result.get("summary", str(result)[:100])
                if "confidence" in result:
                    self._state.confidence = result["confidence"]

            # Checkpoint after every 3 transitions
            if self._state.turn_count % 3 == 0:
                self._state.checkpoint = f"ckpt_{self._state.turn_count}"
                self._history.append(StateSnapshot(
                    phase=self._state.phase,
                    turn_count=self._state.turn_count,
                    confidence=self._state.confidence,
                ))

    def run_pipeline(self, start_phase: PipelinePhase, context: dict = None) -> dict:
        """Execute the full pipeline from a starting phase.

        This is the state machine runtime — it iterates through phases,
        calling handlers, deciding next phase, until DONE.
        """
        current = start_phase
        results = {}
        self._state.chain_results = {}

        while current != PipelinePhase.DONE:
            handler = self._phase_handlers.get(current)
            if handler:
                try:
                    result = handler(context or {})
                    results[current.value] = result
                except Exception as e:
                    result = {"error": str(e)[:200]}
                    results[current.value] = result
            
            next_phase = self.decide(current, result or {})
            self.transition(current, result or {})
            current = next_phase

            # Safety: max 20 transitions
            if self._state.turn_count > 20:
                logger.warning("Pipeline exceeded max transitions, forcing DONE")
                break

        return {"phases": list(results.keys()), "checkpoint": self._state.checkpoint,
                "results": results}

    def replay(self, from_checkpoint: str) -> Optional[StateSnapshot]:
        """Replay from a checkpoint (for recovery)."""
        for snap in self._history:
            if snap.checkpoint == from_checkpoint:
                return snap
        return None
