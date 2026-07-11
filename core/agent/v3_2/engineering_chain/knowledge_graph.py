"""Engineering Knowledge Graph: Constraints, Patterns, Decisions, Quality, AntiPatterns."""
from __future__ import annotations
import logging, uuid
from typing import Dict, List, Optional
from .models import KnowledgeNode, KnowledgeType, ArtifactType, Source, Lifecycle

logger = logging.getLogger(__name__)


class KnowledgeGraph:

    def __init__(self, monitor=None, persistence=None):
        self._nodes: Dict[str, KnowledgeNode] = {}
        self._by_type: Dict[KnowledgeType, List[str]] = {kt: [] for kt in KnowledgeType}
        self._by_artifact_type: Dict[str, List[str]] = {}
        self._monitor = monitor
        self._persistence = persistence
        self._init_presets()

    def _init_presets(self):
        self._add("Every Provider must expose Metrics", KnowledgeType.CONSTRAINT,
                   binds_to=ArtifactType.PROVIDER,
                   evidence=["OpenAIProvider", "ClaudeProvider"], src=Source.CORE)
        self._add("Every Middleware must be placed after RateLimit",
                   KnowledgeType.CONSTRAINT, binds_to=ArtifactType.MIDDLEWARE,
                   evidence=["AuthMiddleware", "LoggerMiddleware"], src=Source.CORE)
        self._add("Every Service must have tests", KnowledgeType.CONSTRAINT,
                   binds_to=ArtifactType.SERVICE, src=Source.CORE)
        self._add("Plugin Pattern: Interface + Factory + Registry + Lifecycle",
                   KnowledgeType.PATTERN, template=["Interface","Factory","Registry","Lifecycle"],
                   src=Source.CORE)
        self._add("Middleware Pattern: Config + Metrics + Health + Retry",
                   KnowledgeType.PATTERN, template=["Config","Metrics","Health","Retry"],
                   src=Source.CORE)
        self._add("Controller must NOT directly access Database",
                   KnowledgeType.ANTIPATTERN,
                   binds_to=ArtifactType.CONTROLLER, src=Source.CORE)
        self._add("Quality: Performance baseline",
                   KnowledgeType.QUALITY,
                   binds_to=ArtifactType.ARTIFACT,
                   impact={"performance": 0.0, "complexity": 0.0, "reliability": 0.0},
                   src=Source.CORE)

    def _add(self, name: str, ktype: KnowledgeType, binds_to: Optional[ArtifactType]=None,
             template: List[str]=None, evidence: List[str]=None,
             impact: dict = None, src: Source=Source.MANUAL) -> KnowledgeNode:
        nid = f"kn_{uuid.uuid4().hex[:8]}"
        node = KnowledgeNode(id=nid, ktype=ktype, name=name, source=src,
                             binds_to_type=binds_to, template=template or [],
                             evidence=evidence or [], lifecycle=Lifecycle.VERIFIED_LC,
                             impact=impact or {})
        self._nodes[nid] = node
        self._by_type[ktype].append(nid)
        if binds_to:
            key = binds_to.value
            self._by_artifact_type.setdefault(key, []).append(nid)
        if self._persistence:
            self._persistence.save_knowledge(node)
        if self._monitor:
            self._monitor.record("knowledge_graph", "add",
                                 {"id": nid, "name": name, "type": ktype.value})
        return node

    def add(self, name: str, ktype: KnowledgeType,
            binds_to: Optional[ArtifactType]=None,
            template: List[str]=None,
            impact: Dict[str,float]=None) -> KnowledgeNode:
        return self._add(name, ktype, binds_to, template, src=Source.MANUAL)

    def get_by_type(self, ktype: KnowledgeType) -> List[KnowledgeNode]:
        return [self._nodes[nid] for nid in self._by_type.get(ktype, [])]

    def get_constraints_for(self, atype: ArtifactType) -> List[KnowledgeNode]:
        from .models import is_a
        result = []
        seen = set()
        for nid_list in self._by_artifact_type.values():
            for nid in nid_list:
                node = self._nodes[nid]
                if nid in seen: continue
                if node.ktype in (KnowledgeType.CONSTRAINT, KnowledgeType.RULE):
                    if node.binds_to_type and is_a(atype, node.binds_to_type):
                        result.append(node)
                        seen.add(nid)
        return result

    def get_pattern_for(self, operation: str) -> Optional[KnowledgeNode]:
        patterns = self.get_by_type(KnowledgeType.PATTERN)
        for p in patterns:
            if operation.lower() in p.name.lower():
                return p
        return patterns[0] if patterns else None

    def get_anti_patterns(self) -> List[KnowledgeNode]:
        return self.get_by_type(KnowledgeType.ANTIPATTERN)
