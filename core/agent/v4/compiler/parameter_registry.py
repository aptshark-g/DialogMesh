"""ParameterRegistry — soft-coded configuration for DialogMesh v4.

Design: All tunable thresholds, confidence floors, TTLs, and
strategy weights live here as a soft-coded registry, not as
hardcoded values in individual modules.

Inspired by: Cortex Parameter Registry (PARAMETER_REGISTRY.md)
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class ParamDef:
    key: str
    value: Any
    type: str          # "float" | "int" | "bool" | "str" | "list"
    description: str
    vmin: Optional[float] = None
    vmax: Optional[float] = None
    adaptive: bool = False


class ParameterRegistry:
    """Central soft-coded configuration store.

    Usage:
        reg = ParameterRegistry()
        reg.load_defaults()
        min_c = reg.get("relation.min_confidence_edge")
        reg.set("relation.min_confidence_edge", 0.25)
    """

    def __init__(self):
        self._params: Dict[str, ParamDef] = {}

    def load_defaults(self):
        """Load all default parameters."""
        defaults = self._defaults()
        for key, value, typ, desc, vmin, vmax, adaptive in defaults:
            self._params[key] = ParamDef(
                key=key, value=value, type=typ,
                description=desc, vmin=vmin, vmax=vmax,
                adaptive=adaptive,
            )

    def get(self, key: str, default: Any = None) -> Any:
        p = self._params.get(key)
        return p.value if p else default

    def set(self, key: str, value: Any) -> bool:
        p = self._params.get(key)
        if not p:
            return False
        if p.vmin is not None and isinstance(value, (int, float)) and value < p.vmin:
            return False
        if p.vmax is not None and isinstance(value, (int, float)) and value > p.vmax:
            return False
        p.value = value
        return True

    def all(self, prefix: str = "") -> Dict[str, Any]:
        return {k: p.value for k, p in self._params.items()
                if k.startswith(prefix)}

    # ---- Defaults ----

    @staticmethod
    def _defaults():
        return [
            ("relation.min_confidence_edge", 0.15, "float", "Min confidence to create a RelationEdge", 0.0, 1.0, True),
            ("relation.min_confidence_reference", 0.5, "float", "Min confidence for reference upgrade", 0.0, 1.0, True),
            ("relation.min_confidence_dependency", 0.7, "float", "Min confidence for dependency upgrade", 0.0, 1.0, True),
            ("relation.min_confidence_causal", 0.8, "float", "Min confidence for causal mechanism generation", 0.0, 1.0, True),
            ("relation.min_evidence_sources_causal", 2, "int", "Min different evidence sources for causal upgrade", 1, 5, False),
            ("behavior.default_confidence", 0.2, "float", "Default confidence for behavioral observations", 0.0, 1.0, True),
            ("behavior.ttl_seconds", 300, "int", "TTL for behavioral edges in seconds", 60, 3600, False),
            ("behavior.decay_rate", 0.05, "float", "Decay rate for behavioral edges", 0.0, 0.5, False),
            ("heading.contains_confidence", 0.4, "float", "Confidence for contains edges from heading", 0.0, 1.0, True),
            ("heading.cooccur_confidence", 0.3, "float", "Confidence for co-occurrence edges", 0.0, 1.0, True),
            ("concept_graph.typed_edge_confidence", 0.5, "float", "Confidence for typed edges from ConceptGraph", 0.0, 1.0, True),
            ("resolver.causal_min_confidence", 0.5, "float", "Min confidence for CausalResolver", 0.0, 1.0, True),
            ("resolver.behavior_min_confidence", 0.1, "float", "Min confidence for BehaviorResolver", 0.0, 1.0, True),
            ("rank.reference_evidence_min", 2, "int", "Min evidence for association->reference", 1, 5, False),
            ("rank.dependency_doc_source_needed", True, "bool", "Whether dependency upgrade requires doc evidence", None, None, False),
            ("link.instantiates_weight", 0.8, "float", "Weight for instantiates cross-layer edge", 0.0, 1.0, True),
            ("link.governs_weight", 0.7, "float", "Weight for governs cross-layer edge", 0.0, 1.0, True),
            ("link.described_by_weight", 0.6, "float", "Weight for described_by cross-layer edge", 0.0, 1.0, True),
            ("link.foundational_to_weight", 0.9, "float", "Weight for foundational_to cross-layer edge", 0.0, 1.0, True),
            ("slow_path.event_threshold", 5, "int", "Events before Slow Path triggers (velocity-adjusted)", 2, 50, False),
            ("slow_path.velocity_window", 30, "int", "Velocity measurement window (seconds)", 10, 300, False),
            ("slow_path.min_text_length", 30, "int", "Min text length for extraction (elastic: half for CamelCase)", 10, 200, False),
        ]
