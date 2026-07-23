"""Semantic World Model: structural world IR layer.

Layer constraint: NEVER imports tree-sitter, LSP, or any adapter-specific code.
The World layer only depends on: stdlib, networkx, and v4 ParameterRegistry.
"""
from core.agent.world.schema import (
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

from core.agent.world.extractor import StructureExtractor
from core.agent.world.community import CommunityDetector
from core.agent.world.importance import (StructuralImportanceStrategy,
    BetweennessStrategy, PageRankStrategy, DegreeStrategy,
    HybridStrategy, compute_backbone_scores)
from core.agent.world.updater import IncrementalUpdater
from core.agent.world.params import WorldParams, get_world_params
from core.agent.world.compiler import StructuralContextCompiler
