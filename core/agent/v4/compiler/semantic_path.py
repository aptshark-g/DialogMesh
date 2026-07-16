"""SemanticPath — concept hierarchy from document heading aggregation.

Design: docs/v3.0/DESIGN_PERSPECTIVE_PLANNER.md §3

Phase 1 builds DocumentPath from observation heading_path, then
cross-aggregates into SemanticPath DAG. Each concept node in
ConceptGraph gets a semantic_parent edge pointing to its parent
in the semantic hierarchy.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict

from core.agent.v4.context.graph_source import ConceptGraph

logger = logging.getLogger(__name__)


class SemanticIndex:
    """DAG of SemanticPath nodes — concept hierarchy across documents.

    Each node has:
      - segments: path from root (e.g. ["DialogMesh", "Runtime", "Observation"])
      - parents: list of parent SemanticPath IDs (DAG — can have multiple)
      - children: list of child SemanticPath IDs
      - document_refs: DocumentPaths pointing to this semantic node
      - concepts: ConceptGraph concepts residing at this semantic location
    """

    def __init__(self):
        self._nodes: Dict[str, dict] = {}      # path_hash → node
        self._path_index: Dict[str, str] = {}   # "DialogMesh/Runtime/Observation" → path_hash
        self._concept_map: Dict[str, str] = {}  # concept_name → path_hash

    # ---- build ----

    def build_from_pool(self, observation_pool,
                        graph: Optional[ConceptGraph] = None) -> int:
        """Build SemanticIndex from ObservationPool + optional ConceptGraph.

        Returns number of SemanticPath nodes created.
        """
        if observation_pool is None:
            return 0
        self._pool = observation_pool

        # Pass 1: extract heading_path from all bundles → DocumentPath candidates
        doc_paths = self._extract_document_paths(observation_pool)
        logger.info("SemanticIndex: %d DocumentPath candidates", len(doc_paths))

        # Pass 2: cross-aggregate heading segments → SemanticPath nodes
        self._aggregate(doc_paths)

        # Pass 2.5: ensure all paths referenced by interpretations are in _nodes
        self._backfill_paths(observation_pool)

        logger.info("SemanticIndex: %d SemanticPath nodes", len(self._nodes))

        # Pass 3: bind concepts to semantic nodes
        if graph and graph._built:
            bound = self._bind_concepts(graph)
            logger.info("SemanticIndex: %d concepts bound to SemanticPath", bound)

        return len(self._nodes)

    # ---- query ----

    def locate(self, concept_name: str) -> Optional[SemanticPath]:
        """Find the SemanticPath for a concept. Returns None if not found."""
        ph = self._concept_map.get(concept_name)
        if ph and ph in self._nodes:
            return SemanticPath.from_node(ph, self._nodes[ph])
        # Fallback: try partial match on segments
        for ph, node in self._nodes.items():
            if concept_name in node["segments"]:
                return SemanticPath.from_node(ph, node)
        return None

    def locate_by_segments(self, segments: List[str]) -> Optional[SemanticPath]:
        """Find SemanticPath by exact segment match."""
        key = "/".join(segments)
        ph = self._path_index.get(key)
        if ph and ph in self._nodes:
            return SemanticPath.from_node(ph, self._nodes[ph])
        return None

    def children_of(self, path_hash: str) -> List[SemanticPath]:
        """Get child SemanticPath nodes of a given node."""
        if path_hash not in self._nodes:
            return []
        return [SemanticPath.from_node(c, self._nodes.get(c, {}))
                for c in self._nodes[path_hash].get("children", [])]

    def root(self) -> Optional[SemanticPath]:
        """Get the root node (no parents, highest node count)."""
        roots = [ph for ph, n in self._nodes.items() if not n.get("parents")]
        if not roots:
            return None
        # Pick root with most children
        roots.sort(key=lambda ph: len(self._nodes[ph].get("children", [])), reverse=True)
        return SemanticPath.from_node(roots[0], self._nodes[roots[0]])

    # ---- view navigation ----

    def descend(self, from_path: SemanticPath, concept: str) -> SemanticPath:
        """Navigate from a SemanticPath down to a child containing 'concept'."""
        children = self.children_of(from_path.path_hash)
        for child in children:
            if concept in child.segments:
                return child
        # Fallback: locate concept directly
        return self.locate(concept) or from_path

    def ascend(self, from_path: SemanticPath) -> SemanticPath:
        """Navigate up to the parent of a SemanticPath."""
        for ph in from_path.parents:
            if ph in self._nodes:
                return SemanticPath.from_node(ph, self._nodes[ph])
        return from_path  # already at root

    @property
    def stats(self) -> dict:
        return {"nodes": len(self._nodes), "concepts": len(self._concept_map)}

    # ---- internal ----

    def _backfill_paths(self, pool):
        """Ensure all heading paths have live SemanticPath nodes.

        After aggregation+merging, some paths in _path_index may point to
        deleted nodes. This method walks all interpretations and guarantees
        each unique heading_path chain has a live entry in _nodes.
        """
        for domain in pool.stats().get("by_domain", {}):
            for bundle in pool.get_by_domain(domain):
                for dom_obs in getattr(bundle, "domain_observations", {}).values():
                    for interp in getattr(dom_obs, "interpretations", []):
                        hp = (interp.get("heading_path") if isinstance(interp, dict)
                              else getattr(interp, "heading_path", None))
                        if not hp:
                            continue
                        hp_key = "/".join(hp)

                        # Check if live node exists for this path
                        existing_ph = self._path_index.get(hp_key)
                        if existing_ph and existing_ph in self._nodes:
                            continue  # alive

                        # Create or re-create node
                        ph = self._hash_path(hp)
                        source = str(interp.get("source_path",
                                     getattr(bundle, "bundle_id", "")))
                        self._nodes[ph] = {
                            "segments": hp,
                            "parents": [],
                            "children": [],
                            "document_refs": [source],
                            "concepts": set(),
                            "cross_weight": 1,
                        }
                        self._path_index[hp_key] = ph

    def _extract_document_paths(self, pool) -> List[DocumentPath]:
        """Extract DocumentPath from all bundles in the pool."""
        paths: List[DocumentPath] = []
        seen = set()

        for domain in pool.stats().get("by_domain", {}):
            for bundle in pool.get_by_domain(domain):
                bid = bundle.bundle_id
                if bid in seen:
                    continue
                seen.add(bid)

                for dom_obs in getattr(bundle, "domain_observations", {}).values():
                    for interp in getattr(dom_obs, "interpretations", []):
                        hp = (interp.get("heading_path") if isinstance(interp, dict)
                              else getattr(interp, "heading_path", None))
                        if not hp:
                            continue
                        source = str(interp.get("source_path",
                                     getattr(bundle, "bundle_id", "")))
                        dp = DocumentPath(
                            source=source,
                            heading_chain=list(hp),
                            concepts=(
                                interp.get("concepts", []) if isinstance(interp, dict)
                                else getattr(interp, "concepts", [])
                            ),
                        )
                        paths.append(dp)

        return paths

    def _aggregate(self, doc_paths: List[DocumentPath]):
        """Cross-aggregate DocumentPaths into SemanticPath DAG.

        Strategy: collapse segments with identical names across documents.
        e.g. "DESIGN_A/Runtime/Observation" + "DESIGN_B/Runtime/Observation"
        → one SemanticPath node "Runtime/Observation" with both document refs.
        """
        # Phase 1: collect segment chains at each position
        #   position 0 → all root-level segments ("DESIGN_A.md", "DESIGN_B.md"...)
        #   position 1 → {"Runtime": set(docs), "Gateway": set(docs)}
        #   etc.
        segment_index: Dict[int, Dict[str, set]] = defaultdict(lambda: defaultdict(set))

        for dp in doc_paths:
            chain = dp.heading_chain
            for i, seg in enumerate(chain):
                segment_index[i][seg].add(dp.source)

        # Phase 2: build SemanticPath nodes for segments appearing in multiple docs
        #   Single-doc segments become children of their parent, not roots
        seen_paths: Set[str] = set()

        for dp in doc_paths:
            chain = dp.heading_chain
            # Build hierarchy: each prefix of chain becomes a node
            for end in range(1, len(chain) + 1):
                segments = chain[:end]
                ph = self._hash_path(segments)
                if ph in seen_paths:
                    continue
                seen_paths.add(ph)

                docs_here = set()
                for s in segments[:1]:  # root segment owns all docs in this chain
                    if 0 in segment_index and s in segment_index[0]:
                        docs_here |= segment_index[0][s]
                # Narrow to docs that contain this exact path
                docs_here = {d for d in docs_here if any(
                    d in segment_index[i].get(seg, set())
                    for i, seg in enumerate(segments)
                )}

                # Cross-doc weight: docs that share this segment
                segment_docs = set()
                for i, seg in enumerate(segments):
                    if i in segment_index and seg in segment_index[i]:
                        segment_docs |= segment_index[i][seg]
                cross_weight = len(segment_docs)

                self._nodes[ph] = {
                    "segments": segments,
                    "parents": [],
                    "children": [],
                    "document_refs": list(docs_here)[:10],
                    "concepts": set(),
                    "cross_weight": cross_weight,
                }
                self._path_index["/".join(segments)] = ph

        # Phase 3: merge duplicate segments — same name at same depth → share parent
        # Collect by (depth, segment_name)
        by_name: Dict[str, List[str]] = defaultdict(list)
        for ph, node in self._nodes.items():
            if not node["segments"]:
                continue
            key = f"{len(node['segments'])-1}:{node['segments'][-1]}"
            by_name[key].append(ph)

        # For segments appearing at same depth with same name in multiple docs,
        # set their parents from the highest-cross-weight parent
        for key, ph_list in by_name.items():
            if len(ph_list) <= 1:
                continue
            # Find best parent (highest cross_weight)
            best_ph = max(ph_list, key=lambda ph: self._nodes[ph].get("cross_weight", 0))
            # Absorb other paths' document refs
            for ph in ph_list:
                if ph == best_ph:
                    continue
                self._nodes[best_ph]["document_refs"].extend(
                    self._nodes[ph]["document_refs"])
                self._nodes[best_ph]["document_refs"] = list(
                    set(self._nodes[best_ph]["document_refs"]))
                # Remap: concepts pointing to ph now point to best_ph
                for c, cph in list(self._concept_map.items()):
                    if cph == ph:
                        self._concept_map[c] = best_ph
                # Transfer children
                for child in self._nodes[ph].get("children", []):
                    if child not in self._nodes[best_ph]["children"]:
                        self._nodes[best_ph]["children"].append(child)
                # Remove merged node
                del self._nodes[ph]

        # Phase 4: wire parent-child
        for ph, node in self._nodes.items():
            segments = node["segments"]
            if len(segments) > 1:
                parent_key = "/".join(segments[:-1])
                parent_ph = self._path_index.get(parent_key)
                if parent_ph and parent_ph in self._nodes and parent_ph != ph:
                    if parent_ph not in node["parents"]:
                        node["parents"].append(parent_ph)
                    if ph not in self._nodes[parent_ph]["children"]:
                        self._nodes[parent_ph]["children"].append(ph)

    def _bind_concepts(self, graph: ConceptGraph) -> int:
        """Bind graph concepts to SemanticPath by fast text match in summaries.

        For each interpretation in the pool: scan its summary for concept names.
        Build hp_key → concepts mapping, then bind.
        """
        # Phase 1: scan pool → (hp_key, concept_set)
        hp_entries: List[Tuple[str, str]] = []  # (hp_key, summary text)
        for domain in self._pool.stats().get("by_domain", {}):
            for bundle in self._pool.get_by_domain(domain):
                for dom_obs in getattr(bundle, "domain_observations", {}).values():
                    for interp in getattr(dom_obs, "interpretations", []):
                        hp = (interp.get("heading_path") if isinstance(interp, dict)
                              else getattr(interp, "heading_path", None))
                        if not hp:
                            continue
                        summary = (interp.get("summary", "") if isinstance(interp, dict)
                                   else getattr(interp, "summary", ""))
                        hp_key = "/".join(hp)
                        hp_entries.append((hp_key, summary))

        # Phase 2: for each concept, find headings where it appears
        concept_hps: Dict[str, Set[str]] = defaultdict(set)
        # Only scan top-2000 concepts by degree (most important ones)
        sorted_concepts = sorted(graph._nodes.keys(),
                                 key=lambda c: len(graph._nodes[c].get("relations", [])),
                                 reverse=True)[:2000]
        concept_set = set(sorted_concepts)

        for hp_key, summary in hp_entries:
            summary_lower = summary.lower()
            for c in concept_set:
                c_lower = c.lower()
                # Exact substring match
                if c in summary:
                    concept_hps[c].add(hp_key)
                # Lowercase match (e.g., "ContextCompiler" matches "context compiler")
                elif c_lower in summary_lower:
                    concept_hps[c].add(hp_key)
                # CamelCase tokenized (e.g., "ContextCompiler" → "context", "compiler")
                elif len(c) >= 10 and _camel_words_in(c_lower, summary_lower):
                    concept_hps[c].add(hp_key)

        # Phase 3: bind
        bound = 0
        for concept_name, hps in concept_hps.items():
            # Pick shortest path (closest to root = most significant heading)
            best_hp = min(hps, key=lambda k: k.count("/"))
            best_ph = self._path_index.get(best_hp)
            if not best_ph or best_ph not in self._nodes:
                continue
            self._concept_map[concept_name] = best_ph
            self._nodes[best_ph]["concepts"].add(concept_name)
            bound += 1

            # semantic_parent edge: use parent segment from heading path
            gnode = graph._nodes.get(concept_name)
            if gnode:
                segments = self._nodes[best_ph]["segments"]
                # The direct parent is the second-to-last segment
                if len(segments) >= 2:
                    parent_name = segments[-2]
                    if parent_name != concept_name:
                        # Find or create parent's SemanticPath node
                        parent_key = "/".join(segments[:-1])
                        parent_ph = self._path_index.get(parent_key)
                        if not parent_ph or parent_ph not in self._nodes:
                            parent_ph = self._hash_path(segments[:-1])
                            self._nodes[parent_ph] = {
                                "segments": segments[:-1],
                                "parents": [], "children": [best_ph],
                                "document_refs": self._nodes[best_ph]["document_refs"],
                                "concepts": set(), "cross_weight": 1,
                            }
                            self._path_index[parent_key] = parent_ph
                            self._nodes[best_ph]["parents"].append(parent_ph)
                        gnode.setdefault("relations", []).append({
                            "target": parent_name,
                            "type": "semantic_parent",
                            "weight": 0.8,
                        })

        return bound

    @staticmethod
    def _hash_path(segments: List[str]) -> str:
        import hashlib
        return hashlib.md5("/".join(segments).encode()).hexdigest()[:12]


def _camel_words_in(camel_name: str, text: str) -> bool:
    """Check if all words from a CamelCase name appear in text.
    E.g., "ContextCompiler" → ["context", "compiler"] → check both in text.
    """
    import re
    words = re.findall(r'[a-z]+', camel_name)
    if len(words) < 2:
        return False
    return all(w in text for w in words)


# ---- data classes ----

class SemanticPath:
    """Concept hierarchy path node."""

    def __init__(self, path_hash: str, segments: List[str],
                 parents: List[str], children: List[str],
                 document_refs: List[str], concepts: Set[str]):
        self.path_hash = path_hash
        self.segments = segments
        self.parents = parents
        self.children = children
        self.document_refs = document_refs
        self.concepts = concepts

    @classmethod
    def from_node(cls, ph: str, node: dict) -> "SemanticPath":
        return cls(
            path_hash=ph,
            segments=node.get("segments", []),
            parents=node.get("parents", []),
            children=node.get("children", []),
            document_refs=node.get("document_refs", []),
            concepts=node.get("concepts", set()),
        )

    def __repr__(self):
        return f"SemanticPath({'/'.join(self.segments)} children={len(self.children)})"


class DocumentPath:
    """Physical location of content in a document."""

    def __init__(self, source: str, heading_chain: List[str],
                 concepts: List[str] = None):
        self.source = source
        self.heading_chain = heading_chain
        self.concepts = concepts or []
