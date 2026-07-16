"""Document Ingestion Layer — package init."""
from .tree import DocumentNode, make_node_id, DocumentTree, Relation
from .observation import DocumentObservation, DocumentObservationBundle
from .parsers import DocumentParser, MarkdownParser
from .extractor import ObservationExtractor
# NOTE: DocumentIngestionPipeline is imported from .pipeline directly to avoid
# circular import with chunking.strategies.

__all__ = [
    "DocumentNode",
    "make_node_id",
    "DocumentTree",
    "Relation",
    "DocumentObservation",
    "DocumentObservationBundle",
    "DocumentParser",
    "MarkdownParser",
    "ObservationExtractor",
    # "DocumentIngestionPipeline",  # import from .pipeline directly
]
