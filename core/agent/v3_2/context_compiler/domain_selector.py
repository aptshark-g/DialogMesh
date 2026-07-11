"""DomainSelector: intent-aware cross-domain selection with soft continuous weights.

Refinements over base spec:
1. Multi-intent weighted fusion via confidence blending
2. Soft continuous domain weights (not binary include/exclude)
3. Adaptive delta learning from user follow-up patterns
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional
from .models import Domain, IntentCategory, IntentEstimate, DomainSelection, DomainFeedback

logger = logging.getLogger(__name__)

STRATEGY_WEIGHTS: Dict[IntentCategory, Dict[Domain, float]] = {
    IntentCategory.TASK:        {Domain.ENGINEERING:0.60, Domain.BEHAVIOR:0.25, Domain.PROFILE:0.15, Domain.CONVERSATION:0.0, Domain.CAUSAL:0.0},
    IntentCategory.QUERY:       {Domain.CONVERSATION:0.60, Domain.ENGINEERING:0.25, Domain.PROFILE:0.15, Domain.BEHAVIOR:0.0, Domain.CAUSAL:0.0},
    IntentCategory.CORRECTION:  {Domain.BEHAVIOR:0.60, Domain.ENGINEERING:0.25, Domain.CAUSAL:0.15, Domain.CONVERSATION:0.0, Domain.PROFILE:0.0},
    IntentCategory.DISCUSSION:  {Domain.PROFILE:0.60, Domain.CONVERSATION:0.25, Domain.ENGINEERING:0.15, Domain.BEHAVIOR:0.0, Domain.CAUSAL:0.0},
    IntentCategory.CASUAL:      {Domain.CONVERSATION:0.60, Domain.PROFILE:0.25, Domain.BEHAVIOR:0.15, Domain.ENGINEERING:0.0, Domain.CAUSAL:0.0},
    IntentCategory.TOPIC_SWITCH:{Domain.CONVERSATION:0.60, Domain.BEHAVIOR:0.25, Domain.PROFILE:0.15, Domain.ENGINEERING:0.0, Domain.CAUSAL:0.0},
}

MISSING_DOMAIN_PATTERNS: Dict[Domain, List[str]] = {
    Domain.ENGINEERING: ["monitor","dependency","module","missing","status"],
    Domain.CAUSAL:      ["why","cause","because","root cause","reason"],
    Domain.BEHAVIOR:    ["before","previously","last time","history","earlier"],
    Domain.PROFILE:     ["I prefer","I usually","my habit","I dislike"],
}


class DomainSelector:

    def __init__(self, monitor=None):
        self._deltas: Dict[IntentCategory, Dict[Domain, float]] = {
            ic: {d: 0.0 for d in Domain} for ic in IntentCategory
        }
        self._feedback_window: List[DomainFeedback] = []
        self._monitor = monitor
        self._turn_count = 0

    def select(self, intents: List[IntentEstimate]) -> DomainSelection:
        self._turn_count += 1
        if not intents:
            intents = [IntentEstimate(IntentCategory.CASUAL, 0.5)]

        total_conf = sum(i.confidence for i in intents) or 1.0
        blended: Dict[Domain, float] = {d: 0.0 for d in Domain}
        for intent in intents:
            base = STRATEGY_WEIGHTS.get(intent.category, STRATEGY_WEIGHTS[IntentCategory.CASUAL])
            w = intent.confidence / total_conf
            for dom in Domain:
                blended[dom] += base[dom] * w

        for dom in Domain:
            delta_sum = sum(self._deltas.get(ic, {}).get(dom, 0.0) * (
                intent.confidence / total_conf) for intent in intents for ic in [intent.category])
            blended[dom] = max(0.0, min(1.0, blended[dom] + delta_sum * 0.1))

        total = sum(blended.values()) or 1.0
        weights = {d: w / total for d, w in blended.items()}
        ordered = sorted(weights, key=lambda d: weights[d], reverse=True)

        hint = "balanced"
        if weights[ordered[0]] > 0.55: hint = "deep_focus"
        elif sum(1 for d in ordered if weights[d] > 0.1) >= 4: hint = "breadth"
        elif Domain.CAUSAL in ordered[:2] or Domain.BEHAVIOR in ordered[:2]: hint = "causal_backtrack"

        ds = DomainSelection(
            weights=weights, primary_domain=ordered[0], domain_order=ordered,
            intent_blend={i.category: i.confidence for i in intents}, strategy_hint=hint,
        )
        if self._monitor:
            self._monitor.record("domain_selector", "select", {
                "primary": ds.primary_domain.value, "strategy": ds.strategy_hint,
                "weights": {d.value: round(w, 2) for d, w in ds.weights.items()},
                "intents": {ic.value: round(c,2) for ic,c in ds.intent_blend.items()},
            })
        return ds

    def feed_missing_domain(self, fb: DomainFeedback):
        self._feedback_window.append(fb)
        if len(self._feedback_window) > 20:
            self._feedback_window = self._feedback_window[-20:]
        delta = fb.confidence * 0.1
        self._deltas[fb.current_intent][fb.missing_domain] = min(
            0.3, self._deltas[fb.current_intent][fb.missing_domain] + delta)

    def detect_missing_domain(self, user_text: str, last_intent: IntentCategory) -> Optional[Domain]:
        text_lower = user_text.lower()
        for domain, keywords in MISSING_DOMAIN_PATTERNS.items():
            if any(kw in text_lower for kw in keywords):
                return domain
        return None


def create_domain_selector(monitor=None) -> DomainSelector:
    return DomainSelector(monitor=monitor)
