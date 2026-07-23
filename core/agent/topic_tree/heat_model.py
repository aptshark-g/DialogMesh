"""Topic Tree — Adaptive Heat Model (ARC-inspired + topology-weighted).

Replaces simple exponential decay with:
  T1 list: recently touched (recency → conversation flow)
  T2 list: frequently revisited (frequency → long-term importance)
  Adaptive balance between T1/T2 based on user behavior pattern
  Topology boost: siblings of active node get priority
  Correction-aware: corrected branches deprioritized
"""

from __future__ import annotations
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
import time, logging

logger = logging.getLogger(__name__)


@dataclass
class HeatEntry:
    node_id: str
    touches: int = 0
    last_touch: float = 0.0
    in_t2: bool = False  # promoted to frequency list
    correction_penalty: float = 0.0  # decreases heat when corrected
    topology_boost: float = 1.0  # multiplier for being near active node


class AdaptiveHeatModel:
    """ARC-like adaptive replacement + topology awareness.
    
    T1 (recency): OrderedDict — recently touched, conversation flow.
    T2 (frequency): OrderedDict — frequently revisited, long-term importance.
    
    Adaptive balance:
      - corrections → T2 weight↓, T1 weight↑ (recent context matters more)
      - stable conversation → T2 weight↑, T1 weight↓ (long-term patterns)
    """
    
    MAX_T1 = 20  # recency list cap
    MAX_T2 = 15  # frequency list cap
    PROMOTE_THRESHOLD = 3  # touches to promote from T1→T2
    
    def __init__(self):
        self.T1: OrderedDict[str, HeatEntry] = OrderedDict()  # recency
        self.T2: OrderedDict[str, HeatEntry] = OrderedDict()  # frequency
        self._all: Dict[str, HeatEntry] = {}
        self.t1_weight: float = 0.5  # adaptive: 0=all T2, 1=all T1
        self.correction_count: int = 0
        self.branch_switches: int = 0
    
    def touch(self, node_id: str):
        """Record access — updates both recency and frequency counts."""
        t = time.time()
        
        if node_id in self._all:
            entry = self._all[node_id]
            entry.touches += 1
            entry.last_touch = t
        else:
            entry = HeatEntry(node_id=node_id, touches=1, last_touch=t)
            self._all[node_id] = entry
        
        # Move to front of T1 (recency)
        if node_id in self.T1:
            del self.T1[node_id]
        self.T1[node_id] = entry
        
        # Evict if T1 too large
        while len(self.T1) > self.MAX_T1:
            oldest = next(iter(self.T1))
            del self.T1[oldest]
        
        # Promote to T2 if frequently touched
        if entry.touches >= self.PROMOTE_THRESHOLD and not entry.in_t2:
            entry.in_t2 = True
            if node_id in self.T2:
                del self.T2[node_id]
            self.T2[node_id] = entry
            while len(self.T2) > self.MAX_T2:
                oldest = next(iter(self.T2))
                self._all[oldest].in_t2 = False
                del self.T2[oldest]
        
        # Adaptive balance: corrections → favor T1 (recent context)
        if self.correction_count > 0:
            self.t1_weight = min(0.8, 0.5 + self.correction_count * 0.1)
    
    def on_correction(self, node_id: str):
        """User corrected — penalize this node and its branch."""
        if node_id in self._all:
            self._all[node_id].correction_penalty += 0.3
            # Demote from T2 if present
            if node_id in self.T2:
                del self.T2[node_id]
                self._all[node_id].in_t2 = False
        self.correction_count += 1
        self.t1_weight = min(0.8, 0.5 + self.correction_count * 0.1)
    
    def on_branch_switch(self):
        """Topic switched — recent context becomes less reliable."""
        self.branch_switches += 1
        # T1 becomes slightly less trusted after branch switch
        self.t1_weight = max(0.3, self.t1_weight - 0.05)
    
    def set_topology_boost(self, node_id: str, boost: float):
        """Node is near active node — boost its effective heat."""
        if node_id in self._all:
            self._all[node_id].topology_boost = max(1.0, boost)
    
    def get_heat(self, node_id: str) -> float:
        """Effective heat score: ARC composite × topology boost × correction penalty."""
        if node_id not in self._all:
            return 0.0
        
        e = self._all[node_id]
        
        # ARC composite score
        t1_score = 1.0 if node_id in self.T1 else 0.0
        t2_score = 1.0 if e.in_t2 else 0.0
        arc_score = self.t1_weight * t1_score + (1 - self.t1_weight) * t2_score
        
        # Frequency bonus
        freq_bonus = min(e.touches / 10.0, 1.0)
        
        # Composite
        heat = (arc_score * 0.5 + freq_bonus * 0.3 + (1.0 - e.correction_penalty) * 0.2)
        heat *= e.topology_boost
        
        return max(0.0, min(1.0, heat))
    
    def hot_nodes(self, limit: int = 10) -> List[str]:
        """Return nodes sorted by effective heat (user channel)."""
        scored = [(nid, self.get_heat(nid)) for nid in self._all]
        scored.sort(key=lambda x: -x[1])
        return [nid for nid, _ in scored[:limit] if _ > 0.1]
    
    def topology_critical(self, active_node: str, neighbors: List[str]) -> List[str]:
        """System channel: topology-critical nodes regardless of heat."""
        # Boost neighbors
        for nid in neighbors:
            if nid != active_node:
                self.set_topology_boost(nid, 2.0)
        
        # Return neighbors sorted by their position × base heat
        scored = []
        for nid in neighbors:
            base_heat = self.get_heat(nid)
            # Topology boost already applied via set_topology_boost
            scored.append((nid, self._all[nid].topology_boost * base_heat if nid in self._all else 0.0))
        
        scored.sort(key=lambda x: -x[1])
        return [nid for nid, _ in scored if _ > 0.05]
    
    @property
    def t1_size(self) -> int:
        return len(self.T1)
    
    @property
    def t2_size(self) -> int:
        return len(self.T2)
    
    def stats(self) -> dict:
        return {
            "t1_size": len(self.T1), "t2_size": len(self.T2),
            "t1_weight": round(self.t1_weight, 2),
            "corrections": self.correction_count,
            "switches": self.branch_switches,
            "total_nodes": len(self._all),
        }
