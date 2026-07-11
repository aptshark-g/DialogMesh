"""EngineeringChain persistence to UnifiedGraphStore."""
from __future__ import annotations
import logging
from typing import List
from core.agent.persistence.unified_graph_store import UnifiedGraphStore
from .models import Artifact, KnowledgeNode, ArtifactType, Source, KnowledgeType, Lifecycle

logger = logging.getLogger(__name__)

class EngineeringChainPersistence:

    def __init__(self, store: UnifiedGraphStore, session_id: str = "default"):
        self._store = store
        self._session_id = session_id

    def save_artifact(self, art: Artifact):
        self._store.save_node(
            node_id=art.id, node_type="artifact", domain="E",
            session_id=self._session_id,
            data={"name": art.name, "atype": art.atype.value,
                  "type_confidence": art.type_confidence,
                  "source": art.source.value, "status": art.status},
            summary=f"{art.atype.value}: {art.name}",
            importance=0.5 if art.source.value == "core" else 0.3)

    def load_artifacts(self) -> List[Artifact]:
        rows = self._store.load_nodes_by_session(self._session_id, domain="E")
        result = []
        for row in rows:
            if row["node_type"] != "artifact": continue
            d = row["data"]
            result.append(Artifact(
                id=row["node_id"], name=d["name"],
                atype=ArtifactType(d.get("atype", "Module")),
                type_confidence=d.get("type_confidence", 1.0),
                source=Source(d.get("source", "manual")),
                status=d.get("status", {}),
            ))
        return result

    def save_knowledge(self, node: KnowledgeNode):
        self._store.save_node(
            node_id=node.id, node_type=node.ktype.value, domain="E",
            session_id=self._session_id,
            data={"name": node.name, "description": node.description,
                  "source": node.source.value,
                  "lifecycle": node.lifecycle.value,
                  "binds_to_type": node.binds_to_type.value if node.binds_to_type else None,
                  "template": node.template, "impact": node.impact,
                  "evidence": node.evidence},
            summary=f"{node.ktype.value}: {node.name}",
            importance=0.6 if node.source.value == "core" else 0.4,
            source_events=node.evidence)
