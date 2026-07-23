"""Runtime configuration loader: reads runtime.yaml and provides typed access."""
from __future__ import annotations
import pathlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class ModuleConfig:
    """Configuration for a single module in the runtime."""
    name: str
    adapter: str
    timeout_ms: int = 5000
    retry: int = 1
    params: dict = field(default_factory=dict)
    trigger: str = ""           # "event" | "checkpoint" | "threshold"
    trigger_config: dict = field(default_factory=dict)


@dataclass
class PathConfig:
    """Configuration for a single path (async/slow/deep)."""
    path_name: str
    modules: List[ModuleConfig] = field(default_factory=list)


@dataclass
class RuntimeConfig:
    """Full runtime configuration."""
    version: str = "1.0"
    paths: Dict[str, PathConfig] = field(default_factory=dict)

    def get_path(self, path_name: str) -> Optional[PathConfig]:
        return self.paths.get(path_name)

    def all_modules(self) -> List[ModuleConfig]:
        result = []
        for pc in self.paths.values():
            result.extend(pc.modules)
        return result


def load_runtime_config(config_path: str = None) -> RuntimeConfig:
    """Load runtime configuration from YAML file.

    Args:
        config_path: Path to runtime.yaml. Defaults to config/runtime.yaml.

    Returns:
        RuntimeConfig with parsed paths and modules.
    """
    if config_path is None:
        # Try project-relative path
        candidates = [
            pathlib.Path("config/runtime.yaml"),
            pathlib.Path(__file__).parent.parent.parent.parent.parent / "config" / "runtime.yaml",
        ]
        for c in candidates:
            if c.exists():
                config_path = str(c)
                break
        else:
            raise FileNotFoundError("Cannot find config/runtime.yaml")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    config = RuntimeConfig(version=raw.get("version", "1.0"))

    for path_name, modules_raw in raw.get("paths", {}).items():
        modules = []
        for m in modules_raw:
            modules.append(ModuleConfig(
                name=m.get("name", ""),
                adapter=m.get("adapter", ""),
                timeout_ms=m.get("timeout_ms", 5000),
                retry=m.get("retry", 1),
                params=m.get("params", {}),
                trigger=m.get("trigger", ""),
                trigger_config=m.get("trigger_config", {}),
            ))
        config.paths[path_name] = PathConfig(path_name=path_name, modules=modules)

    return config


def build_default_config() -> RuntimeConfig:
    """Build a minimal default runtime config (no YAML file needed)."""
    config = RuntimeConfig(version="1.0")
    config.paths["async"] = PathConfig(
        path_name="async",
        modules=[
            ModuleConfig(
                name="observation_compiler",
                adapter="core.agent.v4.runtime.adapter.ObservationCompilerAdapter",
                timeout_ms=2000,
                retry=3,
                trigger="event",
            ),
        ],
    )
    config.paths["slow"] = PathConfig(
        path_name="slow",
        modules=[
            ModuleConfig(
                name="hypothesis_engine",
                adapter="core.agent.v4.runtime.adapter.HypothesisEngineAdapter",
                timeout_ms=30000,
                retry=1,
                trigger="checkpoint",
                trigger_config={"event_count": 50, "time_minutes": 30},
                params={"min_support": 8, "max_conflict": 3},
            ),
        ],
    )
    return config
