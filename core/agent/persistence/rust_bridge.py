"""Persistence compatibility layer — Rust (fast) with Python fallback.

Usage:
    from core.agent.persistence.rust_bridge import get_broker
    broker = get_broker("data/dialogmesh")
    # → PyUnifiedBroker (Rust) if compiled, else UnifiedPersistenceBroker (Python)
"""

from __future__ import annotations
from typing import Any
import logging, os

logger = logging.getLogger(__name__)

_RUST_AVAILABLE = None


def _check_rust() -> bool:
    """Check if Rust persistence library is compiled and importable."""
    global _RUST_AVAILABLE
    if _RUST_AVAILABLE is not None:
        return _RUST_AVAILABLE

    # Check for compiled .pyd/.so
    try:
        import importlib.util
        spec = importlib.util.find_spec("dialogmesh_persistence")
        if spec:
            _RUST_AVAILABLE = True
            logger.info("Rust persistence layer ACTIVE")
            return True
    except Exception:
        pass

    # Check for local build
    pyd_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", 
        "persistence_rs", "target", "release"
    )
    for f in os.listdir(pyd_path) if os.path.exists(pyd_path) else []:
        if f.startswith("dialogmesh_persistence") and (f.endswith(".pyd") or f.endswith(".so")):
            _RUST_AVAILABLE = True
            logger.info("Rust persistence layer ACTIVE (local build)")
            return True

    _RUST_AVAILABLE = False
    logger.info("Rust not compiled — using Python fallback")
    return False


def get_broker(data_dir: str = "data/dialogmesh") -> Any:
    """Get persistence broker — Rust if available, Python otherwise."""
    if _check_rust():
        try:
            import dialogmesh_persistence
            return dialogmesh_persistence.PyUnifiedBroker(data_dir)
        except Exception as e:
            logger.warning("Rust broker failed: %s — falling back to Python", e)

    from core.agent.persistence.broker import UnifiedPersistenceBroker
    return UnifiedPersistenceBroker(data_dir=data_dir)
