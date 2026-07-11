"""Artifact registry: register, unregister, query modules by type."""
from __future__ import annotations
import logging, uuid
from typing import Dict, List, Optional
from .models import Artifact, ArtifactType, Source
from .type_system import TypeRegistry

logger = logging.getLogger(__name__)


class ArtifactRegistry:

    def __init__(self, monitor=None, persistence=None):
        self._artifacts: Dict[str, Artifact] = {}
        self._type_registry = TypeRegistry()
        self._monitor = monitor
        self._persistence = persistence

    def register(self, name: str, atype: Optional[ArtifactType] = None,
                 status: Optional[Dict[str, str]] = None) -> Artifact:
        aid = f"artifact_{uuid.uuid4().hex[:8]}"
        art = Artifact(id=aid, name=name, atype=atype or ArtifactType.MODULE,
                       status=status or {})
        self._type_registry.register(art, explicit_type=atype)
        self._artifacts[aid] = art
        if self._persistence:
            self._persistence.save_artifact(art)
        if self._monitor:
            self._monitor.record("artifact_registry", "register",
                                 {"id": aid, "name": name, "type": art.atype.value})
        return art

    def get(self, artifact_id: str) -> Optional[Artifact]:
        return self._artifacts.get(artifact_id)

    def find_by_type(self, target: ArtifactType) -> List[Artifact]:
        ids = self._type_registry.find_by_type(target)
        return [self._artifacts[aid] for aid in ids if aid in self._artifacts]

    def update_status(self, artifact_id: str, key: str, value: str):
        if artifact_id in self._artifacts:
            self._artifacts[artifact_id].status[key] = value
