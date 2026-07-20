"""Non-LLM Personality Signals — generalization without self-reflection.

Signal sources:
  1. Behavior patterns (A→B) → C, NC, MS, N/S, F/T
  2. Discourse tree topology → O, E, N/S
  3. Inertia breaks → N, MS, C
  4. Content abstraction → N/S (LLM-assisted, lightweight prompt)

Design: BUSINESS_CHAIN_08 v2 §2 (multi-perspective consensus)
"""
from __future__ import annotations
import time, logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


class StructuralSignalExtractor:
    """Extract personality signals from structural + semantic features.

    N/S detection: NOT proxy via O. Uses:
      - Content abstraction: abstract/theoretical vs concrete/practical language
      - Behavior patterns: explore vs execute, deep_chain vs surface
      - Tree topology: chain depth (long chains = abstract reasoning)

    F/T detection: 
      - Harmony patterns: agree→build, empathize→support
      - Adversarial patterns: challenge→refine, critique→improve
      - Collaboration patterns: ask→listen, share→co_create
    """

    def __init__(self, discourse_tree=None, behavior_graph=None,
                 inertia_graph=None, llm_provider=None):
        self._dt = discourse_tree
        self._bg = behavior_graph
        self._ig = inertia_graph
        self._llm = llm_provider
        self._ns_cache: Dict[str, float] = {}  # text_hash → ns_score

    def extract_all(self) -> List[Tuple[str, float, float]]:
        signals = []
        signals.extend(self._from_behavior_patterns())
        signals.extend(self._from_discourse_topology())
        signals.extend(self._from_inertia_breaks())
        return signals

    def extract_ns_from_text(self, text: str) -> Tuple[Optional[float], float]:
        """N/S score from content abstraction level. EMA-smoothed.
        
        Returns (ns_score, confidence).
        ns_score > 0.5 = N (intuitive/abstract)
        ns_score ≤ 0.5 = S (sensing/concrete)
        """
        h = hash(text) % 10000
        if h in self._ns_cache:
            return self._ns_cache[h], 0.6

        abstract = {"概念", "理论", "模式", "框架", "本质", "抽象", "假设",
                    "推测", "想象", "可能", "潜在", "隐含", "系统", "结构",
                    "设计", "架构", "哲学", "逻辑", "关系", "推断"}
        concrete = {"具体", "实际", "操作", "步骤", "数据", "事实", "经验",
                    "细节", "实现", "写", "做", "跑", "测", "看到", "听到",
                    "代码", "测试", "运行", "配置", "文件", "函数"}
        
        abstract_count = sum(1 for w in abstract if w in text)
        concrete_count = sum(1 for w in concrete if w in text)
        total = abstract_count + concrete_count
        
        if total == 0:
            return None, 0.0
        
        raw_score = abstract_count / total
        # EMA smooth with previous score
        prev = getattr(self, '_ns_ema', 0.5)
        self._ns_ema = 0.3 * raw_score + 0.7 * prev  # heavy smoothing
        ns_score = self._ns_ema
        
        confidence = min(0.5, total / 10.0)
        self._ns_cache[h] = ns_score
        return ns_score, confidence

    # ── Source 1: Behavior Patterns → C, NC, N/S, F/T ──

    def _from_behavior_patterns(self) -> List[Tuple[str, float, float]]:
        signals = []
        patterns = {}
        if self._bg and hasattr(self._bg, '_patterns'):
            patterns = self._bg._patterns

        # Quality/C patterns
        quality = {"write_code→add_test", "write_code→add_monitoring",
                   "deploy→verify", "build→test", "refactor→test"}
        # Depth/NC patterns
        depth = {"explore→deep_dive", "question→analyze", 
                 "surface→deep", "curious→research"}
        # Abstract/N patterns
        abstract_pat = {"concept→generalize", "detail→abstract", 
                        "example→pattern", "case→theory"}
        # Concrete/S patterns
        concrete_pat = {"abstract→example", "theory→practice",
                        "concept→implement", "idea→prototype"}
        # Harmony/F patterns
        harmony = {"agree→build", "empathize→support", "acknowledge→extend",
                   "appreciate→share", "listen→reflect"}
        # Adversarial/T patterns  
        adversarial = {"challenge→refine", "critique→improve",
                       "disagree→argue", "question→verify"}

        for key, p in patterns.items():
            conf = getattr(p, 'confidence', 0)
            if conf < 0.6: continue

            delta = 0.03 * conf
            
            if key in quality: signals.append(("C", delta, 0.5))
            elif key in depth: signals.append(("NC", delta, 0.5))
            elif key in abstract_pat: signals.append(("NS", delta, 0.5))  # N signal
            elif key in concrete_pat: signals.append(("NS", -delta, 0.5))  # S signal
            elif key in harmony: signals.append(("FT", delta, 0.5))  # F signal
            elif key in adversarial: signals.append(("FT", -delta, 0.5))  # T signal

        return signals

    # ── Source 2: Discourse Tree Topology → O, N/S, E ──

    def _from_discourse_topology(self) -> List[Tuple[str, float, float]]:
        signals = []
        if not self._dt: return signals

        trees = getattr(self._dt, '_trees', {})
        total_blocks = 0
        max_depth = 0
        total_forks = 0
        
        for tree in trees.values():
            blocks = getattr(tree, 'blocks', {})
            total_blocks += len(blocks)
            total_forks += getattr(tree, '_fork_count', 0) if hasattr(tree, '_fork_count') else 0
            
            for bid, block in blocks.items():
                depth = 0
                current = block
                while hasattr(current, 'parent_id') and current.parent_id:
                    depth += 1
                    current = blocks.get(current.parent_id)
                    if not current: break
                max_depth = max(max_depth, depth)

        if total_blocks < 3: return signals

        # Switch frequency → O
        switch_ratio = total_forks / max(total_blocks, 1)
        if switch_ratio > 0.3:
            signals.append(("O", min(0.05, switch_ratio * 0.1), 0.5))

        # Chain depth → N/S (deep chains = abstract reasoning)
        if max_depth > 5:
            signals.append(("NS", 0.04, 0.4))  # N
        elif max_depth < 2 and total_blocks > 5:
            signals.append(("NS", -0.02, 0.3))  # S (flat structure = concrete)

        # Block count / session → E (more blocks = more engagement)
        if total_blocks > 20:
            signals.append(("E", 0.03, 0.3))

        return signals

    # ── Source 3: Inertia Breaks → N, MS, C ──

    def _from_inertia_breaks(self) -> List[Tuple[str, float, float]]:
        signals = []
        if not self._ig: return signals

        patterns = getattr(self._ig, '_patterns', {})
        for pid, p in patterns.items():
            counters = getattr(p, 'counter_examples', 0)
            state = getattr(p, 'state', '')
            if state in ("weakening", "broken") and counters >= 2:
                if "quality" in pid:
                    signals.append(("C", -0.04, 0.7))  # C dropping (quality concern)
                elif "whitebox" in pid:
                    signals.append(("MS", 0.04, 0.7))
                elif "adversarial" in pid:
                    signals.append(("FT", -0.03, 0.5))  # T weakening → F signal

        return signals


class HybridProfileUpdater:
    """Merge all signal sources into OCEAN profile.
    
    Weights: LLM 0.5 + Structural 0.3 + BFI 0.2 (already in calibrator)
    
    Special dimensions:
      N/S: LLM abstraction analysis + behavior patterns + tree depth
      F/T: harmony patterns + adversarial patterns + inertia
    """

    def __init__(self, ocean_profile, structural_extractor: StructuralSignalExtractor):
        self._profile = ocean_profile
        self._extractor = structural_extractor

    def update(self, llm_signals: Dict[str, float] = None, 
               last_text: str = ""):
        dims = getattr(self._profile, 'dims', {})

        # LLM signals
        if llm_signals:
            for dim, val in llm_signals.items():
                if dim in dims:
                    dims[dim] = 0.5 * val + 0.5 * dims[dim]

        # Structural signals
        struct_sigs = self._extractor.extract_all()
        for dim, delta, confidence in struct_sigs:
            if dim in ("NS", "FT"):
                # These are special dimensions mapped to N and A
                if dim == "NS" and "N" in dims:
                    dims["N"] += confidence * delta * 0.3
                    dims["N"] = max(0.0, min(1.0, dims["N"]))
                elif dim == "FT" and "A" in dims:
                    dims["A"] += confidence * delta * 0.3
                    dims["A"] = max(0.0, min(1.0, dims["A"]))
            elif dim in dims:
                dims[dim] += confidence * delta * 0.3
                dims[dim] = max(0.0, min(1.0, dims[dim]))

        # N/S from content abstraction (lightweight, non-LLM heuristic)
        if last_text and "N" in dims:
            ns_score, ns_conf = self._extractor.extract_ns_from_text(last_text)
            if ns_score is not None and ns_conf > 0.2:
                # Map ns_score (0=S, 1=N) to N dimension delta
                target_n = ns_score  # already in [0,1]
                delta = (target_n - dims["N"]) * ns_conf * 0.2
                dims["N"] = max(0.0, min(1.0, dims["N"] + delta))

        return dims
