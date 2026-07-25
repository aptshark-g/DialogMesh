"""Cold→Hot Feedback — three-layer writeback engine.

Layer 1: Meta urgent corrections → next Tick Observe parameters
Layer 2: Cognition evidence accumulation → threshold-triggered actions
Layer 3: Pattern drift → Blueprint/parameter micro-adjustments

Philosophy: "Don't block current response. Learn for the next one."
"""

from __future__ import annotations
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class MetaDecision:
    """Produced by Meta Subscriber (cold path), consumed by agent_native (hot path)."""

    tick: int = 0
    confidence: float = 0.5

    # Layer 1: urgent correction (high conf + high risk only)
    urgent_correction: Optional[Dict] = None

    # Layer 2: belief update (accumulated evidence)
    belief_update: Optional[Dict] = None

    # Layer 3: parameter shift (minor drift, no urgency)
    parameter_shift: Optional[Dict] = None


class FeedbackBridge:
    """Bridge between cold path (Meta) and hot path (orchestrator).

    Write path (Meta Subscriber):
        bridge.post_decision(decision)  → stored in ring buffer

    Read path (agent_native, at start of each process()):
        correction = bridge.consume()   → applied to PCR params
        belief = bridge.consume_belief() → injected into CognitionHub
        drift = bridge.consume_drift()   → forwarded to BlueprintSelector
    """

    MAX_DECISIONS = 64

    def __init__(self):
        self._decisions: list[MetaDecision] = []

    def post_decision(self, decision: MetaDecision):
        """Called by Meta Subscriber — fire and forget."""
        if len(self._decisions) >= self.MAX_DECISIONS:
            self._decisions.pop(0)
        self._decisions.append(decision)

    def consume(self) -> Optional[Dict]:
        """Called by agent_native before each process() — Layer 1.
        Returns the most recent urgent correction, if any.
        """
        urgent = [d for d in self._decisions if d.urgent_correction]
        if urgent:
            self._decisions[:] = [d for d in self._decisions if d is not urgent[-1]]
            return urgent[-1].urgent_correction
        return None

    def consume_belief(self) -> Optional[Dict]:
        """Called by agent_native at cognition tick — Layer 2."""
        belief = [d for d in self._decisions if d.belief_update]
        if belief:
            result = belief[-1].belief_update
            self._decisions[:] = [d for d in self._decisions if d is not belief[-1]]
            return result
        return None

    def consume_drift(self) -> Optional[Dict]:
        """Called by agent_native at blueprint tick — Layer 3."""
        drift = [d for d in self._decisions if d.parameter_shift]
        if drift:
            result = drift[-1].parameter_shift
            self._decisions[:] = [d for d in self._decisions if d is not drift[-1]]
            return result
        return None

    def has_pending(self) -> bool:
        return len(self._decisions) > 0
