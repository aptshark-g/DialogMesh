"""Neuro-Symbolic Rule Engine — Layer C of ABC architecture.

Rule: composable premise→conclusion with learnable thresholds.
RuleEngine: evaluate, learn, persist. Driven by Mind + Trace data.
Mind stores relations → rules reason over the same substrate.

Design: docs/v3.0/quality_metrics_literature.md §5
"""
from __future__ import annotations
import json, os, logging
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Rule:
    """A composable symbolic rule.

    premise: condition dict checked against engine state
    conclusion: action dict applied when premise is satisfied
    confidence: learned confidence from historical accuracy
    hits: how many times the rule fired correctly
    misses: how many times it fired incorrectly
    """
    name: str
    premise: Dict[str, Any]   # e.g. {"strengthen": {">=": 2}, "domain": "engineering"}
    conclusion: Dict[str, Any] # e.g. {"threshold": "S", "value": 2, "action": "lower"}
    confidence: float = 0.5
    source: str = "manual"     # manual/L3_learned/L2_llm/L1_default
    hits: int = 0
    misses: int = 0

    def accuracy(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> dict:
        return {"name": self.name, "premise": self.premise, "conclusion": self.conclusion,
                "confidence": self.confidence, "source": self.source,
                "hits": self.hits, "misses": self.misses}

    @classmethod
    def from_dict(cls, d: dict) -> "Rule":
        return cls(name=d["name"], premise=d["premise"], conclusion=d["conclusion"],
                   confidence=d.get("confidence", 0.5), source=d.get("source", "manual"),
                   hits=d.get("hits", 0), misses=d.get("misses", 0))


class RuleEngine:
    """Neuro-symbolic rule evaluation + learning engine.

    Evaluates rules against engine state (Trace + Mind).
    Returns best-matching conclusion with confidence.
    Learns from feedback (hit/miss tracking).
    """

    def __init__(self, persist_dir: str = "data", load: bool = True):
        self._rules: Dict[str, Rule] = {}
        self._persist_dir = persist_dir
        self._path = os.path.join(persist_dir, "neuro_symbolic_rules.json")
        self._state_getters: Dict[str, Callable] = {}
        if load:
            self.load()

    def register(self, rule: Rule) -> None:
        self._rules[rule.name] = rule

    def register_state_getter(self, key: str, getter: Callable) -> None:
        """Register a function that extracts state from engine."""
        self._state_getters[key] = getter

    def evaluate(self, engine) -> Optional[Dict[str, Any]]:
        """Evaluate all rules against engine state. Return best match."""
        state = self._extract_state(engine)
        best = None
        best_score = 0

        for rule in self._rules.values():
            score = self._match(rule, state)
            if score > best_score:
                best_score = score
                best = rule

        if best and best_score >= 0.5:
            return {
                "rule": best.name,
                "conclusion": best.conclusion,
                "confidence": best.confidence * best_score,
                "source": f"L3_rule({best.source})",
            }
        return None

    def _extract_state(self, engine) -> Dict[str, Any]:
        """Extract relevant state from engine."""
        state = {}
        # From TraceV3 — per-turn delta (last 3 turns window, not cumulative)
        window = 3
        if hasattr(engine, '_trace_v3') and engine._trace_v3:
            m = engine._trace_v3.meta_analyze()
            rd = m.get("reason_distribution", {})
            # Cumulative state (all-time)
            state["total_strengthen"] = rd.get("strengthen", 0)
            state["total_weaken"] = rd.get("weaken", 0)
            state["total_reject"] = rd.get("reject", 0)
            # Window state (last N turns) — better for personality detection
            all_transitions = getattr(engine._trace_v3, 'transitions', [])
            recent = all_transitions[-window*4:] if len(all_transitions) > window*4 else all_transitions
            from core.agent.state.state_object import TransitionReason
            state["strengthen"] = sum(1 for t in recent if getattr(t, 'reason', None) == TransitionReason.STRENGTHEN)
            state["weaken"] = sum(1 for t in recent if getattr(t, 'reason', None) == TransitionReason.WEAKEN)
            state["reject"] = sum(1 for t in recent if getattr(t, 'reason', None) == TransitionReason.REJECT)
            state["avg_confidence"] = m.get("avg_confidence", 0.7)

        # From Mind
        if hasattr(engine, '_mind') and engine._mind:
            mind_stats = engine._mind.stats()
            state["mind_relations"] = mind_stats.get("active_relations", 0)
            state["mind_anchors"] = mind_stats.get("active_anchors", 0)

        # From Profile
        if hasattr(engine, '_cognitive_profile'):
            state["profile_tags"] = list(getattr(engine._cognitive_profile, 'track_b', {}).keys())

        # Domain: what kind of conversation?
        if hasattr(engine, '_last_context'):
            try:
                entries = engine._last_context._entries
                domains = set(e.domain for e in entries.values() if hasattr(e, 'domain'))
                state["active_domains"] = list(domains)
            except Exception:
                state["active_domains"] = []

        # Registered custom getters
        for key, getter in self._state_getters.items():
            try:
                state[key] = getter(engine)
            except Exception:
                pass

        return state

    def _match(self, rule: Rule, state: Dict[str, Any]) -> float:
        """Score how well a rule's premise matches the state. Returns 0-1."""
        if not rule.premise:
            return 1.0
        scores = []
        for key, condition in rule.premise.items():
            if key not in state:
                scores.append(0.0)
                continue
            actual = state[key]
            if isinstance(condition, dict):
                if ">=" in condition:
                    scores.append(1.0 if actual >= condition[">="] else 0.0)
                elif "<=" in condition:
                    scores.append(1.0 if actual <= condition["<="] else 0.0)
                elif "in" in condition:
                    if isinstance(actual, list):
                        scores.append(1.0 if condition["in"] in actual else 0.0)
                    else:
                        scores.append(1.0 if actual == condition["in"] else 0.0)
                elif "contains" in condition:
                    if isinstance(actual, list):
                        scores.append(1.0 if condition["contains"] in actual else 0.0)
                    else:
                        scores.append(0.0)
            else:
                scores.append(1.0 if actual == condition else 0.0)
        return sum(scores) / len(scores) if scores else 1.0

    def learn(self, rule_name: str, hit: bool) -> None:
        """Update rule confidence based on real-world feedback."""
        if rule_name in self._rules:
            if hit:
                self._rules[rule_name].hits += 1
            else:
                self._rules[rule_name].misses += 1
            self._rules[rule_name].confidence = self._rules[rule_name].accuracy()

    def rules_from_trace(self, engine) -> List[Rule]:
        """Generate new rules from Trace + Mind patterns.

        Extracts: "if strengthen ≥ 2 and domain=engineering → T-type"
        """
        state = self._extract_state(engine)
        new_rules = []

        # Pattern: STRENGTHEN → T-type personality
        if state.get("strengthen", 0) >= 2:
            if "personality_analytical" in state.get("profile_tags", []):
                new_rules.append(Rule(
                    name="personality_t_from_strengthen",
                    premise={"strengthen": {">=": 2}},
                    conclusion={"threshold": "S", "value": 2, "tag": "personality_analytical"},
                    source="L3_learned",
                ))

        # Pattern: WEAKEN + low mind_relations → module mismatch
        if state.get("weaken", 0) >= 3 and state.get("mind_relations", 0) < 5:
            new_rules.append(Rule(
                name="context_mismatch_warning",
                premise={"weaken": {">=": 3}, "mind_relations": {"<=": 5}},
                conclusion={"action": "expand_context", "reason": "unfamiliar_module"},
                source="L3_learned",
            ))

        return new_rules

    def save(self) -> None:
        os.makedirs(self._persist_dir, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump({k: r.to_dict() for k, r in self._rules.items()}, f, indent=2)

    def load(self) -> None:
        if os.path.exists(self._path):
            with open(self._path) as f:
                data = json.load(f)
            self._rules = {k: Rule.from_dict(v) for k, v in data.items()}
            logger.info("Loaded %d neuro-symbolic rules", len(self._rules))

    def stats(self) -> Dict[str, Any]:
        return {
            "total_rules": len(self._rules),
            "by_source": {s: sum(1 for r in self._rules.values() if r.source == s)
                          for s in set(r.source for r in self._rules.values())},
            "avg_confidence": sum(r.confidence for r in self._rules.values()) / max(1, len(self._rules)),
        }


# ═══ Seed rules: bootstrap from current hardcoded logic ═══

SEED_RULES = [
    Rule(
        name="personality_t_type",
        premise={"strengthen": {">=": 2}},
        conclusion={"tag": "personality_analytical", "confidence": 0.7},
        source="manual",
    ),
    Rule(
        name="personality_f_type",
        premise={"weaken": {">=": 3}},
        conclusion={"tag": "personality_emotional", "confidence": 0.7},
        source="manual",
    ),
    Rule(
        name="reject_detected",
        premise={"reject": {">=": 1}},
        conclusion={"action": "meta_warn", "message": "用户纠正信号检测到"},
        source="manual",
    ),
    Rule(
        name="high_confidence_intj",
        premise={"strengthen": {">=": 3}, "profile_tags": {"contains": "personality_analytical"}},
        conclusion={"action": "raise_confidence", "delta": 0.1},
        source="manual",
    ),
    Rule(
        name="low_mind_new_domain",
        premise={"mind_relations": {"<=": 3}, "active_domains": {"in": "engineering"}},
        conclusion={"action": "expand_context", "depth": 3},
        source="manual",
    ),
]
