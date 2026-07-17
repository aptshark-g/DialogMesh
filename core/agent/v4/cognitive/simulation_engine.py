"""Internal Simulation Engine — LLM simulates user cognitive state to generate predictions.

Design (from Cognitive Ontology):
  1. Build User Cognitive State from ConversationTree + SemanticWorld
  2. LLM stands INSIDE that state: "If I were this user, what would I ask?"
  3. Generate candidate questions + confidence scores
  4. Self-supervised: when user actually asks simulated question → reward
  5. Learn which simulation strategies work best

This replaces statistical Prediction with Theory-of-Mind simulation.
"""
from __future__ import annotations
import json, re, time, logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SimulationResult:
    """LLM's internal simulation output."""
    simulated_questions: List[str] = field(default_factory=list)
    confidence_scores: List[float] = field(default_factory=list)
    user_cognitive_state: str = ""
    reasoning: str = ""
    strategy: str = "simulation"  # "simulation" | "pattern" | "topic_transition"
    raw_response: str = ""


@dataclass
class SimulationFeedback:
    """Self-supervised feedback when user's actual question arrives."""
    predicted_question: str
    actual_question: str
    matched: bool
    similarity: float  # BGE cosine or token overlap
    confidence_delta: float  # +/- adjustment
    strategy_effectiveness: float  # updated strategy weight


# Prompt templates
SIMULATION_PROMPT = """You are simulating a user's cognitive state to predict their next question.

Current context:
- Last assistant answer: {last_answer}
- User's current understanding: {user_understanding}
- Recent topics discussed: {recent_topics}
- User's cognitive profile: {user_profile}

Task: stand INSIDE the user's mind. Based on what they currently understand and what was just explained, 
what are the 3 most likely questions or topics they would explore next?

Return ONLY this JSON:
{{
  "user_cognitive_state": "what user currently knows and what gaps remain",
  "questions": [
    {{"text": "question 1", "confidence": 0.85, "reason": "why user would ask this"}},
    {{"text": "question 2", "confidence": 0.72, "reason": "why user would ask this"}},
    {{"text": "question 3", "confidence": 0.55, "reason": "why user would ask this"}}
  ],
  "simulation_strategy": "how you arrived at these predictions"
}}

JSON:"""


class InternalSimulationEngine:
    """LLM-driven user simulation for active prediction.

    Usage:
        engine = InternalSimulationEngine(llm_provider)
        sim = engine.simulate(last_answer, user_state, profile)
        # ... user asks something ...
        feedback = engine.evaluate(sim, user_actual_question)
        engine.learn(feedback)  # self-supervised strategy update
    """

    def __init__(self, llm_provider=None):
        self._llm = llm_provider
        self._strategy_weights = {
            "simulation": 0.7,       # LLM stands in user's mind
            "topic_transition": 0.3, # Pattern-based transition
            "gap_filling": 0.5,      # Fill knowledge gaps
        }
        self._prediction_history: List[Tuple[SimulationResult, Optional[SimulationFeedback]]] = []

    def set_llm(self, provider):
        self._llm = provider

    def simulate(
        self,
        last_answer: str,
        user_understanding: str = "",
        recent_topics: List[str] = None,
        user_profile: str = "",
    ) -> SimulationResult:
        """LLM simulates user cognitive state and generates predicted questions.

        Args:
            last_answer: The assistant's most recent response
            user_understanding: What the user currently knows (from KnowledgeSpace)
            recent_topics: Recently discussed topics (from DiscourseTree)
            user_profile: User's cognitive profile (TrackA+TrackB)
        """
        if self._llm is None:
            return self._fallback_simulate(last_answer, recent_topics or [])

        # Build the richest possible prompt
        uu = user_understanding[:500] if user_understanding else "(unknown)"
        rt = ", ".join(recent_topics[:5]) if recent_topics else "(new conversation)"
        la = last_answer[:800]

        prompt = SIMULATION_PROMPT.format(
            last_answer=la,
            user_understanding=uu,
            recent_topics=rt,
            user_profile=user_profile[:300],
        )

        try:
            from core.agent.llm_providers.base import GenerateRequest
            result = self._llm.generate(GenerateRequest(
                prompt=prompt, max_tokens=400, temperature=0.3,
            ))
            text = result.text if hasattr(result, 'text') else str(result)

            # Parse JSON from response
            match = re.search(r'\{[\s\S]*\}', text)
            if not match:
                return self._fallback_simulate(last_answer, recent_topics or [])

            data = json.loads(match.group())
            questions = [q["text"] for q in data.get("questions", [])]
            scores = [q.get("confidence", 0.5) for q in data.get("questions", [])]

            return SimulationResult(
                simulated_questions=questions,
                confidence_scores=scores,
                user_cognitive_state=data.get("user_cognitive_state", ""),
                reasoning=data.get("simulation_strategy", ""),
                strategy="simulation",
                raw_response=text[:300],
            )
        except Exception as e:
            logger.debug("Simulation LLM failed: %s", e)
            return self._fallback_simulate(last_answer, recent_topics or [])

    def _fallback_simulate(self, last_answer: str, recent_topics: List[str]) -> SimulationResult:
        """Topic-transition fallback when LLM unavailable."""
        from core.agent.v4.tiered.jieba_parser import JiebaRelationParser
        parser = JiebaRelationParser()
        entities = parser.extract_relations(last_answer)
        qs = [f"Can you explain more about {e}?" for e in entities[:3]]
        return SimulationResult(
            simulated_questions=qs or ["What else should I know?"],
            confidence_scores=[0.4] * len(qs) if qs else [0.3],
            strategy="topic_transition",
        )

    def evaluate(
        self,
        simulation: SimulationResult,
        user_actual_question: str,
    ) -> SimulationFeedback:
        """Evaluate simulation accuracy when user's actual question arrives.

        Uses BGE semantic similarity to detect partial matches.
        Returns feedback for self-supervised learning.
        """
        best_match = None
        best_similarity = 0.0

        for i, sq in enumerate(simulation.simulated_questions):
            similarity = self._semantic_similarity(sq, user_actual_question)
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = sq

        matched = best_similarity > 0.6  # BGE cosine threshold
        confidence_delta = 0.0
        if matched:
            # Reward proportional to similarity
            confidence_delta = best_similarity * 0.15  # +0.09 to +0.15
        elif simulation.simulated_questions:
            # Penalty: user asked something we didn't predict
            confidence_delta = -0.05

        # Update strategy effectiveness
        strategy = simulation.strategy
        old_weight = self._strategy_weights.get(strategy, 0.5)
        if matched:
            self._strategy_weights[strategy] = min(1.0, old_weight + 0.05)
        else:
            self._strategy_weights[strategy] = max(0.1, old_weight - 0.02)

        return SimulationFeedback(
            predicted_question=best_match or "",
            actual_question=user_actual_question,
            matched=matched,
            similarity=best_similarity,
            confidence_delta=confidence_delta,
            strategy_effectiveness=self._strategy_weights.get(strategy, 0.5),
        )

    def _semantic_similarity(self, text_a: str, text_b: str) -> float:
        """BGE cosine similarity. Falls back to token overlap."""
        try:
            from core.agent.compiler.semantic_encoder import SemanticEncoder
            import numpy as np
            bge = SemanticEncoder()
            va = bge.encode(text_a[:200])
            vb = bge.encode(text_b[:200])
            a = va.flatten() if len(va.shape) > 1 else va
            b = vb.flatten() if len(vb.shape) > 1 else vb
            return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))
        except Exception:
            # Token overlap fallback
            wa = set(text_a.lower().split())
            wb = set(text_b.lower().split())
            return len(wa & wb) / max(1, len(wa | wb))

    def learn(self, feedback: SimulationFeedback):
        """Record feedback for strategy optimization (self-supervised)."""
        self._prediction_history.append((None, feedback))
        if len(self._prediction_history) > 100:
            self._prediction_history = self._prediction_history[-50:]

    def get_strategy_stats(self) -> Dict[str, float]:
        """Return current strategy weights and history size."""
        return {
            "strategy_weights": self._strategy_weights,
            "total_evaluations": len(self._prediction_history),
            "recent_matches": sum(
                1 for _, fb in self._prediction_history[-10:]
                if fb and fb.matched
            ),
        }
