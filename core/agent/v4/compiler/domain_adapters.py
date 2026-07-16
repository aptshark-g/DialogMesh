"""Topic + Behavior context adapters for v4 ContextAssembler.

Design refs:
  docs/v3.0/DESIGN_INTERACTION_MODEL.md — Conversation Projection
  docs/v3.0/DESIGN_FULL_CONCEPT.md §7 — Cognitive Profile

These are thin adapters: they wrap the existing ConversationTracker
(which already tracks topics and behavior patterns) as ContextSources
that the assembler can route to C (conversation) and B (behavior) domains.
"""
from __future__ import annotations
from typing import List
from core.agent.v4.context.source import ContextSource, ContextItem, _keyword_score
from core.agent.v4.conversation.tracker import ConversationTracker


class TopicContextSource(ContextSource):
    """Provides hierarchical topic context for C (Conversation) domain.

    Wraps ConversationTracker to inject:
      - Current topic + recent subtopics
      - Topic switch boundaries
      - Related past turns by content overlap

    Design: DESIGN_INTERACTION_MODEL.md §2.2 — Conversation Projection
    """

    name = "conversation"

    def __init__(self, tracker: ConversationTracker):
        self._tracker = tracker

    def retrieve(self, query: str, top_k: int = 5,
                 session_id: str = "", **kwargs) -> List[ContextItem]:
        items = []

        # 1. Current topic anchor
        topic = self._tracker.get_current_topic()
        if topic:
            items.append(ContextItem(
                source="conversation",
                content={"type": "current_topic", "topic": topic},
                text=f"[Current Topic] {topic[:200]}",
                relevance=0.9,
            ))

        # 2. Topic boundaries (last 3 switches)
        boundaries = self._tracker.topic_boundaries
        if len(boundaries) >= 1:
            recent = boundaries[-3:]
            items.append(ContextItem(
                source="conversation",
                content={"type": "topic_boundaries", "boundaries": recent},
                text=f"[Topic Structure] {len(boundaries)} topic switches, last at turns {recent}",
                relevance=0.7,
            ))

        # 3. Relevant history (past turns matching current query)
        history = self._tracker.get_history_entries(max_entries=5)
        if history:
            query_words = query.lower().split()
            relevant = []
            for h in history:
                score = _keyword_score(query_words, h["text"].lower())
                if score > 0.15:
                    relevant.append(f"[T{h['turn']}] {h['text'][:150]}")
            if relevant:
                items.append(ContextItem(
                    source="conversation",
                    content={"type": "relevant_history", "turns": relevant},
                    text="[Related History]\n" + "\n".join(relevant[-3:]),
                    relevance=0.6,
                ))

        return items


class BehaviorContextSource(ContextSource):
    """Provides behavior pattern context for B (Behavior) domain.

    Wraps ConversationTracker to inject:
      - Drill-down vs topic-switch pattern detection
      - Conversation pacing (short queries = deep focus, long = exploration)

    Design: DESIGN_FULL_CONCEPT.md §7 — Track A Cognitive Dynamics
    """

    name = "behavior"

    def __init__(self, tracker: ConversationTracker):
        self._tracker = tracker

    def retrieve(self, query: str, top_k: int = 5,
                 session_id: str = "", **kwargs) -> List[ContextItem]:
        items = []
        patterns = self._tracker.behavior_pattern

        if not patterns:
            return items

        # Behavior mode detection
        drill_count = sum(1 for p in patterns[-4:] if p == "drill_down")
        switch_count = sum(1 for p in patterns[-4:] if p == "switch")

        mode = "deep_focus" if drill_count >= 3 else (
            "exploring" if switch_count >= 2 else "mixed"
        )

        mode_descriptions = {
            "deep_focus": "User is drilling deep into current topic — prioritize depth over breadth",
            "exploring": "User is switching topics — provide overviews with jump-off points",
            "mixed": "User is alternating — balance detail with context",
        }

        items.append(ContextItem(
            source="behavior",
            content={"type": "behavior_mode", "mode": mode, "patterns": patterns[-4:]},
            text=f"[Behavior] Mode: {mode} — {mode_descriptions.get(mode, '')}",
            relevance=0.8,
        ))

        # Conversation pacing hint (for LLM response style)
        items.append(ContextItem(
            source="behavior",
            content={"type": "pacing", "drill": drill_count, "switch": switch_count},
            text=f"[Pacing] Recent: {drill_count}× drill-down, {switch_count}× switch",
            relevance=0.5,
        ))

        return items
