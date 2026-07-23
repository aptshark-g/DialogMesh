"""Topic Tree Context Assembly — dual perspective + multi-perspective branch + behavior refresh.

Design: docs/v5/TOPIC_TREE_DISCUSSION.md (Q1-Q4 resolved)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
import time, logging
from .fact_store import FactStore, RelationMetadataStore, FactBlock

logger = logging.getLogger(__name__)


@dataclass
class Summary:
    node_id: str
    content: str
    layer: int  # 1=Fine, 2=Medium, 3=Coarse, 4=Root
    token_count: int = 0
    generated_at: float = field(default_factory=time.time)
    dirty: bool = False
    dirty_reason: str = ""


class DualPerspectiveContext:
    """Two parallel context channels: user (temperature) + system (distance)."""
    
    def __init__(self, fact_store: FactStore, relation_store: RelationMetadataStore):
        self.facts = fact_store
        self.relations = relation_store
        self.heat_map: Dict[str, float] = {}  # block_id → heat score
    
    def touch(self, block_id: str):
        """Mark block as accessed — increases temperature."""
        self.heat_map[block_id] = self.heat_map.get(block_id, 0.0) + 1.0
        # Decay others
        for bid in list(self.heat_map):
            if bid != block_id:
                self.heat_map[bid] *= 0.95
    
    def user_channel(self, active_node: str, budget: int) -> List[Summary]:
        """Temperature-driven: hot nodes = user currently cares about."""
        hot = sorted(self.heat_map.items(), key=lambda x: -x[1])
        summaries = []
        for block_id, heat in hot:
            if budget <= 0:
                break
            fact = self.facts.get(block_id)
            if fact:
                s = Summary(node_id=block_id, content=fact.content[:budget], layer=1,
                          token_count=min(len(fact.content), budget))
                summaries.append(s)
                budget -= s.token_count
        return summaries
    
    def system_channel(self, active_node: str, budget: int) -> List[Summary]:
        """Distance-driven: topology-critical nodes regardless of temperature."""
        # Find neighbors of active node via relation store
        neighbors = []
        for key, meta in self.relations._current.items():
            a, b = key.split("::")
            if a == active_node or b == active_node:
                other = b if a == active_node else a
                neighbors.append((other, meta.relation_type))
        
        summaries = []
        for node_id, rel_type in neighbors:
            if budget <= 0:
                break
            fact = self.facts.get(node_id)
            if fact:
                content = f"[{rel_type}] {fact.content[:budget-20]}"
                s = Summary(node_id=node_id, content=content, layer=2,
                          token_count=min(len(content), budget))
                summaries.append(s)
                budget -= s.token_count
        return summaries
    
    def assemble(self, active_node: str, token_budget: int = 2000) -> List[Summary]:
        """50% user channel + 50% system channel."""
        half = token_budget // 2
        return self.user_channel(active_node, half) + self.system_channel(active_node, half)


class MultiPerspectiveBranchView:
    """Collects branch definitions from multiple modules. Does NOT pick sides."""
    
    def __init__(self):
        self._perspectives: Dict[str, Dict[str, dict]] = {}
    
    def register(self, module: str, block_id: str, branch_id: str, reason: str = "", **extra):
        self._perspectives.setdefault(block_id, {})[module] = {
            "branch": branch_id, "reason": reason, **extra
        }
    
    def get_view(self, block_id: str) -> dict:
        """Return multi-perspective view for LLM consumption."""
        views = self._perspectives.get(block_id, {})
        consensus = len(set(v["branch"] for v in views.values())) == 1 if views else True
        return {
            "block_id": block_id,
            "perspectives": views,
            "consensus": consensus,
            "summary": f"{len(views)} modules: {'all agree' if consensus else 'disagree on branch'}",
        }


class BehaviorDrivenRefresh:
    """Controls summary regeneration based on behavior signals."""
    
    def __init__(self):
        self._dirty_blocks: Dict[str, str] = {}  # block_id → dirty_reason
        self._last_refresh: Dict[str, float] = {}  # block_id → timestamp
        self._local_model_available = False
    
    @property
    def local_model_available(self) -> bool:
        return self._local_model_available
    
    def set_local_model(self, available: bool):
        self._local_model_available = available
    
    def on_correction(self, block_id: str, correction: str):
        """P0: User correction — immediate invalidation."""
        self._dirty_blocks[block_id] = f"user_correction: {correction[:50]}"
        logger.info("P0 refresh: block %s corrected", block_id)
    
    def on_topic_switch(self, branch_id: str):
        """P1: Topic switch — mark active branch dirty."""
        self._dirty_blocks[branch_id] = "topic_switch"
    
    def should_refresh(self, block_id: str, layer: int, ttl_rounds: int = 10) -> bool:
        """Returns True if summary should be regenerated."""
        # P0: explicit correction
        if block_id in self._dirty_blocks:
            return True
        
        # P1: local model available → can refresh every turn for L1
        if layer == 1 and self._local_model_available:
            return True
        
        # P2: TTL check
        last = self._last_refresh.get(block_id, 0)
        if last > 0:
            elapsed = time.time() - last
            if elapsed > ttl_rounds * 30:  # ~30s per round
                return True
        
        return False
    
    def mark_refreshed(self, block_id: str):
        self._dirty_blocks.pop(block_id, None)
        self._last_refresh[block_id] = time.time()
