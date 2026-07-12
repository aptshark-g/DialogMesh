"""Semantic World Model: structural world IR layer.

Layer constraint: NEVER imports tree-sitter, LSP, or any adapter-specific code.
The World layer only depends on: stdlib, networkx, and v4 ParameterRegistry.
"""
from core.agent.v4.world.schema import (
    Location,
    ReferenceUnit,
    StructuralEdge,
    Community,
    StructuralWorldGraph,
    SubgraphResult,
)

__all__ = [
    "CommunityDetector",
    "StructuralImportanceStrategy",
    "BetweennessStrategy",
    "PageRankStrategy",
    "DegreeStrategy",
    "HybridStrategy",
    "StructureExtractor",
    "Location",
    "ReferenceUnit",
    "StructuralEdge",
    "Community",
    "StructuralWorldGraph",
    "SubgraphResult",
    "IncrementalUpdater",
    "WorldParams",
    "get_world_params",
    "StructuralContextCompiler",
]

from core.agent.v4.world.extractor import StructureExtractor
from core.agent.v4.world.community import CommunityDetector
from core.agent.v4.world.importance import (StructuralImportanceStrategy,
    BetweennessStrategy, PageRankStrategy, DegreeStrategy,
    HybridStrategy, compute_backbone_scores)
from core.agent.v4.world.updater import IncrementalUpdater
from core.agent.v4.world.params import WorldParams, get_world_params
from core.agent.v4.world.compiler import StructuralContextCompiler
