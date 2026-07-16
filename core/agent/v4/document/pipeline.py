"""DocumentIngestionPipeline: orchestrate document → ObservationPool flow.

Flow:
    1. Detect file type → select Parser.
    2. Parser.parse() → DocumentNode tree.
    3. ChunkStrategySelector.select() → ChunkStrategy.
    4. Apply chunking per node.
    5. ObservationExtractor.extract() per node.
    6. Bundle → ObservationPool.put().
"""
from __future__ import annotations
import logging
import os
import uuid
from typing import List, Optional

from core.agent.v4.observation_compiler.pool import ObservationPool

from .tree import DocumentNode, DocumentTree
from .parsers import DocumentParser, MarkdownParser
from .extractor import ObservationExtractor
from .observation import DocumentObservation, DocumentObservationBundle
from ..chunking.strategies import ChunkStrategyRegistry, RuntimeConstraints, TaskContext, default_registry

logger = logging.getLogger(__name__)


class DocumentIngestionPipeline:
    """Orchestrate the ingestion of external documents into the cognitive chain.

    Args:
        pool: ObservationPool to deposit bundles into.
        parser: Optional custom parser. Defaults to MarkdownParser.
        registry: Optional ChunkStrategyRegistry. Defaults to built-in registry.
        extractor: Optional ObservationExtractor. Defaults to standard extractor.
    """

    def __init__(
        self,
        pool: Optional[ObservationPool] = None,
        parser: Optional[DocumentParser] = None,
        registry: Optional[ChunkStrategyRegistry] = None,
        extractor: Optional[ObservationExtractor] = None,
    ):
        self._pool = pool
        self._parser = parser or MarkdownParser()
        self._registry = registry or default_registry()
        self._extractor = extractor or ObservationExtractor()

    def ingest_file(
        self,
        file_path: str,
        event_id: str = "",
        constraints: Optional[RuntimeConstraints] = None,
    ) -> DocumentObservationBundle:
        """Ingest a single file into the cognitive chain.

        Returns:
            DocumentObservationBundle (also put into ObservationPool if pool is set).
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.warning("Failed to read %s: %s", file_path, e)
            return DocumentObservationBundle(
                bundle_id=f"doc_bundle_err_{uuid.uuid4().hex[:8]}",
                event_id=event_id or f"ingest_err_{uuid.uuid4().hex[:8]}",
                source_path=file_path,
                observations=[],
            )

        return self.ingest_text(
            content=content,
            source_path=file_path,
            event_id=event_id,
            constraints=constraints,
        )

    def ingest_text(
        self,
        content: str,
        source_path: str,
        event_id: str = "",
        constraints: Optional[RuntimeConstraints] = None,
    ) -> DocumentObservationBundle:
        """Ingest raw text (already read) into the cognitive chain.

        This is the core method; ingest_file() is a thin wrapper around it.
        """
        event_id = event_id or f"ingest_{uuid.uuid4().hex[:8]}"
        constraints = constraints or RuntimeConstraints()

        # 1. Parse → DocumentNode tree
        try:
            root = self._parser.parse(content, source_path)
        except Exception as e:
            logger.warning("Parser failed for %s: %s", source_path, e)
            root = DocumentNode(
                node_id=f"err_{uuid.uuid4().hex[:8]}",
                source_path=source_path,
                raw_text=content,
                node_type="paragraph",
            )

        tree = DocumentTree(root)

        # 2. Select chunk strategy
        context = TaskContext(
            file_type="markdown" if source_path.endswith(".md") else "text",
            doc_size_chars=len(content),
            doc_depth=tree.stats().get("max_level", 0),
            urgency="normal",
            quality_target="balanced",
        )
        strategy = self._registry.select(context, constraints)
        logger.info("Ingesting %s with strategy=%s", source_path, strategy.name)

        # 3. Chunk + Extract observations
        all_observations: List[DocumentObservation] = []
        for node in tree.all_nodes():
            try:
                # Apply chunking
                result = strategy.apply(node)
                nodes_to_extract = result.nodes

                # Extract observations from each chunk
                for chunk_node in nodes_to_extract:
                    observations = self._extractor.extract(chunk_node, event_id=event_id)
                    all_observations.extend(observations)
            except Exception as e:
                logger.warning("Chunk/extract failed for node %s: %s", node.node_id, e)

        # 4. Build bundle
        bundle = DocumentObservationBundle.from_observations(
            source_path=source_path,
            observations=all_observations,
            event_id=event_id,
        )

        # 5. Put into ObservationPool
        if self._pool is not None:
            try:
                obs_bundle = bundle.to_observation_bundle()
                self._pool.put(obs_bundle)
                logger.info("Put bundle %s into ObservationPool (%d observations)",
                            bundle.bundle_id, len(bundle.observations))
            except Exception as e:
                logger.warning("Failed to put bundle into ObservationPool: %s", e)

        return bundle

    def ingest_directory(
        self,
        dir_path: str,
        pattern: str = "*.md",
        constraints: Optional[RuntimeConstraints] = None,
    ) -> List[DocumentObservationBundle]:
        """Ingest all matching files in a directory.

        Returns:
            List of DocumentObservationBundle, one per file.
        """
        import fnmatch
        bundles: List[DocumentObservationBundle] = []
        for root, _dirs, files in os.walk(dir_path):
            for filename in files:
                if fnmatch.fnmatch(filename, pattern):
                    file_path = os.path.join(root, filename)
                    bundle = self.ingest_file(file_path, constraints=constraints)
                    bundles.append(bundle)
        logger.info("Ingested %d files from %s", len(bundles), dir_path)
        return bundles
