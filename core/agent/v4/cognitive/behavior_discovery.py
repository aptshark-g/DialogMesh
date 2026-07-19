"""Behavior Pattern Discovery — 3-stage pipeline.

Design: BUSINESS_CHAIN_05_SUPPLEMENT_DISCOVERY
Stage 1: Statistical discovery (zero LLM cost)
Stage 2: Frontend display (usable before review)
Stage 3: Meta-cognition review → association chain absorption

All thresholds are user-configurable via /v6/parameters.
"""
from __future__ import annotations
import json, os, time, logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BehaviorPattern:
    """A discovered A→B behavior pattern."""
    trigger: str                # action A
    predicted: str              # action B
    confidence: float           # P(B|A)
    support: int                # co-occurrence count
    association: float          # association chain strength
    source: str = "statistical_discovery"
    reviewed: bool = False
    review_verdict: str = ""    # "approved" | "rejected" | "pending"
    discovered_at: float = field(default_factory=time.time)


class BehaviorDiscovery:
    """Statistical pattern discovery + meta-cognition pipeline.
    
    Stage 1: count co-occurrences → find patterns
    Stage 2: patterns immediately available for frontend
    Stage 3: meta-cognition review → association chain absorption
    """

    def __init__(self, parameter_registry=None, meta_cognition=None):
        self._patterns: Dict[str, BehaviorPattern] = {}  # "A→B" → pattern
        self._action_history: List[str] = []              # recent actions
        self._params = parameter_registry
        self._meta = meta_cognition
        self._persist_path = "data/behavior/patterns.json"
        self._load()

    def record_action(self, action: str):
        """Record a user action for pattern discovery."""
        self._action_history.append(action)
        if len(self._action_history) > 200:
            self._action_history = self._action_history[-200:]

    def discover(self) -> List[BehaviorPattern]:
        """Stage 1: Statistical discovery — zero LLM cost."""
        min_repeat = self._get_param("behavior.min_repeat_count", 3)
        min_conf = self._get_param("behavior.min_confidence", 0.75)
        min_assoc = self._get_param("behavior.min_assoc_strength", 0.3)
        window = self._get_param("behavior.window_size", 5)

        unique = list(set(self._action_history))
        discovered = []

        for a in unique:
            for b in unique:
                if a == b: continue
                key = f"{a}→{b}"

                # Count co-occurrences within window
                count = 0
                for i in range(len(self._action_history) - 1):
                    if self._action_history[i] == a:
                        for j in range(i + 1, min(i + window + 1, len(self._action_history))):
                            if self._action_history[j] == b:
                                count += 1
                                break

                if count < min_repeat: continue

                # P(B|A)
                a_count = self._action_history.count(a)
                conf = count / a_count if a_count > 0 else 0

                if conf < min_conf: continue

                # Update or create pattern
                if key in self._patterns:
                    p = self._patterns[key]
                    p.confidence = 0.3 * conf + 0.7 * p.confidence  # EMA
                    p.support = count
                else:
                    p = BehaviorPattern(trigger=a, predicted=b, confidence=conf,
                                       support=count, association=0.5)
                    self._patterns[key] = p
                
                if p.confidence >= min_conf and p.support >= min_repeat:
                    discovered.append(p)

        self._save()
        return discovered

    def submit_to_meta(self, pattern: BehaviorPattern):
        """Stage 3: Send to meta-cognition for review."""
        if not self._meta: return
        
        from core.agent.v4.cognitive.metacognition import ReviewPriority, DecisionMode
        self._meta.submit(
            source="behavior_discovery",
            target=f"behavior.pattern.{pattern.trigger}→{pattern.predicted}",
            data={
                "trigger": pattern.trigger, "predicted": pattern.predicted,
                "confidence": pattern.confidence, "support": pattern.support,
                "association": pattern.association,
            },
            priority=ReviewPriority.NORMAL,
            mode=DecisionMode.DELIBERATE,
        )
        pattern.reviewed = True

    def handle_user_feedback(self, pattern_key: str, accepted: bool):
        """Handle user ✓/✗ feedback from frontend."""
        p = self._patterns.get(pattern_key)
        if not p: return

        if accepted:
            p.confidence = min(1.0, p.confidence + 0.05)
            p.review_verdict = "user_approved"
        else:
            p.confidence = max(0.1, p.confidence - 0.1)
            p.review_verdict = "user_rejected"
        
        self.submit_to_meta(p)
        self._save()

    def pending_review(self) -> List[BehaviorPattern]:
        """Patterns not yet reviewed by meta-cognition."""
        return [p for p in self._patterns.values() if not p.reviewed and p.confidence > 0.6]

    def stats(self) -> Dict[str, Any]:
        return {
            "total_patterns": len(self._patterns),
            "pending_review": len(self.pending_review()),
            "user_approved": sum(1 for p in self._patterns.values() if p.review_verdict == "user_approved"),
            "top": sorted(self._patterns.values(), key=lambda x: x.confidence, reverse=True)[:5],
        }

    # ── Helpers ──

    def _get_param(self, key: str, default: Any) -> Any:
        if self._params and hasattr(self._params, 'get'):
            return self._params.get(key, default)
        return default

    def _save(self):
        os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
        data = {}
        for k, p in self._patterns.items():
            data[k] = {
                "trigger": p.trigger, "predicted": p.predicted,
                "confidence": p.confidence, "support": p.support,
                "association": p.association, "reviewed": p.reviewed,
                "verdict": p.review_verdict, "discovered_at": p.discovered_at,
            }
        with open(self._persist_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self):
        if not os.path.exists(self._persist_path): return
        with open(self._persist_path, encoding="utf-8") as f:
            data = json.load(f)
        for k, d in data.items():
            self._patterns[k] = BehaviorPattern(
                trigger=d["trigger"], predicted=d["predicted"],
                confidence=d["confidence"], support=d["support"],
                association=d.get("association", 0.5),
                reviewed=d.get("reviewed", False),
                review_verdict=d.get("verdict", ""),
                discovered_at=d.get("discovered_at", time.time()),
            )


# ── Association Chain L1.5: Cognitive Completion Engine ──

class CompletionEngine:
    """L1.5: fast+slow completion of implicit references.
    
    Design: BUSINESS_CHAIN_06 §2.2
    Fast channel (<5ms): profile hit, context inheritance, anchor match
    Slow channel (~50ms): lightweight model (BERT-mini placeholder)
    Fallback: preserve original features, don't force completion
    
    Output: implicit constraint matrix for L2 semantic mapping
    """

    def __init__(self, profile=None, mind=None, association_chain=None):
        self._profile = profile
        self._mind = mind
        self._assoc = association_chain

    def complete(self, text: str, context: List[str] = None) -> Dict[str, Any]:
        """Complete implicit references in text. Returns constraint matrix."""
        result = {"explicit": {}, "implicit_subject": None, "default_chain": [], "confidence": 0.0}

        # Fast: profile hit
        if self._profile and hasattr(self._profile, 'dims'):
            dims = self._profile.dims
            if dims.get("CL", 0.5) > 0.7:  # high curiosity → more exploratory completion
                result["confidence"] += 0.1

        # Fast: context inheritance (last 3 turns)
        if context:
            for ctx_text in context[-3:]:
                # Simple entity overlap
                words = set(text) & set(ctx_text)
                if len(words) > 3:
                    result["explicit"]["context_overlap"] = list(words)[:5]
                    result["confidence"] += 0.2
                    break

        # Fast: anchor match (Mind.attention)
        if self._mind and hasattr(self._mind, 'attention'):
            anchors = getattr(self._mind.attention, '_anchors', {})
            for anchor_key, anchor_val in anchors.items():
                if anchor_key in text:
                    result["explicit"]["anchor"] = anchor_key
                    result["confidence"] += 0.3
                    break

        # Clamp confidence
        result["confidence"] = min(0.9, result.get("confidence", 0.0))

        return result

    def get_preferences(self) -> Dict[str, Any]:
        """Get completion preferences from user profile."""
        if not self._profile: return {}
        dims = getattr(self._profile, 'dims', {})
        return {
            "prefer_fast": dims.get("C", 0.5) > 0.7,  # high C → want fast, deterministic
            "prefer_deep": dims.get("NC", 0.5) > 0.7,  # high NC → want deep completion
            "prefer_explore": dims.get("CL", 0.5) > 0.7,  # high CL → explore weak associations
        }
