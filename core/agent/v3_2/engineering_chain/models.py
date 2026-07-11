"""Engineering Chain: Artifact types, Knowledge nodes, Edges, Type tree."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

class Source(Enum):
    MANUAL="manual"; DERIVED="derived"; LEARNED="learned"; VERIFIED="verified"; CORE="core"
def source_confidence(s: Source) -> float:
    return {Source.MANUAL:0.90,Source.DERIVED:0.40,Source.LEARNED:0.30,Source.VERIFIED:0.85,Source.CORE:1.00}[s]

class Lifecycle(Enum):
    CANDIDATE="candidate"; SUGGESTED="suggested"; DERIVED_LC="derived"; VERIFIED_LC="verified"; DRAFT="draft"; CORE_LC="core"; DEPRECATED="deprecated"

class ArtifactType(Enum):
    ARTIFACT="Artifact"; MODULE="Module"; PROVIDER="Provider"; MIDDLEWARE="Middleware"; CONTROLLER="Controller"; SERVICE="Service"; REPOSITORY="Repository"; TOOL="Tool"; CONFIG="Config"; API="API"; PIPELINE="Pipeline"; WORKFLOW="Workflow"; DATABASE="Database"; DIRECTORY="Directory"

ARTIFACT_TREE: Dict[ArtifactType,Optional[ArtifactType]]={ArtifactType.ARTIFACT:None,ArtifactType.MODULE:ArtifactType.ARTIFACT,ArtifactType.PROVIDER:ArtifactType.MODULE,ArtifactType.MIDDLEWARE:ArtifactType.MODULE,ArtifactType.CONTROLLER:ArtifactType.MODULE,ArtifactType.SERVICE:ArtifactType.MODULE,ArtifactType.REPOSITORY:ArtifactType.MODULE,ArtifactType.TOOL:ArtifactType.MODULE,ArtifactType.CONFIG:ArtifactType.ARTIFACT,ArtifactType.API:ArtifactType.ARTIFACT,ArtifactType.PIPELINE:ArtifactType.ARTIFACT,ArtifactType.WORKFLOW:ArtifactType.ARTIFACT,ArtifactType.DATABASE:ArtifactType.ARTIFACT,ArtifactType.DIRECTORY:ArtifactType.ARTIFACT}

def is_a(child: ArtifactType, parent: ArtifactType) -> bool:
    c = child
    while c is not None:
        if c == parent: return True
        c = ARTIFACT_TREE.get(c)
    return False

class KnowledgeType(Enum):
    CONSTRAINT="constraint"; RULE="rule"; PATTERN="pattern"; ANTIPATTERN="anti_pattern"; DECISION="decision"; QUALITY="quality_attribute"; SKILL="skill"

class EdgeType(Enum):
    DEPENDS_ON="depends_on"; REQUIRES="requires"; IMPLEMENTS="implements"; FOLLOWS="follows"; VIOLATES="violates"; IMPROVES="improves"; DERIVED_FROM="derived_from"; GENERATED_BY="generated_by"; EXTENDS="extends"; PRECEDES="precedes"; INFLUENCES="influences"; JUSTIFIES="justifies"; SUPERSEDES="supersedes"; INSTANTIATES="instantiates"; CONTAINS="contains"; REFERENCES="references"

@dataclass
class Artifact:
    id: str; name: str; atype: ArtifactType; type_confidence: float=1.0; source: Source=Source.MANUAL
    status: Dict[str,str]=field(default_factory=dict); metadata: Dict=field(default_factory=dict)
    def is_type(self, target: ArtifactType) -> bool: return is_a(self.atype, target)

@dataclass
class ArtifactEdge:
    id: str; source_id: str; target_id: str; etype: EdgeType; weight: float=1.0; confidence: float=0.9

@dataclass
class KnowledgeNode:
    id: str; ktype: KnowledgeType; name: str; description: str=""; source: Source=Source.MANUAL
    confidence: float=0.9; lifecycle: Lifecycle=Lifecycle.VERIFIED_LC
    binds_to_type: Optional[ArtifactType]=None; evidence: List[str]=field(default_factory=list)
    template: List[str]=field(default_factory=list); impact: Dict[str,float]=field(default_factory=dict)
    metadata: Dict=field(default_factory=dict)
    def __post_init__(self):
        if self.confidence==0.9 and self.source!=Source.MANUAL:
            self.confidence=source_confidence(self.source)

@dataclass
class KnowledgeEdge:
    id: str; source_id: str; target_id: str; etype: EdgeType; weight: float=1.0; confidence: float=0.9; is_negative: bool=False

@dataclass
class EngineeringContext:
    applicable_constraints: List[KnowledgeNode]=field(default_factory=list)
    matched_patterns: List[KnowledgeNode]=field(default_factory=list)
    quality_impact: Dict[str,float]=field(default_factory=dict)
    violated_anti_patterns: List[KnowledgeNode]=field(default_factory=list)
    relevant_decisions: List[KnowledgeNode]=field(default_factory=list)
    module_status: Dict[str,str]=field(default_factory=dict)
