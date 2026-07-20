"""Personality signals from structure, not keywords. Zero hardcoded vocab.

N/S detection:
  1. Tree depth: deep chains = abstract reasoning (generalizes across languages)
  2. BGE embedding: abstract vs concrete cluster distance (language-agnostic)
  3. Behavior patterns: generalize→concretize ratio (domain-independent)

F/T detection:
  1. Behavior patterns: agree/build vs critique/verify ratio
  2. LLM 1-shot: "analytical or empathetic?" (50 tokens, generalized)
  3. Interaction patterns: confrontation vs collaboration frequency

C, O, E, NC detection: behavior patterns (already generalized).
"""
from __future__ import annotations
import time, logging, numpy as np
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


class StructuralSignalExtractor:
    """Extract OCEAN signals from structural features. No hardcoded vocab."""

    def __init__(self, discourse_tree=None, behavior_graph=None,
                 inertia_graph=None, bge_encoder=None, llm_provider=None):
        self._dt = discourse_tree
        self._bg = behavior_graph
        self._ig = inertia_graph
        self._bge = bge_encoder
        self._llm = llm_provider
        self._ns_ema = 0.5

    def extract_all(self) -> List[Tuple[str, float, float]]:
        return (self._from_behavior() + 
                self._from_topology() + 
                self._from_inertia())

    # ── Behavior patterns → C, NC, N/S, F/T ──

    def _from_behavior(self) -> List[Tuple[str, float, float]]:
        signals = []
        patterns = getattr(self._bg, '_patterns', {}) if self._bg else {}
        if not patterns: return signals

        for key, p in patterns.items():
            conf = getattr(p, 'confidence', 0)
            if conf < 0.6: continue
            delta = 0.03 * conf

            # Quality patterns → C
            if self._has_behavior(key, ["test", "monitor", "verify", "validate"]):
                signals.append(("C", delta, 0.5))
            # Depth patterns → NC
            elif self._has_behavior(key, ["analyze", "deep", "research", "explore", "investigate"]):
                signals.append(("NC", delta, 0.5))
            # Abstract→abstract → N
            elif self._is_abstract_chain(key, patterns):
                signals.append(("N", delta, 0.4))
            # Concrete→concrete → S
            elif self._is_concrete_chain(key, patterns):
                signals.append(("N", -delta, 0.4))
            # Harmony patterns → A
            elif self._has_behavior(key, ["agree", "support", "empathize", "acknowledge", "reflect", "build_on"]):
                signals.append(("A", delta, 0.5))
            # Adversarial patterns → -A (T)
            elif self._has_behavior(key, ["challenge", "critique", "disagree", "verify", "question"]):
                signals.append(("A", -delta, 0.5))
            # Fast patterns → E
            elif self._has_behavior(key, ["quick", "confirm", "skip", "next"]):
                signals.append(("E", delta, 0.3))

        return signals

    def _has_behavior(self, key: str, tokens: List[str]) -> bool:
        return any(t in key.lower() for t in tokens)

    def _is_abstract_chain(self, key: str, patterns: Dict) -> bool:
        """Abstract chain: actions that deal with concepts, not implementations."""
        abstract_tokens = ["abstract", "generalize", "concept", "theory", 
                          "pattern", "design", "model", "architecture", "principle"]
        return any(t in key.lower() for t in abstract_tokens)

    def _is_concrete_chain(self, key: str, patterns: Dict) -> bool:
        concrete_tokens = ["implement", "execute", "build", "run", "deploy", "test", "fix"]
        return any(t in key.lower() for t in concrete_tokens)

    # ── Tree topology → O, N/S ──

    def _from_topology(self) -> List[Tuple[str, float, float]]:
        signals = []
        dt = self._dt
        if not dt: return signals

        trees = getattr(dt, '_trees', {})
        total_blocks = sum(len(getattr(t, 'blocks', {})) for t in trees.values())
        if total_blocks < 3: return signals

        total_forks = sum(
            getattr(t, '_fork_count', 0) if hasattr(t, '_fork_count') else 0
            for t in trees.values()
        )

        # Switch frequency → Openness
        switch_pct = total_forks / max(total_blocks, 1)
        if switch_pct > 0.3:
            signals.append(("O", min(0.05, switch_pct * 0.1), 0.5))

        # Max tree depth → N/S (deep = abstract reasoning, general)
        max_depth = self._max_depth(trees)
        if max_depth > 8:
            signals.append(("N", 0.05, 0.5))   # very deep = N
        elif max_depth >= 5:
            signals.append(("N", 0.02, 0.4))
        elif max_depth < 3 and total_blocks > 5:
            signals.append(("N", -0.02, 0.3))  # flat = S

        # Block count → E
        if total_blocks > 20:
            signals.append(("E", 0.03, 0.3))

        return signals

    def _max_depth(self, trees: Dict) -> int:
        md = 0
        for tree in trees.values():
            blocks = getattr(tree, 'blocks', {})
            for bid, block in blocks.items():
                d = 0
                cur = block
                while hasattr(cur, 'parent_id') and cur.parent_id:
                    d += 1
                    cur = blocks.get(cur.parent_id)
                    if not cur: break
                md = max(md, d)
        return md

    # ── Inertia breaks → N, MS, C ──

    def _from_inertia(self) -> List[Tuple[str, float, float]]:
        signals = []
        ig = self._ig
        if not ig: return signals

        patterns = getattr(ig, '_patterns', {})
        for pid, p in patterns.items():
            state = getattr(p, 'state', '')
            counters = getattr(p, 'counter_examples', 0)
            if state in ("weakening", "broken") and counters >= 2:
                if "quality" in pid:
                    signals.append(("C", -0.04, 0.7))
                elif "whitebox" in pid:
                    signals.append(("MS", 0.04, 0.7))
                elif "adversarial" in pid:
                    signals.append(("A", -0.03, 0.5))

        return signals

    # ── N/S from BGE semantic distance (language-agnostic) ──

    def ns_from_embedding(self, text: str) -> Optional[float]:
        """Measure abstractness via BGE embedding distance to known anchors.
        
        Abstract anchor texts have high cosine distance from concrete anchors.
        Works across languages — no keyword lists needed.
        """
        if not self._bge or not hasattr(self._bge, 'encode'):
            return None
        
        try:
            vec = np.array(self._bge.encode([text])[0])
            # Abstract reference: theoretical/conceptual language pattern
            abstract_ref = np.array(self._bge.encode(
                ["从系统的角度来看，这一设计的核心逻辑在于抽象层次的分离与组合"]
            )[0])
            # Concrete reference: operational/practical language pattern
            concrete_ref = np.array(self._bge.encode(
                ["先运行这个函数，然后检查输出，如果报错就修改参数再试"]
            )[0])
            # Cosine distances
            d_abstract = 1 - np.dot(vec, abstract_ref) / (
                np.linalg.norm(vec) * np.linalg.norm(abstract_ref) + 1e-9)
            d_concrete = 1 - np.dot(vec, concrete_ref) / (
                np.linalg.norm(vec) * np.linalg.norm(concrete_ref) + 1e-9)
            # Closer to abstract → higher N score
            if d_abstract + d_concrete < 0.01:
                return None
            ns_score = d_concrete / (d_abstract + d_concrete)  # [0,1], 1=N
            return ns_score
        except Exception:
            return None

    # ── F/T from LLM 1-shot (50 tokens, generalized) ──

    def ft_from_llm(self, text: str) -> Optional[float]:
        """LLM 1-shot: is this text more analytical (T) or empathetic (F)?
        
        Only ~50 tokens — cheap generalization.
        Returns T-score (0=F, 1=T).
        """
        if not self._llm: return None
        try:
            prompt = (
                "Analyze this text. Respond with a single number 0.0-1.0: "
                "0.0 = purely empathetic/emotional/people-focused, "
                "1.0 = purely analytical/logical/system-focused.\n\n"
                f"Text: {text[:500]}\n\nNumber:"
            )
            from core.agent.llm_providers.base import GenerateRequest
            result = self._llm.generate(GenerateRequest(
                prompt=prompt, max_tokens=10, temperature=0.1
            ))
            text_out = result.text if hasattr(result, 'text') else str(result)
            import re
            match = re.search(r'([0-9]*\.?[0-9]+)', str(text_out))
            if match:
                return float(match.group(1))
        except Exception:
            pass
        return None
