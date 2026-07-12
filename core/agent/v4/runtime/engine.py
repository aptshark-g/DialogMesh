"""CognitiveRuntimeEngine: orchestrates v4 modules across four paths."""
from __future__ import annotations
import importlib, time, logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent.v4.event_ir import EventIR
from core.agent.v4.runtime.adapter import (
    RuntimeAdapter, RuntimeContext, AdapterResult,
)
from core.agent.v4.runtime.config import (
    RuntimeConfig, ModuleConfig, PathConfig, load_runtime_config, build_default_config,
)
from core.agent.v4.world.params import WorldParams, get_world_params

logger = logging.getLogger(__name__)


@dataclass
class PathStats:
    """Runtime statistics for a single path."""
    path_name: str
    trigger_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0
    last_triggered_at: float = 0.0


class CognitiveRuntimeEngine:
    """Orchestrates v4 cognitive modules across Fast/Async/Slow/Deep paths.

    Usage:
        engine = CognitiveRuntimeEngine()
        engine.start()

        # On each user event:
        engine.on_event(event_ir)

        # Or manually trigger checkpoint:
        engine.trigger_checkpoint()
    """

    def __init__(self, config_path: str = None, world_params: WorldParams = None):
        """Initialize the runtime engine.

        Args:
            config_path: Path to runtime.yaml. If None, uses default config.
            world_params: WorldParams for parameter injection. If None, uses defaults.
        """
        if config_path:
            self._config = load_runtime_config(config_path)
        else:
            self._config = build_default_config()

        self._world_params = world_params or get_world_params()
        self._adapters: Dict[str, RuntimeAdapter] = {}
        self._stats: Dict[str, PathStats] = {}
        self._event_buffer: List[EventIR] = []
        self._running = False

        # Initialize path stats
        for path_name in self._config.paths:
            self._stats[path_name] = PathStats(path_name=path_name)

    # ---- Lifecycle ----

    def start(self) -> None:
        """Start the runtime engine. Instantiates all adapters."""
        self._running = True
        self._instantiate_adapters()
        logger.info("CognitiveRuntimeEngine started with %d adapters", len(self._adapters))

    def stop(self) -> None:
        """Stop the runtime engine."""
        self._running = False
        self._adapters.clear()
        self._event_buffer.clear()
        logger.info("CognitiveRuntimeEngine stopped")

    # ---- Event-driven triggers ----

    def on_event(self, event: EventIR) -> None:
        """Process a single user event through the Async Path."""
        if not self._running:
            return

        self._event_buffer.append(event)
        self._stats["async"].trigger_count += 1
        self._stats["async"].last_triggered_at = time.time()

        path_config = self._config.get_path("async")
        if not path_config:
            return

        ctx = RuntimeContext(event=event)
        for module_config in path_config.modules:
            adapter = self._adapters.get(module_config.name)
            if adapter is None:
                continue

            start = time.time()
            result = adapter.timed_execute(ctx)
            elapsed = (time.time() - start) * 1000

            pas = self._stats["async"]
            pas.total_latency_ms += elapsed
            if result.ok:
                pas.success_count += 1
                # Feed observation into context for downstream modules
                if result.data is not None:
                    ctx.observations.append(result.data)
            else:
                pas.failure_count += 1
                logger.warning("Async adapter %s failed: %s", module_config.name, result.error)

        # Check if checkpoint should fire
        slow_path = self._config.get_path("slow")
        if slow_path and slow_path.modules:
            for mc in slow_path.modules:
                if mc.trigger == "checkpoint":
                    tc = mc.trigger_config
                    if len(self._event_buffer) >= tc.get("event_count", 50):
                        self.trigger_checkpoint()
                        break

    def trigger_checkpoint(self) -> List[AdapterResult]:
        """Manually trigger the Slow Path (checkpoint)."""
        return self._run_path("slow")

    def trigger_deep(self) -> List[AdapterResult]:
        """Manually trigger the Deep Path."""
        return self._run_path("deep")

    # ---- Internal ----

    def _run_path(self, path_name: str) -> List[AdapterResult]:
        """Run all modules in a given path."""
        if not self._running:
            return []

        path_config = self._config.get_path(path_name)
        if not path_config:
            return []

        self._stats[path_name].trigger_count += 1
        self._stats[path_name].last_triggered_at = time.time()

        ctx = RuntimeContext(observations=list(self._event_buffer))
        results = []

        for module_config in path_config.modules:
            adapter = self._adapters.get(module_config.name)
            if adapter is None:
                continue

            start = time.time()
            result = adapter.timed_execute(ctx)
            elapsed = (time.time() - start) * 1000

            stats = self._stats[path_name]
            stats.total_latency_ms += elapsed
            if result.ok:
                stats.success_count += 1
            else:
                stats.failure_count += 1

            results.append(result)

        # Clear buffer after checkpoint
        if path_name == "slow":
            self._event_buffer.clear()

        return results

    def _instantiate_adapters(self) -> None:
        """Instantiate all adapters from config."""
        for path_config in self._config.paths.values():
            for module_config in path_config.modules:
                adapter_cls = self._import_class(module_config.adapter)
                if adapter_cls is None:
                    logger.error("Cannot import adapter: %s", module_config.adapter)
                    continue

                # Merge params: WorldParams default -> config override
                merged_params = dict(self._world_params.__dict__)
                merged_params.update(module_config.params)

                try:
                    adapter = adapter_cls(
                        name=module_config.name,
                        timeout_ms=module_config.timeout_ms,
                        retry=module_config.retry,
                        params=merged_params,
                    )
                    self._adapters[module_config.name] = adapter
                    logger.info("Instantiated adapter: %s -> %s", module_config.name, adapter_cls.__name__)
                except Exception as e:
                    logger.error("Failed to instantiate adapter %s: %s", module_config.name, e)

    @staticmethod
    def _import_class(full_path: str):
        """Import a class from a dotted path string."""
        try:
            parts = full_path.rsplit(".", 1)
            module = importlib.import_module(parts[0])
            return getattr(module, parts[1])
        except Exception:
            return None

    # ---- Accessors ----

    @property
    def stats(self) -> Dict[str, PathStats]:
        return dict(self._stats)

    @property
    def config(self) -> RuntimeConfig:
        return self._config

    @property
    def adapter_count(self) -> int:
        return len(self._adapters)
