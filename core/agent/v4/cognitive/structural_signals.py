"""Non-LLM Personality Signals — generalization without self-reflection.

Three signal sources (zero LLM cost):
  1. Behavior patterns (A→B) → OCEAN C, NC
  2. Discourse tree topology → OCEAN O, E
  3. Inertia breaks → OCEAN N, MS

Design: BUSINESS_CHAIN_08 v2 §2 (multi-perspective consensus)
These signals augment LLM-based extraction, providing baseline even
when the user never asks self-reflective questions.
"""
from __future__ import annotations
import time, logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class StructuralSignalExtractor:
    """Extract personality signals from structural features (non-LLM).

    Maps observable behavior patterns → OCEAN dimension updates.
    Each signal produces a (dimension, delta, confidence) tuple.
    """

    def __init__(self, discourse_tree=None, behavior_graph=None,
                 inertia_graph=None):
        self._dt = discourse_tree
        self._bg = behavior_graph
        self._ig = inertia_graph

    def extract_all(self) -> List[Tuple[str, float, float]]:
        """Return all signals: [(dimension, delta, confidence), ...]."""
        signals = []
        signals.extend(self._from_behavior_patterns())
        signals.extend(self._from_discourse_topology())
        signals.extend(self._from_inertia_breaks())
        return signals

    # ── Source 1: Behavior Patterns → C, NC ──

    def _from_behavior_patterns(self) -> List[Tuple[str, float, float]]:
        """Infer OCEAN from discovered A→B patterns.

        Pattern                         Signal
        ─────────────────────────────────────────
        write_code → add_test           C +0.05 (quality-focused)
        write_code → add_monitoring     C +0.05
        write_code → refactor           C +0.03, NC +0.03
        explore → deep_dive              NC +0.05 (need for cognition)
        ask_question → clarify          MS +0.03 (metacognitive)
        switch_topic → explore          O +0.03 (openness)
        reply_quick → next              E +0.02 (extraversion, fast-paced)
        """
        signals = []
        patterns = getattr(self._bg, '_patterns', {}) if self._bg else {}

        quality_patterns = {"write_code→add_test", "write_code→add_monitoring",
                           "deploy→verify", "build→test"}
        depth_patterns = {"explore→deep_dive", "question→analyze", "surface→deep"}
        meta_patterns = {"ask→clarify", "confused→self_explain"}
        explore_patterns = {"switch_topic→explore", "curious→search"}
        fast_patterns = {"reply_quick→next", "action→confirm"}

        for key, p in patterns.items():
            conf = getattr(p, 'confidence', 0)
            if conf < 0.6: continue

            if key in quality_patterns:
                signals.append(("C", 0.03 * conf, 0.5))
            elif key in depth_patterns:
                signals.append(("NC", 0.04 * conf, 0.5))
            elif key in meta_patterns:
                signals.append(("MS", 0.03 * conf, 0.4))
            elif key in explore_patterns:
                signals.append(("O", 0.03 * conf, 0.4))
            elif key in fast_patterns:
                signals.append(("E", 0.02 * conf, 0.3))

        return signals

    # ── Source 2: Discourse Tree Topology → O, E, N ──

    def _from_discourse_topology(self) -> List[Tuple[str, float, float]]:
        """Infer OCEAN from discourse tree structure.

        Feature                          Signal
        ────────────────────────────────────────────
        Topic switch frequency > 0.4     O +0.03 (divergent thinking)
        Average block depth > 3          NC +0.02 (deep analysis)
        Fork events > merge events       O +0.03 (exploration preference)
        Block reuse (cold→active) > 5    C +0.02 (structured revisiting)
        """
        signals = []
        dt = self._dt
        if not dt: return signals

        trees = getattr(dt, '_trees', {})
        total_blocks = sum(len(getattr(tree, 'blocks', {})) for tree in trees.values())
        total_forks = sum(
            getattr(tree, '_fork_count', 0) if hasattr(tree, '_fork_count') else 0
            for tree in trees.values()
        )

        if total_blocks < 3: return signals

        # Switch frequency: forks / blocks
        switch_ratio = total_forks / max(total_blocks, 1)
        if switch_ratio > 0.3:
            signals.append(("O", min(0.05, switch_ratio * 0.1), 0.5))
        if switch_ratio > 0.6:
            signals.append(("N", 0.02, 0.3))  # high divergence = potential stress

        # Block depth → NC
        avg_depth = self._avg_depth(trees)
        if avg_depth > 3:
            signals.append(("NC", min(0.05, avg_depth * 0.01), 0.4))

        return signals

    def _avg_depth(self, trees: Dict) -> float:
        if not trees: return 0
        depths = []
        for tree in trees.values():
            blocks = getattr(tree, 'blocks', {})
            for bid, block in blocks.items():
                depth = 0
                current = block
                while hasattr(current, 'parent_id') and current.parent_id:
                    depth += 1
                    current = blocks.get(current.parent_id)
                    if not current: break
                depths.append(depth)
        return sum(depths) / max(len(depths), 1)

    # ── Source 3: Inertia Breaks → N, MS, A ──

    def _from_inertia_breaks(self) -> List[Tuple[str, float, float]]:
        """Inertia breaks are the strongest non-LLM personality signals.

        Inertia break type                Signal
        ────────────────────────────────────────────
        quality_centric break             N +0.05 (stress/tension)
        whitebox_pref break               MS +0.05 (re-evaluating)
        adversarial_thinking break        A +0.03 (changing stance)
        """
        signals = []
        ig = self._ig
        if not ig: return signals

        patterns = getattr(ig, '_patterns', {})
        for pid, p in patterns.items():
            counters = getattr(p, 'counter_examples', 0)
            state = getattr(p, 'state', '')
            if state in ("weakening", "broken") and counters >= 2:
                if "quality" in pid:
                    signals.append(("N", 0.04, 0.7))   # stress from quality drop
                elif "whitebox" in pid:
                    signals.append(("MS", 0.04, 0.7))   # metacognitive re-eval
                elif "adversarial" in pid:
                    signals.append(("A", 0.03, 0.5))    # changing stance

        return signals


class HybridProfileUpdater:
    """Merge LLM-extracted + structural signals into OCEAN profile.

    Weights:
      LLM extraction:   0.5 (high accuracy, expensive)
      Structural:       0.3 (medium accuracy, zero cost)
      BFI calibrator:   0.2 (literature-validated, survey-based)
    """

    def __init__(self, ocean_profile, structural_extractor: StructuralSignalExtractor):
        self._profile = ocean_profile
        self._extractor = structural_extractor

    def update(self, llm_signals: Dict[str, float] = None):
        """One round of profile update with all signal sources."""
        dims = getattr(self._profile, 'dims', {})

        # 1. LLM signals (if available)
        if llm_signals:
            for dim, val in llm_signals.items():
                if dim in dims:
                    dims[dim] = 0.5 * val + 0.5 * dims[dim]

        # 2. Structural signals (zero LLM cost)
        struct_signals = self._extractor.extract_all()
        for dim, delta, confidence in struct_signals:
            if dim in dims:
                dims[dim] += confidence * delta * 0.3
                dims[dim] = max(0.0, min(1.0, dims[dim]))

        # 3. BFI override remains separate (done by BFICalibrator)

        return dims
