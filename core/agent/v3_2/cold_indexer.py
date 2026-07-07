"""ColdIndexer - Layer 3 cold storage for BehaviorGraph edges.
Stores edge meta-data (keywords, summary, profile_bias) after activation-based pruning.
Supports keyword search, reconstruction to full BehaviorEdge via flat data provider."""

from dataclasses import dataclass, field
from typing import Optional, Callable
import time


@dataclass
class ColdEdgeRecord:
    """A cooled-down edge record in Layer 3 cold index."""
    edge_id: str
    from_summary: str
    to_summary: str
    keywords: list = field(default_factory=list)
    profile_bias: float = 0.0
    activation_history: int = 0
    last_active: float = 0.0


class ColdIndexer:
    """Layer 3 cold index for behavior graph edges.
    
    Stores meta-data for edges that have been pruned from the active BehaviorGraph.
    Supports keyword-based search and full reconstruction via flat data provider.
    Thresholds with anchor + range for online adaptation.
    """
    
    MAX_RECORDS = 5000          # anchor
    MAX_RECORDS_RANGE = (2000, 10000)
    RECALL_TOP_K = 3            # anchor
    RECALL_TOP_K_RANGE = (2, 5)
    
    def __init__(self, max_records=None):
        self.max_records = max_records or self.MAX_RECORDS
        self.records: dict[str, ColdEdgeRecord] = {}
    
    def store(self, edge, keywords=None):
        """Move an edge to cold index. Preserves meta-data, drops full weight/samples."""
        if edge.edge_id in self.records:
            return
        if len(self.records) >= self.max_records:
            stalest = min(self.records.values(), key=lambda r: r.last_active)
            del self.records[stalest.edge_id]
        kw = keywords or self._extract_keywords(edge)
        self.records[edge.edge_id] = ColdEdgeRecord(
            edge_id=edge.edge_id,
            from_summary=getattr(edge, 'action_summary', str(edge.from_step_id)),
            to_summary=getattr(edge, 'to_summary', str(edge.to_step_id)),
            keywords=kw,
            profile_bias=0.0,
            activation_history=getattr(edge, 'activation_count', 0),
            last_active=time.time(),
        )
    
    def _extract_keywords(self, edge):
        words = []
        fs = getattr(edge, 'action_summary', '')
        if fs:
            words.extend(fs.lower().split())
        ts = getattr(edge, 'to_summary', '')
        if ts:
            words.extend(ts.lower().split())
        return list(set(words))[:10]
    
    def search(self, query_tokens: set, top_k=None) -> list:
        """Search cold index by keyword overlap. Returns matching records."""
        k = top_k or self.RECALL_TOP_K
        scored = []
        for rec in self.records.values():
            overlap = len(query_tokens & set(rec.keywords))
            if overlap > 0:
                scored.append((rec, overlap + rec.profile_bias * 0.3))
        scored.sort(key=lambda x: -x[1])
        return [r for r, _ in scored[:k]]
    
    def recall(self, record: ColdEdgeRecord, full_data_provider: Callable):
        """Reconstruct a full BehaviorEdge from cold record + flat data provider."""
        from .behavior_graph.models import BehaviorEdge
        flat = full_data_provider(record.edge_id)
        if not flat:
            return None
        return BehaviorEdge(
            edge_id=record.edge_id,
            from_step_id=flat.get('from_step_id', ''),
            to_step_id=flat.get('to_step_id', ''),
            weight=0.5,
            activation_count=record.activation_history,
            importance=0.5,
            sample_count=1,
        )
    
    def compute_importance_from_profile(self, action_type: str, profile) -> float:
        """Compute profile-weighted importance for this action type."""
        if not profile or not hasattr(profile, 'traits'):
            return 0.0
        base = 0.5
        td = getattr(profile.traits, 'technical_depth', {}).get('value', 0.0) if hasattr(profile, 'traits') else 0.0
        if td > 0.6 and any(k in action_type.lower() for k in ['debug', 'scan', 'config']):
            base += 0.2
        verb = getattr(profile, 'verbosity', 0.5)
        if verb > 0.7:
            base += 0.1
        return min(1.0, base)
    
    def get_stats(self) -> dict:
        return {'records': len(self.records), 'max': self.max_records}
