"""Learning ingestion pipeline — search → fetch → embed → store.

Extensible: implement SearchSource → SourceRegistry.register().
"""

from core.agent.learning.sources import SearchSource, ArxivSource, DuckDuckGoSource, ScholarSource, GitHubSource
from core.agent.learning.source_registry import SourceRegistry
from core.agent.learning.content_fetcher import ContentFetcher
from core.agent.learning.embedder import Embedder
from core.agent.learning.credibility import CredibilityEvaluator
from core.agent.learning.ingestion import IngestionPipeline
