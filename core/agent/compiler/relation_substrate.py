"""RelationSubstrate — unified relation layer beneath SemanticObject.

Design: docs/v3.0/DESIGN_RELATION_SUBSTRATE.md v2.0

Replaces the scattered relation representations (ConceptGraph typed edges,
BehaviorGraph, CausalSubstrate) with a single substrate. All relations are
stored as RelationEdges with evidence chains. Causal is not a type — it's
an explanation layer (high confidence + multi-source evidence + mechanism).
"""
from __future__ import annotations
import re
import time
import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---- Data ----

@dataclass
class Evidence:
    """One piece of evidence supporting a relation."""
    evidence_id: str
    source: str           # "document" | "code" | "behavior" | "git" | "heading"
    claim: str            # e.g. "A depends_on B per DESIGN_RUNTIME.md"
    confidence: float
    predicate: str        # e.g. "depends_on"
    extracted_at: float = field(default_factory=time.time)
    raw_ref: str = ""

    def __hash__(self):
        return hash(self.evidence_id)


@dataclass
class RelationEdge:
    """One relation in the world. Source and target are SemanticObject identities."""

    identity: str
    source: str
    target: str

    # Two orthogonal dimensions
    relation_kind: str       # "structural" | "behavioral" | "temporal"
    semantic_strength: str   # "association" | "reference" | "dependency" | "implementation"

    # RDF semantics
    predicate: str           # "depends_on" | "contains" | "calls" | "produces" | ...
    inverse: str             # "depended_by" | "contained_by" | ...

    confidence: float = 0.3
    evidence: List[Evidence] = field(default_factory=list)

    # Causal explanation layer (only when confidence > 0.8 + multi-source)
    mechanism: Optional[str] = None

    # Lifecycle
    created_at: float = field(default_factory=time.time)
    ttl: Optional[float] = None
    decay_rate: float = 0.01

    def __hash__(self):
        return hash(self.identity)


# ---- Substrate ----

class RelationSubstrate:
    """Unified relation store.

    Queries:
      by source → "what does DomainSelector relate to?"
      by target → "what relates to DomainSelector?"
      by type   → "show all behavioral edges"
      by confidence → "show high-confidence structural edges"
    """

    def __init__(self, params=None):
        self._edges: Dict[str, RelationEdge] = {}
        self._by_source: Dict[str, Set[str]] = {}
        self._by_target: Dict[str, Set[str]] = {}
        self._params = params  # ParameterRegistry (optional, for soft-coded thresholds)

    # ---- Build ----

    def build_from_extractions(self, extractions: list) -> int:
        """Feed extracted relations (from jieba/LMStudio/DeepSeek) into substrate."""
        count = 0
        for ext in extractions:
            if isinstance(ext, dict):
                src = ext.get("subject", ext.get("source", ""))
                tgt = ext.get("object", ext.get("target", ""))
                pred = ext.get("predicate", "depends_on")
                conf = ext.get("confidence", 0.5)
            else:
                src = getattr(ext, "source", "")
                tgt = getattr(ext, "target", "")
                pred = getattr(ext, "predicate", "depends_on")
                conf = getattr(ext, "confidence", 0.5)
            if src and tgt:
                inv_map = {"depends_on":"depended_by","calls":"called_by","produces":"produced_by","implements":"implemented_by","extends":"extended_by","references":"referenced_by","constrains":"constrained_by","controls":"controlled_by","modifies":"modified_by"}
                inv = inv_map.get(pred, f"inv_{pred}")
                eid = f"ext:{src}:{pred}:{tgt}"
                edge = RelationEdge(
                    identity=eid, source=src, target=tgt,
                    relation_kind="structural", semantic_strength="dependency",
                    predicate=pred, inverse=inv,
                    confidence=conf,
                    evidence=[Evidence(
                        evidence_id=f"ext_ev_{eid}", source="extraction",
                        claim=f"{src} {pred} {tgt}", confidence=conf,
                        predicate=pred,
                    )],
                )
                self._add(edge)
                count += 1
        logger.info("RelationSubstrate: fed %d extraction edges", count)
        return count

    def build_from_concept_graph(self, graph) -> int:
        """Import typed edges from ConceptGraph as structural relations."""
        count = 0
        for name, node in graph._nodes.items():
            for rel in node.get("relations", []):
                rel_type = rel.get("type", "association")
                target_name = rel.get("target", "")
                if not target_name or rel_type == "co_occurs":
                    continue

                predicate = rel_type
                inverse_map = {
                    "depends_on": "depended_by", "calls": "called_by",
                    "contains": "contained_by", "creates": "created_by",
                    "implements": "implemented_by", "extends": "extended_by",
                    "references": "referenced_by", "triggers": "triggered_by",
                    "constrains": "constrained_by", "leads_to": "led_by",
                }

                edge = RelationEdge(
                    identity=f"cg:{name}→{target_name}:{rel_type}",
                    source=name, target=target_name,
                    relation_kind="structural",
                    semantic_strength=self._infer_strength(rel_type),
                    predicate=predicate,
                    inverse=inverse_map.get(rel_type, f"inv_{rel_type}"),
                    confidence=self._get("concept_graph.typed_edge_confidence", 0.5),
                    evidence=[Evidence(
                        evidence_id=f"cg:{name}→{target_name}",
                        source="concept_graph", claim=f"{name} {rel_type} {target_name}",
                        confidence=self._get("concept_graph.typed_edge_confidence", 0.5),
                        predicate=predicate,
                    )],
                )
                self._add(edge)
                count += 1

        logger.info("RelationSubstrate: %d edges from ConceptGraph", count)
        return count

    def build_from_heading(self, semantic_index, graph) -> int:
        """Import heading hierarchy as structural contains relations."""
        count = 0
        _chunk_re = re.compile(r'\[chunk\s*\d+\]')

        for ph, snode in semantic_index._nodes.items():
            segments = [re.sub(_chunk_re, '', s).strip()
                        for s in snode.get("segments", [])
                        if s and not _chunk_re.match(s.strip())]
            if len(segments) < 2:
                continue
            parent_name = segments[-2]
            child_name = segments[-1]
            if parent_name == child_name:
                continue

            edge = RelationEdge(
                identity=f"hdr:{parent_name}→{child_name}",
                source=parent_name, target=child_name,
                relation_kind="structural",
                semantic_strength="dependency",
                predicate="contains",
                inverse="contained_by",
                confidence=self._get("heading.contains_confidence", 0.4),
                evidence=[Evidence(
                    evidence_id=f"hdr:{parent_name}→{child_name}",
                    source="heading", claim=f"{parent_name} heading contains {child_name}",
                    confidence=self._get("heading.contains_confidence", 0.4),
                    predicate="contains",
                )],
            )
            self._add(edge)
            count += 1

        logger.info("RelationSubstrate: %d edges from heading hierarchy", count)
        return count

    # ---- Query ----

    def query(self, source: str = None, target: str = None,
              relation_kind: str = None, semantic_strength: str = None,
              predicate: str = None, min_confidence: float = 0.0,
              limit: int = 50) -> List[RelationEdge]:
        """Query relations by any combination of filters."""
        candidates: Set[str] = set()

        if source:
            candidates = self._by_source.get(source, set()).copy()
        elif target:
            candidates = self._by_target.get(target, set()).copy()
        else:
            candidates = set(self._edges.keys())

        if target and source:
            candidates &= self._by_target.get(target, set())

        results = []
        for eid in candidates:
            edge = self._edges.get(eid)
            if not edge:
                continue
            if target and edge.target != target:
                continue
            if source and edge.source != source:
                continue
            if relation_kind and edge.relation_kind != relation_kind:
                continue
            if semantic_strength and edge.semantic_strength != semantic_strength:
                continue
            if predicate and edge.predicate != predicate:
                continue
            if edge.confidence < min_confidence:
                continue
            results.append(edge)

        results.sort(key=lambda e: e.confidence, reverse=True)
        return results[:limit]

    def get_all_related(self, identity: str, limit: int = 20) -> List[RelationEdge]:
        """Get all edges where identity is source or target."""
        return self.query(source=identity, limit=limit // 2) + \
               self.query(target=identity, limit=limit // 2)

    # ---- Mutate ----

    def add(self, edge: RelationEdge):
        """Add or update a relation edge."""
        self._add(edge)

    def add_behavior(self, source: str, target: str):
        """Record a behavioral observation (user navigated source → target)."""
        eid = f"bhv:{source}→{target}:{int(time.time())}"
        edge = RelationEdge(
            identity=eid, source=source, target=target,
            relation_kind="behavioral", semantic_strength="association",
            predicate="navigated_to", inverse="navigated_from",
            confidence=self._get("behavior.default_confidence", 0.2),
            ttl=self._get("behavior.ttl_seconds", 300),
            decay_rate=self._get("behavior.decay_rate", 0.05),
            evidence=[Evidence(
                evidence_id=eid, source="behavior",
                claim=f"user navigated {source} → {target}",
                confidence=self._get("behavior.default_confidence", 0.2),
                predicate="navigated_to",
            )],
        )
        self._add(edge)

    def build_ontology_seeds(self, seed_nodes: List[dict],
                             cross_links: List[dict] = None) -> int:
        """Import ontology seed nodes with cross-layer linkage edges.

        seed_nodes: [{"id": "meta-1", "name": "Double-Loop Learning",
                       "level": 0, "category": "meta-learning"}, ...]
        cross_links: [{"from": "method-4", "to": "math-3",
                        "predicate": "instantiates"}, ...]

        Returns number of edges added.
        """
        count = 0

        # Import nodes as structural edges from L{X} → concept
        for node in seed_nodes:
            nid = node.get("id", "")
            name = node.get("name", "")
            level = node.get("level", 0)
            if not nid or not name:
                continue

            edge = RelationEdge(
                identity=f"seed:{nid}",
                source=f"L{level}", target=name,  # L0→Double-Loop Learning
                relation_kind="structural",
                semantic_strength="dependency",
                predicate="defines",
                inverse="defined_in",
                confidence=0.9,
                evidence=[Evidence(
                    evidence_id=f"seed:ev:{nid}", source="ontology",
                    claim=f"ontology seed L{level}: {name}",
                    confidence=0.9, predicate="defines",
                )],
            )
            self._add(edge)
            count += 1

        # Import cross-layer links
        if cross_links:
            for link in cross_links:
                pred = link.get("predicate", "related_to")
                weight = self._get(f"link.{pred}_weight", 0.7)
                edge = RelationEdge(
                    identity=f"link:{link.get('from')}→{link.get('to')}:{pred}",
                    source=link.get("from", ""),
                    target=link.get("to", ""),
                    relation_kind="structural",
                    semantic_strength="dependency",
                    predicate=pred,
                    inverse=f"inv_{pred}",
                    confidence=weight,
                    evidence=[Evidence(
                        evidence_id=f"link:ev:{link.get('from')}",
                        source="ontology", claim=f"cross-layer {pred}",
                        confidence=weight, predicate=pred,
                    )],
                )
                self._add(edge)
                count += 1

        logger.info("RelationSubstrate: %d ontology edges", count)
        return count

    @property
    def stats(self) -> dict:
        from collections import Counter
        kinds = Counter(e.relation_kind for e in self._edges.values())
        strengths = Counter(e.semantic_strength for e in self._edges.values())
        with_mech = sum(1 for e in self._edges.values() if e.mechanism)
        return {
            "total": len(self._edges),
            "kinds": dict(kinds),
            "strengths": dict(strengths),
            "with_mechanism": with_mech,
        }

    # ---- Internal ----

    def _add(self, edge: RelationEdge):
        self._edges[edge.identity] = edge
        self._by_source.setdefault(edge.source, set()).add(edge.identity)
        self._by_target.setdefault(edge.target, set()).add(edge.identity)

    def _get(self, key: str, default: Any) -> Any:
        """Get soft-coded parameter or fallback default."""
        if self._params:
            return self._params.get(key, default)
        return default

    @staticmethod
    def _infer_strength(rel_type: str) -> str:
        if rel_type in ("calls", "implements", "creates"):
            return "implementation"
        if rel_type in ("depends_on", "constrains", "contains"):
            return "dependency"
        if rel_type in ("references", "extends", "triggers"):
            return "reference"
        return "association"
