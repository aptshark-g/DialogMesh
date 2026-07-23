"""L2.5 Belief Accumulator — Bayesian sequential update + 7D structured state + belief trace.

Design: docs/BUSINESS_CHAIN_06_ASSOCIATION.md §2.4 (Bayesian)
        docs/blog/chapter2_relation_over_prompt.md (7D BeliefState)
        core/agent/hypothesis/models.py (HypothesisNode)
Frontier: BLF (linguistic belief state), PersuasionTrace, Dynamic Belief Graph
Fusion: Bayesian core + 7D explainability + trace audit + LLM high-order resolution
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import time, logging, math

logger = logging.getLogger(__name__)


@dataclass
class Evidence:
    """Single piece of evidence from L2 ontology graph."""
    entity_id: str
    entity_name: str
    relation_type: str  # "co_occurrence", "causes", "triggers"
    confidence: float
    turn_num: int
    source: str = "l2_graph"  # "l2_graph" | "llm_inference" | "user_correction"


@dataclass  
class BeliefTraceEntry:
    """One step in belief evolution — audit trail."""
    turn: int
    evidence: Evidence
    probability_before: Dict[str, float]
    probability_after: Dict[str, float]
    hypothesis_updated: str
    timestamp: float = field(default_factory=time.time)


class BayesianUpdater:
    """Core Bayesian sequential updating.
    
    P(intent|evidence_t) = P(intent) + (1 - P(intent)) * likelihood(intent, evidence_t)
    """

    def update(self, priors: Dict[str, float], evidence: Evidence, 
               likelihood_matrix: Dict[str, Dict[str, float]] = None) -> Dict[str, float]:
        """Update intent probabilities with new evidence.
        
        Args:
            priors: current P(intent) distribution
            evidence: new evidence from L2
            likelihood_matrix: P(evidence|intent) for each intent type, or defaults
        
        Returns updated distribution.
        """
        posteriors = dict(priors)
        conf = evidence.confidence
        
        if likelihood_matrix is None:
            # Default: evidence affinity based on relation type
            likelihood_matrix = self._default_likelihood(evidence)
        
        for intent, prior in priors.items():
            likelihood = likelihood_matrix.get(evidence.relation_type, {}).get(intent, 0.5)
            # Bayesian: P(H|E) = P(H) * P(E|H) / P(E)
            # Simplified: P(H|E) ≈ prior + (1 - prior) * likelihood * confidence
            posterior = prior + (1.0 - prior) * likelihood * conf
            posteriors[intent] = min(posterior, 0.99)
        
        return posteriors
    
    def _default_likelihood(self, evidence: Evidence) -> Dict[str, Dict[str, float]]:
        """Likelihood matrix from config/l2_config.json. Falls back to built-in defaults."""
        try:
            from ..association.l2_config import get as cfg_get
            matrix = cfg_get('l2_5.likelihood_matrix', None)
            if matrix:
                return matrix
        except Exception:
            pass
        # Fallback defaults
        return {
            "causes": {"诊断": 0.85, "修复": 0.70, "探索": 0.40, "吐槽": 0.15, "信息查询": 0.30},
            "triggers": {"诊断": 0.75, "修复": 0.60, "探索": 0.50, "吐槽": 0.10, "信息查询": 0.30},
            "co_occurrence": {"诊断": 0.55, "修复": 0.55, "探索": 0.60, "吐槽": 0.40, "信息查询": 0.50},
            "depends_on": {"修复": 0.80, "诊断": 0.60, "探索": 0.45, "吐槽": 0.10, "信息查询": 0.20},
        }
        return mapping
    
    def entropy(self, distribution: Dict[str, float]) -> float:
        """Entropy of probability distribution — high = uncertain."""
        values = list(distribution.values())
        total = sum(values)
        if total == 0:
            return 1.0
        probs = [v / total for v in values]
        return -sum(p * math.log(p + 1e-8) for p in probs if p > 0) / math.log(len(probs))


class BeliefAccumulator:
    """L2.5: combines Bayesian core with 7D structured state and belief trace.
    
    Usage:
        acc = BeliefAccumulator(intents=["诊断", "修复", "探索", "吐槽"])
        acc.ingest(evidence)  # from L2 RelationSubstrate edge
        acc.status()  # -> {intent: {probability, belief_7d, trace}}
    """
    
    LLM_TRIGGER_ENTROPY = 0.5  # overridden by config/l2_config.json l2_5.thresholds
    LOCK_THRESHOLD = 0.85
    FORCE_CRYSTAL_TURNS = 5
    
    def __init__(self, intents: List[str] = None, llm_provider=None):
        self.intents = intents or ["诊断", "修复", "探索", "吐槽", "信息查询"]
        self.priors: Dict[str, float] = {i: 1.0 / len(self.intents) for i in self.intents}
        self.bayesian = BayesianUpdater()
        self.llm = llm_provider
        self._load_config()
        
        # 7D structured belief for each intent
        self._belief_7d: Dict[str, dict] = {
            i: {"support": 0, "conflict": 0, "stability": 1.0,
                "coverage": 0.0, "recency": 1.0, "novelty": 1.0, "entropy": 0.0}
            for i in self.intents
        }
        
        # Belief trace
        self.trace: List[BeliefTraceEntry] = []
        self.turn_count: int = 0
        self.locked_intent: Optional[str] = None
    
    def ingest(self, evidence: Evidence):
        """Process one piece of evidence from L2."""
        if self.locked_intent:
            return  # Already locked, no more updates
        
        self.turn_count += 1
        prior_snapshot = dict(self.priors)
        
        # Step 1: Bayesian update
        self.priors = self.bayesian.update(self.priors, evidence)
        
        # Step 2: Update 7D state
        for intent in self.intents:
            b7d = self._belief_7d[intent]
            # Find best-matching intent
            if intent == self._best_intent():
                b7d["support"] += 1
                b7d["recency"] = 1.0
                b7d["novelty"] = max(0.0, b7d["novelty"] - 0.2)
            else:
                if evidence.confidence > 0.7:
                    b7d["conflict"] += 1
                b7d["recency"] *= 0.9
            
            # Derived
            sup = max(1, b7d["support"])
            con = max(1, b7d["conflict"])
            b7d["stability"] = sup / (sup + con)
            b7d["coverage"] = min(1.0, self.turn_count / 10.0)
            b7d["entropy"] = self.bayesian.entropy(self.priors)
        
        # Step 3: Record trace
        self.trace.append(BeliefTraceEntry(
            turn=self.turn_count,
            evidence=evidence,
            probability_before=prior_snapshot,
            probability_after=dict(self.priors),
            hypothesis_updated=self._best_intent(),
        ))
        
        # Step 4: Check lock threshold
        best = self._best_intent()
        if self.priors[best] >= self.LOCK_THRESHOLD:
            self.locked_intent = best
            logger.info("Intent locked: %s (p=%.3f)", best, self.priors[best])
        
        # Step 5: Check force crystal
        if self.turn_count >= self.FORCE_CRYSTAL_TURNS and not self.locked_intent:
            self.locked_intent = best
            logger.info("Force crystal: %s after %d turns", best, self.turn_count)
    
    def needs_llm(self) -> bool:
        """True when Bayesian update is stuck — entropy > threshold and not locked."""
        if self.locked_intent:
            return False
        ent = self.bayesian.entropy(self.priors)
        return ent > self.LLM_TRIGGER_ENTROPY and self.turn_count >= 2
    
    def llm_resolve(self) -> Optional[str]:
        """Trigger LLM to resolve ambiguity. Returns resolved intent or None."""
        if not self.llm or not self.needs_llm():
            return None
        
        top2 = sorted(self.priors.items(), key=lambda x: -x[1])[:2]
        prompt = f"""Resolve ambiguous user intent from these competing hypotheses:

Top hypotheses:
1. {top2[0][0]}: P={top2[0][1]:.3f} (support={self._belief_7d[top2[0][0]]['support']}, conflict={self._belief_7d[top2[0][0]]['conflict']})
2. {top2[1][0]}: P={top2[1][1]:.3f} (support={self._belief_7d[top2[1][0]]['support']}, conflict={self._belief_7d[top2[1][0]]['conflict']})

Return JSON: {{"resolved": "intent_name", "reason": "..."}}"""
        
        try:
            response = self.llm.generate(prompt, max_tokens=100)
            import json
            data = json.loads(response) if response else {}
            resolved = data.get("resolved", "")
            if resolved in self.intents:
                # LLM resolution = strong evidence
                llm_evidence = Evidence(
                    entity_id="llm_resolve", entity_name="LLM",
                    relation_type="triggers", confidence=0.9,
                    turn_num=self.turn_count, source="llm_inference"
                )
                self.ingest(llm_evidence)
                return resolved
        except Exception as e:
            logger.debug("LLM resolve failed: %s", e)
        return None
    
    def _load_config(self):
        from .l2_config import get as cfg_get
        t = cfg_get('l2_5.thresholds', {})
        if t:
            self.LLM_TRIGGER_ENTROPY = t.get('llm_trigger_entropy', 0.5)
            self.LOCK_THRESHOLD = t.get('lock_threshold', 0.85)
            self.FORCE_CRYSTAL_TURNS = t.get('force_crystal_turns', 5)

    def _best_intent(self) -> str:
        return max(self.priors, key=self.priors.get)
    
    def status(self) -> dict:
        """Full status: probabilities + 7D belief + trace summary."""
        return {
            "locked": self.locked_intent,
            "probabilities": dict(self.priors),
            "belief_7d": {i: dict(b) for i, b in self._belief_7d.items()},
            "turn_count": self.turn_count,
            "entropy": self.bayesian.entropy(self.priors),
            "needs_llm": self.needs_llm(),
            "trace_last_3": [
                {"turn": t.turn, "evidence": t.evidence.entity_name, 
                 "best_before": max(t.probability_before, key=t.probability_before.get),
                 "best_after": max(t.probability_after, key=t.probability_after.get)}
                for t in self.trace[-3:]
            ],
        }
