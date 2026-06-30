# -*- coding: utf-8 -*-
"""
core/agent/pcr/interface.py
──────────────────────────
Pre-Cognitive Router (PCR) abstract base class interface.

All PCR implementations must inherit from IPCRRouter and implement every
abstract method. The interface is designed for:
  - Zero state mutation (evaluate is pure computation)
  - Full lifecycle management (warm-up, shutdown, hot-reload)
  - Observable telemetry (health, latency, error rates)
  - Configurable schemas (JSON Schema for UI validation)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Tuple

from core.agent.pcr.datacontract import PCRInput_v1, PCROutput_v1


# ═══════════════════════════════════════════════════════════════════════════════
# Health Status
# ═══════════════════════════════════════════════════════════════════════════════

class PCRHealthStatus(Enum):
    """Health status of a PCR implementation instance."""
    HEALTHY = "healthy"          # Fully operational
    DEGRADED = "degraded"        # Partially degraded (e.g. LLM timeout, fell back to rules)
    UNHEALTHY = "unhealthy"      # Completely unavailable (requires restart or swap)
    WARMING = "warming"          # Still warming up (cold start, model loading)

    @property
    def is_healthy(self) -> bool:
        """Return True if status is operational (HEALTHY or DEGRADED)."""
        return self in (PCRHealthStatus.HEALTHY, PCRHealthStatus.DEGRADED)


# ═══════════════════════════════════════════════════════════════════════════════
# Abstract Base Class
# ═══════════════════════════════════════════════════════════════════════════════

class IPCRRouter(ABC):
    """
    Pre-Cognitive Router interface.

    Contract rules:
    1. Pure computation: evaluate() must not mutate input_data or any global state.
    2. Exception safety: Callers (FallbackEngine) wrap evaluate() in try-except,
       but implementations should also catch internal exceptions and map to fallback output.
    3. Latency budget: Document expected latency in get_capabilities().
    4. Thread safety: If shared state is used, implementations must manage their own locks.
    5. Idempotency: shutdown() must be safe to call multiple times.
    """

    # ── Identity ──────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Implementation identifier, e.g. 'rule_based_v1', 'llm_enhanced_v2'."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Implementation version, e.g. '1.0.0'. Used for compatibility checks."""
        pass

    # ── Lifecycle ─────────────────────────────────────────────────────────

    @abstractmethod
    def warm_up(self, config: Dict[str, Any]) -> None:
        """
        Warm-up phase. Called once during system initialization.

        Rules:
        - Load configuration, compile regexes, warm caches, pre-load models.
        - Must NOT call external services (e.g. LLM APIs) — only local initialization.
        - Any exception raised here will be caught by LifecycleManager and mark the
          implementation as DEGRADED or UNHEALTHY.
        """
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """
        Graceful shutdown. Release resources, threads, file handles, caches.

        Rules:
        - Must be idempotent: calling multiple times has no side effects.
        - Must not raise exceptions; log errors internally but swallow them.
        """
        pass

    def reload_config(self, config: Dict[str, Any]) -> bool:
        """
        Hot-reload configuration at runtime. Optional — default implementation
        returns False (requires restart).

        Implementations that support hot-reload should override this method,
        validate the new config, apply changes atomically, and return True.

        Args:
            config: New configuration dict (same schema as warm_up).

        Returns:
            True if hot-reload succeeded, False if restart is required.
        """
        return False

    # ── Core evaluation ────────────────────────────────────────────────────

    @abstractmethod
    def evaluate(self, input_data: PCRInput_v1) -> PCROutput_v1:
        """
        Evaluate user input and return a cognitive-state packet.

        Requirements:
        - Latency: declare expected range in get_capabilities().
          Typical: rule-based < 10ms, LLM-enhanced < 500ms.
        - Exception safety: internal try-except is encouraged; callers also wrap
          this in FallbackEngine for defense in depth.
        - Statelessness: do not modify input_data (frozen dataclass), do not
          modify global or instance state that would affect subsequent calls.
        - Thread safety: if using shared caches, lock them internally.

        Args:
            input_data: The versioned input contract (PCRInput_v1).

        Returns:
            PCROutput_v1: The versioned output contract with full derived strategies.
        """
        pass

    # ── Observability ──────────────────────────────────────────────────────

    @abstractmethod
    def get_health(self) -> PCRHealthStatus:
        """Return current health status of this implementation."""
        pass

    @abstractmethod
    def get_telemetry(self) -> Dict[str, Any]:
        """
        Return runtime telemetry data. Minimum required fields:

        Returns:
            Dict with at least these keys:
                - call_count: int — total evaluate() calls
                - error_count: int — exceptions raised
                - avg_latency_ms: float — average latency
                - p99_latency_ms: float — 99th percentile latency
                - cache_hit_rate: float — 0.0–1.0 (if caching is used)
                - last_error: Optional[str] — last error message (sanitized)
                - health_history: List[str] — recent health transitions (optional)
        """
        pass

    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Return capability description. Used by registry UIs and compatibility checks.

        Returns:
            Dict with at least these keys:
                - supported_expectations: List[str] — e.g. ["TOOL", "ADVISOR", "COMPANION", "UNKNOWN"]
                - has_cognitive_profile: bool
                - has_noise_estimation: bool
                - has_complexity_estimation: bool
                - requires_llm: bool
                - latency_range_ms: List[int] — e.g. [0, 10] for rule-based
                - supports_hot_reload: bool
                - config_schema: Dict — JSON Schema of accepted configuration
        """
        pass

    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """
        Return JSON Schema describing the configuration accepted by warm_up().
        Used by frontend configuration UI and ConfigManager for validation.

        Returns:
            JSON Schema dict (draft-07 compatible).
        """
        pass

    # ── Convenience: default capabilities template ─────────────────────────

    def _default_capabilities(self) -> Dict[str, Any]:
        """Convenience template for implementations that only need to override a few fields."""
        return {
            "supported_expectations": ["TOOL", "ADVISOR", "COMPANION", "UNKNOWN"],
            "has_cognitive_profile": True,
            "has_noise_estimation": True,
            "has_complexity_estimation": True,
            "requires_llm": False,
            "latency_range_ms": [0, 10],
            "supports_hot_reload": False,
            "config_schema": self.get_schema(),
        }
