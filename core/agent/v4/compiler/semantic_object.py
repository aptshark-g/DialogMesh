"""SemanticObject — v4 纯数据对象模型.

Design: docs/v3.0/DESIGN_SEMANTIC_OBJECT.md §2

SemanticObject is pure data: identity + composition + projections + relations.
All behaviour lives in ObjectRuntime. No rendering logic here.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class CompositionEdge:
    """Typed parent-child edge in object composition.

    Not just "A contains B" — the type says HOW.
    contains | pipeline | phase | owns | implements | strategy | refines
    """
    target: str
    type: str = "contains"
    weight: float = 1.0


@dataclass
class LOD:
    """Continuous level-of-detail. Not discrete scale.

    level 1.0 = name + 1-line summary
    level 2.0 = composition children + definitions
    level 3.0 = expanded children + relations
    level 4.0 = full leaf content
    """
    level: float = 2.0
    token_budget: int = 1800
    strategy: str = "structural_summary"

    @classmethod
    def from_horizon(cls, horizon) -> "LOD":
        """From PerspectivePlanner's Horizon."""
        from core.agent.v4.compiler.perspective_planner import Horizon
        if isinstance(horizon, Horizon):
            return cls(
                level=float(horizon.depth),
                token_budget=horizon.budget,
                strategy=horizon.strategy,
            )
        return cls(level=float(horizon.depth) if hasattr(horizon, 'depth') else 2.0)


@dataclass
class SemanticObject:
    """v4 first-class object — pure data.

    A concept that:
      - has internal structure (composition_edges) — expand to zoom in
      - has multiple projections (projection_resolvers) — different worlds
      - has horizontal relations (relations) — same level connections
      - has a position in concept space (semantic_path)

    No rendering logic. No storage access. Just data.
    """
    identity: str
    name: str
    composition_edges: List[CompositionEdge] = field(default_factory=list)
    projection_resolvers: Dict[str, str] = field(default_factory=dict)
    semantic_path: List[str] = field(default_factory=list)
    relations: List[dict] = field(default_factory=list)

    def __hash__(self):
        return hash(self.identity)

    def __eq__(self, other):
        return isinstance(other, SemanticObject) and self.identity == other.identity


def build_from_graph(graph, semantic_index, pool=None) -> Dict[str, SemanticObject]:
    """Build SemanticObject dict from ConceptGraph + SemanticIndex.

    Each graph node becomes a SemanticObject:
      - semantic_path ← SemanticIndex.locate(name), cleaned of [chunk N] junk
      - composition_edges ← parent→child from semantic_parent (filtered)
      - intermediate objects created for non-leaf heading segments
      - relations ← non-parent edges
      - projection_resolvers["design"] ← "DesignResolver"
    """
    objects: Dict[str, SemanticObject] = {}
    import re
    _chunk_re = re.compile(r'\[chunk\s*\d+\]')

    # Helper: clean heading path segments
    def _clean_segments(segments: list) -> list:
        return [re.sub(_chunk_re, '', s).strip() for s in segments if s and not _chunk_re.match(s.strip())]

    # Phase 1: build from graph nodes
    for name, node in graph._nodes.items():
        path = semantic_index.locate(name)
        raw_segments = path.segments if path else []
        segments = _clean_segments(raw_segments)

        # Filter: keep only non-self-referential, non-parent-edge relations
        relations = [r for r in node.get("relations", [])
                     if r.get("type") != "semantic_parent"]

        obj = SemanticObject(
            identity=name,
            name=name,
            composition_edges=[],
            projection_resolvers={"design": "DesignResolver",
                                  "causal": "CausalResolver",
                                  "behavior": "BehaviorResolver",
                                  "implementation": "ImplementationResolver"},
            semantic_path=segments,
            relations=relations,
        )
        objects[name] = obj

    # Phase 2: create intermediate objects for heading segments
    # that exist in SemanticIndex but not in ConceptGraph
    intermediate_count = 0
    for ph, snode in semantic_index._nodes.items():
        segments = _clean_segments(snode.get("segments", []))
        if len(segments) < 2:
            continue
        # The "leaf" segment name might match a concept node
        leaf_name = segments[-1]
        if leaf_name in objects:
            continue
        # Create an intermediate if this heading path is meaningful
        identity = f"intermediate:{leaf_name}"
        if identity not in objects:
            objects[f"intermediate:{leaf_name}"] = SemanticObject(
                identity=f"intermediate:{leaf_name}",
                name=leaf_name,
                composition_edges=[],
                projection_resolvers={"design": "DesignResolver",
                                      "causal": "CausalResolver",
                                      "behavior": "BehaviorResolver",
                                      "implementation": "ImplementationResolver"},
                semantic_path=segments,
                relations=[],
            )
            intermediate_count += 1

    # Phase 3: wire composition from semantic_parent edges (parent→child)
    for name, node in graph._nodes.items():
        for rel in node.get("relations", []):
            if rel.get("type") != "semantic_parent":
                continue
            parent_name = rel.get("target", "")
            if not parent_name or parent_name == name:
                continue  # skip self-referential
            # Find parent object (may be intermediate)
            parent_obj = objects.get(parent_name)
            if not parent_obj:
                parent_obj = objects.get(f"intermediate:{parent_name}")
            if not parent_obj:
                continue
            child_obj = objects.get(name)
            if not child_obj:
                continue
            # Add only if not already there
            if not any(e.target == name for e in parent_obj.composition_edges):
                parent_obj.composition_edges.append(CompositionEdge(
                    target=name,
                    type=_infer_comp_type(rel.get("type", "contains")),
                ))

    # Phase 4: wire intermediate objects between heading levels
    for obj in list(objects.values()):
        if not obj.semantic_path or len(obj.semantic_path) < 2:
            continue
        parent_seg = obj.semantic_path[-2]
        # Try to find parent (concept or intermediate)
        parent_obj = objects.get(parent_seg)
        if not parent_obj:
            parent_obj = objects.get(f"intermediate:{parent_seg}")
        if parent_obj and obj.identity != parent_obj.identity:
            if not any(e.target == obj.identity for e in parent_obj.composition_edges):
                parent_obj.composition_edges.append(CompositionEdge(
                    target=obj.identity,
                    type=_infer_comp_type("contains"),
                ))

    return objects


def _infer_comp_type(rel_type: str) -> str:
    """Infer composition type from relation type."""
    type_map = {
        "semantic_parent": "contains",
        "pipeline": "pipeline",
        "phase": "phase",
        "owns": "owns",
        "implements": "implements",
        "strategy": "strategy",
        "refines": "refines",
    }
    return type_map.get(rel_type, "contains")
