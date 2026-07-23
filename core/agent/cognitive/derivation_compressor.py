"""Derivation Compression — divergence→convergence heuristic chain.

Design: docs/v5/DESIGN_DERIVATION_COMPRESSION_V2.md
Philosophy: 规则归纳=过拟合, 正确路径=发散→收敛→启发链
Input: L2 entity edges + L2.5 belief trace
Output: HeuristicChain (compressed, testable, reversible)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import time, logging

logger = logging.getLogger(__name__)


@dataclass
class StateTransition:
    """One state→state transition extracted from L2/L2.5."""
    from_state: str
    to_state: str
    evidence_type: str  # "entity_relation" | "belief_change" | "intent_shift"
    entities: List[str] = field(default_factory=list)
    confidence: float = 0.5
    turn: int = 0


@dataclass
class DivergenceGuess:
    """One divergent guess from LLM (no context, high temperature)."""
    content: str
    confidence: float = 0.0
    source: str = "llm_diverge"


@dataclass
class HeuristicChain:
    """The compressed artifact — divergence→convergence→heuristic chain."""
    chain_id: str
    summary: str  # 启发链描述
    conditions: List[str] = field(default_factory=list)  # 适用条件
    counter_examples: List[str] = field(default_factory=list)  # 反例
    reasoning_path: str = ""  # 推理路径
    coverage: float = 1.0  # 启发覆盖率 (↓ = 需要重新压缩)
    total_tests: int = 0
    hits: int = 0
    created_at: float = field(default_factory=time.time)
    last_used_at: float = 0.0
    
    def record_test(self, matched: bool):
        self.total_tests += 1
        if matched:
            self.hits += 1
        self.coverage = self.hits / max(1, self.total_tests)
        self.last_used_at = time.time()
    
    @property
    def is_stale(self) -> bool:
        return self.coverage < 0.5 and self.total_tests >= 5
    
    @property
    def freshness(self) -> float:
        if self.total_tests == 0: return 1.0
        return self.coverage * min(1.0, 1.0 / (time.time() - self.last_used_at + 1))


class DerivationCompressor:
    """Extract state transitions → diverge (LLM no context) → converge (LLM + context) → heuristic chain.
    
    Usage:
        comp = DerivationCompressor(llm_provider=deepseek)
        transitions = comp.extract(edge_history, belief_trace)
        guesses = comp.diverge(transitions)
        verified = comp.converge(transitions, guesses, discourse_context)
        chain = comp.heuristic(transitions, verified)
        comp.pool.append(chain)
    """
    
    DIVERGE_TEMPERATURE = 0.8
    CONVERGE_TEMPERATURE = 0.1
    COMPRESSION_INTERVAL = 5  # compress every N turns
    
    def __init__(self, llm_provider=None):
        self.llm = llm_provider
        self.pool: List[HeuristicChain] = []
        self._transition_buffer: List[StateTransition] = []
        self._turn_counter: int = 0
    
    def extract(self, edge_history: list, belief_trace: list) -> List[StateTransition]:
        """Extract state transitions from L2 edges + L2.5 belief trace."""
        transitions = []
        
        # From entity edges
        for edge in edge_history[-10:]:
            if hasattr(edge, 'relation_kind') and hasattr(edge, 'target'):
                transitions.append(StateTransition(
                    from_state=getattr(edge, 'source', 'unknown'),
                    to_state=edge.target,
                    evidence_type="entity_relation",
                    entities=[getattr(edge, 'source', ''), edge.target],
                    confidence=getattr(edge, 'confidence', 0.5),
                ))
        
        # From belief trace
        for entry in belief_trace[-10:]:
            if hasattr(entry, 'probability_before') and hasattr(entry, 'probability_after'):
                best_before = max(entry.probability_before, key=entry.probability_before.get)
                best_after = max(entry.probability_after, key=entry.probability_after.get)
                if best_before != best_after:
                    transitions.append(StateTransition(
                        from_state=best_before,
                        to_state=best_after,
                        evidence_type="belief_change",
                        confidence=abs(entry.probability_after[best_after] - entry.probability_before[best_before]),
                    ))
        
        self._transition_buffer.extend(transitions)
        return transitions
    
    def diverge(self, transitions: List[StateTransition]) -> List[DivergenceGuess]:
        """LLM diverges: no context, high temperature → creative guesses."""
        if not self.llm or len(transitions) < 3:
            return []
        
        chain_desc = "\n".join(
            f"  {t.from_state} → {t.to_state} ({t.evidence_type}, conf={t.confidence:.2f})"
            for t in transitions[-5:]
        )
        prompt = f"""Given these state transitions, freely brainstorm what deeper patterns or constraints might be at play. Be creative — explore unusual angles.

Transitions:
{chain_desc}

Generate 3-5 divergent hypotheses. Return JSON array of strings: ["hypothesis 1", "hypothesis 2", ...]"""
        
        try:
            import json
            response = self.llm.generate(prompt, max_tokens=300, temperature=self.DIVERGE_TEMPERATURE)
            response = self._clean_json(response) if response else ''
            guesses_raw = json.loads(response) if response else []
            return [DivergenceGuess(content=g) for g in guesses_raw[:5]]
        except Exception as e:
            logger.debug("Diverge failed: %s", e)
            return []
    
    def converge(self, transitions: List[StateTransition], guesses: List[DivergenceGuess],
                 discourse_context: str = "") -> List[DivergenceGuess]:
        """LLM converges: full context, low temperature → filter + verify guesses."""
        if not self.llm or not guesses:
            return []
        
        chain_desc = "\n".join(
            f"  {t.from_state} → {t.to_state} ({t.evidence_type})"
            for t in transitions[-5:]
        )
        guess_desc = "\n".join(f"  {i+1}. {g.content}" for i, g in enumerate(guesses))
        ctx = f"\nDialogue context: {discourse_context[:200]}" if discourse_context else ""
        
        prompt = f"""Verify which of these hypotheses are supported by the evidence.

Evidence chain:
{chain_desc}
{ctx}

Hypotheses (from creative brainstorming):
{guess_desc}

For each hypothesis, return: {{"index": N, "verdict": "accept"/"reject", "confidence": 0.0-1.0, "reason": "..."}}
Return JSON array."""
        
        try:
            import json
            response = self.llm.generate(prompt, max_tokens=400, temperature=self.CONVERGE_TEMPERATURE)
            response = self._clean_json(response) if response else ''
            verdicts = json.loads(response) if response else []
            verified = []
            for v in verdicts:
                idx = v.get("index", 0) - 1
                if 0 <= idx < len(guesses) and v.get("verdict") == "accept":
                    guesses[idx].confidence = v.get("confidence", 0.5)
                    verified.append(guesses[idx])
            return verified
        except Exception as e:
            logger.debug("Converge failed: %s", e)
            return []
    
    def heuristic(self, transitions: List[StateTransition], verified: List[DivergenceGuess],
                  chain_id: str = "") -> Optional[HeuristicChain]:
        """Generate heuristic chain from verified guesses."""
        if not self.llm or not verified:
            return None
        
        chain_desc = "\n".join(
            f"  {t.from_state} → {t.to_state}"
            for t in transitions[-5:]
        )
        ver_desc = "\n".join(
            f"  {g.content} (conf={g.confidence:.2f})" for g in verified
        )
        
        prompt = f"""Synthesize a heuristic chain from these verified insights.

Evidence:
{chain_desc}

Verified insights:
{ver_desc}

Generate a heuristic chain that:
1. Describes the DERIVATION pattern (not just the topic)
2. Lists WHEN this heuristic applies (conditions)
3. Lists WHEN it does NOT apply (counter-examples)
4. Explains the reasoning path

Return JSON: {{"summary": "...", "conditions": ["..."], "counter_examples": ["..."], "reasoning": "..."}}"""
        
        try:
            import json
            response = self.llm.generate(prompt, max_tokens=500, temperature=0.1)
            response = self._clean_json(response) if response else ''
            data = json.loads(response) if response else {}
            return HeuristicChain(
                chain_id=chain_id or f"hc_{int(time.time())}",
                summary=data.get("summary", ""),
                conditions=data.get("conditions", []),
                counter_examples=data.get("counter_examples", []),
                reasoning_path=data.get("reasoning", ""),
            )
        except Exception as e:
            logger.debug("Heuristic failed: %s", e)
            return None
    
    def _clean_json(self, text: str) -> str:
        """Strip markdown code fences from LLM JSON response."""
        import re
        # Remove ```json ... ``` wrapper
        text = re.sub(r'```(?:json)?\s*\n?', '', text)
        text = re.sub(r'\n?```', '', text)
        return text.strip()

    def should_compress(self) -> bool:
        """Should we run compression now?"""
        self._turn_counter += 1
        return self._turn_counter % self.COMPRESSION_INTERVAL == 0 and len(self._transition_buffer) >= 5
    
    def ingest_turn(self, edge_history: list, belief_trace: list, discourse_context: str = ""):
        """Full compression cycle for one turn — called from engine."""
        self._turn_counter += 1
        if not self.should_compress() or not self.llm:
            return
        
        transitions = self.extract(edge_history, belief_trace)
        if len(transitions) < 5:
            return
        
        guesses = self.diverge(transitions)
        verified = self.converge(transitions, guesses, discourse_context)
        chain = self.heuristic(transitions, verified)
        
        if chain:
            # Replace stale chains
            stale = [c for c in self.pool if c.is_stale]
            for s in stale:
                self.pool.remove(s)
            self.pool.append(chain)
            logger.info("Compressed: chain %s (pool=%d)", chain.chain_id, len(self.pool))
    
    def best_chain(self) -> Optional[HeuristicChain]:
        """Return the most fresh, high-coverage chain."""
        active = [c for c in self.pool if not c.is_stale]
        if not active:
            return None
        return max(active, key=lambda c: (c.freshness, c.coverage))
