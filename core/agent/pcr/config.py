# -*- coding: utf-8 -*-
"""
core/agent/pcr/config.py
───────────────────────
PCR configuration manager.

Responsibilities:
  1. Load global and per-implementation configuration from YAML/JSON files.
  2. Support environment variable overrides (e.g. PCR_IMPLEMENTATION=rule_based).
  3. Validate configuration against schemas.
  4. Detect file changes at runtime for hot-reload.
  5. Provide typed access to configuration values.

Zero external dependencies beyond standard library and PyYAML (already used
by MemoryGraph).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = None  # Lazy import to avoid circular dependency

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


# ═══════════════════════════════════════════════════════════════════════════════
# Global Configuration
# ═══════════════════════════════════════════════════════════════════════════════

class PCRGlobalConfig:
    """Typed global configuration for the PCR subsystem."""

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        self._raw = data or {}
        self.implementation: str = self._raw.get("implementation", "rule_based")
        self.fallback_strategy: str = self._raw.get("fallback_strategy", "conservative")
        self.fallback_chain: List[str] = self._raw.get("fallback_chain", [])
        self.max_retry: int = self._raw.get("max_retry", 1)
        self.retry_delay_ms: float = self._raw.get("retry_delay_ms", 100.0)
        self.log_errors: bool = self._raw.get("log_errors", True)
        self.expose_errors_to_user: bool = self._raw.get("expose_errors_to_user", False)
        self.enable_telemetry: bool = self._raw.get("enable_telemetry", True)
        self.health_check_interval_sec: float = self._raw.get("health_check_interval_sec", 60.0)
        self.plugin_dirs: List[str] = self._raw.get("plugin_dirs", [])
        self.impl_config: Dict[str, Any] = self._raw.get("impl_config", {})

    def validate(self) -> Tuple[bool, Optional[str]]:
        if not isinstance(self.implementation, str) or not self.implementation:
            return False, "implementation must be a non-empty string"
        if self.fallback_strategy not in ("conservative", "degraded", "pass_through"):
            return False, f"fallback_strategy must be conservative/degraded/pass_through, got {self.fallback_strategy}"
        if not isinstance(self.max_retry, int) or self.max_retry < 0:
            return False, "max_retry must be a non-negative integer"
        if not isinstance(self.retry_delay_ms, (int, float)) or self.retry_delay_ms < 0:
            return False, "retry_delay_ms must be a non-negative number"
        if not isinstance(self.health_check_interval_sec, (int, float)) or self.health_check_interval_sec <= 0:
            return False, "health_check_interval_sec must be a positive number"
        return True, None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "implementation": self.implementation,
            "fallback_strategy": self.fallback_strategy,
            "fallback_chain": self.fallback_chain,
            "max_retry": self.max_retry,
            "retry_delay_ms": self.retry_delay_ms,
            "log_errors": self.log_errors,
            "expose_errors_to_user": self.expose_errors_to_user,
            "enable_telemetry": self.enable_telemetry,
            "health_check_interval_sec": self.health_check_interval_sec,
            "plugin_dirs": self.plugin_dirs,
            "impl_config": self.impl_config,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Config Manager
# ═══════════════════════════════════════════════════════════════════════════════

class ConfigManager:
    """
    Manages configuration files with hot-reload detection.

    Supports:
      - Global config file (YAML or JSON)
      - Per-implementation config files (YAML or JSON)
      - Environment variable overrides (PCR_* prefix)
      - Runtime file modification detection
    """

    def __init__(
        self,
        global_path: str,
        implementation_configs: Optional[Dict[str, str]] = None,
    ):
        self._global_path = Path(global_path)
        self._impl_paths: Dict[str, Path] = {}
        if implementation_configs:
            for name, path in implementation_configs.items():
                self._impl_paths[name] = Path(path)

        self._global_config: Optional[PCRGlobalConfig] = None
        self._impl_configs: Dict[str, Dict[str, Any]] = {}
        self._last_modified: Dict[str, float] = {}

        self._load_all()

    # ── Loading ─────────────────────────────────────────────────────────────

    def _load_all(self) -> None:
        """Load all configured files."""
        if self._global_path.exists():
            self._global_config = self._load_global_file(self._global_path)
            self._last_modified[str(self._global_path)] = self._global_path.stat().st_mtime

        for name, path in self._impl_paths.items():
            if path.exists():
                self._impl_configs[name] = self._load_file(path)
                self._last_modified[str(path)] = path.stat().st_mtime

    def _load_global_file(self, path: Path) -> PCRGlobalConfig:
        """Load global config with environment variable overrides."""
        data = self._load_file(path)
        data = self._apply_env_overrides(data)
        return PCRGlobalConfig(data)

    def _load_file(self, path: Path) -> Dict[str, Any]:
        """Load a single YAML or JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            if path.suffix in (".yaml", ".yml"):
                if yaml is None:
                    raise RuntimeError("PyYAML is required for .yaml files but not installed")
                return yaml.safe_load(f) or {}
            elif path.suffix == ".json":
                return json.load(f)
            else:
                # Try YAML first, then JSON
                content = f.read()
                try:
                    if yaml:
                        return yaml.safe_load(content) or {}
                except Exception:
                    pass
                try:
                    return json.loads(content)
                except Exception:
                    pass
                raise ValueError(f"Cannot parse {path}: expected YAML or JSON")

    @staticmethod
    def _apply_env_overrides(data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply PCR_* environment variable overrides to config data."""
        result = dict(data)
        for key, val in os.environ.items():
            if key.startswith("PCR_"):
                # PCR_IMPLEMENTATION=rule_based -> implementation
                # PCR_MAX_RETRY=3 -> max_retry
                config_key = key[4:].lower()
                # Convert snake_case to the expected key name
                # Simple conversion: PCR_MAX_RETRY -> max_retry
                config_key = config_key.lower()
                # Type coercion for known fields
                if config_key in ("max_retry",):
                    try:
                        result[config_key] = int(val)
                    except ValueError:
                        result[config_key] = val
                elif config_key in ("retry_delay_ms", "health_check_interval_sec"):
                    try:
                        result[config_key] = float(val)
                    except ValueError:
                        result[config_key] = val
                elif config_key in ("log_errors", "expose_errors_to_user", "enable_telemetry"):
                    result[config_key] = val.lower() in ("true", "1", "yes", "on")
                else:
                    result[config_key] = val
        return result

    # ── Hot reload detection ────────────────────────────────────────────────

    def check_hot_reload(self) -> List[str]:
        """
        Check if any configuration file has been modified since last load.

        Returns:
            List of changed file paths (absolute strings).
        """
        changed: List[str] = []
        for path_str, last_mtime in self._last_modified.items():
            path = Path(path_str)
            if path.exists() and path.stat().st_mtime > last_mtime:
                changed.append(path_str)
                self._last_modified[path_str] = path.stat().st_mtime

        if changed:
            self._load_all()

        return changed

    # ── Accessors ──────────────────────────────────────────────────────────

    def get_global(self) -> PCRGlobalConfig:
        """Return the global configuration. Creates a default if not loaded."""
        if self._global_config is None:
            return PCRGlobalConfig()
        return self._global_config

    def get_implementation(self, name: str) -> Dict[str, Any]:
        """Return per-implementation configuration."""
        return self._impl_configs.get(name, {})

    def get_all_implementation_names(self) -> List[str]:
        """Return list of known implementation config names."""
        return list(self._impl_configs.keys())

    def has_changed(self, path_str: str) -> bool:
        """Check if a specific file has changed since last load."""
        path = Path(path_str)
        if not path.exists():
            return False
        last = self._last_modified.get(path_str, 0)
        return path.stat().st_mtime > last
