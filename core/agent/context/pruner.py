"""Subgraph overflow pruning: 4-round trim + 3-step landing.

Design ref: docs/v3.0/DESIGN_CROSS_DOMAIN_CONTEXT.md §11.3–11.4

Implements the full algorithm:
- R1: Capacitance sort — mark bottom 30% as prune candidates
- R2: Structural protection — remove candidates with betweenness > threshold
- R3: Temporal repair — remove recently accessed nodes (< recency_turns)
- R4: Compression — summarize remaining candidates, expand range if still over budget
- 3-step landing: old topic summary → keep connectors → expand new topic
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class PruningNode:
    """A node in the subgraph that may be pruned or compressed."""
    node_id: str
    domain: str
    content: str
    activation_count: int = 0
    last_accessed_turn: int = 0
    betweenness: float = 0.0
    estimated_tokens: int = 0
    cross_ref_ids: List[str] = field(default_factory=list)
    compressed: bool = False
    summary: Optional[str] = None

    @property
    def effective_tokens(self) -> int:
        """Return compressed token count if compressed, else original."""
        return max(8, self.estimated_tokens // 3) if self.compressed else self.estimated_tokens

    @property
    def effective_content(self) -> str:
        """Return compressed summary if compressed, else original content."""
        return self.summary if self.compressed else self.content


@dataclass
class PruningConfig:
    """Three-dimensional scoring weights per intent."""
    alpha: float = 0.3      # frequency weight
    beta: float = 0.2       # recency weight
    gamma: float = 0.5      # structural weight
    struct_threshold: float = 0.6
    recency_turns: int = 3
    compression_ratio: float = 0.33  # compressed tokens = original * ratio
    min_tokens_after_compress: int = 8


# Intent-specific pruning configurations (§11.2)
_INTENT_CONFIG: Dict[str, PruningConfig] = {
    "task":       PruningConfig(0.3, 0.2, 0.5, struct_threshold=0.6, recency_turns=3),
    "discussion": PruningConfig(0.2, 0.5, 0.3, struct_threshold=0.5, recency_turns=2),
    "correction": PruningConfig(0.5, 0.3, 0.2, struct_threshold=0.4, recency_turns=3),
    "topic_switch": PruningConfig(0.1, 0.6, 0.3, struct_threshold=0.5, recency_turns=2),
    "casual":     PruningConfig(0.4, 0.4, 0.2, struct_threshold=0.4, recency_turns=2),
    "query":      PruningConfig(0.3, 0.3, 0.4, struct_threshold=0.5, recency_turns=3),
}


def _score(n: PruningNode, c: PruningConfig, turn: int) -> float:
    """Three-dimensional node retention score (§11.2).

    Higher score = more important = less likely to be pruned.
    """
    recency = max(0, turn - n.last_accessed_turn)
    return (
        c.alpha * n.activation_count
        - c.beta * recency
        + c.gamma * n.betweenness
    )


def _compress_node(n: PruningNode, cfg: PruningConfig) -> None:
    """Compress a node: truncate content, reduce token estimate."""
    if n.compressed:
        return
    # Summarize: first 40 chars + ellipsis, or existing summary
    if n.summary is None:
        n.summary = n.content[:40] + "…" if len(n.content) > 40 else n.content
    n.estimated_tokens = max(
        cfg.min_tokens_after_compress,
        int(n.estimated_tokens * cfg.compression_ratio)
    )
    n.compressed = True
    logger.debug("Compressed node %s: %d -> %d tokens", n.node_id, n.estimated_tokens, n.effective_tokens)


def _domain_compress(n: PruningNode, cfg: PruningConfig) -> None:
    """Domain-aware compression (§11.3 R4).

    Different domains compress differently:
    - C (Conversation): L2 Summary (topic-level)
    - E (Engineering): module name + status tags only
    - P (Profile): only dimensions relevant to current intent
    - B (Behavior): last N operations only
    - K (Causal): edges with confidence > 0.8 only
    """
    if n.compressed:
        return

    domain = n.domain.upper()
    if domain == "C":
        n.summary = f"[Topic:{n.node_id}] {n.content[:30]}…"
    elif domain == "E":
        n.summary = f"[Module:{n.node_id}] {n.content[:25]}…"
    elif domain == "P":
        n.summary = f"[Profile:{n.node_id}] {n.content[:25]}…"
    elif domain == "B":
        n.summary = f"[Action:{n.node_id}] {n.content[:25]}…"
    elif domain == "K":
        n.summary = f"[Causal:{n.node_id}] {n.content[:25]}…"
    else:
        n.summary = n.content[:40] + "…" if len(n.content) > 40 else n.content

    n.estimated_tokens = max(
        cfg.min_tokens_after_compress,
        int(n.estimated_tokens * cfg.compression_ratio)
    )
    n.compressed = True


class SubgraphPruner:
    """4-round trim + 3-step landing subgraph overflow pruner.

    Implements the full algorithm from DESIGN_CROSS_DOMAIN_CONTEXT.md §11.3–11.4.
    """

    def __init__(self, cfg: Optional[PruningConfig] = None):
        self._cfg = cfg or PruningConfig()

    def prune(self, nodes: List[PruningNode], budget: int, turn: int, intent: str = "task") -> List[PruningNode]:
        """Execute 4-round trim on nodes to fit within budget.

        R1: Capacitance sort — mark bottom 30% as candidates
        R2: Structural protection — remove high-betweenness candidates
        R3: Temporal repair — remove recently accessed candidates
        R4: Compression — compress remaining candidates, expand if still over budget

        Args:
            nodes: List of PruningNode to trim.
            budget: Maximum token budget.
            turn: Current turn number (for recency calculation).
            intent: Intent category for weight selection.

        Returns:
            Trimmed list of nodes within budget.
        """
        if not nodes:
            return []

        cfg = _INTENT_CONFIG.get(intent, self._cfg)
        total_tokens = sum(n.effective_tokens for n in nodes)
        if total_tokens <= budget:
            return list(nodes)

        # Make a copy to avoid mutating input
        working = [PruningNode(
            node_id=n.node_id, domain=n.domain, content=n.content,
            activation_count=n.activation_count,
            last_accessed_turn=n.last_accessed_turn,
            betweenness=n.betweenness,
            estimated_tokens=n.estimated_tokens,
            cross_ref_ids=list(n.cross_ref_ids),
            compressed=n.compressed, summary=n.summary,
        ) for n in nodes]

        # R1: Capacitance sort — mark bottom 30% as candidates
        scored = [(n, _score(n, cfg, turn)) for n in working]
        scored.sort(key=lambda x: x[1])  # lowest score first = most pruneable
        candidate_count = max(1, int(len(scored) * 0.3))
        candidates: Set[str] = {n.node_id for n, _ in scored[:candidate_count]}
        logger.debug("R1: %d/%d nodes marked as prune candidates", len(candidates), len(working))

        # R2: Structural protection — remove high-betweenness candidates
        protected = {n.node_id for n in working if n.betweenness > cfg.struct_threshold}
        candidates -= protected
        logger.debug("R2: removed %d struct-protected nodes from candidates", len(protected & candidates))

        # R3: Temporal repair — remove recently accessed candidates
        recent = {n.node_id for n in working if turn - n.last_accessed_turn < cfg.recency_turns}
        candidates -= recent
        logger.debug("R3: removed %d recent nodes from candidates", len(recent & candidates))

        # R4: Compression — compress remaining candidates
        for n in working:
            if n.node_id in candidates:
                _domain_compress(n, cfg)

        # Check if still over budget after compression
        compressed_total = sum(n.effective_tokens for n in working)
        if compressed_total > budget:
            # Expand candidate range to 50% and compress more
            expanded_candidates = {n.node_id for n, _ in scored[:max(1, int(len(scored) * 0.5))]}
            expanded_candidates -= protected
            expanded_candidates -= recent
            for n in working:
                if n.node_id in expanded_candidates and n.node_id not in candidates:
                    _domain_compress(n, cfg)
            logger.debug("R4 expanded: compressed %d additional nodes", len(expanded_candidates - candidates))

        # Greedy selection: highest score first, within budget
        working.sort(key=lambda n: _score(n, cfg, turn), reverse=True)
        out: List[PruningNode] = []
        used = 0
        for n in working:
            if used + n.effective_tokens <= budget:
                out.append(n)
                used += n.effective_tokens
            else:
                # Try to compress this node to fit
                if not n.compressed:
                    _domain_compress(n, cfg)
                    if used + n.effective_tokens <= budget:
                        out.append(n)
                        used += n.effective_tokens

        logger.info(
            "Pruned %d -> %d nodes (%d -> %d tokens) for intent=%s",
            len(nodes), len(out), total_tokens, used, intent
        )
        return out

    def topic_switch_landing(self, old_nodes: List[PruningNode], new_nodes: List[PruningNode],
                             budget: int, turn: int) -> List[PruningNode]:
        """Three-step landing for topic switch (§11.4).

        Step 1: Compress old topic nodes (except connectors)
        Step 2: Keep connector nodes (high betweenness)
        Step 3: Expand new topic with remaining budget

        Args:
            old_nodes: Nodes from the previous topic.
            new_nodes: Nodes from the new topic.
            budget: Total token budget.
            turn: Current turn number.

        Returns:
            Combined list of kept old nodes + pruned new nodes.
        """
        cfg = _INTENT_CONFIG.get("topic_switch", self._cfg)

        # Step 1: Compress old topic nodes (except connectors)
        old_working = [PruningNode(
            node_id=n.node_id, domain=n.domain, content=n.content,
            activation_count=n.activation_count,
            last_accessed_turn=n.last_accessed_turn,
            betweenness=n.betweenness,
            estimated_tokens=n.estimated_tokens,
            cross_ref_ids=list(n.cross_ref_ids),
            compressed=n.compressed, summary=n.summary,
        ) for n in old_nodes]

        for n in old_working:
            if n.betweenness <= cfg.struct_threshold:
                _domain_compress(n, cfg)

        # Step 2: Keep connector nodes (high betweenness) uncompressed
        keep = [n for n in old_working if n.betweenness > cfg.struct_threshold]
        keep += [n for n in old_working if n.betweenness <= cfg.struct_threshold and n.compressed]

        keep_tokens = sum(n.effective_tokens for n in keep)
        remaining_budget = max(0, budget - keep_tokens)

        logger.debug(
            "Topic switch landing: keep %d old nodes (%d tokens), "
            "remaining budget for new: %d",
            len(keep), keep_tokens, remaining_budget
        )

        # Step 3: Expand new topic with remaining budget
        pruned_new = self.prune(new_nodes, remaining_budget, turn, "topic_switch")

        # Combine: keep connectors + compressed old + pruned new
        result = keep + pruned_new
        total = sum(n.effective_tokens for n in result)
        logger.info(
            "Topic switch: %d old + %d new -> %d total nodes (%d tokens)",
            len(old_nodes), len(new_nodes), len(result), total
        )
        return result

    def get_pruning_stats(self, original: List[PruningNode], pruned: List[PruningNode]) -> Dict[str, any]:
        """Return statistics about the pruning operation."""
        orig_tokens = sum(n.estimated_tokens for n in original)
        pruned_tokens = sum(n.effective_tokens for n in pruned)
        compressed_count = sum(1 for n in pruned if n.compressed)
        return {
            "original_nodes": len(original),
            "pruned_nodes": len(pruned),
            "original_tokens": orig_tokens,
            "pruned_tokens": pruned_tokens,
            "compression_ratio": pruned_tokens / orig_tokens if orig_tokens > 0 else 0.0,
            "compressed_nodes": compressed_count,
            "removed_nodes": len(original) - len(pruned),
        }
