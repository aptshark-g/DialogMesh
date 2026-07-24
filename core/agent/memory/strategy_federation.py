"""Rule Validation Loop — strategy federation + meta-orchestrator.

Multiple clustering strategies (LLM, blueprint, Markov, greedy)
orchestrated as behavior patterns. No single "correct" algorithm.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
import logging, json, time

logger = logging.getLogger(__name__)


@dataclass
class ClusterState:
    """Current clustering state."""
    clusters: List[List[str]]     # [[entity1, entity2], [entity3], ...]
    cohesion_scores: List[float]  # per-cluster cohesion
    entropy: float = 0.0          # global entropy
    turn: int = 0


@dataclass
class StrategyAction:
    """One strategy's proposed adjustment."""
    name: str                     # "merge", "split", "pivot", "expand"
    strategy: str                 # "llm" | "blueprint" | "markov" | "greedy" | "user"
    target_clusters: List[int]    # which clusters to modify
    new_clusters: List[List[str]] # proposed new structure
    confidence: float = 0.5
    reasoning: str = ""


@dataclass
class ValidationResult:
    """Outcome of applying a strategy."""
    action: StrategyAction
    success: bool
    cohesion_after: float
    entropy_after: float
    timestamp: float = field(default_factory=time.time)


class StrategyFederation:
    """Multiple strategies, orchestrated as behavior patterns.

    Usage:
        fed = StrategyFederation()
        fed.register("llm", llm_strategy_fn)
        fed.register("blueprint", blueprint_fn)
        
        result = fed.adjust(current_clusters, context)
    """

    def __init__(self):
        self._strategies: Dict[str, Callable] = {}
        self._history: List[ValidationResult] = []
        self._strategy_scores: Dict[str, List[float]] = {}  # rolling success rates
        self._locked: Dict[str, List[int]] = {}  # strategy → clusters where it failed

    def register(self, name: str, strategy_fn: Callable):
        """Register a strategy. fn(clusters, context) → StrategyAction."""
        self._strategies[name] = strategy_fn

    def adjust(self, state: ClusterState, context: dict = None,
               preferred_strategy: str = None) -> List[StrategyAction]:
        """Federation adjustment: try strategies, record outcomes.

        Returns all proposed actions. Caller (meta-orchestrator) picks.
        """
        proposals = []

        # Phase 1: Generate proposals from all strategies
        for name, fn in self._strategies.items():
            if preferred_strategy and name != preferred_strategy:
                continue
            try:
                action = fn(state, context)
                if action:
                    proposals.append(action)
            except Exception as e:
                logger.debug("Strategy %s failed: %s", name, e)

        # Phase 2: Conflict resolution — same target clusters, different proposals
        proposals = self._resolve_conflicts(proposals)

        # Phase 3: Record which strategies were attempted
        for p in proposals:
            self._record_attempt(p.strategy)

        return proposals

    def apply_and_learn(self, state: ClusterState, action: StrategyAction,
                        result_clusters: ClusterState) -> ValidationResult:
        """Apply one action, validate outcome, learn preference."""
        cohesion_delta = (sum(result_clusters.cohesion_scores) / max(1, len(result_clusters.cohesion_scores))
                         - sum(state.cohesion_scores) / max(1, len(state.cohesion_scores)))
        entropy_delta = result_clusters.entropy - state.entropy

        success = cohesion_delta > 0 and entropy_delta < 1.0

        vr = ValidationResult(
            action=action,
            success=success,
            cohesion_after=cohesion_delta,
            entropy_after=entropy_delta,
        )
        self._history.append(vr)

        # Learn: update strategy scores
        if action.strategy not in self._strategy_scores:
            self._strategy_scores[action.strategy] = []
        self._strategy_scores[action.strategy].append(1.0 if success else 0.0)

        # Lock: if a strategy consistently fails for a cluster
        if not success:
            self._locked.setdefault(action.strategy, []).extend(action.target_clusters)

        # Keep rolling window
        for k in list(self._strategy_scores.keys()):
            if len(self._strategy_scores[k]) > 20:
                self._strategy_scores[k] = self._strategy_scores[k][-10:]

        return vr

    def best_strategy(self) -> str:
        """Which strategy has the highest rolling success rate?"""
        if not self._strategy_scores:
            return "blueprint"  # default
        
        best, best_score = "blueprint", 0.0
        for name, scores in self._strategy_scores.items():
            if not scores:
                continue
            avg = sum(scores) / len(scores)
            if avg > best_score:
                best_score = avg
                best = name
        return best

    def should_avoid(self, strategy: str, cluster_idx: int) -> bool:
        """Is this strategy known to fail for this cluster?"""
        return cluster_idx in self._locked.get(strategy, [])

    def _resolve_conflicts(self, proposals: List[StrategyAction]) -> List[StrategyAction]:
        """Multiple strategies targeting same clusters → keep highest confidence."""
        by_target = {}
        for p in proposals:
            key = tuple(sorted(p.target_clusters))
            if key not in by_target or p.confidence > by_target[key].confidence:
                by_target[key] = p
        return list(by_target.values())

    def _record_attempt(self, strategy: str):
        pass  # tracked via apply_and_learn

    def status(self) -> dict:
        return {
            "strategies": list(self._strategies.keys()),
            "best": self.best_strategy(),
            "scores": {k: round(sum(v)/len(v), 2) if v else 0 
                      for k, v in self._strategy_scores.items()},
            "attempts": len(self._history),
        }


# ── Built-in Strategies ──

def blueprint_strategy(state: ClusterState, context: dict = None) -> Optional[StrategyAction]:
    """Rule-based blueprint: merge high-cohesion, split low-cohesion, pivot high-entropy."""
    if not state.clusters:
        return None

    # Merge: two clusters with highest cross-cohesion
    if len(state.clusters) >= 2 and state.entropy < 0.5:
        return StrategyAction(
            name="merge", strategy="blueprint",
            target_clusters=[0, 1],
            new_clusters=[state.clusters[0] + state.clusters[1]] + state.clusters[2:],
            confidence=0.7,
            reasoning="low entropy → merge safe"
        )

    # Split: cluster with lowest cohesion
    if state.cohesion_scores:
        min_idx = state.cohesion_scores.index(min(state.cohesion_scores))
        cluster = state.clusters[min_idx]
        if len(cluster) >= 3:
            mid = len(cluster) // 2
            new = state.clusters[:min_idx] + [cluster[:mid], cluster[mid:]] + state.clusters[min_idx+1:]
            return StrategyAction(
                name="split", strategy="blueprint",
                target_clusters=[min_idx],
                new_clusters=new,
                confidence=0.6,
                reasoning="low cohesion cluster → split"
            )

    return None


def greedy_strategy(state: ClusterState, context: dict = None) -> Optional[StrategyAction]:
    """Greedy: always merge the two most similar clusters."""
    if len(state.clusters) < 2:
        return None

    # Find two most similar clusters (by size match as proxy)
    sizes = [len(c) for c in state.clusters]
    matched = None
    min_diff = float('inf')
    for i in range(len(sizes)):
        for j in range(i+1, len(sizes)):
            diff = abs(sizes[i] - sizes[j])
            if diff < min_diff:
                min_diff = diff
                matched = (i, j)

    if matched:
        i, j = matched
        merged = state.clusters[i] + state.clusters[j]
        new = [state.clusters[k] for k in range(len(state.clusters)) if k not in (i, j)] + [merged]
        return StrategyAction(
            name="merge_similar", strategy="greedy",
            target_clusters=[i, j],
            new_clusters=new,
            confidence=0.5,
            reasoning="greedy merge of most similar sized clusters"
        )
    return None


def llm_strategy_builder(llm) -> Callable:
    """Create an LLM-driven strategy function."""
    def llm_strategy(state: ClusterState, context: dict = None) -> Optional[StrategyAction]:
        if not llm or not state.clusters:
            return None

        ctx = {
            "clusters": state.clusters,
            "cohesion": state.cohesion_scores,
            "entropy": round(state.entropy, 3),
            "turn": state.turn,
        }
        prompt = f"""Current clustering state needs adjustment. Propose ONE action.

STATE: {json.dumps(ctx, ensure_ascii=False)}

Actions: merge(merge two clusters), split(split one cluster), 
         pivot(move entity to different cluster), expand(add new cluster)

Output JSON: {{"action": "merge|split|pivot|expand", "target": [indices], 
               "reasoning": "why this action", "confidence": 0.0-1.0}}"""

        try:
            import re
            resp = llm.generate(prompt, max_tokens=200, temperature=0.2)
            cleaned = re.sub(r'```(?:json)?\s*\n?', '', str(resp))
            cleaned = re.sub(r'\n?```', '', cleaned).strip()
            s = cleaned.find('{'); e = cleaned.rfind('}')
            if s >= 0 and e > s:
                data = json.loads(cleaned[s:e+1])
                return StrategyAction(
                    name=data.get("action", "merge"),
                    strategy="llm",
                    target_clusters=data.get("target", [0]),
                    new_clusters=state.clusters,  # LLM proposes, caller applies
                    confidence=data.get("confidence", 0.6),
                    reasoning=data.get("reasoning", ""),
                )
        except Exception:
            pass
        return None

    return llm_strategy
