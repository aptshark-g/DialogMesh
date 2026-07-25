"""Cognition Integration — HypothesisEngine + BeliefAccumulator bridge.

Connects the v4 Hypothesis Engine (Match→Vote→Decay→Resolve) into the
Cognition.Converge phase of the pipeline.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class CognitionHub:
    """Unified cognition layer — HypothesisEngine + BeliefAccumulator + RelationExtractor.

    Usage:
        hub = CognitionHub()
        hub.ingest_relations([rel1, rel2, ...])
        hub.converge()  # runs Match→Vote→Decay→Resolve
        beliefs = hub.get_active_beliefs()
    """

    def __init__(self):
        self._hypothesis_engine = None
        self._belief_accumulator = None
        self._relation_extractor = None
        self._relations_buffer: List[Dict] = []
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._loaded = True

        try:
            from core.agent.hypothesis.pipeline import HypothesisPipeline
            self._hypothesis_engine = HypothesisPipeline()
        except Exception:
            logger.debug("HypothesisPipeline not available")

        try:
            from core.agent.association.l2_5_belief import BeliefAccumulator
            self._belief_accumulator = BeliefAccumulator()
        except Exception:
            logger.debug("BeliefAccumulator not available (already in pipeline)")

        try:
            from core.agent.compiler.llm_relation_extractor import RelationClusterer
            self._relation_extractor = RelationClusterer()
        except Exception:
            logger.debug("RelationClusterer not available")

    @property
    def is_loaded(self) -> bool:
        self._ensure_loaded()
        return self._hypothesis_engine is not None

    def ingest_relations(self, relations: List[Dict]):
        """Feed relations from Association funnel into hypothesis buffer."""
        self._relations_buffer.extend(relations)
        self._ensure_loaded()

    def converge(self) -> Dict:
        """Run convergence: Match→Vote→Decay→Resolve.

        Returns: {active_beliefs, resolved, frozen_knowledge}
        """
        self._ensure_loaded()
        result = {"active_beliefs": [], "resolved": 0, "frozen_knowledge": 0}

        # 1. Run Hypothesis Engine if available
        if self._hypothesis_engine:
            try:
                for rel in self._relations_buffer[-20:]:  # last 20
                    self._hypothesis_engine.ingest(rel)
                self._hypothesis_engine.tick()
                result["resolved"] = getattr(self._hypothesis_engine, 'resolved_count', 0)
                result["frozen_knowledge"] = getattr(self._hypothesis_engine, 'frozen_count', 0)
            except Exception as e:
                logger.debug("HypothesisEngine.converge failed: %s", e)

        # 2. Get active beliefs from BeliefAccumulator
        if self._belief_accumulator:
            try:
                active = getattr(self._belief_accumulator, 'get_active', lambda: [])()
                result["active_beliefs"] = active
            except Exception:
                pass

        # 3. Cluster accumulated predicates
        if self._relation_extractor and self._relations_buffer:
            try:
                from core.agent.compiler.llm_relation_extractor import OpenRelation
                rels = [
                    OpenRelation(
                        identity=r.get("identity", f"rel_{i}"),
                        source=r.get("source", ""), target=r.get("target", ""),
                        predicate=r.get("predicate", ""), confidence=r.get("confidence", 0.5),
                    ) for i, r in enumerate(self._relations_buffer)
                ]
                clusters = self._relation_extractor.cluster(rels)
                result["predicate_clusters"] = len(clusters)
            except Exception:
                pass

        self._relations_buffer.clear()
        return result

    def get_status(self) -> Dict:
        self._ensure_loaded()
        return {
            "hypothesis_engine": self._hypothesis_engine is not None,
            "belief_accumulator": self._belief_accumulator is not None,
            "relation_extractor": self._relation_extractor is not None,
            "buffered_relations": len(self._relations_buffer),
        }
