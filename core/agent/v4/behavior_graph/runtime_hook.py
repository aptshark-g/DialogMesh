"""BehaviorGraph runtime integration: hooks into CognitiveRuntimeEngine.

Provides:
    - BehaviorGraphRuntimeHook: callable for engine lifecycle events
    - register_with_engine(): one-line integration into existing engine

NOTE: Uses TYPE_CHECKING to avoid circular import with engine.py.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from core.agent.v4.event_ir import EventIR
from core.agent.v4.behavior_graph.adapter import BehaviorGraphAdapter
from core.agent.v4.behavior_graph.causal_adapter import CausalSubstrateAdapter

if TYPE_CHECKING:
    from core.agent.v4.runtime.engine import CognitiveRuntimeEngine

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
    ):
        self._engine = engine
        self._behavior = behavior_adapter or BehaviorGraphAdapter(graph_path=graph_path)
        self._causal = causal_adapter or CausalSubstrateAdapter(self._behavior)
        self._enable_causal = enable_causal_on_checkpoint
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
        return {
            "causal_insights": causal_results,
            "behavior_stats": self._behavior.stats(),
            "event_count": self._event_count,
        }

    def on_session_end(self) -> None:
        try:
            self._behavior.save()
            logger.info("BehaviorGraph persisted on session end")
        except Exception as e:
            logger.warning("BehaviorGraph session-end save failed: %s", e)

    def stats(self) -> Dict[str, Any]:
        return {
            "behavior": self._behavior.stats(),
            "causal": self._causal.stats(),
            "events_recorded": self._event_count,
        }

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
):
    return BehaviorGraphRuntimeHook(
        engine=engine,
        graph_path=graph_path,
        enable_causal_on_checkpoint=enable_causal,
    )
