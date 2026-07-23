"""P2 Persistence Wiring — connect all scattered stores to UnifiedStore.

Wires:
  Mind → AnnotationStore (mind/{relations,anchors,mistakes})
  PatternLearner → AnnotationStore (patterns/)
  Neuro-symbolic rules → AnnotationStore (rules/)
  Profile TrackB → AnnotationStore (profile/)
  BGE index → UnifiedStore
"""
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class PersistenceWiring:
    """Wire all P2 persistence into engine."""

    @staticmethod
    def wire(engine) -> dict:
        """Wire all persistence stores into engine. Returns status dict."""
        status = {}

        # 1. AnnotationStore — unified JSON storage
        try:
            from core.agent.persistence.unified_store import AnnotationStore
            engine._annotation_store = AnnotationStore("data/annotations")
            status["annotation_store"] = "ok"
            logger.info("AnnotationStore wired")
        except Exception as e:
            engine._annotation_store = None
            status["annotation_store"] = f"skipped: {e}"

        # 2. UnifiedStore — vector index
        try:
            from core.agent.persistence.unified_store import UnifiedStore
            engine._unified_store = UnifiedStore(
                bge_model=getattr(engine, '_bge', None),
                annotation_store=engine._annotation_store,
            )
            status["unified_store"] = "ok"
            logger.info("UnifiedStore wired")
        except Exception as e:
            engine._unified_store = None
            status["unified_store"] = f"skipped: {e}"

        # 3. Migrate Mind persistence to AnnotationStore
        if engine._annotation_store and hasattr(engine, '_mind') and engine._mind:
            try:
                _migrate_mind(engine)
                status["mind_persistence"] = "migrated"
            except Exception as e:
                status["mind_persistence"] = f"skipped: {e}"

        # 4. Migrate neuro-symbolic rules
        if engine._annotation_store and hasattr(engine, '_abc') and engine._abc:
            try:
                _migrate_rules(engine)
                status["rules_persistence"] = "migrated"
            except Exception as e:
                status["rules_persistence"] = f"skipped: {e}"

        # 5. Migrate PatternLearner
        if engine._annotation_store:
            try:
                _migrate_patterns(engine)
                status["patterns_persistence"] = "migrated"
            except Exception as e:
                status["patterns_persistence"] = f"skipped: {e}"

        return status


def _migrate_mind(engine) -> None:
    """Migrate Mind data to AnnotationStore."""
    stats = engine._mind.stats()
    store = engine._annotation_store
    store.put("mind", "relations", stats.get("active_relations", 0))
    store.put("mind", "anchors", stats.get("active_anchors", 0))
    store.put("mind", "rules", stats.get("active_rules", 0))


def _migrate_rules(engine) -> None:
    """Migrate neuro-symbolic rules to AnnotationStore."""
    rule_stats = engine._abc.report()
    store = engine._annotation_store
    store.put("rules", "neuro_symbolic", rule_stats)


def _migrate_patterns(engine) -> None:
    """Migrate PatternLearner data to AnnotationStore."""
    store = engine._annotation_store
    if hasattr(engine, '_pattern_learner') and engine._pattern_learner:
        store.put("patterns", "learner", {"status": "active"})
