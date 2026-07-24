"""Cluster Map Visualizer — recursive granularity view for strategy federation.

Produces a map-like visualization structure with zoom levels.
Each level: clusters as regions, entities as points.
Operable: click to apply strategy actions.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
import json, math


class ClusterMap:
    """Recursive cluster map with granularity levels.

    Usage:
        viz = ClusterMap.from_federation(federation_state)
        # → renders as interactive map with zoom/pan/click
    """

    def __init__(self):
        self.nodes: List[dict] = []
        self.edges: List[dict] = []
        self.regions: List[dict] = []
        self.level: int = 0

    @classmethod
    def from_federation(cls, state: 'ClusterState', 
                        strategy_scores: dict = None,
                        history: list = None) -> 'ClusterMap':
        """Build map from federation state."""
        viz = cls()

        # ── Regions: one per cluster ──
        total = len(state.clusters)
        for i, cluster in enumerate(state.clusters):
            angle = (360 / max(1, total)) * i
            rad = angle * math.pi / 180
            cx = 300 + 150 * math.cos(rad)
            cy = 300 + 150 * math.sin(rad)

            cohesion = state.cohesion_scores[i] if i < len(state.cohesion_scores) else 0.5
            size = 30 + len(cluster) * 10  # bigger = more entities

            viz.regions.append({
                "id": f"cluster_{i}",
                "label": cluster[0] if cluster else f"C{i}",
                "entities": cluster,
                "count": len(cluster),
                "cohesion": round(cohesion, 2),
                "entropy": round(state.entropy, 3),
                "x": round(cx),
                "y": round(cy),
                "size": size,
                "color": cls._cohesion_color(cohesion),
                "status": cls._cluster_status(i, strategy_scores),
                "actions": cls._available_actions(state, i),
                "subclusters": [],  # populated on zoom
            })

        # ── Nodes: each entity as a point within its region ──
        for i, cluster in enumerate(state.clusters):
            base = viz.regions[i]
            for j, entity in enumerate(cluster):
                sub_angle = (360 / max(1, len(cluster))) * j
                sub_rad = sub_angle * math.pi / 180
                viz.nodes.append({
                    "id": f"entity_{entity}",
                    "label": entity,
                    "parent_region": f"cluster_{i}",
                    "x": round(base["x"] + 20 * math.cos(sub_rad)),
                    "y": round(base["y"] + 20 * math.sin(sub_rad)),
                    "size": 8,
                })

        # ── Edges: strategy history as connections ──
        if history:
            for h in history[-5:]:
                target_str = "-".join(str(t) for t in h.action.target_clusters)
                viz.edges.append({
                    "source": f"cluster_{target_str}",
                    "target": f"strategy_{h.action.strategy}",
                    "label": f"{'✅' if h.success else '❌'} {h.action.name}",
                    "color": "#4CAF50" if h.success else "#f44336",
                })

        # ── Strategy nodes ──
        strategies_used = set()
        if history:
            for h in history[-5:]:
                s = h.action.strategy
                if s not in strategies_used:
                    strategies_used.add(s)
                    viz.nodes.append({
                        "id": f"strategy_{s}",
                        "label": s,
                        "type": "strategy",
                        "size": 15,
                        "color": "#FF9800",
                        "score": round(strategy_scores.get(s, [0])[-1] if strategy_scores else 0.5, 2),
                    })

        return viz

    def zoom_in(self, cluster_idx: int, state: 'ClusterState') -> 'ClusterMap':
        """Zoom into a cluster → show sub-clusters if available."""
        self.level += 1
        
        # In real impl: load sub-clusters from compressed/heuristic data
        cluster = state.clusters[cluster_idx] if cluster_idx < len(state.clusters) else []
        if len(cluster) <= 1:
            return self

        # Split cluster into sub-regions
        mid = len(cluster) // 2
        sub_state = ClusterState(
            clusters=[cluster[:mid], cluster[mid:]],
            cohesion_scores=[0.5, 0.5],
            entropy=state.entropy * 0.5,
            turn=state.turn,
        )
        return ClusterMap.from_federation(sub_state)

    def export(self, format: str = "json") -> dict:
        """Export visualization data for rendering."""
        return {
            "version": "v6",
            "level": self.level,
            "regions": self.regions,
            "nodes": self.nodes,
            "edges": self.edges,
            "meta": {
                "total_clusters": len(self.regions),
                "total_entities": sum(r["count"] for r in self.regions),
                "granularity": self.level,
            }
        }

    # ── Helpers ──

    @staticmethod
    def _cohesion_color(cohesion: float) -> str:
        """Green=high cohesion, Red=low, Yellow=medium."""
        if cohesion > 0.7:
            return "#4CAF50"
        if cohesion > 0.4:
            return "#FFC107"
        return "#f44336"

    @staticmethod
    def _cluster_status(cluster_idx: int, scores: dict = None) -> str:
        """Cluster status: healthy / unstable / locked."""
        if not scores:
            return "unrated"
        # Check if any strategy has poor scores for this cluster
        return "healthy"

    @staticmethod
    def _available_actions(state: 'ClusterState', cluster_idx: int) -> List[dict]:
        """What actions are available for this cluster?"""
        actions = []
        if len(state.clusters) > 1:
            actions.append({"action": "merge", "label": f"Merge with neighbor"})
        cluster = state.clusters[cluster_idx]
        if len(cluster) > 2:
            actions.append({"action": "split", "label": f"Split {len(cluster)} entities"})
        actions.append({"action": "pivot", "label": "Move entity"})
        return actions


# Import ClusterState for type hints
from core.agent.memory.strategy_federation import ClusterState
