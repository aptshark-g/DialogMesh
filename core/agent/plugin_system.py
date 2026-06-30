# -*- coding: utf-8 -*-
"""
core/agent/plugin_system.py
───────────────────────────
Plugin registry for custom strategy implementations.

Allows users to register and inject custom Segmenter, SummaryEngine,
and HeaderInjector implementations into the DiscoursePipeline.

Usage:
    from core.agent.plugin_system import PluginRegistry

    PluginRegistry.register_strategy(
        name="aggressive_split",
        component_type="segmenter",
        factory_func=lambda: AggressiveSegmenter()
    )

    dp = DiscoursePipeline(strategy={"segmenter": "aggressive_split"})
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Type

logger = logging.getLogger(__name__)

# ── Default import paths ──────────────────────────────────────────
_DEFAULT_SEGMENTER = "core.agent.discourse_block_tree.segmenter:Segmenter"
_DEFAULT_SUMMARY = "core.agent.discourse_block_tree.summary_engine:SummaryEngine"
_DEFAULT_INJECTOR = "core.agent.compiler.header_injector:HeaderInjector"


def _import_default(path: str):
    """Dynamically import a default class by module:class path."""
    module_path, class_name = path.split(":")
    mod = __import__(module_path, fromlist=[class_name])
    return getattr(mod, class_name)


class PluginRegistry:
    """Global registry for custom DiscourseBlock Tree strategy plugins."""

    # Supported component types
    COMPONENT_TYPES = {"segmenter", "summary_engine", "header_injector"}

    # Lazy-loaded default factories
    _default_factories: Dict[str, Callable[[], Any]] = {}
    _custom_factories: Dict[str, Dict[str, Callable[[], Any]]] = {
        "segmenter": {},
        "summary_engine": {},
        "header_injector": {},
    }

    @classmethod
    def register_strategy(
        cls,
        name: str,
        component_type: str,
        factory_func: Callable[[], Any],
    ) -> None:
        """Register a custom strategy factory.

        Args:
            name: Unique strategy name (e.g., "my_custom_segmenter").
            component_type: One of "segmenter", "summary_engine", "header_injector".
            factory_func: Zero-argument callable that returns the component instance.

        Raises:
            ValueError: If component_type is not supported.
        """
        if component_type not in cls.COMPONENT_TYPES:
            raise ValueError(
                f"Unsupported component_type: {component_type}. "
                f"Must be one of {cls.COMPONENT_TYPES}"
            )
        cls._custom_factories[component_type][name] = factory_func
        logger.info(f"Registered strategy '{name}' for {component_type}")

    @classmethod
    def get_strategy(
        cls,
        component_type: str,
        name: Optional[str] = None,
    ) -> Any:
        """Resolve and instantiate a strategy.

        If *name* is None or not registered, falls back to the default implementation.

        Args:
            component_type: One of the supported component types.
            name: Registered strategy name, or None for default.

        Returns:
            An instantiated component (e.g., a Segmenter instance).
        """
        if component_type not in cls.COMPONENT_TYPES:
            raise ValueError(
                f"Unsupported component_type: {component_type}. "
                f"Must be one of {cls.COMPONENT_TYPES}"
            )

        custom_map = cls._custom_factories.get(component_type, {})
        if name and name in custom_map:
            logger.debug(f"Using custom strategy '{name}' for {component_type}")
            return custom_map[name]()

        # Fallback to default
        logger.debug(f"Using default strategy for {component_type}")
        return cls._get_default(component_type)()

    @classmethod
    def _get_default(cls, component_type: str) -> Callable[[], Any]:
        """Lazy-load and cache the default factory for a component type."""
        if component_type not in cls._default_factories:
            if component_type == "segmenter":
                cls._default_factories[component_type] = lambda: _import_default(
                    _DEFAULT_SEGMENTER
                )()
            elif component_type == "summary_engine":
                cls._default_factories[component_type] = lambda: _import_default(
                    _DEFAULT_SUMMARY
                )()
            elif component_type == "header_injector":
                cls._default_factories[component_type] = lambda: _import_default(
                    _DEFAULT_INJECTOR
                )()
        return cls._default_factories[component_type]

    @classmethod
    def list_strategies(cls, component_type: Optional[str] = None) -> Dict[str, list]:
        """List all registered custom strategy names.

        Args:
            component_type: Filter by component type, or None for all.

        Returns:
            Dict mapping component_type → list of registered strategy names.
        """
        if component_type:
            if component_type not in cls.COMPONENT_TYPES:
                raise ValueError(f"Unsupported component_type: {component_type}")
            return {component_type: list(cls._custom_factories[component_type].keys())}
        return {
            ct: list(factories.keys())
            for ct, factories in cls._custom_factories.items()
        }

    @classmethod
    def unregister_strategy(cls, name: str, component_type: str) -> bool:
        """Unregister a custom strategy.

        Returns:
            True if the strategy was removed, False if it did not exist.
        """
        custom_map = cls._custom_factories.get(component_type, {})
        if name in custom_map:
            del custom_map[name]
            logger.info(f"Unregistered strategy '{name}' from {component_type}")
            return True
        return False

    @classmethod
    def clear(cls) -> None:
        """Clear all registered custom strategies (mainly for testing)."""
        for ct in cls.COMPONENT_TYPES:
            cls._custom_factories[ct].clear()
        logger.info("Cleared all custom strategy registrations")


# ── Example: Minimal always-split Segmenter (plugin demo) ───────

class AlwaysSplitSegmenter:
    """Example plugin: a Segmenter that always splits every EDU into its own block.

    This is a minimal demonstration of how to write a custom plugin.
    """

    def __init__(self, threshold: float = 0.0):
        self.threshold = threshold

    def segment(self, edus):
        """Segment every EDU into its own DiscourseBlock."""
        from core.agent.discourse_block_tree.models import BlockState, DiscourseBlock

        blocks = []
        for edu in edus:
            block = DiscourseBlock(
                id=f"block:{edu.id}",
                edus=[edu],
                start_turn=edu.turn_index,
                end_turn=edu.turn_index,
                state=BlockState.ACTIVE,
            )
            block._update_entity_signature()
            blocks.append(block)
        return blocks

    def compute_block_boundary_cohesion(self, block_a, block_b):
        """Always return 0.0 (never merge)."""
        return 0.0


# Register the demo plugin on module import (optional convenience)
PluginRegistry.register_strategy(
    name="always_split",
    component_type="segmenter",
    factory_func=lambda: AlwaysSplitSegmenter(),
)
