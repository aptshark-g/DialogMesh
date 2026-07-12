"""Semantic World Model: Schema definitions for Phase 1.

ReferenceUnit, StructuralEdge, StructuralWorldGraph, and supporting types.
This is the World layer -- never imports tree-sitter or any adapter-specific code.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Location:
    """File location with optional line range."""
    file_path: str
    start_line: int = 0
    end_line: int = 0
    start_col: int = 0
    end_col: int = 0


@dataclass
class ReferenceUnit:
    """The only node criterion: anything that can be externally referenced.

    Cross-language unified: Python class == Rust struct == unit_type="class".
    Not nodes: if(){}, for(){}, while(){}, local variables, comments, magic numbers, inline lambdas.
    """
    unit_id: str                    # "pkg::module::ClassName" or file path
    unit_type: str                  # "file" | "class" | "function" | "variable" | "module"
    name: str                       # human-readable name
    world: str                      # "code" | "cad" | "unity" | "dom" | "db"
    language: str = ""              # "python" | "rust" | "java" | ...
    location: Location | None = None
    attributes: dict = field(default_factory=dict)  # world-specific metadata
    backbone_score: float = 0.0     # backbone coloring score (0.0-1.0)
    last_updated: float = field(default_factory=time.time)

    def is_code(self) -> bool:
        return self.world == "code"

    def qualified_name(self) -> str:
        """Full qualified name for display."""
        if self.language:
            return f"{self.name} [{self.language}]"
        return self.name


@dataclass
class StructuralEdge:
    """Multi-type edge between ReferenceUnits.

    Different edge types carry different semantics and propagation weights.
    """
    edge_id: str
    edge_type: str                  # "imports" | "calls" | "references" | "overrides" | ...
    source_id: str                  # source ReferenceUnit ID
    target_id: str                  # target ReferenceUnit ID
    weight: float = 1.0             # propagation weight for community detection
    source: str = ""                # "static" | "trace" | "commit" | "test"
    confidence: float = 1.0         # 0.0-1.0

    # Edge type propagation weights (used by CommunityDetector)
    PROPAGATION_WEIGHTS: dict = field(default_factory=lambda: {
        "imports": 0.30,
        "calls": 0.25,
        "co_changes": 0.25,
        "overrides": 0.20,
        "implements": 0.20,
        "constrains": 0.20,
        "references": 0.15,
        "generates": 0.15,
        "tests": 0.10,
    }, init=False, repr=False)

    def effective_weight(self) -> float:
        """Weight adjusted by edge type's propagation factor."""
        type_weight = self.PROPAGATION_WEIGHTS.get(self.edge_type, 0.10)
        return self.weight * type_weight * self.confidence


@dataclass
class Community:
    """A detected community (module boundary) in the structural graph."""
    community_id: str
    unit_ids: List[str] = field(default_factory=list)
    name: str = ""
    anchor_size: int = 5            # dynamic index anchor size (via ParameterRegistry)


@dataclass
class StructuralWorldGraph:
    """Container for the full structural world model.

    Holds all ReferenceUnits, edges, communities, and backbone scores
    for a single world (e.g., "code").
    """
    graph_id: str
    world: str                      # "code" | "cad" | ...
    units: Dict[str, ReferenceUnit] = field(default_factory=dict)
    edges: List[StructuralEdge] = field(default_factory=list)
    communities: Dict[str, List[str]] = field(default_factory=dict)  # community_id -> unit_ids
    backbone: Dict[str, float] = field(default_factory=dict)         # unit_id -> backbone_score
    created_at: float = field(default_factory=time.time)
    last_extracted_at: float = 0.0

    @property
    def node_count(self) -> int:
        return len(self.units)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def get_unit(self, unit_id: str) -> Optional[ReferenceUnit]:
        return self.units.get(unit_id)

    def get_edges_for(self, unit_id: str) -> List[StructuralEdge]:
        """All edges where unit_id is either source or target."""
        return [e for e in self.edges if e.source_id == unit_id or e.target_id == unit_id]

    def get_neighbors(self, unit_id: str) -> List[str]:
        """All neighbor unit IDs (both directions)."""
        neighbors = set()
        for e in self.edges:
            if e.source_id == unit_id:
                neighbors.add(e.target_id)
            elif e.target_id == unit_id:
                neighbors.add(e.source_id)
        return list(neighbors)

    def to_networkx(self):
        """Convert to networkx Graph for community detection / betweenness."""
        import networkx as nx
        G = nx.Graph()
        for uid in self.units:
            G.add_node(uid)
        for e in self.edges:
            G.add_edge(e.source_id, e.target_id, weight=e.effective_weight())
        return G


@dataclass
class SubgraphResult:
    """Output of StructuralContextCompiler.compile_subgraph()."""
    nodes: List[ReferenceUnit] = field(default_factory=list)
    edges: List[StructuralEdge] = field(default_factory=list)
    backbone_units: List[str] = field(default_factory=list)  # high-backbone node IDs
    total_tokens_estimate: int = 0
