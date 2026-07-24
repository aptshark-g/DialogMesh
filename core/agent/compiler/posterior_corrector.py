"""Posterior Correction — topic drift triggers node re-affiliation.

Bridge: BM25→LLM drift → Belief accumulation → Node re-classify.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class DriftRecord:
    """One detected topic drift."""
    from_topic: str
    to_topic: str
    query: str
    turn: int
    confidence: float


@dataclass
class CorrectionEvent:
    """A posterior correction applied to a discourse node."""
    block_id: str
    from_topic: str
    to_topic: str
    reason: str
    turn: int


class PosteriorCorrector:
    """Accumulate drifts → when evidence threshold met → correct node affiliation.

    Usage:
        corrector = PosteriorCorrector()
        drift = corrector.check_drift(matcher, query, llm)
        if drift:
            corrector.apply_to_block(block, drift.to_topic)
    """

    DRIFT_THRESHOLD = 2  # re-affiliate after this many drifts in same direction

    def __init__(self):
        self._drifts: List[DriftRecord] = []
        self._corrections: List[CorrectionEvent] = []
        self._turn = 0

    def check_drift(self, matcher, query: str, llm) -> Optional[DriftRecord]:
        """Run dual-track match. Return drift if BM25 and LLM disagree."""
        self._turn += 1
        result = matcher.dual_track_match(query, llm) if matcher else {"drift": False}

        if not result.get("drift"):
            return None

        drift = DriftRecord(
            from_topic=matcher.match(query, top_k=1)[0][0].topic if matcher else "",
            to_topic=result["topic"],
            query=query,
            turn=self._turn,
            confidence=result.get("confidence", 0.5),
        )
        self._drifts.append(drift)
        return drift

    def should_correct(self, from_topic: str, to_topic: str) -> bool:
        """Have we accumulated enough evidence to re-affiliate?"""
        count = sum(1 for d in self._drifts
                    if d.from_topic == from_topic and d.to_topic == to_topic)
        return count >= self.DRIFT_THRESHOLD

    def apply_to_block(self, block: Any, new_topic: str, from_topic: str = "",
                       turn: int = 0) -> Optional[CorrectionEvent]:
        """Re-affiliate a discourse block to a new topic."""
        if not block:
            return None

        old = getattr(block, 'topic', '') or from_topic
        if old == new_topic:
            return None

        # Apply correction
        try:
            block.topic = new_topic
            block.corrected_at = turn
            block.correction_reason = f"drift: {old} → {new_topic}"
        except AttributeError:
            # Block doesn't have topic attribute — set as metadata
            if not hasattr(block, 'metadata'):
                block.metadata = {}
            block.metadata['topic'] = new_topic
            block.metadata['corrected_from'] = old

        event = CorrectionEvent(
            block_id=getattr(block, 'block_id', 'unknown'),
            from_topic=old,
            to_topic=new_topic,
            reason=f"Posterior correction after {self._turn} turns",
            turn=turn or self._turn,
        )
        self._corrections.append(event)
        logger.info("Corrected: %s → %s (block=%s)", old, new_topic, event.block_id)
        return event

    def apply_to_tree(self, tree_manager, session_id: str) -> List[CorrectionEvent]:
        """Apply accumulated drifts to all blocks in a discourse tree."""
        events = []
        tree = tree_manager._trees.get(session_id) if tree_manager else None
        if not tree:
            return events

        # Group drifts by topic direction
        for drift in self._drifts[-10:]:
            if self.should_correct(drift.from_topic, drift.to_topic):
                # Find blocks matching the old topic
                for block in tree.blocks:
                    block_topic = getattr(block, 'topic', '') or \
                                  getattr(block, 'metadata', {}).get('topic', '')
                    if block_topic == drift.from_topic:
                        ev = self.apply_to_block(block, drift.to_topic,
                                                 drift.from_topic, drift.turn)
                        if ev:
                            events.append(ev)

        return events

    def status(self) -> dict:
        """Correction status for monitoring."""
        return {
            "total_drifts": len(self._drifts),
            "total_corrections": len(self._corrections),
            "last_drift": self._drifts[-1].to_topic if self._drifts else None,
            "pending_corrections": sum(
                1 for d in self._drifts[-10:]
                if not self.should_correct(d.from_topic, d.to_topic)
            ),
        }
