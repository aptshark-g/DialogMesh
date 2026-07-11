"""Adapters for BehaviorGraph(B), UserProfile(P), CausalSubstrate(K)."""
from __future__ import annotations
import logging
from typing import Any, Dict, List
from .domain_adapter import DomainAdapter
from .unified_graph_store import UnifiedGraphStore

logger = logging.getLogger(__name__)


class BehaviorAdapter(DomainAdapter):

    def __init__(self, store: UnifiedGraphStore, session_id: str = ""):
        super().__init__(store, "B", session_id)

    def save_step(self, step_id: str, action: str, context: str = "",
                  confidence: float = 0.5, metadata: dict = None) -> bool:
        try:
            data = {"step_id": step_id, "action": action, "context": context,
                    "confidence": confidence, "metadata": metadata or {}}
            self._save(step_id, "behavior_step", data,
                       summary=f"{action}: {context[:100]}",
                       importance=confidence)
            return True
        except Exception:
            logger.exception("Failed to save behavior step %s", step_id)
            return False

    def save_edge(self, edge_id: str, source_id: str, target_id: str,
                  weight: float = 1.0, metadata: dict = None) -> bool:
        try:
            self._save(edge_id, "behavior_edge",
                       {"source_id": source_id, "target_id": target_id,
                        "weight": weight, "metadata": metadata or {}},
                       summary=f"B:{source_id}->{target_id}",
                       importance=weight)
            return True
        except Exception:
            logger.exception("Failed to save behavior edge %s", edge_id)
            return False

    def load_steps(self) -> List[dict]:
        return self._load_all("behavior_step")

    def recent_actions(self, limit: int = 10) -> List[dict]:
        steps = self.load_steps()
        return steps[:limit]


class UserProfileAdapter(DomainAdapter):

    def __init__(self, store: UnifiedGraphStore, session_id: str = ""):
        super().__init__(store, "P", session_id)

    def save_dimension(self, dim_id: str, name: str, value: float | str,
                       confidence: float = 0.5) -> bool:
        try:
            self._save(dim_id, "profile_dim",
                       {"name": name, "value": value, "confidence": confidence},
                       summary=f"Profile.{name}={value}",
                       importance=confidence)
            return True
        except Exception:
            logger.exception("Failed to save profile dimension %s", dim_id)
            return False

    def load_dimensions(self) -> List[dict]:
        return self._load_all("profile_dim")


class CausalAdapter(DomainAdapter):

    def __init__(self, store: UnifiedGraphStore, session_id: str = ""):
        super().__init__(store, "K", session_id)

    def save_causal_edge(self, edge_id: str, cause: str, effect: str,
                         confidence: float = 0.5, skeleton: str = "") -> bool:
        try:
            self._save(edge_id, "causal_edge",
                       {"cause": cause, "effect": effect,
                        "confidence": confidence, "skeleton": skeleton},
                       summary=f"{cause} -> {effect}",
                       importance=confidence)
            return True
        except Exception:
            logger.exception("Failed to save causal edge %s", edge_id)
            return False

    def load_causal_edges(self) -> List[dict]:
        return self._load_all("causal_edge")
