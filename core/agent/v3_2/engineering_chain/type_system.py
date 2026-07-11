"""Artifact type registry with is_a hierarchy and type inference."""
from __future__ import annotations
import logging
from typing import Dict, List, Optional, Set
from .models import ArtifactType, Artifact, ARTIFACT_TREE, is_a, Source

logger = logging.getLogger(__name__)


class TypeRegistry:

    def __init__(self):
        self._types: Dict[str, ArtifactType] = {}

    def register(self, artifact: Artifact, explicit_type: Optional[ArtifactType] = None) -> ArtifactType:
        inferred = explicit_type or self._infer(artifact)
        self._types[artifact.id] = inferred
        return inferred

    def get(self, artifact_id: str) -> Optional[ArtifactType]:
        return self._types.get(artifact_id)

    def find_by_type(self, target: ArtifactType) -> List[str]:
        return [aid for aid, at in self._types.items() if is_a(at, target)]

    def _infer(self, artifact: Artifact) -> ArtifactType:
        name_lower = artifact.name.lower()
        if "provider" in name_lower: return ArtifactType.PROVIDER
        if "middleware" in name_lower: return ArtifactType.MIDDLEWARE
        if "controller" in name_lower: return ArtifactType.CONTROLLER
        if "service" in name_lower: return ArtifactType.SERVICE
        if "repository" in name_lower: return ArtifactType.REPOSITORY
        if "config" in name_lower: return ArtifactType.CONFIG
        if "pipeline" in name_lower: return ArtifactType.PIPELINE
        if "database" in name_lower or "db" in name_lower: return ArtifactType.DATABASE
        if "tool" in name_lower: return ArtifactType.TOOL
        if "api" in name_lower: return ArtifactType.API
        return ArtifactType.MODULE

    def add_custom_type(self, name: str, parent: ArtifactType = ArtifactType.ARTIFACT):
        pass  # placeholder: extend enum at runtime via Knowledge Graph
