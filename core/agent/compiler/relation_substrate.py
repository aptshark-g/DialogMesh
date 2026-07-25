"""RelationSubstrate — unified relation layer beneath SemanticObject.

Design: docs/v3.0/DESIGN_RELATION_SUBSTRATE.md v2.0
V3: LLM-native open-type relations replace hardcoded 3×4 classification.
"""

from __future__ import annotations
import re, time, logging
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field

# Import LLM-native extraction
try:
    from core.agent.compiler.llm_relation_extractor import (
        LLMRelationExtractor, RelationClusterer, OpenRelation
    )
    _LLM_AVAILABLE = True
except ImportError:
    _LLM_AVAILABLE = False

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

    # RDF semantics
    predicate: str           # "depends_on" | "contains" | "calls" | "produces" | ...
    inverse: str             # "depended_by" | "contained_by" | ...

    # Two orthogonal dimensions (nullable — LLM may not always classify)
    relation_kind: Optional[str] = None      # "structural" | "behavioral" | "temporal" | None
    semantic_strength: Optional[str] = None  # "association" | "reference" | "dependency" | "implementation" | None

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

@dataclass
class EntityNode:
    """Conversation entity — lightweight node for L2 ontology graph."""
    entity_id: str
    name: str
    types: List[str] = field(default_factory=list)  # e.g. ["工具", "现象"]
    cluster_id: str = ""
    first_seen_turn: int = 0
    last_seen_turn: int = 0

    def __hash__(self):
        return hash(self.entity_id)


class RelationSubstrate:
    """Unified relation store.

    Queries:
      by source → "what does DomainSelector relate to?"
      by target → "what relates to DomainSelector?"
      by type   → "show all behavioral edges"
      by confidence → "show high-confidence structural edges"
    """

    def __init__(self, params=None, llm_fn=None):
        self._edges: Dict[str, RelationEdge] = {}
        self._by_source: Dict[str, Set[str]] = {}
        self._by_target: Dict[str, Set[str]] = {}
        self._params = params
        self._entities: Dict[str, EntityNode] = {}
        self._llm_fn = llm_fn  # LLM call function for relation classification
        self._inverse_cache: Dict[str, str] = {}  # predicate → inverse (LLM or heuristic)
        self._clusterer = RelationClusterer() if _LLM_AVAILABLE else None

    # ---- L2 Conversation Entity Methods ----

    def add_entity(self, entity: EntityNode):
        self._entities[entity.entity_id] = entity

    def add_conversation_edge(self, source_id: str, target_id: str,
                              predicate: str, turn_num: int,
                              bm25_score: float = 0.0, llm_confidence: float = 0.0):
        """Add edge with conversation evidence (BM25 + LLM)."""
        evidence = []
        if bm25_score > 0:
            evidence.append(Evidence(
                evidence_id=f"bm25_turn_{turn_num}_{source_id}_{target_id}",
                source="conversation_bm25", claim=f"BM25 hit in turn {turn_num}",
                confidence=bm25_score, predicate=predicate,
            ))
        if llm_confidence > 0:
            evidence.append(Evidence(
                evidence_id=f"llm_turn_{turn_num}_{source_id}_{target_id}",
                source="conversation_llm", claim=f"LLM extracted in turn {turn_num}",
                confidence=llm_confidence, predicate=predicate,
            ))
        edge_id = f"conv_{turn_num}_{source_id}_{target_id}"
        edge = RelationEdge(
            identity=edge_id,
            source=source_id, target=target_id,
            predicate=predicate,
            inverse="associated_with",
            relation_kind="temporal" if predicate in ("sequential","co_occurrence") else "structural",
            semantic_strength="association",
            confidence=max(bm25_score, llm_confidence, 0.3),
            evidence=evidence,
        )
        self.add(edge)
        return edge_id

    def entity_neighbors(self, entity_id: str, hops: int = 2) -> dict:
        """1-2 hop neighbor traversal for L2 ontology.
        Returns: {"1hop": [entity_ids], "2hop": [entity_ids], "edges": [edge_ids]}
        """
        result = {"1hop": [], "2hop": [], "edges": []}
        visited = {entity_id}
        frontier = {entity_id}
        
        for hop in [1, 2]:
            next_frontier = set()
            for eid in frontier:
                for edge_id in self._by_source.get(eid, set()):
                    edge = self._edges.get(edge_id)
                    if edge and edge.target not in visited:
                        key = "1hop" if hop == 1 else "2hop"
                        result[key].append(edge.target)
                        result["edges"].append(edge_id)
                        visited.add(edge.target)
                        next_frontier.add(edge.target)
            frontier = next_frontier
        
        return result

    def entity_edge(self, from_id: str, to_id: str) -> Optional[RelationEdge]:
        """Get edge between two entities."""
        for eid in self._by_source.get(from_id, set()):
            edge = self._edges.get(eid)
            if edge and edge.target == to_id:
                return edge
        return None

    def get_entity(self, entity_id: str) -> Optional[EntityNode]:
        return self._entities.get(entity_id)

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
                    predicate=pred, inverse=inv,
                    relation_kind="structural", semantic_strength="dependency",
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
                    predicate=predicate,
                    inverse=inverse_map.get(rel_type, f"inv_{rel_type}"),
                    relation_kind="structural",
                    semantic_strength=self._heuristic_strength(rel_type),
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
                predicate="contains",
                inverse="contained_by",
                relation_kind="structural",
                semantic_strength="dependency",
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
            predicate="navigated_to", inverse="navigated_from",
            relation_kind="behavioral", semantic_strength="association",
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
                predicate="defines",
                inverse="defined_in",
                relation_kind="structural",
                semantic_strength="dependency",
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
                    predicate=pred,
                    inverse=f"inv_{pred}",
                    relation_kind="structural",
                    semantic_strength="dependency",
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

    # ── V3: LLM-native relation classification ──

    def infer_relation_kind(self, predicate: str, context: str = "") -> tuple:
        """Infer relation_kind + semantic_strength via LLM or heuristic fallback.

        Returns: (kind, strength) — either may be None if LLM uncertain.
        """
        # Try LLM first
        if self._llm_fn:
            try:
                prompt = (
                    f"Classify this relation predicate into kind and strength.\n"
                    f"Predicate: '{predicate}'\n"
                    f"Context: '{context}'\n\n"
                    f"Respond ONLY with JSON: {{\"kind\": \"structural|behavioral|temporal\", "
                    f"\"strength\": \"association|reference|dependency|implementation\"}}"
                )
                result = self._llm_fn(prompt)
                import json
                d = json.loads(result) if isinstance(result, str) else result
                return (d.get("kind"), d.get("strength"))
            except Exception:
                pass

        # Heuristic fallback (preserves backward compatibility)
        return (self._heuristic_kind(predicate), self._heuristic_strength(predicate))

    def infer_inverse(self, predicate: str) -> str:
        """Generate inverse predicate — LLM or heuristic."""
        if predicate in self._inverse_cache:
            return self._inverse_cache[predicate]

        # Heuristic suffix patterns (covers 80% of cases)
        known = {
            "depends_on": "depended_by", "calls": "called_by", "contains": "contained_by",
            "produces": "produced_by", "implements": "implemented_by", "extends": "extended_by",
            "references": "referenced_by", "constrains": "constrained_by",
            "triggers": "triggered_by", "creates": "created_by", "leads_to": "led_by",
            "controls": "controlled_by", "modifies": "modified_by",
        }
        inv = known.get(predicate)
        if not inv:
            # Generate: "validates_output_of" → "validated_by_output"
            if "_by_" in predicate:
                inv = predicate.replace("_by_", "_")
            elif predicate.endswith("ed"):
                inv = predicate[:-2] + "ing"
            elif predicate.endswith("s"):
                inv = predicate[:-1] + "ed_by"
            else:
                inv = f"inverse_of_{predicate}"
        
        self._inverse_cache[predicate] = inv
        return inv

    def cluster_predicates(self) -> dict:
        """Cluster accumulated predicates into families. Returns cluster summary."""
        if not self._clusterer:
            return {"clusters": 0}
        # Build OpenRelation list from stored edges
        rels = []
        for e in self._edges.values():
            if e.predicate:
                rels.append(OpenRelation(
                    identity=e.identity, source=e.source, target=e.target,
                    predicate=e.predicate, confidence=e.confidence, direction="directed"
                ))
        clusters = self._clusterer.cluster(rels)
        return {
            "total_clusters": len(clusters),
            "clusters": [(c.canonical_name, c.frequency) for c in clusters[:10]],
        }

    # ── Heuristic fallbacks (preserve backward compatibility) ──

    @staticmethod
    def _heuristic_kind(predicate: str) -> Optional[str]:
        word = predicate.lower().replace("_", " ")
        if any(w in word for w in ("depend", "call", "implement", "contain", "create", "define", "extend")):
            return "structural"
        if any(w in word for w in ("navigat", "click", "visit", "select", "prefer")):
            return "behavioral"
        if any(w in word for w in ("before", "after", "sequence", "trigger", "lead to", "follow")):
            return "temporal"
        return None  # LLM-unclassified — leave null

    @staticmethod
    def _heuristic_strength(predicate: str) -> Optional[str]:
        word = predicate.lower().replace("_", " ")
        if any(w in word for w in ("call", "implement", "creat")):
            return "implementation"
        if any(w in word for w in ("depend", "constrain", "contain", "require")):
            return "dependency"
        if any(w in word for w in ("refer", "extend", "trigger", "instantiat", "validat")):
            return "reference"
        return "association"  # default
