"""Dual-Track Intent Pipeline — hot path subgraph + cold path meta-cognition.

Hot (<1s):   Subgraph summary → single LLM → intent split
Cold (bg):   Multi-perspective → L2.5 belief → HeuristicChain → optimizes hot path
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Unified intent pipeline result."""
    is_multi: bool
    segments: List[str] = field(default_factory=list)
    confidence: float = 0.0
    source: str = ""           # "hot_single" | "hot_heuristic" | "cold_multiperspective"
    latency_ms: float = 0.0
    cold_enqueued: bool = False  # was multi-perspective triggered?


class DualTrackIntentPipeline:
    """Hot path for speed, cold path for accuracy. Cold path optimizes hot path.

    Usage:
        pipeline = DualTrackIntentPipeline(
            llm=deepseek,
            belief_acc=L2_5_accumulator,
            compressor=derivation_compressor,
        )
        result = pipeline.process("先定位延迟然后修复", profile=..., association=..., history=...)
    """

    def __init__(self, llm=None, belief_acc=None, compressor=None):
        self.llm = llm
        self.belief = belief_acc
        self.compressor = compressor  # DerivationCompressor

        from .multi_intent_splitter import MultiIntentSplitter
        from .multi_perspective import MultiPerspectiveAnalyzer
        from .ambiguity_bridge import IntentAmbiguityResolver

        self._splitter = MultiIntentSplitter(llm=llm)
        self._analyzer = MultiPerspectiveAnalyzer(llm=llm)
        self._bridge = IntentAmbiguityResolver(llm=llm, belief_acc=belief_acc) if belief_acc else None

        # Track cold path triggers
        self._cold_trigger_count = 0
        self._hot_cache: Dict[str, PipelineResult] = {}

    def process(self, text: str, profile: dict = None,
                association: dict = None, history: List[str] = None) -> PipelineResult:
        """Hot path: fast single LLM. Trigger cold path when confidence is low."""
        t0 = time.time()

        # ── Check heuristic cache first ──
        if self.compressor:
            cached = self._check_heuristic_cache(text)
            if cached:
                return PipelineResult(
                    is_multi=cached.is_multi,
                    segments=cached.segments,
                    confidence=cached.confidence,
                    source="hot_heuristic",
                    latency_ms=(time.time() - t0) * 1000,
                )

        # ── Hot path: single LLM split ──
        result = self._splitter.split(text, history=history or [])
        latency = (time.time() - t0) * 1000

        hot_result = PipelineResult(
            is_multi=result.is_multi,
            segments=[si.text for si in result.sub_intents],
            confidence=result.split_confidence,
            source="hot_single",
            latency_ms=latency,
        )

        # ── Trigger cold path if confidence is low ──
        if result.split_confidence < 0.7 and self.llm:
            self._enqueue_cold_path(text, profile, association, history)
            hot_result.cold_enqueued = True

        return hot_result

    def _check_heuristic_cache(self, text: str) -> Optional[PipelineResult]:
        """Check if compressor has a high-coverage heuristic for this text."""
        if not self.compressor:
            return None
        chain = self.compressor.best_chain()
        if chain and chain.coverage > 0.7:
            # Heuristic chain exists and is reliable → use cached pattern
            return PipelineResult(
                is_multi=True,
                segments=[text],  # heuristic won't have segments, fallback later
                confidence=chain.coverage,
                source="hot_heuristic",
            )
        return None

    def _enqueue_cold_path(self, text: str, profile: dict,
                           association: dict, history: list):
        """Trigger cold path: multi-perspective → belief → compression."""
        self._cold_trigger_count += 1

        # Only run cold path every N triggers (avoid thrashing)
        if self._cold_trigger_count % 3 != 0:
            return

        try:
            # Multi-perspective analysis
            result = self._analyzer.analyze(
                text, profile=profile, association=association, history=history
            )

            # Feed into DerivationCompressor as state transitions
            if self.compressor:
                from ..cognitive.derivation_compressor import StateTransition
                for a in result.analyses:
                    self.compressor._transition_buffer.append(StateTransition(
                        from_state="unknown",
                        to_state="multi" if result.is_multi else "single",
                        evidence_type="multi_perspective",
                        entities=[text[:30]],
                        confidence=a.confidence,
                    ))

                # Trigger compression if enough transitions accumulated
                if self.compressor.should_compress():
                    transitions = self.compressor._transition_buffer[:]
                    guesses = self.compressor.diverge(transitions)
                    verified = self.compressor.converge(transitions, guesses, "")
                    chain = self.compressor.heuristic(transitions, verified, f"intent_{int(time.time())}")
                    if chain:
                        self.compressor.pool.append(chain)
                        logger.info("Cold path: new heuristic chain %s (pool=%d)",
                                   chain.chain_id, len(self.compressor.pool))
        except Exception as e:
            logger.debug("Cold path failed: %s", e)

    def status(self) -> dict:
        """Pipeline status for monitoring."""
        best = self.compressor.best_chain() if self.compressor else None
        return {
            "hot_cache_size": len(self._hot_cache),
            "cold_triggers": self._cold_trigger_count,
            "compressor_pool": len(self.compressor.pool) if self.compressor else 0,
            "best_coverage": best.coverage if best else 0,
        }
