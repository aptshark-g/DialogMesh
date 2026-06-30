# -*- coding: utf-8 -*-
"""
core/agent/pcr/fallback.py
─────────────────────────
PCR fallback strategy engine.

Wraps an IPCRRouter instance with multi-level fallback, retry, and telemetry
aggregation. Guarantees that evaluate() always returns a valid PCROutput_v1,
even if the primary PCR fails completely.

Fallback strategies:
  - conservative: Always return a safe default output on failure.
  - degraded: Try fallback_chain implementations; if all fail, return default.
  - pass_through: Re-raise the last exception (for callers that want to handle it).

Retry: For transient errors (e.g. LLM timeout), retry N times with backoff.
"""

from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type

from core.agent.pcr.datacontract import PCRInput_v1, PCROutput_v1
from core.agent.pcr.interface import IPCRRouter, PCRHealthStatus

logger = logging.getLogger("pcr.fallback")


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=False)
class FallbackConfig:
    """Configuration for the fallback engine."""
    strategy: str = "conservative"          # "conservative" | "degraded" | "pass_through"
    fallback_chain: List[str] = field(default_factory=list)  # Ordered list of fallback PCR names
    max_retry: int = 1                     # Retries for transient errors (0 = disabled)
    retry_delay_ms: float = 100.0          # Delay between retries
    log_errors: bool = True
    expose_errors_to_user: bool = False    # If True, error details are included in trace_log

    def validate(self) -> tuple[bool, Optional[str]]:
        if self.strategy not in ("conservative", "degraded", "pass_through"):
            return False, f"strategy must be conservative/degraded/pass_through, got {self.strategy}"
        if self.max_retry < 0:
            return False, "max_retry must be >= 0"
        if self.retry_delay_ms < 0:
            return False, "retry_delay_ms must be >= 0"
        return True, None


# ═══════════════════════════════════════════════════════════════════════════════
# Fallback Engine
# ═══════════════════════════════════════════════════════════════════════════════

class FallbackEngine:
    """
    Wraps a primary IPCRRouter with fallback, retry, and telemetry.

    Thread safety: This class is NOT thread-safe by default. If used from
    multiple threads, wrap calls in a lock at the caller level (e.g. in
    LifecycleManager).
    """

    def __init__(
        self,
        primary: IPCRRouter,
        registry: Dict[str, Type[IPCRRouter]],
        config: FallbackConfig,
    ):
        self._primary = primary
        self._registry = registry
        self._config = config

        self._fallback_instances: Dict[str, IPCRRouter] = {}
        self._call_count = 0
        self._error_count = 0
        self._retry_count = 0
        self._last_error: Optional[str] = None
        self._last_fallback_name: Optional[str] = None

    # ── Core evaluation ───────────────────────────────────────────────────

    def evaluate(self, input_data: PCRInput_v1) -> PCROutput_v1:
        """Evaluate with primary, fallback, retry, and safe default."""
        self._call_count += 1
        start = time.time()

        # 1. Try primary
        try:
            result = self._primary.evaluate(input_data)
            result = self._annotate_result(result, start, self._primary.name)
            if result.is_fallback and self._config.log_errors:
                logger.warning(
                    f"Primary PCR '{self._primary.name}' returned fallback: {result.fallback_reason}"
                )
            return result
        except Exception as e:
            self._error_count += 1
            self._last_error = f"{type(e).__name__}: {str(e)}"
            if self._config.log_errors:
                logger.error(
                    f"Primary PCR '{self._primary.name}' failed: {e}\n{traceback.format_exc()}"
                )

        # 2. Retry (for transient errors like LLM timeout)
        if self._config.max_retry > 0:
            for attempt in range(1, self._config.max_retry + 1):
                try:
                    if self._config.retry_delay_ms > 0:
                        time.sleep(self._config.retry_delay_ms / 1000.0)
                    result = self._primary.evaluate(input_data)
                    self._retry_count += 1
                    result = self._annotate_result(result, start, self._primary.name)
                    result.trace_log.append(f"[RETRY] Succeeded on attempt {attempt}")
                    return result
                except Exception as e:
                    if self._config.log_errors:
                        logger.warning(
                            f"Primary PCR '{self._primary.name}' retry {attempt}/{self._config.max_retry} failed: {e}"
                        )

        # 3. Degraded: try fallback chain
        if self._config.strategy == "degraded":
            for fallback_name in self._config.fallback_chain:
                try:
                    fallback = self._get_fallback_instance(fallback_name)
                    result = fallback.evaluate(input_data)
                    self._last_fallback_name = fallback_name
                    result = self._annotate_result(
                        result, start, fallback_name,
                        is_fallback=True,
                        fallback_reason=(
                            f"Primary '{self._primary.name}' failed after {self._config.max_retry} retries; "
                            f"activated fallback '{fallback_name}'"
                        )
                    )
                    if self._config.log_errors:
                        logger.warning(f"Activated fallback PCR: '{fallback_name}'")
                    return result
                except Exception as e:
                    if self._config.log_errors:
                        logger.error(f"Fallback PCR '{fallback_name}' also failed: {e}")

        # 4. Conservative default (or degraded exhausted)
        if self._config.strategy in ("conservative", "degraded"):
            reason = (
                f"Primary PCR '{self._primary.name}' failed after {self._config.max_retry} retries. "
                f"Last error: {self._last_error}"
            )
            if self._last_fallback_name:
                reason += f"; fallback chain exhausted at '{self._last_fallback_name}'"

            fallback_output = PCROutput_v1.default_fallback(reason=reason)
            fallback_output = self._annotate_result(fallback_output, start, "default_fallback")
            if self._config.expose_errors_to_user:
                fallback_output.trace_log.append(f"[ERROR] {self._last_error}")
            return fallback_output

        # 5. pass_through: re-raise
        raise RuntimeError(
            f"Primary PCR '{self._primary.name}' failed and no fallback is configured: {self._last_error}"
        )

    # ── Telemetry ─────────────────────────────────────────────────────────

    def get_telemetry(self) -> Dict[str, Any]:
        """Aggregate telemetry from primary + fallback engine."""
        primary_telemetry = self._primary.get_telemetry()
        fallback_telemetry: Dict[str, Any] = {}
        for name, inst in self._fallback_instances.items():
            try:
                fallback_telemetry[name] = inst.get_telemetry()
            except Exception as e:
                fallback_telemetry[name] = {"error": str(e)}

        return {
            **primary_telemetry,
            "fallback_engine": {
                "call_count": self._call_count,
                "error_count": self._error_count,
                "retry_count": self._retry_count,
                "error_rate": self._error_count / max(1, self._call_count),
                "last_error": self._last_error,
                "last_fallback_activated": self._last_fallback_name,
                "fallback_instances": fallback_telemetry,
            },
        }

    def get_health(self) -> PCRHealthStatus:
        """Aggregate health: primary + fallback chain."""
        primary_health = self._primary.get_health()
        if primary_health == PCRHealthStatus.HEALTHY:
            return PCRHealthStatus.HEALTHY

        # Primary degraded/unhealthy — check if fallback chain is healthy
        if self._config.strategy == "degraded" and self._config.fallback_chain:
            for name in self._config.fallback_chain:
                try:
                    inst = self._get_fallback_instance(name)
                    if inst.get_health() == PCRHealthStatus.HEALTHY:
                        return PCRHealthStatus.DEGRADED
                except Exception:
                    pass

        return PCRHealthStatus.UNHEALTHY

    # ── Internal helpers ────────────────────────────────────────────────────

    def _get_fallback_instance(self, name: str) -> IPCRRouter:
        """Get or create a fallback instance."""
        if name not in self._fallback_instances:
            cls = self._registry.get(name)
            if not cls:
                raise ValueError(f"Fallback PCR '{name}' not found in registry")
            inst = cls()
            try:
                inst.warm_up({})
            except Exception as e:
                logger.warning(f"Fallback PCR '{name}' warm_up failed with empty config: {e}")
            self._fallback_instances[name] = inst
        return self._fallback_instances[name]

    @staticmethod
    def _annotate_result(
        result: PCROutput_v1, start_time: float, implementation: str,
        is_fallback: bool = False, fallback_reason: Optional[str] = None
    ) -> PCROutput_v1:
        """Annotate result with latency and implementation name."""
        # dataclass is frozen — create a new instance with updated fields
        # This is a bit verbose but maintains immutability contract
        return PCROutput_v1(
            version=result.version,
            expectation=result.expectation,
            noise_level=result.noise_level,
            complexity_level=result.complexity_level,
            cognitive_profile=result.cognitive_profile,
            execution_mode=result.execution_mode,
            parser_config_overrides=result.parser_config_overrides,
            prompt_style=result.prompt_style,
            ambiguity_strategy=result.ambiguity_strategy,
            suggested_next_actions=result.suggested_next_actions,
            should_attach_process=result.should_attach_process,
            should_refresh_analysis=result.should_refresh_analysis,
            trace_log=result.trace_log,
            latency_ms=(time.time() - start_time) * 1000.0,
            implementation=implementation,
            cache_hit=result.cache_hit,
            is_fallback=is_fallback,
            fallback_reason=fallback_reason,
        )
