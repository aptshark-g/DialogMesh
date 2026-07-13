"""WorldParams: centralized parameters for the Semantic World Model.

All thresholds, weights, and strategy names are defined here with defaults
matching DESIGN_SEMANTIC_WORLD_MODEL.md. When a centralized ParameterRegistry
is built, these params can be migrated there.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class WorldParams:
    """Centralized parameters for all Semantic World Model components.

    Usage:
        params = WorldParams()
        detector = CommunityDetector(resolution=params.community_resolution)
        strategy = StructuralImportanceStrategy.from_name(params.importance_strategy)
        backbone = compute_backbone_scores(graph, structural, **params.backbone_weights)
    """

    # ---- Community Detection ----
    community_resolution: float = 1.0
    """Louvain resolution: higher = more/finer communities."""

    community_random_seed: int = 42
    """Random seed for Louvain community detection."""

    community_anchor_size: int = 5
    """Default anchor size for community index anchors."""

    # ---- Structural Importance ----
    importance_strategy: str = "tiered"
    """Default strategy: tiered | betweenness | k_sampling | community_chunk | pagerank | degree | hybrid."""

    importance_tier0_max: int = 5000
    """Tier 0: max nodes for exact betweenness."""

    importance_tier1_max: int = 20000
    """Tier 1: max nodes for k-sampling."""

    importance_tier2_max: int = 50000
    """Tier 2: max nodes for community chunk."""

    importance_k_sampling_size: int = 1000
    """K for Brandes k-sampling."""

    importance_community_resolution: float = 1.0
    """Louvain resolution for community chunk strategy."""

    pagerank_alpha: float = 0.85
    """PageRank damping factor (0-1). Higher = more weight on incoming edges."""

    # ---- Backbone Score Fusion Weights ----
    backbone_weights: dict = field(default_factory=lambda: {
        "w_structural": 0.30,
        "w_runtime": 0.30,
        "w_commit": 0.20,
        "w_retrieval": 0.20,
    })

    # ---- Hybrid Strategy Weights ----
    hybrid_weights: dict = field(default_factory=lambda: {
        "w_betweenness": 0.40,
        "w_pagerank": 0.30,
        "w_degree": 0.30,
    })

    # ---- Context Compiler ----
    compiler_max_nodes: int = 300
    """Default max nodes for subgraph compilation."""

    compiler_token_budget: int = 2000
    """Target token budget for compiled context."""

    compiler_fallback_seed_count: int = 5
    """Number of backbone nodes used as seeds when no intent is given."""

    compiler_keyword_seed_count: int = 10
    """Max seeds from keyword matching."""

    compiler_token_base: int = 500
    """Base token estimate for subgraph (nodes + edges overhead)."""

    compiler_token_per_node: int = 5
    """Estimated tokens per node in the subgraph."""

    # ---- Incremental Update ----
    incremental_enabled: bool = True
    """Whether to process git.commit events for incremental updates."""

        # ---- LSP (Tier 2) ----
    lsp_enabled: bool = False
    """Enable LSP-based deep extraction (future)."""

    lsp_languages: list = field(default_factory=lambda: ["python"])
    """Languages to attempt LSP connection for."""

# ---- Extraction ----
    extraction_tier: int = 1
    """Default extraction tier: 0 (imports only) or 1 (full AST)."""

    # ---- Bayesian Optimizer ----
    optimizer_enabled: bool = False
    """Enable Bayesian parameter optimization."""

    optimizer_top_params: list = field(default_factory=lambda: [
        "min_support", "max_conflict", "min_stability",
        "community_resolution", "compiler_max_nodes",
    ])
    """Parameters under Bayesian optimization. Start with 5 core params."""

    # ---- Hypothesis Engine (frozen thresholds) ----
    min_support: int = 8
    """Min support votes for Hypothesis to freeze into Knowledge."""

    max_conflict: int = 3
    """Max conflict votes before Hypothesis is rejected."""

    min_stability: float = 0.70
    """Min stability score for Hypothesis freeze."""

    # ---- Compiler ----
    compiler_max_nodes: int = 300
    """Max nodes for subgraph compilation."""


# Global defaults instance
DEFAULTS = WorldParams()


def get_world_params(overrides: dict = None) -> WorldParams:
    """Get WorldParams with optional overrides.

    Later, this can be backed by a centralized ParameterRegistry.
    """
    if overrides is None:
        return DEFAULTS
    # Create a copy with overrides applied
    params = WorldParams()
    for key, value in overrides.items():
        if hasattr(params, key):
            setattr(params, key, value)
    return params
