"""PCR dimension units — declarative registry (DESIGN_PCR §3.1).

Alignment: snips-nlu ProcessingUnit pattern. Each axis (X/Y/Z) is a set of
independently registered units (deterministic / vector / llm) executed in
registration order; a unit returns None to fall through to the next one.

This file is the ARCHITECTURE SKELETON — behaviour is preserved from
pcr_router_v2 (no re-tuning here). Units forward to the router's split
methods; the router owns class state (_mood_vectors, embedders, stanza).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CONFIG: Optional[Dict[str, Any]] = None
_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "pcr_dimensions.yaml"


def load_config() -> Dict[str, Any]:
    """Lazy-load config/pcr_dimensions.yaml (weights, order, thresholds)."""
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    try:
        import yaml
        with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
            _CONFIG = yaml.safe_load(fh) or {}
    except Exception as exc:
        logger.debug("pcr_dimensions.yaml not loaded (%s); using registry defaults", exc)
        _CONFIG = {}
    return _CONFIG


def axis_config(axis: str) -> Dict[str, Any]:
    """Per-axis config; falls back to empty dict when absent."""
    cfg = load_config()
    dims = cfg.get("dimensions", {})
    key = {"x": "x_distance", "y": "y_granularity", "z": "z_temperature"}.get(axis)
    return dims.get(key, {}) if key else {}


# ══════════════════════════════════════════════════════════════════════
# Registry — unit-name keyed per axis; execution order = registration order
# ══════════════════════════════════════════════════════════════════════

_UNITS: Dict[str, Dict[str, type]] = {}


def register(axis: str, name: str, tier: str):
    """Class decorator: register a dimension unit under axis+name."""
    def deco(cls):
        cls.axis = axis
        cls.name = name
        cls.tier = tier
        _UNITS.setdefault(axis, {})[name] = cls
        return cls
    return deco


def get_units(axis: str) -> List[type]:
    """Units for an axis, in registration (fallback) order."""
    return list(_UNITS.get(axis, {}).values())


def run_axis(axis: str, text: str, ctx: Optional[Dict[str, Any]] = None) -> Optional[float]:
    """Execute an axis's units; first non-None value wins.

    Order comes from config/pcr_dimensions.yaml calculators when present,
    else registration order. Disabled units are skipped. YAML order must
    match registration order to preserve behaviour (baseline config does).
    """
    ctx = ctx or {}
    axis_cfg = axis_config(axis)
    calc_cfg = axis_cfg.get("calculators")

    if calc_cfg:
        by_name = {u.name: u for u in get_units(axis)}
        ordered = []
        for entry in calc_cfg:
            name = entry.get("name") if isinstance(entry, dict) else entry
            if name in by_name and entry.get("enabled", True):
                ordered.append(by_name[name])
    else:
        ordered = get_units(axis)

    for unit_cls in ordered:
        try:
            value = unit_cls().compute(text, ctx)
        except Exception as exc:  # a unit must never break the axis
            logger.debug("unit %s/%s failed: %s", axis, unit_cls.name, exc)
            value = None
        if value is not None:
            return value
    return None


class DimensionUnit:
    """Base class for a single axis calculator."""

    axis: str = ""
    name: str = ""
    tier: str = "deterministic"

    def compute(self, text: str, ctx: Dict[str, Any]) -> Optional[float]:
        raise NotImplementedError


# ══════════════════════════════════════════════════════════════════════
# X axis — cognitive distance (0=near, 1=far)
# order: subgraph prior (vector) → SVO+nomic (vector) → NRC rarity → entity
# ══════════════════════════════════════════════════════════════════════


@register("x", "x_semantic_prior", "vector")
class XSemanticPrior(DimensionUnit):
    """X: real semantic distance vs subgraph/retrieval prior (DESIGN_PCR §5)."""

    def compute(self, text: str, ctx: Dict[str, Any]) -> Optional[float]:
        prior = ctx.get("prior")
        if not prior or not prior.strip():
            return None
        from core.agent.pcr_router_v2 import PCRRouterV2
        return PCRRouterV2._distance_prior(text, prior)


@register("x", "x_svo_nomic", "vector")
class XSvoNomic(DimensionUnit):
    """X: Stanza SVO subject/object cosine via nomic (LM Studio)."""

    def compute(self, text: str, ctx: Dict[str, Any]) -> Optional[float]:
        from core.agent.pcr_router_v2 import PCRRouterV2
        return PCRRouterV2._distance_svo_nomic(text, ctx.get("structural"))


@register("x", "x_nrc_rarity", "deterministic")
class XNrcRarity(DimensionUnit):
    """X: English NRC-VAD word rarity."""

    def compute(self, text: str, ctx: Dict[str, Any]) -> Optional[float]:
        from core.agent.pcr_router_v2 import PCRRouterV2
        return PCRRouterV2._distance_nrc_rarity(text, ctx.get("structural"))


@register("x", "x_entity_density", "deterministic")
class XEntityDensity(DimensionUnit):
    """X: explicit structural degradation (entity_density)."""

    def compute(self, text: str, ctx: Dict[str, Any]) -> Optional[float]:
        from core.agent.pcr_router_v2 import PCRRouterV2
        return PCRRouterV2._distance_entity(text, ctx.get("structural"))


# ══════════════════════════════════════════════════════════════════════
# Y axis — operational granularity (0=atomic, 1=complex)
# order: structural formula → LLM entity gap-fill recompute
# ══════════════════════════════════════════════════════════════════════


@register("y", "y_structural", "deterministic")
class YStructural(DimensionUnit):
    """Y: verb/entity/wordcount formula (unchanged from v2)."""

    def compute(self, text: str, ctx: Dict[str, Any]) -> Optional[float]:
        from core.agent.pcr_router_v2 import PCRRouterV2
        return PCRRouterV2._granularity_structural(text, ctx.get("structural"))


@register("y", "y_llm_entity", "llm")
class YLlmEntity(DimensionUnit):
    """Y: LLM entity gap-fill recompute (only when structural finds none)."""

    def compute(self, text: str, ctx: Dict[str, Any]) -> Optional[float]:
        from core.agent.pcr_router_v2 import PCRRouterV2
        return PCRRouterV2._granularity_llm(text, ctx.get("structural"))


# ══════════════════════════════════════════════════════════════════════
# Z axis — feedback expectation (-1=mirror, 0=explore, +1=solution)
# order: mood soft-vote (vector) → NRC-VAD → structural
# ══════════════════════════════════════════════════════════════════════


@register("z", "z_mood", "vector")
class ZMood(DimensionUnit):
    """Z: BGE mood class-aggregated soft vote (weak signal offline)."""

    def compute(self, text: str, ctx: Dict[str, Any]) -> Optional[float]:
        from core.agent.pcr_router_v2 import PCRRouterV2
        return PCRRouterV2._mood_vector(text)


@register("z", "z_nrc_vad", "deterministic")
class ZNrcVad(DimensionUnit):
    """Z: NRC-VAD lexicon (English dominance/valence)."""

    def compute(self, text: str, ctx: Dict[str, Any]) -> Optional[float]:
        from core.agent.pcr_router_v2 import PCRRouterV2
        return PCRRouterV2._mood_nrc(text)


@register("z", "z_structural", "deterministic")
class ZStructural(DimensionUnit):
    """Z: imperative/question structural fallback."""

    def compute(self, text: str, ctx: Dict[str, Any]) -> Optional[float]:
        from core.agent.pcr_router_v2 import PCRRouterV2
        return PCRRouterV2._mood_structural(text)


__all__ = [
    "DimensionUnit", "register", "get_units", "run_axis",
    "XSemanticPrior", "XSvoNomic", "XNrcRarity", "XEntityDensity",
    "YStructural", "YLlmEntity", "ZMood", "ZNrcVad", "ZStructural",
]
