"""MemoryPoint extraction from dialogue tree turns.

Design: docs/DESIGN_SPECIFICATION.md §5.4 (capacitor model)
         docs/blog/chapter1_design_thinking.md §七

Extracts MemoryPoints from conversation turns with:
  - importance: topic_weight * engagement_signals
  - emotion_polarity: rule-based Chinese sentiment
  - marginal_weight: emotion_intensity * importance
  - activation_count: capacitor model (1 per turn, boosted on access)

Wired into the engine: after each turn, extract → store in CognitiveProfileV2.
"""
from __future__ import annotations
import re, time, math
from typing import List, Optional, Tuple
from collections import Counter

from core.agent.v4.cognitive.models import MemoryPoint


class MemoryExtractor:
    """Extract MemoryPoints from dialogue turn data.

    Computes importance and emotional polarity from text,
    stores as capacitor-based MemoryPoints.
    """

    # Positive sentiment keywords (Chinese + English)
    POSITIVE = re.compile(
        r'(很棒|不错|好的|感谢|谢谢|对了|可以|很好|完美|nice|great|thanks|good|'
        r'cool|awesome|excellent|确实|没错|正解|解决了|有用|帮助)',
        re.IGNORECASE,
    )
    NEGATIVE = re.compile(
        r'(不对|错了|不行|不是|不好|糟糕|差|失败|错误|误导|不清楚|不理解|'
        r'wrong|bad|fails?|error|broken|bug|confus|mislea)',
        re.IGNORECASE,
    )
    QUESTION = re.compile(r'[?？]|[为什么|怎么|如何|什么是|能不能|可以吗]')

    # Topic importance boost words
    IMPORTANCE_BOOST = re.compile(
        r'(必须|重要|关键|核心|一定要|务必|critical|important|essential|must|'
        r'架构|设计|算法|原理|性能|安全)',
        re.IGNORECASE,
    )

    def extract(self, user_text: str, system_response: str = "",
                turn_number: int = 1, topic_weights: dict = None,
                corrections: int = 0) -> Optional[MemoryPoint]:
        """Extract a MemoryPoint from one dialogue turn.

        Returns None if the turn contains no significant content.
        """
        if not user_text or len(user_text.strip()) < 3:
            return None

        # Importance: topic weight + engagement signals
        importance = self._compute_importance(user_text, system_response,
                                               topic_weights, corrections)

        # Emotional polarity
        polarity = self._compute_polarity(user_text, system_response)

        # Marginal weight: intensity * importance
        intensity = self._compute_intensity(user_text, system_response, polarity)
        marginal_weight = intensity * importance

        # Topic tags
        tags = self._extract_topic_tags(user_text, system_response)

        point = MemoryPoint(
            point_id=f"mp_{turn_number}_{int(time.time() * 1000)}",
            timestamp=time.time(),
            content=user_text[:200],
            activation_count=1,
            importance=importance,
            emotion_polarity=polarity,
            topic_tags=tags,
        )
        # Capacitor: marginal_weight sets initial charge
        point.marginal_weight = marginal_weight

        return point

    def extract_from_history(self, turns: List[Tuple[str, str, int]],
                             topic_weights: dict = None
                             ) -> List[MemoryPoint]:
        """Batch extract from a list of (user_text, system_response, turn_number)."""
        points = []
        for user, sys_r, tn in turns:
            mp = self.extract(user, sys_r, tn, topic_weights)
            if mp:
                points.append(mp)
        return points

    # ── Internal ──

    def _compute_importance(self, user_text: str, system_response: str,
                            topic_weights: dict = None, corrections: int = 0) -> float:
        """Importance = topic_weight + engagement + boost_words.
        Scale: [0.1, 1.0]. Default 0.3 for normal turns.
        """
        base = 0.3

        # Topic weight contribution (0-0.3)
        if topic_weights:
            # Check if any important topic words appear in user text
            matched_count = sum(
                1 for topic, weight in topic_weights.items()
                if topic.lower() in user_text.lower()
            )
            if matched_count > 0:
                base += min(0.3, matched_count * 0.1)

        # Boost words (+0.2)
        boost_count = len(self.IMPORTANCE_BOOST.findall(user_text))
        base += min(0.2, boost_count * 0.05)

        # Correction penalty: corrections reduce importance (user correcting = topic unclear)
        if corrections > 0:
            base -= min(0.2, corrections * 0.05)

        # Question signal: asking questions = engaged (+0.1)
        if self.QUESTION.search(user_text):
            base += 0.1

        # Response length: longer responses = more substantive (+0.1)
        if len(system_response) > 200:
            base += 0.1

        return max(0.1, min(1.0, base))

    def _compute_polarity(self, user_text: str, system_response: str) -> float:
        """Emotion polarity: [-1, 1]. Rule-based Chinese sentiment.

        Positive words → +1, negative → -1. Combined text gives weighted score.
        """
        combined = user_text + " " + system_response
        pos_count = len(self.POSITIVE.findall(combined))
        neg_count = len(self.NEGATIVE.findall(combined))

        if pos_count == 0 and neg_count == 0:
            return 0.0  # neutral

        total = pos_count + neg_count
        return (pos_count - neg_count) / max(1, total)

    def _compute_intensity(self, user_text: str, system_response: str,
                           polarity: float, ) -> float:
        """Emotion intensity: [0, 1]. Sharp polarity = higher intensity.

        Also boosted by text length (more words = more emotional content).
        """
        # Base: absolute polarity
        intensity = abs(polarity)

        # Boost from question marks and exclamation
        q_count = user_text.count('?') + user_text.count('？')
        e_count = user_text.count('!') + user_text.count('！')
        intensity += min(0.3, (q_count + e_count) * 0.05)

        # Boost from text length (longer = more engagement)
        text_len = len(user_text)
        if text_len > 50:
            intensity += 0.1
        if text_len > 200:
            intensity += 0.1

        return max(0.0, min(1.0, intensity))

    def _extract_topic_tags(self, user_text: str, system_response: str) -> List[str]:
        """Extract topic tags from turn text. Simple keyword-based."""
        tags = set()
        combined = user_text.lower() + " " + system_response.lower()

        # Common technical topic patterns
        patterns = [
            (r'context.?compiler', 'ContextCompiler'),
            (r'domain.?selector', 'DomainSelector'),
            (r'budget.?allocat', 'BudgetAllocator'),
            (r'behavior.?graph', 'BehaviorGraph'),
            (r'causal.?substrate', 'CausalSubstrate'),
            (r'topic.?tree', 'TopicTree'),
            (r'memory.?compiler', 'MemoryCompiler'),
            (r'planning.?skill', 'PlanningSkill'),
            (r'hypothesis.?engine', 'HypothesisEngine'),
            (r'cognitive.?profile', 'CognitiveProfile'),
            (r'discourse.?block', 'DiscourseBlock'),
            (r'context.?ir', 'ContextIR'),
        ]

        for pat, tag in patterns:
            if re.search(pat, combined):
                tags.add(tag)

        return list(tags)[:5]


class MemoryManager:
    """Capacitor-based memory management.

    Links: Dialogue Tree → MemoryPoints → CognitiveProfileV2.
    """

    def __init__(self, profile=None):
        self._profile = profile
        self._extractor = MemoryExtractor()

    def set_profile(self, profile):
        self._profile = profile

    def ingest_turn(self, user_text: str, system_response: str,
                    turn_number: int, topic_weights: dict = None,
                    corrections: int = 0) -> Optional[MemoryPoint]:
        """Extract and store a MemoryPoint for this turn."""
        if self._profile is None:
            return None

        point = self._extractor.extract(
            user_text, system_response, turn_number,
            topic_weights, corrections,
        )
        if point:
            # Capacitor: initial access
            self._profile.memory_points.append(point)
            # Limit to last 500 points
            if len(self._profile.memory_points) > 500:
                self._profile.memory_points = self._profile.memory_points[-500:]
        return point

    def activate(self, point_id: str) -> bool:
        """Access a memory point — capacitor charges up."""
        for mp in self._profile.memory_points:
            if mp.point_id == point_id:
                mp.access()
                return True
        return False

    def get_relevant(self, query: str, top_k: int = 5) -> List[MemoryPoint]:
        """Retrieve top-k memory points by relevance to query."""
        if not self._profile or not self._profile.memory_points:
            return []

        query_lower = query.lower()
        scored = []
        for mp in self._profile.memory_points:
            # Simple keyword overlap score
            overlap = sum(1 for word in query_lower.split() if word in mp.content.lower())
            # Boost high-importance, high-activation points
            score = overlap * mp.weight * 0.5 + mp.importance * 0.3 + min(1.0, mp.activation_count * 0.02)
            if score > 0:
                scored.append((mp, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [mp for mp, _ in scored[:top_k]]

    def persist(self, store) -> bool:
        """Persist memory points to ProfileStore (SQLite).

        The capacitor model survives session boundaries:
        activation_count carries forward, naturally favoring
        frequently-accessed memories across sessions.
        """
        if not self._profile:
            return False
        return store.save(self._profile)

    def restore(self, store, user_id: str, session_id: str = "") -> bool:
        """Restore memory points from ProfileStore.

        Merges cross-session memory points into current profile.
        """
        restored = store.load(user_id, session_id)
        if restored and restored.memory_points:
            # Merge: keep current + restored, deduplicate by content
            existing_contents = {mp.content[:100] for mp in self._profile.memory_points}
            for mp in restored.memory_points:
                key = mp.content[:100]
                if key not in existing_contents:
                    self._profile.memory_points.append(mp)
                    existing_contents.add(key)
            # Keep most recent 500
            self._profile.memory_points.sort(key=lambda x: x.timestamp, reverse=True)
            self._profile.memory_points = self._profile.memory_points[:500]
            return True
        return False
