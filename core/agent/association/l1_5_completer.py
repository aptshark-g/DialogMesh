"""L1.5 Collaborative Completer — Syntax candidates + LLM ranking + consensus fusion.

Design: docs/BUSINESS_CHAIN_06_ASSOCIATION.md §2.2
Pattern: Syntax produces candidates, LLM ranks+reasons, consensus=high confidence, divergence→meta.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import json, logging, re
from enum import Enum

logger = logging.getLogger(__name__)


class CandidateSource(Enum):
    SYNTAX = "syntax"
    LLM = "llm"
    CONSENSUS = "consensus"


@dataclass
class CompletionCandidate:
    entity: str
    cluster_id: str
    confidence: float  # 0-1
    source: CandidateSource
    reasoning: str = ""
    recency: int = 999  # turns since last seen

    @property
    def is_consensus(self) -> bool:
        return self.source == CandidateSource.CONSENSUS


@dataclass
class CompletionResult:
    completed_text: str
    candidates: List[CompletionCandidate]
    consensus: bool  # True if syntax+LLM agree
    ambiguous: bool  # True if multiple viable candidates
    reasoning_trace: str = ""


class CollaborativeCompleter:
    """Syntax+LLM collaborative entity completion.

    Syntax: modifier_context → entity_cluster search → syntax_candidates
    LLM: receives candidates + text → ranks + reasons
    Fusion: intersect syntax_candidates ∩ llm_candidates → consensus
    """

    def __init__(self, llm_provider=None):
        self.llm = llm_provider

    def complete(
        self,
        text: str,
        modifier_context: str,
        entity_clusters: Dict[str, dict],
    ) -> CompletionResult:
        """Complete implicit entities: syntax search → LLM rank → consensus."""
        
        # Step 1: Syntax produces candidates from modifier_context + entity_clusters
        syntax_candidates = self._syntax_search(modifier_context, entity_clusters)
        
        # Step 2: If no modifiers and no clusters, no completion needed
        if not modifier_context and not entity_clusters:
            return CompletionResult(
                completed_text=text,
                candidates=[],
                consensus=True,
                ambiguous=False,
                reasoning_trace="no_context"
            )
        
        # Step 3: LLM ALWAYS participates when available — not just syntax fallback
        llm_candidates = self._llm_rank(text, syntax_candidates, modifier_context, entity_clusters)
        
        # Step 4: Consensus fusion
        result = self._fuse(syntax_candidates, llm_candidates, text, entity_clusters)
        return result

    def _syntax_search(
        self, modifier_context: str, entity_clusters: Dict[str, dict]
    ) -> List[CompletionCandidate]:
        """Search entity clusters using modifier context as query."""
        if not modifier_context or not entity_clusters:
            return []
        
        candidates = []
        query_terms = set(re.findall(r'[\u4e00-\u9fff]{2,}|[A-Z][a-z]+', modifier_context.lower()))
        
        for cid, cluster in entity_clusters.items():
            entities = cluster.get("entities", [])
            last_seen = cluster.get("last_seen", 999)
            
            # Score: how many query terms overlap with cluster entities
            entity_text = " ".join(str(e).lower() for e in entities)
            overlap = sum(1 for t in query_terms if t.lower() in entity_text)
            
            if overlap > 0 or last_seen == 0:
                conf = min(0.3 * overlap + 0.4 * (1.0 / (last_seen + 1)), 0.8)
                candidates.append(CompletionCandidate(
                    entity=entities[0] if entities else str(cid),
                    cluster_id=cid,
                    confidence=conf,
                    source=CandidateSource.SYNTAX,
                    reasoning=f"modifier match: {overlap} terms, recency={last_seen}",
                    recency=last_seen,
                ))
        
        # Sort: confidence desc, then recency asc
        candidates.sort(key=lambda c: (-c.confidence, c.recency))
        return candidates[:5]

    def _llm_rank(
        self,
        text: str,
        syntax_candidates: List[CompletionCandidate],
        modifier_context: str,
        entity_clusters: Dict[str, dict],
    ) -> List[CompletionCandidate]:
        """LLM ranks candidates with reasoning. Always called when LLM available."""
        if not self.llm:
            # No LLM: syntax-only
            if syntax_candidates:
                return [CompletionCandidate(
                    entity=c.entity, cluster_id=c.cluster_id,
                    confidence=c.confidence * 0.7, source=CandidateSource.SYNTAX,
                    reasoning=c.reasoning + " (syntax-only)", recency=c.recency,
                ) for c in syntax_candidates]
            return []

        # Build prompt with modifier context + entity clusters + syntax hints
        cluster_desc = "\n".join(
            f"  {cid}: {cluster.get('entities', [])} (last_seen={cluster.get('last_seen', '?')})"
            for cid, cluster in entity_clusters.items()
        )
        syn_hints = "\n".join(
            f"  [{c.cluster_id}] {c.entity} (conf={c.confidence:.2f})"
            for c in syntax_candidates
        ) if syntax_candidates else "  (none)"

        prompt = f"""Match this text to entity clusters. Modifiers from syntax parsing may be noisy — trust the raw text more.

Raw text: "{text[:200]}"
Syntax modifiers (may be incomplete): "{modifier_context}"

Entity clusters:
{cluster_desc}

Syntax hints (from modifier matching):
{syn_hints}

Return JSON: {{"ranking": [
  {{"cluster_id": "...", "entity": "...", "confidence": 0.0-1.0, "reason": "..."}}
], "ambiguous": true/false}}"""

        try:
            response = self.llm.generate(prompt, max_tokens=300)
            llm_data = json.loads(response) if response else {}
            ranking = llm_data.get("ranking", [])
            
            return [CompletionCandidate(
                entity=item.get("entity", ""),
                cluster_id=item.get("cluster_id", ""),
                confidence=item.get("confidence", 0.5),
                source=CandidateSource.LLM,
                reasoning=item.get("reason", ""),
                recency=99,
            ) for item in ranking]
        except Exception as e:
            logger.debug("LLM ranking failed: %s", e)
            return []

    def _fuse(
        self,
        syntax_candidates: List[CompletionCandidate],
        llm_candidates: List[CompletionCandidate],
        text: str,
        entity_clusters: Dict[str, dict],
    ) -> CompletionResult:
        """Fuse syntax and LLM: consensus intersection → high confidence."""
        
        if not syntax_candidates and not llm_candidates:
            return CompletionResult(
                completed_text=text, candidates=[], consensus=True,
                ambiguous=False, reasoning_trace="no_candidates"
            )
        
        if not syntax_candidates:
            # LLM-only: trust LLM if confidence high
            best = llm_candidates[0]
            if best.confidence >= 0.6:
                return CompletionResult(
                    completed_text=f"({best.entity}) {text}",
                    candidates=llm_candidates,
                    consensus=False, ambiguous=False,
                    reasoning_trace=f"llm_only(conf={best.confidence:.2f}): {best.reasoning}"
                )
            return CompletionResult(
                completed_text=text, candidates=llm_candidates,
                consensus=False, ambiguous=True,
                reasoning_trace=f"llm_low_conf({best.confidence:.2f})"
            )
        
        if not llm_candidates:
            # LLM unavailable — use best syntax candidate
            best = syntax_candidates[0]
            if best.confidence < 0.4:
                # Low confidence: don't force completion
                return CompletionResult(
                    completed_text=text, candidates=syntax_candidates,
                    consensus=False, ambiguous=True,
                    reasoning_trace=f"low_confidence({best.confidence:.2f})"
                )
            return CompletionResult(
                completed_text=f"({best.entity}) {text}",
                candidates=syntax_candidates,
                consensus=False,
                ambiguous=False,
                reasoning_trace=f"syntax_only: {best.reasoning}"
            )

        # Find intersection: clusters present in BOTH syntax and LLM
        syn_ids = {c.cluster_id for c in syntax_candidates}
        llm_ids = {c.cluster_id for c in llm_candidates}
        consensus_ids = syn_ids & llm_ids

        if consensus_ids:
            # Consensus: pick highest LLM-confidence among consensus
            best = max(
                [c for c in llm_candidates if c.cluster_id in consensus_ids],
                key=lambda c: c.confidence
            )
            return CompletionResult(
                completed_text=f"({best.entity}) {text}",
                candidates=[CompletionCandidate(
                    entity=best.entity,
                    cluster_id=best.cluster_id,
                    confidence=best.confidence,
                    source=CandidateSource.CONSENSUS,
                    reasoning=f"LLM+Syntax agree: {best.reasoning}",
                    recency=99,
                )],
                consensus=True,
                ambiguous=False,
                reasoning_trace=f"consensus: {best.cluster_id}"
            )

        # No consensus: ambiguous
        best_syn = syntax_candidates[0]
        best_llm = llm_candidates[0] if llm_candidates else None
        reason = f"syntax→{best_syn.cluster_id}, llm→{best_llm.cluster_id if best_llm else 'none'}"
        
        return CompletionResult(
            completed_text=text,  # Don't force completion on ambiguity
            candidates=syntax_candidates + llm_candidates,
            consensus=False,
            ambiguous=True,
            reasoning_trace=f"divergent: {reason}"
        )
