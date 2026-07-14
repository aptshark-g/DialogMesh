"""Cognitive Runtime: orchestrates v4 modules across Fast/Async/Slow/Deep paths."""
from core.agent.v4.runtime.config import RuntimeConfig, ModuleConfig, PathConfig, load_runtime_config, build_default_config
from core.agent.v4.runtime.adapter import RuntimeAdapter, RuntimeContext, AdapterResult

__all__ = [
    "RuntimeConfig", "ModuleConfig", "PathConfig", "load_runtime_config", "build_default_config",
    "RuntimeAdapter", "RuntimeContext", "AdapterResult",
    "CognitiveRuntimeEngine", "PathStats",
]

# Lazy import to avoid circular dependency with cognitive_scheduler
_CognitiveRuntimeEngine = None
_PathStats = None

def _load_engine():
    global _CognitiveRuntimeEngine, _PathStats
    if _CognitiveRuntimeEngine is None:
        from core.agent.v4.runtime.engine import CognitiveRuntimeEngine as _CognitiveRuntimeEngine
        from core.agent.v4.runtime.engine import PathStats as _PathStats
    return _CognitiveRuntimeEngine, _PathStats

# Backward-compatible direct access (will trigger lazy load on first use)
class _LazyEngine:
    def __call__(self, *args, **kwargs):
        cls, _ = _load_engine()
        return cls(*args, **kwargs)
    def __getattr__(self, name):
        cls, _ = _load_engine()
        return getattr(cls, name)

CognitiveRuntimeEngine = _LazyEngine()  # type: ignore

class _LazyPathStats:
    def __call__(self, *args, **kwargs):
        _, ps = _load_engine()
        return ps(*args, **kwargs)
    def __getattr__(self, name):
        _, ps = _load_engine()
        return getattr(ps, name)

PathStats = _LazyPathStats()  # type: ignore
