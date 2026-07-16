"""DocumentDomainAdapter: bridge DocumentObservationBundle into ObservationCompiler.

Design: v4 adapter layer — does NOT modify v3_2 code.
Flow:
    DocumentObservationBundle → DomainObservation → ObservationCompiler.compile()

This adapter allows the existing ObservationCompiler to process document-derived
observations without knowing about documents.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from core.agent.v4.observation_compiler.models import (
    ObservationBundle,
    DomainObservation,
    ObservationEvent,
)

from core.agent.v4.document.observation import DocumentObservationBundle

logger = logging.getLogger(__name__)


class DocumentDomainAdapter:
    """Adapter that converts DocumentObservationBundle into ObservationBundle
    and feeds it into the existing ObservationCompiler pipeline.

    Usage:
        adapter = DocumentDomainAdapter(compiler)
        adapter.ingest(bundle)   # bundle is DocumentObservationBundle
    """

    def __init__(self, compiler=None):
        self._compiler = compiler

    def ingest(self, bundle: DocumentObservationBundle) -> Optional[ObservationBundle]:
        """Convert and optionally compile a DocumentObservationBundle.

        Args:
            bundle: The document observation bundle to adapt.

        Returns:
            The standard ObservationBundle (if compiler is None),
            or the result of compiler.compile() (if compiler is set).
        """
        try:
            obs_bundle = bundle.to_observation_bundle()
        except Exception as e:
            logger.warning("DocumentDomainAdapter failed to convert bundle: %s", e)
            return None

        if self._compiler is not None:
            try:
                return self._compiler.compile(obs_bundle)
            except Exception as e:
                logger.warning("DocumentDomainAdapter compiler failed: %s", e)
                return obs_bundle
        return obs_bundle

    def to_domain_observation(self, bundle: DocumentObservationBundle) -> Optional[DomainObservation]:
        """Extract the single DomainObservation for the 'document' domain.

        This is useful for direct insertion into domain-specific pipelines.
        """
        try:
            obs_bundle = bundle.to_observation_bundle()
            return obs_bundle.domain_observations.get("document")
        except Exception as e:
            logger.warning("DocumentDomainAdapter to_domain_observation failed: %s", e)
            return None

    def publish_event(self, bundle: DocumentObservationBundle) -> None:
        """Publish an ObservationEvent that downstream modules can subscribe to."""
        event = ObservationEvent(
            kind="bundle_complete",
            bundle_id=bundle.bundle_id,
            domain="document",
            observation_id=None,
            interpretation_id=None,
            timestamp=bundle.created_at,
        )
        # If compiler has a pool with subscribers, publish there
        if self._compiler is not None:
            pool = getattr(self._compiler, "pool", None)
            if pool is not None and hasattr(pool, "publish"):
                try:
                    pool.publish(event)
                except Exception as e:
                    logger.warning("Failed to publish document event: %s", e)
