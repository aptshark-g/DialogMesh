"""ConversationTracker: multi-dimensional follow-up disambiguation + behavior tracking.

Replaces the naive _enrich_query_with_history() with multi-tier disambiguation:
  Tier 0: Temporal proximity (most recent topic, default)
  Tier 1: Content overlap (keyword/concept match with prior turns)
  Tier 2: Behavior pattern (drill-down vs topic-switch, via CausalPlanner)
  Tier 3: Semantic similarity (BGE embedding, when available)

Also tracks conversation state: turns, topics, and behavior patterns
for CausalPlanner integration.
"""
from __future__ import annotations
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.agent.v4.context.source import _keyword_score

logger = logging.getLogger(__name__)


class ConversationTracker:
    """Tracks conversation turns and resolves follow-up references.

    Key design: follow-up disambiguation is NOT just "prepend prior text."
    It's a multi-dimensional judgment using:
      - Temporal proximity (default: most recent turn)
      - Content overlap (did user reference prior concepts?)
      - Behavior pattern (is user drilling down?)
      - Causal context (does this follow from prior?)

    Usage:
        tracker = ConversationTracker()
        tracker.add_turn("Hypothesis 冻结的流程是什么？", concepts=["Hypothesis","冻结"])
        enriched = tracker.enrich("给我讲一下具体细节")
        # -> "Hypothesis 冻结的流程是什么？"  (resolved to prior topic)
    """

    def __init__(self, max_turns: int = 20):
        self._turns: List[_TurnRecord] = []
        self._max_turns = max_turns
        self._current_topic: Optional[str] = None
        self._topic_boundaries: List[int] = []  # turn indices where topic switched
        self._behavior_patterns: List[str] = []  # ["drill_down","drill_down","switch"]

    def add_turn(self, text: str, concepts: List[str] = None,
                 turn_number: int = 0) -> None:
        """Record a turn with extracted concepts."""
        record = _TurnRecord(
            text=text,
            concepts=concepts or [],
            timestamp=time.time(),
            turn_number=turn_number or len(self._turns) + 1,
        )
        self._turns.append(record)

        # Detect topic boundary
        if len(self._turns) >= 2:
            prior = self._turns[-2]
            overlap = self._content_overlap(record, prior)
            if overlap < 0.15 and len(record.text) > 10:
                self._topic_boundaries.append(len(self._turns) - 1)
                self._current_topic = record.text
                self._behavior_patterns.append("switch")
            else:
                self._behavior_patterns.append("drill_down")
        elif self._turns:
            self._current_topic = text

        # Prune old turns
        if len(self._turns) > self._max_turns:
            self._turns = self._turns[-self._max_turns:]

    def enrich(self, current_text: str) -> str:
        """Enrich a follow-up query by resolving to the correct prior context.

        Multi-tier disambiguation:
          1. If current is short/ambiguous, check temporal proximity first
          2. If temporal match is weak, check content overlap against all prior turns
          3. If behavior pattern suggests topic switch, don't force enrichment

        Returns enriched text or original if no enrichment needed.
        """
        if len(self._turns) < 1:
            return current_text

        # Skip the current turn (it was just added before enrich is called)
        # If the most recent turn matches current_text, look at _turns[-2]
        prior_idx = -2 if (self._turns[-1].text == current_text and len(self._turns) >= 2) else -1
        prior = self._turns[prior_idx]

        is_short = len(current_text) <= 10
        has_follow_marker = any(m in current_text for m in {
            "具体", "详细", "继续", "然后", "还有", "比如", "怎么", "为什么",
            "再", "如何", "说说", "展开", "细说", "再说", "呢", "吗",
        })
        needs_enrichment = is_short or has_follow_marker

        if not needs_enrichment:
            return current_text

        # ---- Tier 0: Temporal proximity (most recent turn) ----
        temporal_score = 0.9  # high weight for most recent

        # ---- Tier 1: Content overlap with current query ----
        query_words = current_text.lower().split()
        prior_words = prior.text.lower().split()
        content_overlap = _keyword_score(query_words, " ".join(prior_words))
        # But we want to measure: does THIS follow-up contain references to prior?
        # Check if prior concepts appear in current text
        prior_ref_score = self._prior_reference_score(current_text, prior)

        # ---- Tier 2: Behavior pattern ----
        # Check recent behavior: drill-down or topic switch?
        recent_patterns = self._behavior_patterns[-3:] if self._behavior_patterns else []
        drill_count = sum(1 for p in recent_patterns if p == "drill_down")
        switch_count = sum(1 for p in recent_patterns if p == "switch")
        # If user has been drilling down, high confidence this is a follow-up
        behavior_score = 0.5 + 0.2 * drill_count - 0.3 * switch_count
        behavior_score = max(0.1, min(1.0, behavior_score))

        # ---- Combined score ----
        combined = 0.4 * temporal_score + 0.3 * content_overlap + 0.3 * behavior_score

        if combined > 0.4:
            # Resolve to prior topic
            if prior_ref_score > 0.3:
                # Current text already references prior — light enrichment
                logger.debug("Light enrichment (ref=%.2f): %s -> %s",
                           prior_ref_score, current_text[:30], prior.text[:60])
                return current_text  # already clear enough
            else:
                # Heavy enrichment: prepend prior topic
                logger.debug("Heavy enrichment (score=%.2f): %s -> %s",
                           combined, current_text[:30], prior.text[:60])
                return f"{prior.text} | {current_text}"
        else:
            # Likely a topic switch — don't force enrichment
            logger.debug("No enrichment (score=%.2f): %s", combined, current_text)
            return current_text

    def get_history_entries(self, max_entries: int = 5) -> List[dict]:
        """Get conversation history entries for context injection."""
        entries = []
        for turn in self._turns[-max_entries:]:
            entries.append({
                "text": turn.text,
                "turn": turn.turn_number,
                "concepts": turn.concepts,
            })
        return entries

    def get_current_topic(self) -> Optional[str]:
        return self._current_topic

    @property
    def topic_boundaries(self) -> List[int]:
        return list(self._topic_boundaries)

    @property
    def behavior_pattern(self) -> List[str]:
        return list(self._behavior_patterns[-10:])

    # ---- Internal ----

    @staticmethod
    def _content_overlap(a: _TurnRecord, b: _TurnRecord) -> float:
        """How much do two turns overlap in content?"""
        if not a.concepts and not b.concepts:
            # Fall back to keyword overlap on full text
            a_words = set(a.text.lower().split())
            b_words = set(b.text.lower().split())
            if not a_words or not b_words:
                return 0.0
            intersection = a_words & b_words
            union = a_words | b_words
            return len(intersection) / max(1, len(union))
        # Concept-based overlap
        a_set = set(c.lower() for c in a.concepts)
        b_set = set(c.lower() for c in b.concepts)
        intersection = a_set & b_set
        return len(intersection) / max(1, min(len(a_set), len(b_set)))

    @staticmethod
    def _prior_reference_score(current: str, prior: _TurnRecord) -> float:
        """Score how much the current text references the prior turn's concepts."""
        if not prior.concepts:
            return 0.0
        current_lower = current.lower()
        hits = sum(1 for c in prior.concepts if c.lower() in current_lower)
        return min(1.0, hits / max(1, len(prior.concepts)))


class _TurnRecord:
    __slots__ = ("text", "concepts", "timestamp", "turn_number")

    def __init__(self, text: str, concepts: List[str], timestamp: float, turn_number: int):
        self.text = text
        self.concepts = concepts
        self.timestamp = timestamp
        self.turn_number = turn_number
