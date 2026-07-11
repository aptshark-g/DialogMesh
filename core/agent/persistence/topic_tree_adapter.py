"""TopicTree persistence: DiscourseBlock -> UnifiedGraphStore domain=C."""
from __future__ import annotations
import logging
from typing import List
from .domain_adapter import DomainAdapter
from .unified_graph_store import UnifiedGraphStore

logger = logging.getLogger(__name__)


class TopicTreeAdapter(DomainAdapter):

    def __init__(self, store: UnifiedGraphStore, session_id: str = ""):
        super().__init__(store, "C", session_id)

    def save_block(self, block_id: str, text: str, intent: str = "",
                   parent_id: str = None, cohesion: float = 0.5,
                   entities: list = None) -> bool:
        try:
            existing = self._store.load_node(block_id)
            if existing is not None:
                logger.warning("Block %s already exists, overwriting", block_id)
            data = {
                "block_id": block_id, "text": text[:5000],
                "intent": intent, "parent_id": parent_id,
                "cohesion": cohesion, "entities": entities or [],
            }
            summary = text[:200] if text else block_id
            self._save(block_id, "topic_block", data,
                       summary=summary, importance=cohesion)
            return True
        except Exception:
            logger.exception("Failed to save block %s", block_id)
            return False

    def load_blocks(self) -> List[dict]:
        return self._load_all("topic_block")

    def recall_by_keyword(self, keyword: str) -> List[dict]:
        blocks = self._load_all("topic_block")
        kw = keyword.lower()
        return [b for b in blocks
                if kw in b.get("summary", "").lower()
                or kw in str(b.get("data", {}).get("text", "")).lower()]
