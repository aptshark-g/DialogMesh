"""Learning Loop Scheduler — closes the Profile/Behavior/Meta feedback loop.

P0-3: Turns "record-only" modules into a learning system.
  Profile ← Behavior signals ← Meta review → Profile recalibration
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time, logging

logger = logging.getLogger(__name__)


@dataclass
class LearningSignal:
    """A signal from one module to another — drives the feedback loop."""
    source: str          # "behavior", "meta", "profile", "abc", "mind"
    target: str          # which module to notify
    signal_type: str     # "correction", "drift_warning", "pattern_found", "quality_feedback"
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    priority: int = 5    # 1=immediate, 5=background


class LearningLoop:
    """Orchestrates cross-module learning signals.
    
    Profile learns from Behavior and Meta.
    Meta learns from Behavior patterns.
    ABC learns from user feedback.
    Mind integrates all into long-term memory.
    """
    
    def __init__(self):
        self.signals: List[LearningSignal] = []
        self.profile_trust: float = 0.5
        self.behavior_patterns: List[str] = []
        self.correction_count: int = 0
        self.drift_detected: bool = False
    
    # ── Input: modules feed signals ──
    
    def on_user_corrected(self, correction_detail: str = ""):
        """User corrected something — strongest signal."""
        self.correction_count += 1
        self._emit(LearningSignal(
            source="behavior", target="profile",
            signal_type="correction",
            payload={"detail": correction_detail, "count": self.correction_count},
            priority=1,
        ))
        self._emit(LearningSignal(
            source="behavior", target="meta",
            signal_type="correction",
            payload={"detail": correction_detail},
            priority=1,
        ))
    
    def on_pattern_discovered(self, pattern: str, confidence: float):
        """Behavior chain found a recurring pattern."""
        self.behavior_patterns.append(pattern)
        self._emit(LearningSignal(
            source="behavior", target="meta",
            signal_type="pattern_found",
            payload={"pattern": pattern, "confidence": confidence},
            priority=3 if confidence > 0.7 else 5,
        ))
        if confidence > 0.8:
            self._emit(LearningSignal(
                source="behavior", target="profile",
                signal_type="pattern_found",
                payload={"pattern": pattern},
                priority=4,
            ))
    
    def on_profile_drift(self, dimension: str, from_val: float, to_val: float):
        """Profile changed significantly."""
        if abs(from_val - to_val) > 0.3:
            self.drift_detected = True
            self._emit(LearningSignal(
                source="profile", target="meta",
                signal_type="drift_warning",
                payload={"dimension": dimension, "from": from_val, "to": to_val},
                priority=2,
            ))
    
    def on_quality_feedback(self, good: bool, aspect: str = ""):
        """User gave explicit quality feedback (thumbs up/down)."""
        self._emit(LearningSignal(
            source="abc", target="profile",
            signal_type="quality_feedback",
            payload={"good": good, "aspect": aspect},
            priority=3,
        ))
        if not good:
            self._emit(LearningSignal(
                source="abc", target="meta",
                signal_type="quality_feedback",
                payload={"aspect": aspect},
                priority=2,
            ))
    
    # ── Output: modules consume signals ──
    
    def get_signals_for(self, target: str, max_count: int = 5) -> List[LearningSignal]:
        """Get recent signals destined for a specific module."""
        relevant = [s for s in self.signals if s.target == target]
        relevant.sort(key=lambda s: s.priority)
        return relevant[:max_count]
    
    def consume(self, signal: LearningSignal):
        """Mark signal as consumed (removed from queue)."""
        if signal in self.signals:
            self.signals.remove(signal)
    
    def get_profile_adjustment(self) -> dict:
        """Profile module calls this to learn from recent signals."""
        signals = self.get_signals_for("profile", max_count=10)
        adjustments = {"trust_delta": 0.0, "patterns": [], "corrections": self.correction_count}
        
        for s in signals:
            if s.signal_type == "correction":
                adjustments["trust_delta"] -= 0.02  # Trust decreases with corrections
            elif s.signal_type == "quality_feedback":
                if s.payload.get("good"):
                    adjustments["trust_delta"] += 0.01
                else:
                    adjustments["trust_delta"] -= 0.03
            elif s.signal_type == "pattern_found":
                adjustments["patterns"].append(s.payload.get("pattern", ""))
        
        # Clamp
        adjustments["trust_delta"] = max(-0.1, min(0.1, adjustments["trust_delta"]))
        return adjustments
    
    def get_meta_review_needed(self) -> bool:
        """Should Meta Cognitive module run a review now?"""
        return (self.correction_count >= 3 or 
                self.drift_detected or 
                len(self.behavior_patterns) >= 5)
    
    # ── Internal ──
    
    def _emit(self, signal: LearningSignal):
        self.signals.append(signal)
        logger.debug("Learning signal: %s→%s (%s) p=%d",
                    signal.source, signal.target, signal.signal_type, signal.priority)
    
    @property
    def pending_count(self) -> int:
        return len(self.signals)
