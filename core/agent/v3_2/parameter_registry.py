"""DialogMesh v4 ParameterRegistry — adaptive parameter system with integration wiring.

Extends (NOT replaces) the v3.2 adaptive_parameter module:
  - AdaptiveParameter      → kept as-is, extended with v4 reanchor() method
  - ParameterCalibrator    → kept as-is, wrapped by ParameterRegistry
  - CALIBRATOR             → backward-compatible global singleton

New v4 additions:
  - ParameterRegistry      → unified registry with namespace isolation,
                             persistence hooks, integration wiring, and
                             named strategy presets for atomic global switching
  - ParameterNamespace     → scoped parameter groups (compiler, graph,
                             predictor, rewarder, foa, context_engine)
  - IntegrationWiring      → declarative wiring to v3.2 subsystems
  - v4_PREDEFINED          → extended parameter set for Context Engineering
  - Strategy presets       → balanced, conservative, aggressive, exploration, recovery

Backward compatibility:
  >>> from core.agent.v3_2.adaptive_parameter import CALIBRATOR
  >>> CALIBRATOR.value("compiler_confidence")        # still works
  >>> CALIBRATOR.update("compiler_confidence", 0.01) # still works

v4 usage:
  >>> from core.agent.v3_2.parameter_registry import REGISTRY
  >>> REGISTRY.get("compiler.confidence")            # dot-notation namespace
  >>> REGISTRY.switch_strategy("aggressive")         # atomic global re-anchor
  >>> REGISTRY.wire_to("compiler", pipeline.compiler) # integration wiring
"""

from __future__ import annotations

import time
import json
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional, Any
from pathlib import Path
from enum import Enum

# ---------------------------------------------------------------------------
# Import v3.2 base classes (extended, not replaced)
# Use a guarded import to avoid triggering the v3_2 __init__ (which loads
# numpy-dependent modules) when this file is loaded in isolation.
# ---------------------------------------------------------------------------
try:
    from .adaptive_parameter import (
        ParamConfig,
        AdaptiveParameter,
        ParameterCalibrator,
        PREDEFINED as v3_PREDEFINED,
        CALIBRATOR as v3_CALIBRATOR,
    )
except ImportError:
    # Fallback for when the package __init__ is not yet importable
    import importlib.util
    import os
    _ap_path = os.path.join(os.path.dirname(__file__), "adaptive_parameter.py")
    _spec = importlib.util.spec_from_file_location("adaptive_parameter", _ap_path)
    _ap_mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_ap_mod)
    ParamConfig = _ap_mod.ParamConfig
    AdaptiveParameter = _ap_mod.AdaptiveParameter
    ParameterCalibrator = _ap_mod.ParameterCalibrator
    v3_PREDEFINED = _ap_mod.PREDEFINED
    v3_CALIBRATOR = _ap_mod.CALIBRATOR

__all__ = [
    # v3.2 re-exports
    "ParamConfig",
    "AdaptiveParameter",
    "ParameterCalibrator",
    "v3_CALIBRATOR",
    # v4 new
    "ParameterRegistry",
    "ParameterNamespace",
    "IntegrationWiring",
    "v4_PREDEFINED",
    "STRATEGY_PRESETS",
    "REGISTRY",
    "get_value",
    "get_param",
    # reward_signals_v30
    "SignalSource",
    "SignalEvent",
    "ParameterSnapshot",
    "create_registry_with_preset",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# reward_signals_v30 — signal provenance and event tracking
# ---------------------------------------------------------------------------

class SignalSource(Enum):
    """Canonical sources for reward signals in v3.2."""
    PREDICTOR = "predictor"
    REWARDER = "rewarder"
    TRAINING_LOOP = "training_loop"
    NOISE_ADAPTATION = "noise_adaptation"
    ABL_REFLECTION = "abl_reflection"
    MANUAL = "manual"
    EXTERNAL = "external"


@dataclass
class SignalEvent:
    """A single reward signal event with full provenance."""
    param_name: str
    value: float
    source: SignalSource = SignalSource.MANUAL
    timestamp: float = field(default_factory=time.time)
    context: dict = field(default_factory=dict)
    edge_key: str = ""
    turn: int = 0

    def to_dict(self) -> dict:
        return {
            "param_name": self.param_name,
            "value": round(self.value, 6),
            "source": self.source.value,
            "timestamp": self.timestamp,
            "context": self.context,
            "edge_key": self.edge_key,
            "turn": self.turn,
        }


@dataclass
class ParameterSnapshot:
    """Immutable snapshot of a parameter at a point in time."""
    name: str
    value: float
    anchor: float
    range: tuple
    lr: float
    update_count: int
    timestamp: float

    def drift_from_anchor(self) -> float:
        """Relative drift from literature anchor: 0 = at anchor, ±1 = at bound."""
        lo, hi = self.range
        span = hi - lo
        if span == 0:
            return 0.0
        return (self.value - self.anchor) / span

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": round(self.value, 6),
            "anchor": self.anchor,
            "range": self.range,
            "lr": self.lr,
            "update_count": self.update_count,
            "timestamp": self.timestamp,
            "drift": round(self.drift_from_anchor(), 6),
        }


# ---------------------------------------------------------------------------
# v4 extended predefined parameters (Context Engineering additions)
# ---------------------------------------------------------------------------

@dataclass
class v4ParamConfig(ParamConfig):
    """Extended ParamConfig with v4 metadata."""
    namespace: str = "default"      # e.g. "compiler", "graph", "context_engine"
    description: str = ""
    tunable: bool = True            # false = frozen literature anchor
    persist: bool = True            # false = ephemeral, not saved
    version: str = "4.0.0"


# Flat name → v4ParamConfig (used for strategy preset compatibility)
# Also defines explicit dot-notation aliases for namespace access
v4_PREDEFINED: dict[str, v4ParamConfig] = {
    # --- Compiler ---
    "compiler_confidence": v4ParamConfig("compiler_confidence", 0.75, 0.65, 0.85, lr=0.02, namespace="compiler", description="HybridCompiler confidence threshold"),
    "stability_min": v4ParamConfig("stability_min", 0.60, 0.50, 0.70, lr=0.01, namespace="compiler", description="Minimum parse stability to accept"),
    "llm_retries": v4ParamConfig("llm_retries", 1, 0, 3, lr=0.1, namespace="compiler", description="Max LLM retry attempts"),

    # --- Graph ---
    "graph_alpha": v4ParamConfig("graph_alpha", 0.25, 0.10, 0.40, lr=0.01, namespace="graph", description="ACT-R activation decay factor"),
    "graph_beta": v4ParamConfig("graph_beta", 0.30, 0.15, 0.50, lr=0.01, namespace="graph", description="ACT-R base-level learning rate"),
    "graph_gamma": v4ParamConfig("graph_gamma", 0.05, 0.02, 0.15, lr=0.005, namespace="graph", description="Edge weight spreading factor"),
    "graph_delta": v4ParamConfig("graph_delta", 0.05, 0.03, 0.25, lr=0.005, namespace="graph", description="Edge weight consolidation factor"),

    # --- Predictor ---
    "pred_llm": v4ParamConfig("pred_llm", 0.35, 0.25, 0.55, lr=0.01, namespace="predictor", description="LLM predictor weight (ESMM/MMoE)"),
    "pred_history": v4ParamConfig("pred_history", 0.30, 0.15, 0.45, lr=0.01, namespace="predictor", description="History predictor weight"),
    "pred_cognitive": v4ParamConfig("pred_cognitive", 0.20, 0.05, 0.30, lr=0.005, namespace="predictor", description="Cognitive profile predictor weight"),
    "pred_profile": v4ParamConfig("pred_profile", 0.15, 0.05, 0.25, lr=0.005, namespace="predictor", description="User profile predictor weight"),

    # --- Rewarder ---
    "reward_hit": v4ParamConfig("reward_hit", 0.10, 0.05, 0.20, lr=0.005, namespace="rewarder", description="Positive reward for correct prediction"),
    "reward_fail": v4ParamConfig("reward_fail", -0.15, -0.25, -0.08, lr=0.005, namespace="rewarder", description="Negative reward for failed prediction"),
    "reward_correction": v4ParamConfig("reward_correction", -0.20, -0.35, -0.12, lr=0.005, namespace="rewarder", description="Penalty for user correction"),

    # --- FoA ---
    "foa_decay": v4ParamConfig("foa_decay", 0.30, 0.20, 0.50, lr=0.01, namespace="foa", description="Focus of Attention decay rate"),
    "foa_threshold": v4ParamConfig("foa_threshold", 0.30, 0.15, 0.50, lr=0.01, namespace="foa", description="FoA activation threshold"),

    # --- Similarity ---
    "sim_threshold": v4ParamConfig("sim_threshold", 0.75, 0.55, 0.85, lr=0.01, namespace="similarity", description="BGE semantic similarity threshold"),

    # --- v4 Context Engineering additions ---
    "ctx_token_budget": v4ParamConfig("ctx_token_budget", 500, 200, 2000, lr=1.0, namespace="context_engine", description="Context IR token budget", tunable=False),
    "ctx_compile_timeout": v4ParamConfig("ctx_compile_timeout", 100, 50, 500, lr=5.0, namespace="context_engine", description="Context Compiler timeout (ms)", tunable=False),
    "ctx_subgraph_hops": v4ParamConfig("ctx_subgraph_hops", 2, 1, 4, lr=0.1, namespace="context_engine", description="Subgraph expansion hop count"),
    "ctx_relevance_cutoff": v4ParamConfig("ctx_relevance_cutoff", 0.6, 0.3, 0.9, lr=0.01, namespace="context_engine", description="Minimum edge relevance for inclusion"),

    "mem_checkpoint_interval": v4ParamConfig("mem_checkpoint_interval", 50, 10, 200, lr=1.0, namespace="memory_compiler", description="Events between checkpoints", tunable=False),
    "mem_conflict_threshold": v4ParamConfig("mem_conflict_threshold", 0.8, 0.5, 0.95, lr=0.005, namespace="memory_compiler", description="Embedding similarity for conflict detection"),

    "fusion_meta_cog_weight": v4ParamConfig("fusion_meta_cog_weight", 0.15, 0.05, 0.30, lr=0.005, namespace="fusion", description="Metacognition signal weight in fusion"),
    "fusion_causal_weight": v4ParamConfig("fusion_causal_weight", 0.10, 0.03, 0.20, lr=0.005, namespace="fusion", description="Causal discovery signal weight in fusion"),
}

# Explicit dot-notation aliases: dot_key → flat_key
# This maps human-readable dot names to the flat v4_PREDEFINED keys.
DOT_ALIASES: dict[str, str] = {
    # Compiler
    "compiler.confidence": "compiler_confidence",
    "compiler.stability_min": "stability_min",
    "compiler.llm_retries": "llm_retries",
    # Graph
    "graph.alpha": "graph_alpha",
    "graph.beta": "graph_beta",
    "graph.gamma": "graph_gamma",
    "graph.delta": "graph_delta",
    # Predictor
    "predictor.llm": "pred_llm",
    "predictor.history": "pred_history",
    "predictor.cognitive": "pred_cognitive",
    "predictor.profile": "pred_profile",
    # Rewarder
    "rewarder.hit": "reward_hit",
    "rewarder.fail": "reward_fail",
    "rewarder.correction": "reward_correction",
    # FoA
    "foa.decay": "foa_decay",
    "foa.threshold": "foa_threshold",
    # Similarity
    "similarity.threshold": "sim_threshold",
    # Context Engine
    "context_engine.token_budget": "ctx_token_budget",
    "context_engine.compile_timeout": "ctx_compile_timeout",
    "context_engine.subgraph_hops": "ctx_subgraph_hops",
    "context_engine.relevance_cutoff": "ctx_relevance_cutoff",
    # Memory Compiler
    "memory_compiler.checkpoint_interval": "mem_checkpoint_interval",
    "memory_compiler.conflict_threshold": "mem_conflict_threshold",
    # Fusion
    "fusion.meta_cog_weight": "fusion_meta_cog_weight",
    "fusion.causal_weight": "fusion_causal_weight",
}


# ---------------------------------------------------------------------------
# Strategy presets — each strategy is a dict of {param_name: override_anchor}
# ---------------------------------------------------------------------------

STRATEGY_PRESETS: dict[str, dict[str, float]] = {
    "balanced": {},  # empty = use default anchors from PREDEFINED
    "conservative": {
        "compiler_confidence": 0.80,
        "stability_min": 0.65,
        "llm_retries": 2,
        "graph_alpha": 0.20,
        "graph_beta": 0.25,
        "graph_gamma": 0.03,
        "graph_delta": 0.03,
        "pred_llm": 0.30,
        "pred_history": 0.35,
        "pred_cognitive": 0.25,
        "pred_profile": 0.20,
        "reward_hit": 0.08,
        "reward_fail": -0.12,
        "reward_correction": -0.15,
        "foa_decay": 0.25,
        "foa_threshold": 0.35,
        "sim_threshold": 0.78,
    },
    "aggressive": {
        "compiler_confidence": 0.70,
        "stability_min": 0.55,
        "llm_retries": 0,
        "graph_alpha": 0.30,
        "graph_beta": 0.35,
        "graph_gamma": 0.08,
        "graph_delta": 0.08,
        "pred_llm": 0.40,
        "pred_history": 0.25,
        "pred_cognitive": 0.15,
        "pred_profile": 0.10,
        "reward_hit": 0.12,
        "reward_fail": -0.18,
        "reward_correction": -0.25,
        "foa_decay": 0.35,
        "foa_threshold": 0.25,
        "sim_threshold": 0.70,
    },
    "exploration": {
        "compiler_confidence": 0.72,
        "stability_min": 0.52,
        "llm_retries": 1,
        "graph_alpha": 0.35,
        "graph_beta": 0.40,
        "graph_gamma": 0.10,
        "graph_delta": 0.12,
        "pred_llm": 0.45,
        "pred_history": 0.20,
        "pred_cognitive": 0.18,
        "pred_profile": 0.12,
        "reward_hit": 0.15,
        "reward_fail": -0.10,
        "reward_correction": -0.18,
        "foa_decay": 0.40,
        "foa_threshold": 0.20,
        "sim_threshold": 0.65,
    },
    "recovery": {
        "compiler_confidence": 0.82,
        "stability_min": 0.68,
        "llm_retries": 3,
        "graph_alpha": 0.15,
        "graph_beta": 0.20,
        "graph_gamma": 0.02,
        "graph_delta": 0.02,
        "pred_llm": 0.25,
        "pred_history": 0.40,
        "pred_cognitive": 0.25,
        "pred_profile": 0.20,
        "reward_hit": 0.05,
        "reward_fail": -0.20,
        "reward_correction": -0.30,
        "foa_decay": 0.22,
        "foa_threshold": 0.40,
        "sim_threshold": 0.80,
    },
}


# ---------------------------------------------------------------------------
# ParameterNamespace — scoped parameter group
# ---------------------------------------------------------------------------

class ParameterNamespace:
    """A scoped namespace within the ParameterRegistry.

    Provides dot-notation access like ``ns.get("confidence")``
    which resolves to the full key ``{namespace}.confidence``.
    """

    def __init__(self, name: str, registry: ParameterRegistry):
        self.name = name
        self._registry = registry

    def _key(self, short_name: str) -> str:
        return f"{self.name}.{short_name}"

    def get(self, short_name: str) -> Optional[AdaptiveParameter]:
        return self._registry.get(self._key(short_name))

    def value(self, short_name: str) -> float:
        return self._registry.value(self._key(short_name))

    def update(self, short_name: str, signal: float):
        self._registry.update(self._key(short_name), signal)

    def multi_update(self, signals: dict[str, float]):
        mapped = {self._key(k): v for k, v in signals.items()}
        self._registry.multi_update(mapped)

    def report(self) -> dict[str, dict]:
        prefix = self.name + "."
        return {
            k[len(prefix):]: v
            for k, v in self._registry.report().items()
            if k.startswith(prefix)
        }

    def __repr__(self):
        return f"<ParameterNamespace '{self.name}'>"


# ---------------------------------------------------------------------------
# IntegrationWiring — declarative subsystem wiring
# ---------------------------------------------------------------------------

class IntegrationWiring:
    """Declarative wiring from ParameterRegistry to v3.2 subsystems.

    Each ``wire_to()`` call registers a subsystem and binds its
    configuration attributes to registry parameters.  When a parameter
    updates, the wired attribute is automatically refreshed.
    """

    def __init__(self, registry: ParameterRegistry):
        self._registry = registry
        self._wires: dict[str, dict[str, str]] = {}   # subsystem → {attr: param_key}
        self._instances: dict[str, Any] = {}          # subsystem → instance

    def wire_to(self, subsystem_name: str, instance: Any, mapping: Optional[dict[str, str]] = None):
        """Wire a subsystem instance to registry parameters.

        Args:
            subsystem_name: logical name, e.g. "compiler", "graph"
            instance: the actual object to wire into
            mapping: optional dict ``{instance_attr: registry_param_key}``.
                     If omitted, auto-discovers from ``v4_PREDEFINED``.
        """
        if mapping is None:
            mapping = {
                cfg.name.replace(f"{subsystem_name}_", ""): key
                for key, cfg in v4_PREDEFINED.items()
                if cfg.namespace == subsystem_name
            }
        self._wires[subsystem_name] = mapping
        self._instances[subsystem_name] = instance
        self._apply(subsystem_name)
        logger.debug("[ParameterRegistry] Wired '%s' (%d params)", subsystem_name, len(mapping))

    def _apply(self, subsystem_name: str):
        """Push current registry values into the wired instance."""
        instance = self._instances.get(subsystem_name)
        mapping = self._wires.get(subsystem_name, {})
        if instance is None:
            return
        for attr, param_key in mapping.items():
            val = self._registry.value(param_key)
            if hasattr(instance, attr):
                try:
                    setattr(instance, attr, val)
                except Exception as e:
                    logger.warning("[ParameterRegistry] Cannot set %s.%s = %s: %s", subsystem_name, attr, val, e)
            elif hasattr(instance, f"_{attr}"):
                try:
                    setattr(instance, f"_{attr}", val)
                except Exception as e:
                    logger.warning("[ParameterRegistry] Cannot set %s._%s = %s: %s", subsystem_name, attr, val, e)

    def refresh(self, subsystem_name: Optional[str] = None):
        """Refresh wired attributes from registry values.

        Call after loading persisted parameters or batch updates.
        """
        if subsystem_name:
            self._apply(subsystem_name)
        else:
            for name in self._wires:
                self._apply(name)

    def on_parameter_update(self, param_key: str):
        """Callback invoked by ParameterRegistry when a parameter changes.

        Only touches subsystems that actually map to the updated key.
        """
        for sub_name, mapping in self._wires.items():
            if param_key in mapping.values():
                self._apply(sub_name)

    def get_wiring_status(self) -> dict:
        """Return current wiring configuration for diagnostics."""
        return {
            sub: {
                "instance_type": type(self._instances[sub]).__name__,
                "mapped_params": list(mapping.values()),
            }
            for sub, mapping in self._wires.items()
        }


# ---------------------------------------------------------------------------
# ParameterRegistry — v4 unified registry
# ---------------------------------------------------------------------------

class ParameterRegistry(ParameterCalibrator):
    """v4 unified parameter registry with namespace isolation,
    persistence hooks, integration wiring, and named strategy presets.

    Backward compatibility:
      - ``registry.value("compiler_confidence")`` works (flat key)
      - ``registry.value("compiler.confidence")`` works (namespaced)
      - ``CALIBRATOR`` global remains untouched

    New capabilities:
      - switch_strategy(name)   — atomic re-anchor all params to strategy preset
      - register_strategy()     — add custom strategy dict
      - current_strategy        — read active strategy name
      - auto_switch()           — heuristic auto-switch based on runtime signals
      - wire_to()               — declarative subsystem integration wiring
      - save()/load()           — JSON persistence
      - checkpoint()            — context-manager for temporary overrides
    """

    def __init__(self, initial_strategy: str = "balanced"):
        super().__init__()
        self._strategies: dict[str, dict[str, float]] = dict(STRATEGY_PRESETS)
        self._current_strategy: str = initial_strategy
        self._switch_history: list[dict] = []
        self._wiring = IntegrationWiring(self)
        self._persist_path: Optional[Path] = None
        self._version = "4.0.0"
        self._load_count = 0
        self._save_count = 0
        # reward_signals_v30 state
        self._events: list[SignalEvent] = []
        self._events_by_param: dict[str, list[SignalEvent]] = {}
        self._snapshots: dict[str, list[ParameterSnapshot]] = {}
        self._history_limit = 500
        self._snapshot_interval = 50
        self._update_counter = 0
        self._bindings: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Registration (extends ParameterCalibrator)
    # ------------------------------------------------------------------

    def register(self, config: ParamConfig) -> AdaptiveParameter:
        """Register a single parameter."""
        key = getattr(config, "name", None) or "unknown"
        ap = AdaptiveParameter(config)
        self._params[key] = ap
        # Also register under dot-notation alias if namespace present
        namespace = getattr(config, "namespace", None)
        if namespace and namespace != "default":
            short = key.replace(f"{namespace}_", "")
            dot_key = f"{namespace}.{short}"
            self._params[dot_key] = ap
        return ap

    def register_preset(self):
        """Load all v4 predefined parameters."""
        for key, cfg in v4_PREDEFINED.items():
            # Copy config to avoid mutating shared v4_PREDEFINED entries
            # when reanchor() is called during strategy switching
            cfg_copy = v4ParamConfig(
                name=cfg.name,
                anchor=cfg.anchor,
                min_val=cfg.min_val,
                max_val=cfg.max_val,
                lr=cfg.lr,
                signal_fn=cfg.signal_fn,
                namespace=getattr(cfg, "namespace", "default"),
                description=getattr(cfg, "description", ""),
                tunable=getattr(cfg, "tunable", True),
                persist=getattr(cfg, "persist", True),
                version=getattr(cfg, "version", "4.0.0"),
            )
            if key not in self._params:
                self._params[key] = AdaptiveParameter(cfg_copy)
            # Ensure flat name alias exists
            raw_name = cfg_copy.name
            if raw_name not in self._params:
                self._params[raw_name] = self._params[key]
        # Register explicit dot-notation aliases from DOT_ALIASES
        for dot_key, flat_key in DOT_ALIASES.items():
            if flat_key in self._params and dot_key not in self._params:
                self._params[dot_key] = self._params[flat_key]
        logger.info("[ParameterRegistry] Loaded %d predefined parameters", len(v4_PREDEFINED))

    def namespace(self, name: str) -> ParameterNamespace:
        """Return a ParameterNamespace accessor."""
        return ParameterNamespace(name, self)

    # ------------------------------------------------------------------
    # Access (extends ParameterCalibrator)
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[AdaptiveParameter]:
        """Get parameter by flat or dot-notation key."""
        p = self._params.get(key)
        if p:
            return p
        # Try dot-notation: look up all params with matching namespace prefix
        if "." in key:
            parts = key.split(".")
            ns = parts[0]
            short = parts[1]
            # Search v4_PREDEFINED for a config whose namespace matches
            for flat_key, cfg in v4_PREDEFINED.items():
                if cfg.namespace == ns:
                    cfg_short = cfg.name.replace(f"{ns}_", "")
                    if cfg_short == short or cfg.name == short:
                        return self._params.get(flat_key)
            # Fallback: simple concatenation guess
            flat_guess = f"{ns}_{short}"
            return self._params.get(flat_guess)
        return None

    def value(self, key: str) -> float:
        """Get current value by key (flat or dot-notation)."""
        p = self.get(key)
        if p:
            return p.current
        # Fallback to v3_PREDEFINED or v4_PREDEFINED anchor
        flat_key = key.replace(".", "_")
        cfg = v3_PREDEFINED.get(flat_key) or v4_PREDEFINED.get(key) or v4_PREDEFINED.get(flat_key)
        if cfg:
            return cfg.anchor
        logger.warning("[ParameterRegistry] Unknown parameter '%s', returning 0.5", key)
        return 0.5

    # ------------------------------------------------------------------
    # Updates (extends ParameterCalibrator)
    # ------------------------------------------------------------------

    def update(self, name: str, signal: float):
        """Update parameter by signal (with bounds enforcement)."""
        p = self.get(name)
        if p:
            p.update(signal)
            self._wiring.on_parameter_update(name)
        else:
            logger.warning("[ParameterRegistry] Cannot update unknown parameter '%s'", name)

    def multi_update(self, signals: dict[str, float]):
        """Batch update multiple parameters."""
        for key, signal in signals.items():
            self.update(key, signal)

    def reset(self, key: str):
        """Reset parameter to its literature anchor."""
        p = self.get(key)
        if p:
            p.reset()
            self._wiring.on_parameter_update(key)

    def reset_all(self):
        """Reset all parameters to anchors."""
        for p in self._params.values():
            p.reset()
        self._wiring.refresh()

    # ------------------------------------------------------------------
    # v3.2 Calibrator compatibility shim
    # ------------------------------------------------------------------

    def suggest(self, prediction_hit: bool, correction: bool):
        """Backward-compatible suggest() from ParameterCalibrator."""
        if prediction_hit:
            self.update("pred_llm", 0.01)
            self.update("pred_history", -0.005)
            self._log_event("pred_llm", 0.01, SignalSource.PREDICTOR, context={"prediction_hit": True})
            self._log_event("pred_history", -0.005, SignalSource.PREDICTOR, context={"prediction_hit": True})
        if correction:
            self.update("pred_llm", -0.02)
            self.update("pred_history", 0.01)
            self.update("reward_correction", -0.002)
            self._log_event("pred_llm", -0.02, SignalSource.PREDICTOR, context={"correction": True})
            self._log_event("pred_history", 0.01, SignalSource.PREDICTOR, context={"correction": True})
            self._log_event("reward_correction", -0.002, SignalSource.REWARDER, context={"correction": True})
        if prediction_hit and not correction:
            self.update("reward_hit", 0.001)
            self.update("reward_fail", -0.001)
            self._log_event("reward_hit", 0.001, SignalSource.REWARDER, context={"prediction_hit": True, "correction": False})
            self._log_event("reward_fail", -0.001, SignalSource.REWARDER, context={"prediction_hit": True, "correction": False})
        if correction and not prediction_hit:
            self.update("reward_fail", 0.002)
            self._log_event("reward_fail", 0.002, SignalSource.REWARDER, context={"prediction_hit": False, "correction": True})

    # ------------------------------------------------------------------
    # reward_signals_v30 — Signal API
    # ------------------------------------------------------------------

    def apply_signal(
        self,
        name: str,
        value: float,
        source: SignalSource = SignalSource.MANUAL,
        context: Optional[dict[str, Any]] = None,
        edge_key: str = "",
        turn: int = 0,
    ) -> bool:
        """Apply a reward signal to a parameter with full provenance.

        Returns True if the parameter exists and was updated.
        """
        param = self.get(name)
        if param is None:
            return False

        # Clamp signal to avoid runaway updates
        clamped = max(-1.0, min(1.0, value))

        # Apply via legacy calibrator (bypass our own update() to avoid double-log)
        ParameterCalibrator.update(self, name, clamped)
        self._update_counter += 1

        # Log event
        evt = SignalEvent(
            param_name=name,
            value=clamped,
            source=source,
            context=context or {},
            edge_key=edge_key,
            turn=turn,
        )
        self._log_event_obj(evt)

        # Periodic snapshot
        if self._update_counter % self._snapshot_interval == 0:
            self._take_snapshot(name)

        return True

    def apply_signals(
        self,
        signals: list[SignalEvent],
        conflict_resolution: str = "sum",
    ) -> dict[str, bool]:
        """Batch-apply multiple signals with optional conflict resolution.

        conflict_resolution:
            "sum"    — add all signals for same param (default)
            "last"   — keep only the last signal per param
            "max"    — keep the signal with largest absolute value
            "mean"   — average signals per param
        """
        # Group by param
        grouped: dict[str, list[SignalEvent]] = {}
        for s in signals:
            grouped.setdefault(s.param_name, []).append(s)

        results = {}
        for name, evts in grouped.items():
            if conflict_resolution == "last":
                chosen = [evts[-1]]
            elif conflict_resolution == "max":
                chosen = [max(evts, key=lambda e: abs(e.value))]
            elif conflict_resolution == "mean":
                mean_val = sum(e.value for e in evts) / len(evts)
                merged = SignalEvent(
                    param_name=name,
                    value=mean_val,
                    source=SignalSource.EXTERNAL,
                    context={"merged_count": len(evts), "resolution": "mean"},
                )
                chosen = [merged]
            else:  # sum
                total = sum(e.value for e in evts)
                merged = SignalEvent(
                    param_name=name,
                    value=total,
                    source=SignalSource.EXTERNAL,
                    context={"merged_count": len(evts), "resolution": "sum"},
                )
                chosen = [merged]

            for evt in chosen:
                ok = self.apply_signal(
                    evt.param_name,
                    evt.value,
                    source=evt.source,
                    context=evt.context,
                    edge_key=evt.edge_key,
                    turn=evt.turn,
                )
                results[name] = ok
        return results

    # ------------------------------------------------------------------
    # reward_signals_v30 — Subsystem Bindings
    # ------------------------------------------------------------------

    def bind_rewarder(self, rewarder: Any):
        """Bind a BehaviorRewarder so its signals auto-route to registry.

        After binding, rewarder.on_prediction_result outputs are
        automatically fed into parameter updates.
        """
        self._bindings["rewarder"] = rewarder
        original_on_result = rewarder.on_prediction_result

        def _patched_on_result(prediction, actual, is_correction=False,
                               delta_t=0.0, context="", turn=0, has_alternative=False):
            sig, ref = original_on_result(prediction, actual, is_correction,
                                          delta_t, context, turn, has_alternative)
            # Route reward signal to registry
            if sig and getattr(sig, "edge_key", None):
                raw = getattr(sig, "raw_reward", getattr(sig, "reward", 0.0))
                eff = getattr(sig, "effective_reward", raw)
                self.apply_signal(
                    "reward_hit",
                    eff if not is_correction else 0.0,
                    source=SignalSource.REWARDER,
                    context={"raw": raw, "effective": eff, "edge_key": sig.edge_key},
                    edge_key=sig.edge_key,
                    turn=turn,
                )
                if is_correction:
                    self.apply_signal(
                        "reward_correction",
                        eff,
                        source=SignalSource.REWARDER,
                        context={"raw": raw, "effective": eff, "edge_key": sig.edge_key},
                        edge_key=sig.edge_key,
                        turn=turn,
                    )
            return sig, ref

        rewarder.on_prediction_result = _patched_on_result

    def bind_training_loop(self, training_loop: Any):
        """Bind a TrainingFeedbackLoop so its TrainingSignals update registry."""
        self._bindings["training_loop"] = training_loop
        original_on_user_action = training_loop.on_user_action

        def _patched_on_user_action(prediction, actual, actual_type, is_correction=False, delta_t=0.0):
            result = original_on_user_action(prediction, actual, actual_type, is_correction, delta_t)
            signal = result[0] if isinstance(result, tuple) else None
            edge_key = result[1] if isinstance(result, tuple) and len(result) > 1 else ""
            if signal:
                reward = getattr(signal, "reward", 0.0)
                # Route to predictor weights based on reward magnitude
                if reward > 0:
                    self.apply_signal("pred_llm", reward * 0.1,
                                      source=SignalSource.TRAINING_LOOP,
                                      context={"actual": actual, "is_correction": is_correction},
                                      edge_key=str(edge_key),
                                      turn=getattr(training_loop, "turn", 0))
                elif reward < 0:
                    self.apply_signal("pred_history", abs(reward) * 0.05,
                                      source=SignalSource.TRAINING_LOOP,
                                      context={"actual": actual, "is_correction": is_correction},
                                      edge_key=str(edge_key),
                                      turn=getattr(training_loop, "turn", 0))
            return result

        training_loop.on_user_action = _patched_on_user_action

    # ------------------------------------------------------------------
    # reward_signals_v30 — Introspection & History
    # ------------------------------------------------------------------

    def get_events(self, param_name: Optional[str] = None,
                   source: Optional[SignalSource] = None,
                   limit: int = 100) -> list[SignalEvent]:
        """Retrieve signal events with optional filtering."""
        evts = self._events_by_param.get(param_name, self._events) if param_name else self._events
        if source:
            evts = [e for e in evts if e.source == source]
        return evts[-limit:]

    def get_snapshots(self, param_name: str, limit: int = 50) -> list[ParameterSnapshot]:
        """Get historical snapshots for a parameter."""
        return self._snapshots.get(param_name, [])[-limit:]

    def drift_report(self) -> dict[str, float]:
        """Report how far each parameter has drifted from its anchor."""
        report = {}
        for name, param in self._params.items():
            snap = ParameterSnapshot(
                name=name,
                value=param.current,
                anchor=param.config.anchor,
                range=(param.config.min_val, param.config.max_val),
                lr=param.config.lr,
                update_count=len(param._history),
                timestamp=time.time(),
            )
            report[name] = round(snap.drift_from_anchor(), 6)
        return report

    def full_report(self) -> dict:
        """Extended report including v4 history, drift, and strategy metrics."""
        legacy = self.report()
        for name, stats in legacy.items():
            stats["drift"] = self.drift_report().get(name, 0.0)
            stats["recent_events"] = len(self._events_by_param.get(name, []))
        legacy["_registry_meta"] = {
            "total_events": len(self._events),
            "total_updates": self._update_counter,
            "bound_subsystems": list(self._bindings.keys()),
            "current_strategy": self._current_strategy,
            "history_limit": self._history_limit,
        }
        return legacy

    def export_history(self, param_name: Optional[str] = None) -> list[dict]:
        """Export event history as plain dicts for serialization."""
        evts = self.get_events(param_name=param_name)
        return [e.to_dict() for e in evts]

    # ------------------------------------------------------------------
    # reward_signals_v30 — Internal helpers
    # ------------------------------------------------------------------

    def _log_event_obj(self, evt: SignalEvent):
        self._events.append(evt)
        self._events_by_param.setdefault(evt.param_name, []).append(evt)
        # Trim if over limit
        if len(self._events) > self._history_limit:
            self._events.pop(0)
        for buf in self._events_by_param.values():
            if len(buf) > self._history_limit:
                buf.pop(0)

    def _log_event(self, param_name: str, value: float, source: SignalSource,
                   context: Optional[dict[str, Any]] = None):
        self._log_event_obj(SignalEvent(
            param_name=param_name,
            value=value,
            source=source,
            context=context or {},
        ))

    def _take_snapshot(self, name: str):
        param = self.get(name)
        if not param:
            return
        snap = ParameterSnapshot(
            name=name,
            value=param.current,
            anchor=param.config.anchor,
            range=(param.config.min_val, param.config.max_val),
            lr=param.config.lr,
            update_count=len(param._history),
            timestamp=time.time(),
        )
        self._snapshots.setdefault(name, []).append(snap)
        buf = self._snapshots[name]
        if len(buf) > 100:
            buf.pop(0)

    # ------------------------------------------------------------------
    # Strategy management (v4 new)
    # ------------------------------------------------------------------

    @property
    def current_strategy(self) -> str:
        return self._current_strategy

    def register_strategy(self, name: str, overrides: dict[str, float]):
        """Register a custom strategy preset."""
        self._strategies[name] = dict(overrides)

    def switch_strategy(self, name: str, reason: str = "") -> dict:
        """Atomically switch all registered parameters to a named strategy.

        Returns a report of what changed.
        """
        if name not in self._strategies:
            raise ValueError(f"Unknown strategy '{name}'. Known: {list(self._strategies.keys())}")

        overrides = self._strategies[name]
        old_strategy = self._current_strategy
        changes: dict[str, tuple[float, float]] = {}

        for pname, param in self._params.items():
            if pname in overrides:
                old_anchor = param.config.anchor
                new_anchor = overrides[pname]
                if old_anchor != new_anchor:
                    param.reanchor(new_anchor)
                    changes[pname] = (old_anchor, new_anchor)
            else:
                # Reset to default anchor if not in new strategy
                default_cfg = v3_PREDEFINED.get(pname) or v4_PREDEFINED.get(pname)
                if default_cfg and param.config.anchor != default_cfg.anchor:
                    old_anchor = param.config.anchor
                    param.reanchor(default_cfg.anchor)
                    changes[pname] = (old_anchor, default_cfg.anchor)

        self._current_strategy = name
        entry = {
            "t": time.time(),
            "from": old_strategy,
            "to": name,
            "reason": reason,
            "changes": len(changes),
        }
        self._switch_history.append(entry)
        self._wiring.refresh()
        return {
            "strategy": name,
            "previous": old_strategy,
            "changes": changes,
            "changed_count": len(changes),
        }

    def auto_switch(self, runtime_signals: dict[str, float]) -> Optional[dict]:
        """Heuristic auto-switch based on runtime signals.

        Signals expected (all optional):
          - failure_rate: float 0-1  → high -> recovery
          - correction_rate: float 0-1 → high -> conservative
          - exploration_score: float 0-1 → high -> exploration
          - stability: float 0-1 → low -> aggressive
        Returns switch report if a switch occurred, else None.
        """
        fr = runtime_signals.get("failure_rate", 0.0)
        cr = runtime_signals.get("correction_rate", 0.0)
        es = runtime_signals.get("exploration_score", 0.0)
        st = runtime_signals.get("stability", 1.0)

        if fr > 0.4:
            target = "recovery"
        elif cr > 0.3:
            target = "conservative"
        elif es > 0.6:
            target = "exploration"
        elif st < 0.4:
            target = "aggressive"
        else:
            target = "balanced"

        if target != self._current_strategy:
            return self.switch_strategy(
                target,
                reason=f"auto: failure={fr:.2f} correction={cr:.2f} "
                       f"exploration={es:.2f} stability={st:.2f}"
            )
        return None

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def report(self) -> dict[str, dict]:
        """Full report of all registered parameters."""
        # Deduplicate by object identity
        seen: set[int] = set()
        result: dict[str, dict] = {}
        for key, p in self._params.items():
            oid = id(p)
            if oid in seen:
                continue
            seen.add(oid)
            result[key] = p.stats()
        return result

    def report_namespace(self, ns: str) -> dict[str, dict]:
        """Report only parameters in a given namespace."""
        prefix = ns + "."
        return {k: v for k, v in self.report().items() if k.startswith(prefix) or v.get("name", "").startswith(f"{ns}_")}

    def strategy_report(self) -> dict:
        """Full registry status report."""
        return {
            "current_strategy": self._current_strategy,
            "available_strategies": list(self._strategies.keys()),
            "switch_history": self._switch_history[-10:],
            "parameters": self.report(),
        }

    def stats(self) -> dict:
        """Registry-level statistics."""
        r = self.report()
        return {
            "total_params": len(r),
            "total_updates": sum(v.get("updates", 0) for v in r.values()),
            "version": self._version,
            "current_strategy": self._current_strategy,
            "persist_path": str(self._persist_path) if self._persist_path else None,
            "load_count": self._load_count,
            "save_count": self._save_count,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def set_persist_path(self, path: str | Path):
        """Set the file path for JSON persistence."""
        self._persist_path = Path(path)

    def save(self, path: Optional[str | Path] = None) -> bool:
        """Save current parameter values to JSON.

        Stores only tunable, non-ephemeral parameters.
        """
        target = Path(path) if path else self._persist_path
        if not target:
            logger.warning("[ParameterRegistry] No persist path set")
            return False
        payload = {
            "version": self._version,
            "saved_at": time.time(),
            "current_strategy": self._current_strategy,
            "parameters": {},
        }
        for key, p in self._params.items():
            cfg = p.config
            if getattr(cfg, "tunable", True) and getattr(cfg, "persist", True):
                payload["parameters"][key] = {
                    "value": p.current,
                    "anchor": cfg.anchor,
                    "min": cfg.min_val,
                    "max": cfg.max_val,
                    "lr": cfg.lr,
                    "updates": len(p._history),
                }
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            self._save_count += 1
            logger.info("[ParameterRegistry] Saved %d params to %s", len(payload["parameters"]), target)
            return True
        except Exception as e:
            logger.error("[ParameterRegistry] Save failed: %s", e)
            return False

    def load(self, path: Optional[str | Path] = None) -> bool:
        """Load parameter values from JSON, overlaying on current config."""
        target = Path(path) if path else self._persist_path
        if not target or not target.exists():
            return False
        try:
            with open(target, "r", encoding="utf-8") as f:
                payload = json.load(f)
            for key, data in payload.get("parameters", {}).items():
                p = self.get(key)
                if p:
                    # Restore value within bounds
                    p.value = max(p.config.min_val, min(p.config.max_val, data.get("value", p.config.anchor)))
                else:
                    # Unknown param in file — register as ephemeral
                    cfg = v4ParamConfig(
                        name=key, anchor=data.get("anchor", 0.5),
                        min_val=data.get("min", 0.0), max_val=data.get("max", 1.0),
                        lr=data.get("lr", 0.01), persist=False,
                    )
                    self.register(cfg)
            # Restore strategy if present
            saved_strategy = payload.get("current_strategy")
            if saved_strategy and saved_strategy in self._strategies:
                self._current_strategy = saved_strategy
            self._load_count += 1
            self._wiring.refresh()
            logger.info("[ParameterRegistry] Loaded %d params from %s", len(payload.get("parameters", {})), target)
            return True
        except Exception as e:
            logger.error("[ParameterRegistry] Load failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Integration wiring access
    # ------------------------------------------------------------------

    @property
    def wiring(self) -> IntegrationWiring:
        return self._wiring

    def wire_to(self, subsystem_name: str, instance: Any, mapping: Optional[dict[str, str]] = None):
        """Convenience: delegate to IntegrationWiring."""
        self._wiring.wire_to(subsystem_name, instance, mapping)

    # ------------------------------------------------------------------
    # Context-manager support for checkpoint-scoped overrides
    # ------------------------------------------------------------------

    def checkpoint(self) -> "_CheckpointScope":
        """Return a context manager for temporary parameter overrides.

        Usage:
            with REGISTRY.checkpoint() as cp:
                cp.override("compiler.confidence", 0.99)
                # ... run experiment ...
            # values automatically restored
        """
        return _CheckpointScope(self)

    def clone_for_context(self, context_id: str) -> "ParameterRegistry":
        """Create a shallow copy with same strategy but independent params.
        Useful for per-session or per-user parameter contexts."""
        clone = ParameterRegistry(initial_strategy=self._current_strategy)
        clone._strategies = dict(self._strategies)
        for name, param in self._params.items():
            # Only copy each physical parameter once
            if name in clone._params:
                continue
            clone._params[name] = AdaptiveParameter(ParamConfig(
                name=param.config.name,
                anchor=param.config.anchor,
                min_val=param.config.min_val,
                max_val=param.config.max_val,
                lr=param.config.lr,
                signal_fn=param.config.signal_fn,
            ))
        return clone


class _CheckpointScope:
    """Context manager for temporary parameter overrides."""

    def __init__(self, registry: ParameterRegistry):
        self._registry = registry
        self._snapshots: dict[str, float] = {}

    def override(self, key: str, value: float):
        p = self._registry.get(key)
        if p and key not in self._snapshots:
            self._snapshots[key] = p.current
            p.value = max(p.config.min_val, min(p.config.max_val, value))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for key, old in self._snapshots.items():
            p = self._registry.get(key)
            if p:
                p.value = old
        self._registry.wiring.refresh()


# ---------------------------------------------------------------------------
# Global singletons
# ---------------------------------------------------------------------------

REGISTRY = ParameterRegistry()
REGISTRY.register_preset()


def create_registry_with_preset() -> ParameterRegistry:
    """Factory: create a ParameterRegistry pre-loaded with PREDEFINED parameters."""
    reg = ParameterRegistry()
    reg.register_preset()
    return reg


# ---------------------------------------------------------------------------
# Convenience helpers (default to REGISTRY, fallback to CALIBRATOR)
# ---------------------------------------------------------------------------

def get_value(name: str, use_registry: bool = True) -> float:
    if use_registry:
        return REGISTRY.value(name)
    return v3_CALIBRATOR.value(name)


def get_param(name: str, use_registry: bool = True) -> Optional[AdaptiveParameter]:
    if use_registry:
        return REGISTRY.get(name)
    return v3_CALIBRATOR.get(name)
