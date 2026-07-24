"""LLM-native Relation Extractor — open-type relations, post-hoc clustering.

Replaces hardcoded 3×4 relation matrix with:
  1. LLM extraction: (source, predicate, target, confidence, evidence)
  2. Clustering: normalize free-form predicates → relation families
  3. Meta-cognition: condense frequently-co-occurring relations → rules

Design: docs/v5/DESIGN_LLM_NATIVE_RELATIONS.md
"""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import Counter
import time, logging

logger = logging.getLogger(__name__)


# ── Data ──

@dataclass
class OpenRelation:
    """A single LLM-extracted relation — no predefined type."""
    identity: str
    source: str                        # entity A
    target: str                        # entity B
    predicate: str                     # free-form: "validates_output_of", "is_blocked_by", ...
    confidence: float                  # 0-1
    direction: str = "directed"        # directed | undirected | bidirectional
    evidence: List[dict] = field(default_factory=list)  # [{source, text, turn}]
    mechanism: str = ""                # causal explanation (optional)
    created_at: float = field(default_factory=time.time)
    ttl: float = 86400 * 7             # default 7 days

    def to_xml(self) -> str:
        ev = "\n".join(
            f'    <evidence source="{e.get("source","")}" turn="{e.get("turn","")}">{e.get("text","")[:200]}</evidence>'
            for e in self.evidence
        )
        mech = f'  <mechanism>{self.mechanism}</mechanism>\n' if self.mechanism else ""
        return f"""<relation id="{self.identity}" confidence="{self.confidence:.2f}">
  <source>{self.source}</source>
  <predicate direction="{self.direction}">{self.predicate}</predicate>
  <target>{self.target}</target>
{mech}
  <evidence>
{ev}
  </evidence>
</relation>"""


@dataclass
class RelationCluster:
    """A family of related predicates after clustering."""
    cluster_id: str
    canonical_name: str               # e.g. "depends_on"
    members: List[str]                 # original predicates: ["validates_output_of", "relies_on", ...]
    frequency: int = 0
    avg_confidence: float = 0.0
    examples: List[str] = field(default_factory=list)  # sample raw texts

    def merge(self, others: List[OpenRelation]):
        """Update cluster from new members."""
        self.members.extend([r.predicate for r in others])
        self.frequency += len(others)
        self.avg_confidence = sum(r.confidence for r in others) / max(1, len(others))


# ── Extractor ──

class LLMRelationExtractor:
    """Extract open-type relations from conversation using LLM.

    Prompt design: tell LLM to list ALL relations between entities,
    in free-form natural language predicates. No classification needed.
    """

    EXTRACTION_PROMPT = """Analyze this conversation and extract ALL relations between entities, concepts, or actions.

Return ONLY valid XML. For each relation found:
<extracted_relations>
  <relation confidence="0.95">
    <source>entity_name_A</source>
    <predicate direction="directed">natural_language_predicate</predicate>
    <target>entity_name_B</target>
    <evidence>brief quote from conversation</evidence>
  </relation>
  ...
</extracted_relations>

Rules:
- predicate is FREE-FORM natural language: "validates_output_of", "is_blocked_by", "triggers_notification", "replaces_v2_endpoint"
- confidence reflects how certain the relation is (0.0-1.0)
- direction: "directed" (A→B), "undirected" (A↔B), or "bidirectional"
- entity names should be consistent across extractions
- include ALL non-trivial relations, even weak ones
- do NOT try to classify into predefined types
"""

    def __init__(self, llm_call_fn=None):
        """llm_call_fn(prompt, context) → str"""
        self.llm_call = llm_call_fn

    def extract(self, conversation_text: str, existing_entities: List[str] = None) -> List[OpenRelation]:
        """Extract relations from conversation text."""
        if not self.llm_call:
            logger.warning("No LLM call function configured")
            return []

        context = f"Known entities: {', '.join(existing_entities or [])}\n\nConversation:\n{conversation_text[:3000]}"
        try:
            raw = self.llm_call(self.EXTRACTION_PROMPT, context)
            return self._parse_response(raw)
        except Exception as e:
            logger.debug("Relation extraction failed: %s", e)
            return []

    def _parse_response(self, raw: str) -> List[OpenRelation]:
        """Parse LLM XML response into OpenRelation objects."""
        import xml.etree.ElementTree as ET
        relations = []
        try:
            # Extract XML from response (may have surrounding text)
            start = raw.find("<extracted_relations>")
            end = raw.find("</extracted_relations>")
            if start < 0 or end < 0:
                return []
            xml = raw[start:end + len("</extracted_relations>")]
            root = ET.fromstring(xml)
            for rel_el in root.findall("relation"):
                ident = f"rel_{hash(rel_el.find('source').text or '')}_{int(time.time()*1000)}"
                r = OpenRelation(
                    identity=ident,
                    source=(rel_el.find("source").text or "").strip(),
                    target=(rel_el.find("target").text or "").strip(),
                    predicate=(rel_el.find("predicate").text or "").strip(),
                    confidence=float(rel_el.get("confidence", 0.5)),
                    direction=rel_el.find("predicate").get("direction", "directed") if rel_el.find("predicate") is not None else "directed",
                    evidence=[{"text": (rel_el.find("evidence").text or "")[:200]}] if rel_el.find("evidence") is not None else [],
                )
                relations.append(r)
        except Exception as e:
            logger.debug("Parse XML relations failed: %s", e)
        return relations


# ── Clustering ──

class RelationClusterer:
    """Post-hoc clustering of free-form predicates into families.

    Two-pass approach:
      1. Embedding-based clustering (nomic 768d)
      2. LLM validation of clusters (optional)

    Clusters become the "relation vocabulary" — evolving, not static.
    """

    def __init__(self, embedding_fn=None, llm_fn=None,
                 similarity_threshold: float = 0.75):
        self.embed = embedding_fn
        self.llm = llm_fn
        self.threshold = similarity_threshold
        self._clusters: Dict[str, RelationCluster] = {}

    def cluster(self, relations: List[OpenRelation]) -> List[RelationCluster]:
        """Cluster relations into families. Returns updated cluster list."""
        if not self.embed:
            # Fallback: simple prefix-based clustering (word overlap)
            return self._simple_cluster(relations)

        # Embedding-based clustering
        predicates = [r.predicate for r in relations]
        embs = [self.embed(p) for p in predicates]

        clusters = []
        assigned = set()

        for i, rel in enumerate(relations):
            if i in assigned:
                continue
            family = [rel]
            assigned.add(i)
            for j in range(i + 1, len(relations)):
                if j in assigned:
                    continue
                sim = self._cosine_sim(embs[i], embs[j])
                if sim > self.threshold:
                    family.append(relations[j])
                    assigned.add(j)
            
            cluster = RelationCluster(
                cluster_id=f"cl_{len(clusters)}",
                canonical_name=family[0].predicate,  # first member as canonical
                members=list(set(r.predicate for r in family)),
                frequency=len(family),
                avg_confidence=sum(r.confidence for r in family) / len(family),
                examples=[f"{r.source} → {r.target}" for r in family[:3]],
            )
            clusters.append(cluster)

        self._clusters = {c.canonical_name: c for c in clusters}
        return clusters

    def _simple_cluster(self, relations: List[OpenRelation]) -> List[RelationCluster]:
        """Word-overlap based clustering fallback."""
        groups: Dict[str, List[OpenRelation]] = {}
        for rel in relations:
            # Extract root words: "validates_output_of" → ["validates", "output"]
            words = set(rel.predicate.lower().replace("_", " ").split())
            key = "_".join(sorted(words)[:2])  # first 2 words as key
            groups.setdefault(key, []).append(rel)

        return [
            RelationCluster(
                cluster_id=f"cl_{i}",
                canonical_name=max(rels, key=lambda r: r.confidence).predicate,
                members=list(set(r.predicate for r in rels)),
                frequency=len(rels),
                examples=[f"{r.source} → {r.target}" for r in rels[:2]],
            )
            for i, (key, rels) in enumerate(groups.items())
        ]

    def get_evolution(self) -> dict:
        """Return cluster evolution for meta-cognitive analysis."""
        return {
            "total_clusters": len(self._clusters),
            "most_frequent": sorted(
                [(c.canonical_name, c.frequency) for c in self._clusters.values()],
                key=lambda x: -x[1]
            )[:5],
            "avg_size": sum(c.frequency for c in self._clusters.values()) / max(1, len(self._clusters)),
        }

    @staticmethod
    def _cosine_sim(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        return dot / max(0.001, norm_a * norm_b)
