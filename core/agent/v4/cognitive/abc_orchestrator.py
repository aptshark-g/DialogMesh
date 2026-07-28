"""ABC Orchestrator — three-layer decision system.

Layer 3 (C): Neuro-symbolic rules → first priority, fastest, explainable
Layer 2 (B): LLM adaptation    → second, generates new rules
Layer 1 (A): JSON soft config  → fallback defaults, always available

Usage:
    abc = ABCOrchestrator(engine, llm_provider=prov)
    result = abc.decide()  # Returns best conclusion from 3 layers
"""
from __future__ import annotations
import logging
from typing import Dict, Any, Optional

from .neuro_symbolic import RuleEngine, SEED_RULES
from .llm_adapter import LLMAdapter

logger = logging.getLogger(__name__)


# Layer A: Default configuration (JSON-serializable, user-editable)
DEFAULT_CONFIG = {
    "thresholds": {
        "personality_t": {"strengthen": 2, "source": "L1_default"},
        "personality_f": {"weaken": 3, "source": "L1_default"},
        "reject_warn": {"reject": 1, "source": "L1_default"},
        "confidence_floor": 0.4,
        "bge_top_k": 10,
        "subgraph_depth": 2,
        "subgraph_max_nodes": 50,
        "discourse_jaccard": 0.3,
        "mind_learn_interval": 5,
    },
    "layers": {
        "C_enabled": True,   # Neuro-symbolic rules
        "B_enabled": True,   # LLM adaptation
        "A_enabled": True,   # JSON defaults
    },
}


class ABCOrchestrator:
    """Three-layer decision engine for DialogMesh v6.

    Priority: C (symbolic) > B (LLM) > A (JSON).
    C is fastest (pure logic), B is adaptive (LLM once, rule forever),
    A is the safety net.
    """

    def __init__(self, config: Optional[Dict] = None, llm_provider=None,
                 persist_dir: str = "data", enable_b: bool = True, enable_c: bool = True):
        self._config = config or DEFAULT_CONFIG
        self._llm = llm_provider

        # Layer C: Neuro-symbolic rules
        self._rule_engine: Optional[RuleEngine] = None
        if enable_c:
            self._rule_engine = RuleEngine(persist_dir=persist_dir)
            for rule in SEED_RULES:
                self._rule_engine.register(rule)
            self._rule_engine.save()

        # Layer B: LLM adapter
        self._llm_adapter: Optional[LLMAdapter] = None
        if enable_b and llm_provider and self._rule_engine:
            self._llm_adapter = LLMAdapter(llm_provider=llm_provider,
                                           rule_engine=self._rule_engine)

        self._history: list = []

    def decide(self, engine) -> Dict[str, Any]:
        """C → B → A fallback chain. Returns best decision with source."""
        state = {"decision": None, "source": "none", "confidence": 0}

        # Layer C: Symbolic rules
        if self._rule_engine:
            result = self._rule_engine.evaluate(engine)
            if result:
                result["layer"] = "C"
                self._history.append(result)
                return result

        # Layer B: LLM adaptation
        if self._llm_adapter:
            raw_state = self._rule_engine._extract_state(engine) if self._rule_engine else {}
            rule = self._llm_adapter.adapt(engine, raw_state)
            if rule:
                result = {
                    "layer": "B",
                    "rule": rule.name,
                    "conclusion": rule.conclusion,
                    "confidence": rule.confidence,
                    "source": "L2_llm",
                }
                self._history.append(result)
                return result

        # Layer A: JSON defaults
        state["decision"] = self._get_default()
        state["source"] = "L1_default"
        state["layer"] = "A"
        state["confidence"] = 0.6  # Defaults are reliable but not adaptive
        self._history.append(state)
        return state

    def _get_default(self) -> Dict[str, Any]:
        return self._config.get("thresholds", DEFAULT_CONFIG["thresholds"])

    def learn_from_feedback(self, rule_name: str, correct: bool) -> None:
        """User feedback → update rule confidence in C layer."""
        if self._rule_engine:
            self._rule_engine.learn(rule_name, correct)
            self._rule_engine.save()

    def generate_rules_from_session(self, engine) -> int:
        """Learn rules from a completed session trace."""
        if not self._rule_engine:
            return 0
        new_rules = self._rule_engine.rules_from_trace(engine)
        for rule in new_rules:
            self._rule_engine.register(rule)
        if new_rules:
            self._rule_engine.save()
            logger.info("L3: learned %d new rules from session", len(new_rules))
        return len(new_rules)

    def report(self) -> Dict[str, Any]:
        return {
            "hits": len(self._history),
            "by_layer": {
                layer: sum(1 for h in self._history if h.get("layer") == layer)
                for layer in ["C", "B", "A"]
            },
            "rules": self._rule_engine.stats() if self._rule_engine else {},
            "config_layers": {
                "C": self._config["layers"]["C_enabled"],
                "B": self._config["layers"]["B_enabled"],
                "A": self._config["layers"]["A_enabled"],
            },
        }


    def add_rule(self, rule: dict) -> None:
        """Add a neuro-symbolic rule (CLI)."""
        if not hasattr(self, '_custom_rules'):
            self._custom_rules = []
        self._custom_rules.append(rule)

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by id (CLI)."""
        if not hasattr(self, '_custom_rules'):
            return False
        before = len(self._custom_rules)
        self._custom_rules = [r for r in self._custom_rules if r.get('id') != rule_id]
        return len(self._custom_rules) < before
