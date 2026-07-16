"""SemanticObjectBuilder — Object Genesis from multi-source evidence.

Design: DESIGN_SEMANTIC_OBJECT.md, Phase A.5

Three phases:
  I:  Scan pool → extract SemanticFacts (definition, relation, property)
  II: Group facts by subject → CandidateObject
  III: IdentityResolver — merge by semantic fingerprint (neighbor overlap)
  IV: Build SemanticObjects from resolved candidates
"""
from __future__ import annotations
import re
import logging
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict, Counter

from core.agent.v4.compiler.semantic_object import (
    SemanticObject, CompositionEdge, build_from_graph,
)
from core.agent.v4.context.source import _keyword_score

logger = logging.getLogger(__name__)


# ---- Data classes ----

class SemanticFact:
    """One extracted fact from text."""
    def __init__(self, subject: str, predicate: str,
                 obj: str = "", text: str = "", confidence: float = 0.5):
        self.subject = subject
        self.predicate = predicate
        self.object = obj
        self.text = text
        self.confidence = confidence


class CandidateObject:
    """Pre-resolution object candidate."""
    def __init__(self, name: str):
        self.name = name
        self.definitions: List[str] = []        # "X 是..."
        self.relations: List[Tuple[str, str]] = []  # (target, type)
        self.source_docs: Set[str] = set()
        self.surrounding: Set[str] = set()       # concepts appearing nearby
        self.heading_paths: List[List[str]] = []  # all heading_paths where this appears


# ---- Phase I: Semantic Extractor ----

class SemanticExtractor:
    """Extract SemanticFacts from observation pool interpretations.

    Scans raw paragraph text for patterns like:
      - "X 是 Y" / "X 定义为 Y" → definition
      - "X 依赖于 Y" / "X 调用 Y" → relation
      - "X 的 Y 是 Z" → property
    """

    # (pattern, predicate, regex group for subject, regex group for object)
    _PATTERNS: List[Tuple[str, str, int, int]] = [
        # Definitions
        (r'([A-Z][A-Za-z]+(?:[A-Z][A-Za-z]+)*)\s*(?:是|定义为|指|指的是|即|是指)\s*(.+?)(?:[。；;]|$)', "definition", 1, 2),
        (r'[\u4e00-\u9fff]{2,8}\s*是\s*[一一个种]?\s*(.+?)(?:[。；;]|$)', "definition", 0, 0),
        # Relations (typed edges)
        (r'([A-Z][A-Za-z]+(?:[A-Z][A-Za-z]+)*)\s*(?:依赖于|依赖|depends?\s*on)\s*([A-Z][A-Za-z]+(?:[A-Z][A-Za-z]+)*)', "depends_on", 1, 2),
        (r'([A-Z][A-Za-z]+(?:[A-Z][A-Za-z]+)*)\s*(?:调用|calls?)\s*([A-Z][A-Za-z]+(?:[A-Z][A-Za-z]+)*)', "calls", 1, 2),
        (r'([A-Z][A-Za-z]+(?:[A-Z][A-Za-z]+)*)\s*(?:继承|扩展|extends?)\s*([A-Z][A-Za-z]+(?:[A-Z][A-Za-z]+)*)', "extends", 1, 2),
        (r'([A-Z][A-Za-z]+(?:[A-Z][A-Za-z]+)*)\s*(?:实现|implements?)\s*([A-Z][A-Za-z]+(?:[A-Z][A-Za-z]+)*)', "implements", 1, 2),
    ]

    def extract(self, observation_pool) -> List[SemanticFact]:
        """Scan all interpretations for semantic facts.

        Strategy: scan interpretation summaries for CamelCase terms
        as candidate subjects, then match definition/relation patterns
        involving those subjects. Avoids noise from concepts field
        (which is polluted by code fragments and file paths).
        """
        facts: List[SemanticFact] = []
        _camel = re.compile(r'\b[A-Z][A-Za-z]{2,}(?:[A-Z][A-Za-z]{2,})+\b')  # e.g. ContextCompiler

        for domain in observation_pool.stats().get("by_domain", {}):
            for bundle in observation_pool.get_by_domain(domain):
                for dom_obs in getattr(bundle, "domain_observations", {}).values():
                    interpretations = getattr(dom_obs, "interpretations", [])
                    full_text = " ".join(
                        i.get("summary", "") if isinstance(i, dict) else getattr(i, "summary", "")
                        for i in interpretations
                    )
                    if not full_text:
                        continue

                    # Find all CamelCase terms as candidate subjects
                    subjects = set(_camel.findall(full_text))
                    # Skip code-like terms
                    subjects = {s for s in subjects
                                if not s.startswith(('http','def','class','import','return'))
                                and not s.endswith(('py','js','ts','md'))
                                and ':' not in s and '/' not in s}

                    for concept in subjects:
                        if len(concept) < 5:  # skip very short
                            continue
                        self._extract_facts_for(concept, full_text, facts)
                        # Always record: concept exists in this interpretation
                        # (minimal fact that allows candidates to be created)
                        facts.append(SemanticFact(
                            subject=concept, predicate="exists",
                            obj="this_document", text=full_text[:200], confidence=0.2,
                        ))

        logger.info("SemanticExtractor: %d facts from pool", len(facts))
        return facts

    def _extract_facts_for(self, concept: str, text: str, facts: List[SemanticFact]):
        """Extract facts involving a specific concept from text."""
        # Definition: "Concept 是/定义为/指 ..."
        # Find the concept in text, then look for definition patterns nearby
        pos = text.find(concept)
        if pos < 0:
            return
        window = text[max(0, pos-5):pos + 200]

        # Try definition patterns
        for pattern in [
            rf'{re.escape(concept)}\s*(?:是|定义为|指|指的是|是指)\s*(.+?)(?:[。；;]|$)',
            rf'{re.escape(concept)}\s*—\s*(.+?)(?:[。；;]|$)',
        ]:
            m = re.search(pattern, text[pos:pos+300])
            if m:
                obj = m.group(1).strip()[:200]
                facts.append(SemanticFact(
                    subject=concept, predicate="definition",
                    obj=obj, text=window, confidence=0.6,
                ))
                break

        # Relation patterns: look for "concept verb target" within nearby text
        for rel_pattern, rel_type in [
            (r'依赖于|依赖|depends?\s*on', "depends_on"),
            (r'调用|calls?', "calls"),
            (r'继承|扩展|extends?', "extends"),
            (r'实现|implements?', "implements"),
            (r'引用|references?|refers?\s*to', "references"),
            (r'触发|triggers?', "triggers"),
            (r'约束|限制|constrains?|restricts?', "constrains"),
            (r'创建|生成|creates?|generates?', "creates"),
        ]:
            rel_m = re.search(
                rf'{re.escape(concept)}\s*(?:{rel_pattern})\s*([A-Z][A-Za-z]{{2,}}(?:[A-Z][A-Za-z]+)*)',
                text[pos:pos+300]
            )
            if rel_m:
                target = rel_m.group(1).strip()
                facts.append(SemanticFact(
                    subject=concept, predicate=rel_type,
                    obj=target, text=window, confidence=0.5,
                ))
                # Also add reverse: target has relation to concept
                # (but only if it's a potential concept name)
                # omitted for now to avoid noise


# ---- Phase II: CandidateObject Builder ----

def build_candidates(facts: List[SemanticFact],
                     pool) -> Dict[str, CandidateObject]:
    """Group SemanticFacts by subject → CandidateObjects enriched with context."""
    candidates: Dict[str, CandidateObject] = {}
    _chunk_re = re.compile(r'\[chunk\s*\d+\]')

    # Build from facts
    for fact in facts:
        subj = fact.subject
        if subj not in candidates:
            candidates[subj] = CandidateObject(subj)
        c = candidates[subj]
        if fact.predicate == "definition":
            if fact.object not in c.definitions and fact.object != "this_document":
                c.definitions.append(fact.object)
        elif fact.predicate == "exists":
            pass  # handled by enrichment below
        else:
            c.relations.append((fact.object, fact.predicate))

    # Enrich with heading paths and surroundings from pool
    for domain in pool.stats().get("by_domain", {}):
        for bundle in pool.get_by_domain(domain):
            for dom_obs in getattr(bundle, "domain_observations", {}).values():
                for interp in getattr(dom_obs, "interpretations", []):
                    summary = (interp.get("summary", "") if isinstance(interp, dict)
                               else getattr(interp, "summary", ""))
                    concepts = (interp.get("concepts", []) if isinstance(interp, dict)
                                else getattr(interp, "concepts", []))
                    hp = (interp.get("heading_path") if isinstance(interp, dict)
                          else getattr(interp, "heading_path", None))

                    # Match: which candidates appear in this interpretation
                    matched = [c_name for c_name in candidates
                               if c_name in summary or c_name.lower() in summary.lower()]
                    for c_name in matched:
                        c = candidates[c_name]
                        if hp:
                            clean_hp = [re.sub(_chunk_re, '', s).strip() for s in hp
                                        if s and not re.match(_chunk_re, s.strip())]
                            if clean_hp not in c.heading_paths:
                                c.heading_paths.append(clean_hp)
                        c.surrounding.update(concepts)
                        c.source_docs.add(getattr(bundle, "bundle_id", ""))

    logger.info("CandidateObjects: %d subjects, %d with definition, %d with relation",
                len(candidates),
                sum(1 for c in candidates.values() if c.definitions),
                sum(1 for c in candidates.values() if c.relations))
    return candidates


# ---- Phase III: Identity Resolver ----

class IdentityResolver:
    """Merge candidates by semantic fingerprint (neighbor overlap).

    Score(a,b) = 0.4×name_sim + 0.3×neighbor_overlap + 0.2×shared_relations + 0.1×doc_overlap
    If score > threshold → merge.
    """

    def __init__(self, threshold: float = 0.45):
        self.threshold = threshold

    def resolve(self, candidates: Dict[str, CandidateObject]
                ) -> Dict[str, CandidateObject]:
        """Merge candidates that refer to the same real-world concept."""
        names = list(candidates.keys())
        merged = set()
        resolved: Dict[str, CandidateObject] = {}

        for i, name_a in enumerate(names):
            if name_a in merged:
                continue
            ca = candidates[name_a]
            best_match = None
            best_score = 0.0

            for name_b in names[i+1:]:
                if name_b in merged:
                    continue
                cb = candidates[name_b]
                score = self._score(ca, cb)
                if score > self.threshold and score > best_score:
                    best_score = score
                    best_match = name_b

            if best_match:
                # Merge cb into ca
                cb = candidates[best_match]
                ca.definitions.extend(cb.definitions)
                ca.relations.extend(cb.relations)
                ca.source_docs.update(cb.source_docs)
                ca.surrounding.update(cb.surrounding)
                ca.heading_paths.extend(cb.heading_paths)
                merged.add(best_match)
                logger.debug("Merged %s → %s (score=%.2f)", best_match, name_a, best_score)

            resolved[name_a] = ca

        logger.info("IdentityResolver: %d→%d (merged %d duplicates)",
                    len(candidates), len(resolved), len(merged))
        return resolved

    def _score(self, a: CandidateObject, b: CandidateObject) -> float:
        """Compute semantic identity score."""
        return (
            0.4 * self._name_sim(a.name, b.name) +
            0.3 * self._overlap(a.surrounding, b.surrounding) +
            0.2 * self._relation_overlap(a.relations, b.relations) +
            0.1 * self._overlap(a.source_docs, b.source_docs)
        )

    @staticmethod
    def _name_sim(a: str, b: str) -> float:
        """Token-based name similarity."""
        if a.lower() == b.lower():
            return 1.0
        if a.lower() in b.lower() or b.lower() in a.lower():
            return 0.85
        a_tokens = set(re.findall(r'[a-z]+', a.lower()))
        b_tokens = set(re.findall(r'[a-z]+', b.lower()))
        if not a_tokens or not b_tokens:
            return 0.0
        shared = a_tokens & b_tokens
        return len(shared) / max(len(a_tokens | b_tokens), 1)

    @staticmethod
    def _overlap(a: set, b: set) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / max(len(a | b), 1)

    @staticmethod
    def _relation_overlap(a: List, b: List) -> float:
        if not a or not b:
            return 0.0
        shared = set(a) & set(b)
        return len(shared) / max(len(set(a) | set(b)), 1)


# ---- Phase IV: Build SemanticObjects ----

def build_from_candidates(candidates: Dict[str, CandidateObject],
                          graph=None, semantic_index=None) -> Dict[str, SemanticObject]:
    """Convert resolved CandidateObjects to SemanticObjects.

    Uses definitions directly. Falls back to graph+semantic_index for
    concepts that had no extracted facts.
    """
    objects: Dict[str, SemanticObject] = {}

    for name, cand in candidates.items():
        # Best definition: longest or first
        definition = max(cand.definitions, key=len) if cand.definitions else ""
        # Best heading path: shortest (closest to root)
        best_hp = min(cand.heading_paths, key=len) if cand.heading_paths else []

        obj = SemanticObject(
            identity=name,
            name=name,
            composition_edges=[],
            projection_resolvers={"design": "DesignResolver",
                                  "causal": "CausalResolver",
                                  "behavior": "BehaviorResolver",
                                  "implementation": "ImplementationResolver"},
            semantic_path=best_hp,
            relations=[{"target": t, "type": ty} for t, ty in cand.relations],
        )
        objects[name] = obj

    # Phase IV-b: backfill from graph for concepts not in candidates
    if graph:
        for name, node in graph._nodes.items():
            if name in objects:
                continue
            path = semantic_index.locate(name) if semantic_index else None
            segments = path.segments if path else []
            objects[name] = SemanticObject(
                identity=name, name=name,
                composition_edges=[],
                projection_resolvers={"design": "DesignResolver"},
                semantic_path=segments,
                relations=[r for r in node.get("relations", [])
                           if r.get("type") != "semantic_parent"],
            )

    # Wire composition from heading hierarchy (same as build_from_graph Phase 4)
    _wire_composition(objects)

    # Also use explicit candidate relations as composition edges
    for name, cand in candidates.items():
        if name not in objects:
            continue
        obj = objects[name]
        existing_targets = {e.target for e in obj.composition_edges}
        for target, rel_type in cand.relations:
            if target in objects and target not in existing_targets and rel_type != "definition":
                obj.composition_edges.append(CompositionEdge(
                    target=target, type=rel_type))
                existing_targets.add(target)

    return objects


def _wire_composition(objects: Dict[str, SemanticObject]):
    """Wire composition from semantic_path hierarchy."""
    for obj in list(objects.values()):
        if not obj.semantic_path or len(obj.semantic_path) < 2:
            continue
        parent_seg = obj.semantic_path[-2]
        parent_obj = objects.get(parent_seg)
        if not parent_obj:
            parent_obj = objects.get(f"intermediate:{parent_seg}")
        if parent_obj and obj.identity != parent_obj.identity:
            if not any(e.target == obj.identity for e in parent_obj.composition_edges):
                parent_obj.composition_edges.append(CompositionEdge(
                    target=obj.identity, type="contains"))


# ---- Top-level API ----

def build_object_graph(pool, graph=None, semantic_index=None) -> Dict[str, SemanticObject]:
    """Full Object Genesis pipeline: Extract → Candidate → Resolve → Build.

    Returns Dict[identity, SemanticObject] ready for ObjectRuntime.
    """
    # Phase I
    extractor = SemanticExtractor()
    facts = extractor.extract(pool)

    # Phase II
    candidates = build_candidates(facts, pool)

    # Phase III
    resolver = IdentityResolver(threshold=0.45)
    resolved = resolver.resolve(candidates)

    # Phase IV: build from candidates first, then backfill from graph
    objects = build_from_candidates(resolved, graph, semantic_index)

    # Phase V: enrich composition with full heading hierarchy
    # (same as build_from_graph Phase 2-4 for intermediate objects)
    if semantic_index:
        _enrich_hierarchy(objects, semantic_index, graph)

    logger.info("Object Graph: %d objects from %d facts via %d resolved candidates",
                len(objects), len(facts), len(resolved))
    return objects


def _enrich_hierarchy(objects: Dict[str, SemanticObject],
                      semantic_index, graph):
    """Add intermediate objects and wire composition from heading hierarchy."""
    import re
    _chunk_re = re.compile(r'\[chunk\s*\d+\]')

    def clean(segs): return [re.sub(_chunk_re, '', s).strip() for s in segs if s and not _chunk_re.match(s.strip())]

    # Add intermediate objects from SemanticIndex
    for ph, snode in semantic_index._nodes.items():
        segments = clean(snode.get("segments", []))
        if len(segments) < 2:
            continue
        leaf = segments[-1]
        if leaf in objects or f"intermediate:{leaf}" in objects:
            continue
        objects[f"intermediate:{leaf}"] = SemanticObject(
            identity=f"intermediate:{leaf}", name=leaf,
            composition_edges=[], projection_resolvers={"design": "DesignResolver"},
            semantic_path=segments, relations=[])

    # Wire composition from heading segments (Phase 4)
    for obj in list(objects.values()):
        if not obj.semantic_path or len(obj.semantic_path) < 2:
            continue
        parent_seg = obj.semantic_path[-2]
        parent_obj = objects.get(parent_seg) or objects.get(f"intermediate:{parent_seg}")
        if parent_obj and obj.identity != parent_obj.identity:
            if not any(e.target == obj.identity for e in parent_obj.composition_edges):
                parent_obj.composition_edges.append(CompositionEdge(
                    target=obj.identity, type="contains"))
