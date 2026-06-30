# -*- coding: utf-8 -*-
"""
core/agent/pcr/registry.py
─────────────────────────
PCR plugin discovery and registration engine.

Supports two registration patterns:
  1. Explicit registration: code calls register_pcr()
  2. Directory auto-discovery: scan a directory tree, auto-import __init__.py

Directory structure convention:
    pcr_plugins/
    ├── __init__.py
    ├── rule_based/
    │   ├── __init__.py          # contains: register_pcr("rule_based", RuleBasedPCR)
    │   ├── identifier.py
    │   ├── estimator.py
    │   └── config.yaml
    └── llm_enhanced/
        ├── __init__.py
        └── ...

Usage:
    from core.agent.pcr import register_pcr, create_pcr, discover_pcr_plugins
    register_pcr("rule_based", RuleBasedPCR)
    pcr = create_pcr("rule_based", config={"complexity_map": "..."})
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from core.agent.pcr.interface import IPCRRouter

logger = logging.getLogger("pcr.registry")

# ═══════════════════════════════════════════════════════════════════════════════
# Global Registry
# ═══════════════════════════════════════════════════════════════════════════════

_PCR_REGISTRY: Dict[str, Type[IPCRRouter]] = {}


def register_pcr(name: str, cls: Type[IPCRRouter]) -> None:
    """Explicitly register a PCR implementation.

    Args:
        name: Unique identifier (e.g. "rule_based", "llm_enhanced").
        cls: Class that implements IPCRRouter.

    Raises:
        TypeError: If cls does not inherit from IPCRRouter.
        ValueError: If name is already registered (prevents accidental overwrite).
    """
    if not isinstance(name, str) or not name:
        raise ValueError("name must be a non-empty string")
    if not issubclass(cls, IPCRRouter):
        raise TypeError(
            f"Cannot register '{name}': {cls.__name__} must implement IPCRRouter "
            f"(or one of its descendants)"
        )
    if name in _PCR_REGISTRY:
        existing = _PCR_REGISTRY[name].__name__
        raise ValueError(
            f"PCR implementation '{name}' is already registered by {existing}. "
            f"Use a different name or unregister the existing one first."
        )
    _PCR_REGISTRY[name] = cls
    logger.info(f"Registered PCR implementation: '{name}' -> {cls.__name__}")


def unregister_pcr(name: str) -> bool:
    """Remove a registered PCR implementation.

    Returns:
        True if the name was found and removed, False otherwise.
    """
    if name in _PCR_REGISTRY:
        del _PCR_REGISTRY[name]
        logger.info(f"Unregistered PCR implementation: '{name}'")
        return True
    return False


def is_registered(name: str) -> bool:
    """Check if a PCR implementation is registered."""
    return name in _PCR_REGISTRY


# ═══════════════════════════════════════════════════════════════════════════════
# Factory
# ═══════════════════════════════════════════════════════════════════════════════

def create_pcr(name: str, config: Optional[Dict[str, Any]] = None) -> IPCRRouter:
    """Factory: create an instance of the named PCR implementation and warm it up.

    Args:
        name: Registered implementation name.
        config: Configuration dict passed to warm_up().

    Returns:
        An initialized IPCRRouter instance (warm_up already called).

    Raises:
        ValueError: If name is not registered.
        RuntimeError: If warm_up raises an exception.
    """
    if name not in _PCR_REGISTRY:
        available = list(_PCR_REGISTRY.keys())
        raise ValueError(
            f"Unknown PCR implementation: '{name}'. "
            f"Available: {available}. "
            f"Call register_pcr() or discover_pcr_plugins() first."
        )

    cls = _PCR_REGISTRY[name]
    instance = cls()
    cfg = config or {}

    try:
        instance.warm_up(cfg)
    except Exception as e:
        raise RuntimeError(
            f"PCR implementation '{name}' warm_up failed: {e}"
        ) from e

    return instance


# ═══════════════════════════════════════════════════════════════════════════════
# Directory Discovery
# ═══════════════════════════════════════════════════════════════════════════════

def discover_pcr_plugins(plugin_dir: str) -> List[str]:
    """Auto-discover and register PCR plugins from a directory.

    Scans the given directory for subdirectories containing __init__.py.
    Each __init__.py is executed in a dynamically created module namespace;
    it should call register_pcr() to register its implementation.

    Args:
        plugin_dir: Absolute or relative path to the plugin directory.

    Returns:
        List of discovered plugin names (those that successfully registered).
    """
    discovered: List[str] = []
    plugin_path = Path(plugin_dir)

    if not plugin_path.exists():
        logger.warning(f"Plugin directory does not exist: {plugin_dir}")
        return discovered

    if not plugin_path.is_dir():
        logger.warning(f"Plugin path is not a directory: {plugin_dir}")
        return discovered

    for subdir in sorted(plugin_path.iterdir()):
        if not subdir.is_dir():
            continue
        if subdir.name.startswith("_") or subdir.name.startswith("."):
            continue

        init_file = subdir / "__init__.py"
        if not init_file.exists():
            continue

        module_name = f"pcr_plugins.{subdir.name}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, init_file)
            if spec is None or spec.loader is None:
                logger.warning(
                    f"Could not create spec for plugin '{subdir.name}' at {init_file}"
                )
                continue

            module = importlib.util.module_from_spec(spec)
            # Prevent re-import collisions
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            discovered.append(subdir.name)
            logger.info(f"Discovered and loaded PCR plugin: '{subdir.name}'")

        except Exception as e:
            logger.error(
                f"Failed to load PCR plugin '{subdir.name}': {e}",
                exc_info=True,
            )

    return discovered


# ═══════════════════════════════════════════════════════════════════════════════
# Introspection
# ═══════════════════════════════════════════════════════════════════════════════

def list_available_pcr() -> Dict[str, Dict[str, Any]]:
    """List all registered PCR implementations and their capabilities.

    Returns:
        Dict mapping name -> capability dict (from get_capabilities()).
    """
    result: Dict[str, Dict[str, Any]] = {}
    for name, cls in _PCR_REGISTRY.items():
        try:
            # Instantiate with no-arg constructor to query capabilities
            # (warm_up not called here — capabilities are static)
            instance = cls()
            result[name] = instance.get_capabilities()
        except Exception as e:
            result[name] = {"error": f"Failed to query capabilities: {e}"}
    return result


def get_pcr_class(name: str) -> Optional[Type[IPCRRouter]]:
    """Get the registered class for a PCR implementation without instantiating."""
    return _PCR_REGISTRY.get(name)


def clear_registry() -> None:
    """Clear all registered implementations. Mainly for testing."""
    _PCR_REGISTRY.clear()
    logger.debug("PCR registry cleared")
