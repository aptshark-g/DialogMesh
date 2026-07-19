"""Inertia Weight Graph — profile v2: cross-chain stable patterns.

Design: BUSINESS_CHAIN_08 v2
Profile is NOT flat OCEAN dimensions — it's a weighted graph of 
inertia patterns validated by multi-perspective consensus.

Lifecycle: fragment → candidate → confirmed → stable → (weakened | broken) → archived
"""
from __future__ import annotations
import json, os, time, math, logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class InertiaPattern:
    """A cross-chain stable behavioral/cognitive pattern."""
    pattern_id: str                # "quality_centric" | "whitebox_pref" | "adversarial_thinking"
    label: str                     # human-readable label
    
    # Multi-perspective evidence
    evidence: Dict[str, float] = field(default_factory=dict)
    # {"design": 0.9, "engineering": 0.85, "behavior": 0.78, "llm": 0.82, "meta": 0.88, "association": 0.75}
    
    # Stability metrics
    weight: float = 0.5            # 0.0-1.0 current weight
    peak_weight: float = 0.5       # historical maximum
    rounds_stable: int = 0         # consecutive rounds without counter-examples
    last_verified: float = field(default_factory=time.time)
    
    # Break tracking
    counter_examples: int = 0
    break_events: List[Dict] = field(default_factory=list)
    
    # Projection: how this inertia affects system behavior
    design_constraints: List[str] = field(default_factory=list)
    parameter_overrides: Dict[str, Any] = field(default_factory=dict)
    
    # Lifecycle
    state: str = "candidate"       # candidate | confirmed | stable | weakening | broken | archived
    created_at: float = field(default_factory=time.time)


class InertiaWeightGraph:
    """Profile v2: weighted graph of cross-chain stable patterns.
    
    Consumed by: all chains (via design_constraints + parameter_overrides)
    Updated by: multi-perspective consensus engine
    """

    def __init__(self, persist_path: str = "data/profile/inertia_graph.json"):
        self._patterns: Dict[str, InertiaPattern] = {}
        self._path = persist_path
        self._load()

    # ── Pattern Management ──

    def register(self, pattern_id: str, label: str, 
                 evidence: Dict[str, float] = None) -> InertiaPattern:
        """Register or update a pattern."""
        if pattern_id in self._patterns:
            p = self._patterns[pattern_id]
        else:
            p = InertiaPattern(pattern_id=pattern_id, label=label)
            self._patterns[pattern_id] = p
        
        if evidence:
            p.evidence.update(evidence)
        
        self._update_state(p)
        return p

    def add_evidence(self, pattern_id: str, source: str, value: float):
        """Add a single evidence point from one perspective."""
        p = self._patterns.get(pattern_id)
        if not p: return
        
        old = p.evidence.get(source, 0)
        # EMA update per source
        p.evidence[source] = 0.3 * value + 0.7 * old
        p.last_verified = time.time()
        
        self._update_state(p)

    def record_counter(self, pattern_id: str, source: str):
        """Record a counter-example (evidence against this pattern)."""
        p = self._patterns.get(pattern_id)
        if not p: return
        
        p.counter_examples += 1
        p.rounds_stable = 0
        p.weight = max(0.05, p.weight - 0.05)
        p.break_events.append({
            "ts": time.time(), "source": source, "counter_count": p.counter_examples,
        })
        
        if p.counter_examples >= 3:
            # Potential break — meta-cognition should review
            p.state = "weakening" if p.counter_examples < 5 else "broken"
            logger.info("Inertia break: %s (%d counters)", pattern_id, p.counter_examples)

    def record_stable_round(self, pattern_id: str):
        """Record one more round without counter-examples."""
        p = self._patterns.get(pattern_id)
        if not p: return
        p.rounds_stable += 1
        p.counter_examples = max(0, p.counter_examples - 1)  # slowly forgive
        p.weight = min(1.0, p.weight + 0.01)
        if p.weight > p.peak_weight:
            p.peak_weight = p.weight

    # ── State Machine ──

    def _update_state(self, p: InertiaPattern):
        """Determine lifecycle state from evidence."""
        verified_views = sum(1 for v in p.evidence.values() if v > 0.5)
        
        if verified_views >= 5 and p.rounds_stable > 30:
            p.state = "stable"
            p.weight = min(1.0, 0.7 + 0.01 * p.rounds_stable)
        elif verified_views >= 3:
            p.state = "confirmed"
            p.weight = 0.5 + 0.1 * (verified_views - 3)
        elif verified_views >= 1:
            p.state = "candidate"
            p.weight = 0.3 + 0.1 * verified_views
        
        if p.weight > p.peak_weight:
            p.peak_weight = p.weight

    # ── Design Constraint Projection ──

    def get_design_constraints(self) -> List[str]:
        """All active design constraints from stable/confirmed patterns."""
        constraints = []
        for p in self._patterns.values():
            if p.state in ("confirmed", "stable") and p.weight > 0.5:
                constraints.extend(p.design_constraints)
        return constraints

    def get_parameter_overrides(self) -> Dict[str, Any]:
        """Aggregated parameter overrides from all patterns."""
        overrides = {}
        for p in self._patterns.values():
            if p.state in ("confirmed", "stable") and p.weight > 0.5:
                overrides.update(p.parameter_overrides)
        return overrides

    # ── Detection Helpers ──

    def detect_quality_centric(self, engine) -> Optional[InertiaPattern]:
        """Detect quality-centric inertia from multi-chain signals."""
        evidence = {}
        
        # Engineering: user frequently requests tests/monitoring
        eng = getattr(engine, '_engineering_knowledge', None)
        if eng and hasattr(eng, '_constraint_counts'):
            c = getattr(eng, '_constraint_counts', {}).get('quality', 0)
            evidence["engineering"] = min(1.0, c / 10.0) if c else 0.3
        
        # Behavior: pattern write_code→add_test frequency
        # (placeholder — real detection needs chain 05)
        evidence["behavior"] = 0.5
        
        # Profile: OCEAN C (conscientiousness) is a proxy
        ocean = getattr(getattr(engine, '_ocean_analyst', None), 'profile', None)
        if ocean and hasattr(ocean, 'dims'):
            evidence["profile"] = ocean.dims.get("C", 0.5)
        
        return self.register("quality_centric", "质量高标准", evidence)

    # ── Queries ──

    def stable_patterns(self, min_weight: float = 0.6) -> List[InertiaPattern]:
        return [p for p in self._patterns.values() 
                if p.state in ("confirmed", "stable") and p.weight >= min_weight]

    def breaking_patterns(self) -> List[InertiaPattern]:
        return [p for p in self._patterns.values() if p.state in ("weakening", "broken")]

    def pattern(self, pattern_id: str) -> Optional[InertiaPattern]:
        return self._patterns.get(pattern_id)

    # ── Persistence ──

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        data = {}
        for pid, p in self._patterns.items():
            data[pid] = {
                "label": p.label,
                "evidence": p.evidence,
                "weight": p.weight, "peak_weight": p.peak_weight,
                "rounds_stable": p.rounds_stable,
                "counter_examples": p.counter_examples,
                "state": p.state,
                "constraints": p.design_constraints,
                "overrides": p.parameter_overrides,
                "created_at": p.created_at,
            }
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self):
        if not os.path.exists(self._path): return
        with open(self._path, encoding="utf-8") as f:
            data = json.load(f)
        for pid, d in data.items():
            p = InertiaPattern(
                pattern_id=pid, label=d["label"],
                evidence=d.get("evidence", {}),
                weight=d.get("weight", 0.5), peak_weight=d.get("peak_weight", 0.5),
                rounds_stable=d.get("rounds_stable", 0),
                counter_examples=d.get("counter_examples", 0),
                state=d.get("state", "candidate"),
                design_constraints=d.get("constraints", []),
                parameter_overrides=d.get("overrides", {}),
                created_at=d.get("created_at", time.time()),
            )
            self._patterns[pid] = p

    def stats(self) -> Dict[str, Any]:
        return {
            "total_patterns": len(self._patterns),
            "stable": sum(1 for p in self._patterns.values() if p.state == "stable"),
            "confirmed": sum(1 for p in self._patterns.values() if p.state == "confirmed"),
            "breaking": sum(1 for p in self._patterns.values() if p.state in ("weakening", "broken")),
            "by_weight": {pid: round(p.weight, 2) for pid, p in self._patterns.items()},
            "constraints": self.get_design_constraints(),
        }
