"""Constraint Engine: type matching, anti-pattern detection, query interface."""
from __future__ import annotations
import logging
from typing import Dict, List, Optional
from .models import Artifact, ArtifactEdge, EdgeType, KnowledgeNode, KnowledgeType, EngineeringContext
from .registry import ArtifactRegistry
from .knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)


class ConstraintEngine:

    def __init__(self, registry: ArtifactRegistry, kg: KnowledgeGraph, monitor=None):
        self._registry = registry
        self._kg = kg
        self._monitor = monitor

    def get_constraints_for(self, artifact: Artifact) -> List[KnowledgeNode]:
        constraints = self._kg.get_constraints_for(artifact.atype)
        if self._monitor:
            self._monitor.record("constraint_engine", "get_constraints",
                                 {"artifact": artifact.name,
                                  "constraints": len(constraints)})
        return constraints

    def get_pattern_for(self, operation: str) -> Optional[KnowledgeNode]:
        return self._kg.get_pattern_for(operation)

    def get_impact(self, artifact: Artifact) -> Dict[str, float]:
        from .models import is_a
        quality_nodes = [n for n in self._kg.get_by_type(KnowledgeType.QUALITY)
                         if n.binds_to_type and is_a(artifact.atype, n.binds_to_type)]
        impact = {}
        for qn in quality_nodes:
            for k, v in qn.impact.items():
                impact[k] = impact.get(k, 0.0) + v
        return impact  # placeholder: compute from QualityKnowledge nodes

    def check_anti_patterns(self, proposed_edge: ArtifactEdge) -> List[KnowledgeNode]:
        anti_patterns = self._kg.get_anti_patterns()
        violations = []
        for ap in anti_patterns:
            if ap.binds_to_type:
                source_artifact = self._registry.get(proposed_edge.source_id)
                if source_artifact and source_artifact.is_type(ap.binds_to_type):
                    violations.append(ap)
        if self._monitor and violations:
            self._monitor.record("constraint_engine", "anti_pattern_violation",
                                 {"edge": f"{proposed_edge.source_id}->{proposed_edge.target_id}",
                                  "violations": len(violations)})
        return violations

    def get_related_decisions(self, artifact: Artifact) -> List[KnowledgeNode]:
        decisions = self._kg.get_by_type(KnowledgeType.DECISION)
        return decisions[:3] if decisions else []

    def compile_context(self, artifact: Artifact) -> EngineeringContext:
        return EngineeringContext(
            applicable_constraints=self.get_constraints_for(artifact),
            matched_patterns=[p for p in [self.get_pattern_for("")] if p],
            quality_impact=self.get_impact(artifact),
            violated_anti_patterns=[],
            relevant_decisions=self.get_related_decisions(artifact),
            module_status=artifact.status,
        )
