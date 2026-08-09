"""BehaviorGraph runtime integration: hooks into CognitiveRuntimeEngine.

Provides:
    - BehaviorGraphRuntimeHook: callable for engine lifecycle events
    - register_with_engine(): one-line integration into existing engine

NOTE: Uses TYPE_CHECKING to avoid circular import with engine.py.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from core.agent.events.event_ir import EventIR
from core.agent.behavior.adapter import BehaviorGraphAdapter
from core.agent.behavior.causal_adapter import CausalSubstrateAdapter

if TYPE_CHECKING:
    from core.agent.runtime.engine import CognitiveRuntimeEngine

logger = logging.getLogger(__name__)


class BehaviorGraphRuntimeHook:
    """Lifecycle hook integrating BehaviorGraph + CausalSubstrate into v4 runtime."""

    def __init__(
        self,
        engine,
        graph_path: Optional[str] = None,
        behavior_adapter: Optional[BehaviorGraphAdapter] = None,
        causal_adapter: Optional[CausalSubstrateAdapter] = None,
        enable_causal_on_checkpoint: bool = True,
        brain=None,
    ):
        self._engine = engine
        self._behavior = behavior_adapter or BehaviorGraphAdapter(graph_path=graph_path)
        self._causal = causal_adapter or CausalSubstrateAdapter(self._behavior)
        self._enable_causal = enable_causal_on_checkpoint
        self._brain = brain
        self._event_count = 0
        self._inject_into_assembler()
        logger.info(
            "BehaviorGraphRuntimeHook attached: behavior_nodes=%d causal_enabled=%s",
            self._behavior.node_count,
            self._enable_causal,
        )

    @property
    def behavior_adapter(self) -> BehaviorGraphAdapter:
        return self._behavior

    @property
    def causal_adapter(self) -> CausalSubstrateAdapter:
        return self._causal

    def on_event(self, event: EventIR, llm_response: Optional[str] = None) -> None:
        try:
            self._behavior.record_event(event, success=True)
            self._event_count += 1
            if self._brain is not None:
                self._brain.learn_from_event(event)
                self._brain.predict_next_background()
            logger.debug("Event recorded in BehaviorGraph: %s", event.id)
        except Exception as e:
            logger.warning("BehaviorGraph event recording failed: %s", e)

    def on_checkpoint(self, results: Optional[list] = None) -> Dict[str, Any]:
        causal_results = []
        if self._enable_causal:
            try:
                insights = self._causal.process_session_chain()
                causal_results = [
                    {
                        "edge_key": i.edge_key,
                        "structural_prior": i.structural_prior,
                        "confidence": i.confidence,
                    }
                    for i in insights
                ]
                logger.info("Causal analysis on checkpoint: %d insights", len(causal_results))
            except Exception as e:
                logger.warning("Causal analysis on checkpoint failed: %s", e)
        brain_stats = {}
        if self._brain is not None:
            try:
                self._brain.on_checkpoint()
                brain_stats = self._brain.stats()
            except Exception as e:
                logger.warning("BehaviorBrain checkpoint failed: %s", e)
        return {
            "causal_insights": causal_results,
            "behavior_stats": self._behavior.stats(),
            "brain": brain_stats,
            "event_count": self._event_count,
        }

    def on_session_end(self) -> None:
        try:
            self._behavior.save()
            logger.info("BehaviorGraph persisted on session end")
        except Exception as e:
            logger.warning("BehaviorGraph session-end save failed: %s", e)

    def stats(self) -> Dict[str, Any]:
        stats = {
            "behavior": self._behavior.stats(),
            "causal": self._causal.stats(),
            "events_recorded": self._event_count,
        }
        if self._brain is not None:
            stats["brain"] = self._brain.stats()
        return stats

    def _inject_into_assembler(self) -> None:
        assembler = getattr(self._engine, "_context_assembler", None)
        if assembler is None:
            return
        try:
            assembler.add_source(self._behavior)
            assembler.add_source(self._causal)
            logger.debug("BehaviorGraph + CausalSubstrate sources injected")
        except Exception as e:
            logger.warning("Failed to inject behavior sources: %s", e)


def register_with_engine(
    engine,
    graph_path: Optional[str] = "data/behavior_graph.json",
    enable_causal: bool = True,
    llm_provider=None,
):
    hook = BehaviorGraphRuntimeHook(
        engine=engine,
        graph_path=graph_path,
        enable_causal_on_checkpoint=enable_causal,
    )
    # P1: attach the behavior brain as the engine's shared kernel (one brain,
    # multiple facades) so production handlers drive the same instance.
    try:
        from core.agent.behavior.brain import BehaviorBrain
        brain = getattr(engine, '_behavior_brain', None)
        if brain is None:
            brain = BehaviorBrain(
                graph=hook._behavior.graph, llm_provider=llm_provider,
            )
            engine._behavior_brain = brain
        hook._brain = brain
    except Exception as e:
        logger.warning("BehaviorBrain unavailable: %s", e)
    return hook
