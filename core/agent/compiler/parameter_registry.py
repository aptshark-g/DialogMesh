"""ParameterRegistry — centralized config for all DialogMesh thresholds.

Design: All tunable thresholds, confidence floors, TTLs, strategy weights
live here. No hardcoded values in individual modules.

Adaptive: Parameters marked adaptive=True auto-adjust via EMA observation.
Strategy presets: named parameter groups for atomic global switching.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class ParamDef:
    key: str
    value: Any
    type: str
    description: str
    vmin: Optional[float] = None
    vmax: Optional[float] = None
    adaptive: bool = False
    # Adaptive tracking
    _ema: Optional[float] = None
    _alpha: float = 0.1
    _last_adjusted: float = 0.0

    def observe(self, actual: float):
        """EMA update for adaptive parameters."""
        if not self.adaptive:
            return
        if self._ema is None:
            self._ema = self.value
        self._ema = self._alpha * actual + (1 - self._alpha) * self._ema
        self._last_adjusted = time.time()

    def adapt(self) -> bool:
        """Apply EMA-smoothed value if significant drift."""
        if not self.adaptive or self._ema is None:
            return False
        drift = abs(self._ema - self.value)
        if drift > 0.05 * max(abs(self.value), 0.01):
            new_val = round(self._ema, 4)
            if self.vmin is not None:
                new_val = max(self.vmin, new_val)
            if self.vmax is not None:
                new_val = min(self.vmax, new_val)
            self.value = new_val
            self._ema = None  # Reset after apply
            return True
        return False


class ParameterRegistry:
    """Central config store with adaptive self-tuning.

    Usage:
        reg = ParameterRegistry()
        reg.get("execution.context_threshold_8k")
        reg.observe("execution.edit_approval_rate", 0.85)
        reg.switch_strategy("conservative")
    """

    # ═══ Strategy Presets ═══

    STRATEGIES = {
        "balanced": {
            "execution.auto_approve_risk": "low",
            "execution.context_threshold_8k": True,
            "execution.context_threshold_16k": False,
            "execution.complexity_split_threshold": 0.6,
            "execution.max_retries": 3,
            "plan.confidence_threshold": 0.6,
            "plan.require_review_on_first_tool": True,
            "plan.require_review_on_risk_high": True,
        },
        "conservative": {
            "execution.auto_approve_risk": "none",
            "execution.context_threshold_8k": True,
            "execution.context_threshold_16k": True,
            "execution.complexity_split_threshold": 0.4,
            "execution.max_retries": 2,
            "plan.confidence_threshold": 0.8,
            "plan.require_review_on_first_tool": True,
            "plan.require_review_on_risk_high": True,
            "execution.stop_on_error": True,
        },
        "aggressive": {
            "execution.auto_approve_risk": "medium",
            "execution.context_threshold_8k": False,
            "execution.context_threshold_16k": False,
            "execution.complexity_split_threshold": 0.8,
            "execution.max_retries": 1,
            "plan.confidence_threshold": 0.4,
            "plan.require_review_on_first_tool": False,
            "plan.require_review_on_risk_high": False,
        },
        "exploration": {
            "execution.auto_approve_risk": "medium",
            "execution.complexity_split_threshold": 0.5,
            "execution.max_retries": 5,
            "plan.confidence_threshold": 0.3,
            "plan.require_review_on_first_tool": False,
        },
        "recovery": {
            "execution.auto_approve_risk": "low",
            "execution.stop_on_error": True,
            "execution.max_retries": 1,
            "plan.confidence_threshold": 0.9,
            "plan.require_review_on_first_tool": True,
            "plan.require_review_on_risk_high": True,
        },
    }

    def __init__(self):
        self._params: Dict[str, ParamDef] = {}
        self._namespace_index: Dict[str, List[str]] = {}
        self.load_all()

    def load_all(self):
        """Load all parameters from all namespaces."""
    def load_all(self):
        """Load all parameters from all namespaces."""
        _ADAPTIVE = {
            "execution.complexity_split_threshold", "execution.max_retries",
            "plan.confidence_threshold", "plan.learn_edit_approval_rate",
            "plan.learn_bash_approval_rate", "plan.learn_mcp_approval_rate",
            "relation.min_confidence_edge", "relation.min_confidence_causal",
            "behavior.default_confidence", "concept_graph.typed_edge_confidence",
        }
        for entry in self._all_defaults():
            key = entry[0]
            adaptive = key in _ADAPTIVE
            entry_list = list(entry)
            entry_list[-1] = adaptive
            self._register(*entry_list)

    def _register(self, key, value, typ, desc, vmin=None, vmax=None, adaptive=False):
        self._params[key] = ParamDef(key=key, value=value, type=typ,
                                      description=desc, vmin=vmin, vmax=vmax,
                                      adaptive=adaptive)
        ns = key.split(".")[0]
        if ns not in self._namespace_index:
            self._namespace_index[ns] = []
        self._namespace_index[ns].append(key)

    # ═══ Public API ═══

    def get(self, key: str, default: Any = None) -> Any:
        p = self._params.get(key)
        return p.value if p else default

    def set(self, key: str, value: Any) -> bool:
        p = self._params.get(key)
        if not p:
            return False
        if p.vmin is not None and isinstance(value, (int, float)) and value < p.vmin:
            return False
        if p.vmax is not None and isinstance(value, (int, float)) and value > p.vmax:
            return False
        p.value = value
        return True

    def observe(self, key: str, actual: float):
        """Record an observation for adaptive tuning."""
        p = self._params.get(key)
        if p and p.adaptive:
            p.observe(actual)

    def adapt_all(self) -> int:
        """Run adaptive adjustment on all params. Returns count of adjusted."""
        count = 0
        for p in self._params.values():
            if p.adapt():
                count += 1
        return count

    def namespace(self, prefix: str) -> Dict[str, Any]:
        return {k: self._params[k].value
                for k in self._namespace_index.get(prefix, [])}

    def all(self) -> Dict[str, Any]:
        return {k: p.value for k, p in self._params.items()}

    def switch_strategy(self, name: str) -> int:
        """Atomically switch to a named strategy preset. Returns count of changed params."""
        preset = self.STRATEGIES.get(name)
        if not preset:
            return 0
        count = 0
        for key, val in preset.items():
            if self.set(key, val):
                count += 1
        logger.info("Strategy switched: %s (%d params)", name, count)
        return count

    # ═══ All Defaults ═══

    @staticmethod
    def _all_defaults():
        return [
            # ── Execution: Context Thresholds ──
            ("execution.context_threshold_8k", True, "bool",
             "Split into sub-agents when context > 8K tokens", None),
            ("execution.context_threshold_16k", False, "bool",
             "Split when > 16K (only in conservative mode)", None),
            ("execution.context_threshold_32k", False, "bool",
             "Split when > 32K (emergency)", None),
            ("execution.context_max_tokens", 4000, "int",
             "Max tokens per sub-agent context window", 1000, 8000, None),

            # ── Execution: Task Decomposition ──
            ("execution.split_mode", "llm", "str",
             "How to decide sub-agent split: llm / threshold / composite / off", None),
            ("execution.complexity_split_threshold", 0.6, "float",
             "Complexity above which LLM considers splitting", 0.1, 1.0, None),
            ("execution.max_sub_agents", 8, "int",
             "Max concurrent sub-agents per task", 1, 20, None),
            ("execution.sub_agent_timeout_s", 60, "int",
             "Max seconds per sub-agent execution", 5, 300, None),

            # ── Execution: Risk & Safety ──
            ("execution.auto_approve_risk", "low", "str",
             "Max risk auto-approved: none / low / medium / high / all", None),
            ("execution.stop_on_error", False, "bool",
             "Stop all steps on first error", None),
            ("execution.max_retries", 3, "int",
             "Max retry attempts per step (ReAct loop)", 1, 10, None),
            ("execution.retry_backoff_ms", 500, "int",
             "Backoff between retries in ms", 100, 5000, None),

            # ── Execution: Memory Node ──
            ("execution.memory_chunk_size", 500, "int",
             "Target tokens per chunk when creating Memory Node", 100, 2000, None),
            ("execution.memory_max_chunks", 20, "int",
             "Max chunks to retrieve per query", 5, 50, None),
            ("execution.archive_after_ticks", 5, "int",
             "Ticks before archiving completed nodes", 1, 20, None),

            # ── Execution: ReAct Loop ──
            ("execution.react_max_cycles", 3, "int",
             "Max ReAct cycles per failing step", 1, 10, None),
            ("execution.react_temperature_drop", 0.2, "float",
             "Temperature drop per retry cycle", 0.05, 0.5, None),

            # ── Plan: Human-in-the-loop ──
            ("plan.confidence_threshold", 0.6, "float",
             "Plan confidence below which user review is required", 0.1, 1.0, None),
            ("plan.require_review_on_first_tool", True, "bool",
             "Require review on first use of edit/bash/MCP", None),
            ("plan.require_review_on_risk_high", True, "bool",
             "Always review HIGH/CRITICAL risk steps", None),
            ("plan.require_review_on_constraints", True, "bool",
             "Review when EngineeringChain flags constraints", None),
            ("plan.max_steps_before_review", 5, "int",
             "Force review when plan has more than N steps", 1, 20, None),

            # ── Plan: User Pattern Learning ──
            ("plan.learn_edit_approval_rate", 0.5, "float",
             "Initial approval rate for edit tool (EMA)", 0.0, 1.0, None),
            ("plan.learn_bash_approval_rate", 0.3, "float",
             "Initial approval rate for bash tool (EMA)", 0.0, 1.0, None),
            ("plan.learn_mcp_approval_rate", 0.2, "float",
             "Initial approval rate for MCP tools (EMA)", 0.0, 1.0, None),
            ("plan.learn_user_preference_ema_alpha", 0.1, "float",
             "EMA alpha for user preference learning", 0.01, 0.5, None),

            # ── Synthesis: Importance & Merge ──
            ("synthesis.high_value_threshold", 0.8, "float",
             "Importance above which = 1-merge (LLM only)", 0.5, 1.0, None),
            ("synthesis.mid_value_threshold", 0.4, "float",
             "Importance 0.4-0.8 = 2-merge (struct+LLM)", 0.2, 0.7, None),
            ("synthesis.max_merge_passes", 3, "int",
             "Max merge passes per item", 1, 5, None),

            # ── External Tool Fusion ──
            ("fusion.dedup_confidence_gap", 0.1, "float",
             "Min confidence gap to prefer one tool's result over another", 0.0, 0.5, None),
            ("fusion.max_tools_per_fusion", 5, "int",
             "Max external tool results to fuse at once", 1, 10, None),

            # ── Relation / Behavior / Concept (existing, kept) ──
            ("relation.min_confidence_edge", 0.15, "float",
             "Min confidence to create RelationEdge", 0.0, 1.0, None),
            ("relation.min_confidence_causal", 0.8, "float",
             "Min confidence for causal mechanism", 0.0, 1.0, None),
            ("behavior.default_confidence", 0.2, "float",
             "Default confidence for behavioral observations", 0.0, 1.0, None),
            ("behavior.ttl_seconds", 300, "int",
             "TTL for behavioral edges", 60, 3600, None),
            ("behavior.decay_rate", 0.05, "float",
             "Decay rate for behavioral edges", 0.0, 0.5, None),
            # ── Behavior Chain: predictor weights (BC05 §5.1 / A18) ──
            ("behavior.predict_weight_llm", 0.4, "float",
             "Predictor weight: LLM probability", 0.0, 1.0, None),
            ("behavior.predict_weight_success", 0.3, "float",
             "Predictor weight: historical success rate", 0.0, 1.0, None),
            ("behavior.predict_weight_load", 0.2, "float",
             "Predictor weight: inverse cognitive load", 0.0, 1.0, None),
            ("behavior.predict_weight_profile", 0.1, "float",
             "Predictor weight: profile match", 0.0, 1.0, None),
            # ── Behavior Chain: reward tiers (BC05 §6.1) ──
            ("behavior.reward_top1_hit", 1.0, "float",
             "Reward: prediction is exact top-1", -1.0, 1.0, None),
            ("behavior.reward_top3_hit", 0.5, "float",
             "Reward: prediction exact within top-3", -1.0, 1.0, None),
            ("behavior.reward_partial", 0.2, "float",
             "Reward: direction correct, detail off", -1.0, 1.0, None),
            ("behavior.reward_alternative", -0.3, "float",
             "Reward: missed but an alternative was offered", -1.0, 1.0, None),
            ("behavior.reward_miss", -0.5, "float",
             "Reward: prediction wrong (BC05 §6.1)", -1.0, 0.0, None),
            ("behavior.reward_correction", -0.2, "float",
             "Reward: user correction signal", -1.0, 0.0, None),
            ("behavior.correction_hard_threshold", 2, "int",
             "Consecutive corrections before hard override", 1, 10, None),
            # ── Behavior Chain: time decay / noise (P2-2 / P2-3) ──
            ("behavior.time_decay_no_decay", 30, "int",
             "Seconds without decay", 1, 3600, None),
            ("behavior.time_decay_moderate_tau", 300, "int",
             "Time-decay tau for moderate interval", 30, 3600, None),
            ("behavior.time_decay_strong_tau", 3600, "int",
             "Time-decay tau for long interval", 300, 86400, None),
            ("behavior.noise_min_samples", 30, "int",
             "Correction samples before noise adaptation engages", 5, 1000, None),
            ("behavior.reward_apply_rate", 0.1, "float",
             "Graph edge weight update rate per reward", 0.01, 0.5, None),
            # ── Behavior Chain: four-layer scheduler (BC05 §3 / A18) ──
            ("behavior.scheduler_token_budget", 2000, "int",
             "L1 cost floor: remaining token budget before stats-only", 100, 100000, None),
            ("behavior.scheduler_cold_turns", 3, "int",
             "L3 cold start: turns threshold for exploration", 0, 20, None),
            ("behavior.scheduler_epsilon_cold", 0.6, "float",
             "L3 cold-start exploration probability", 0.0, 1.0, None),
            ("behavior.scheduler_epsilon_stable", 0.05, "float",
             "Epsilon when data is abundant (BC05 §4)", 0.0, 0.5, None),
            ("behavior.scheduler_ci_converged", 0.15, "float",
             "L4 converged: CI width below this → stats only", 0.01, 0.5, None),
            ("behavior.scheduler_ci_diverged", 0.4, "float",
             "L4 diverged: CI width above this → ask user", 0.15, 1.0, None),
            ("behavior.dpo_min_pairs", 20, "int",
             "Preference pairs before DPO learning triggers (LLM_COLLABORATIVE §四)", 5, 500, None),
            ("behavior.dpo_correction_weight", 0.8, "float",
             "Correction-derived preferred pair weight", 0.0, 1.0, None),
            ("behavior.dpo_noop_weight", 0.3, "float",
             "No-response weak-signal weight (×0.3)", 0.0, 1.0, None),
            ("concept_graph.typed_edge_confidence", 0.5, "float",
             "Confidence for typed ConceptGraph edges", 0.0, 1.0, None),

            # ── Slow Path / Conversation (existing, kept) ──
            ("slow_path.event_threshold", 5, "int",
             "Events before Slow Path triggers", 2, 50, None),
            ("conversation.max_history_entries", 10, "int",
             "Max conversation history entries in context", 3, 30, None),
        ]


# ═══ Global Singleton ═══

_registry: Optional[ParameterRegistry] = None


def get_registry() -> ParameterRegistry:
    global _registry
    if _registry is None:
        _registry = ParameterRegistry()
    return _registry
