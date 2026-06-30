# -*- coding: utf-8 -*-
"""
core/agent/pcr/lifecycle.py
──────────────────────────
PCR lifecycle manager.

Responsibilities:
  1. Initialization: discover plugins, load config, warm-up primary PCR,
     create fallback engine.
  2. Runtime: periodic health checks, hot-reload detection.
  3. Shutdown: graceful release of all PCR instances.

Thread safety: evaluate() is protected by a lock. Background thread runs
health checks independently.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Type

from core.agent.pcr.datacontract import PCRInput_v1, PCROutput_v1, Modality
from core.agent.pcr.fallback import FallbackConfig, FallbackEngine
from core.agent.pcr.interface import IPCRRouter, PCRHealthStatus
from core.agent.pcr.registry import (
    _PCR_REGISTRY,
    create_pcr,
    discover_pcr_plugins,
    is_registered,
    list_available_pcr,
)

logger = logging.getLogger("pcr.lifecycle")


# ═══════════════════════════════════════════════════════════════════════════════
# Lifecycle Manager
# ═══════════════════════════════════════════════════════════════════════════════

class PCRLifecycleManager:
    """
    Manages the full lifecycle of the PCR subsystem.

    Usage:
        manager = PCRLifecycleManager()
        ok, err = manager.initialize({
            "implementation": "rule_based",
            "fallback_strategy": "conservative",
            "fallback_chain": ["rule_based"],  # self-fallback
            "plugin_dirs": ["core/agent/pcr/plugins"],
        })
        if not ok:
            raise RuntimeError(err)
        
        result = manager.evaluate(PCRInput_v1(query="..."))
        
        manager.shutdown()
    """

    def __init__(self):
        self._primary: Optional[IPCRRouter] = None
        self._fallback_engine: Optional[FallbackEngine] = None
        self._config: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._running = False
        self._health_thread: Optional[threading.Thread] = None
        self._health_check_interval_sec: float = 60.0

    # ── Initialization ───────────────────────────────────────────────────────

    def initialize(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Initialize the PCR subsystem.

        Args:
            config: Configuration dict with keys:
                - implementation: str — primary PCR name
                - fallback_strategy: str — "conservative" | "degraded" | "pass_through"
                - fallback_chain: List[str] — ordered fallback PCR names
                - plugin_dirs: List[str] — directories to auto-discover plugins
                - impl_config: Dict — per-implementation config (passed to warm_up)
                - health_check_interval_sec: float — background health check interval

        Returns:
            (success, error_message). If success is False, error_message explains why.
        """
        try:
            self._config = config

            # 1. Validate primary implementation
            impl_name = config.get("implementation", "rule_based")
            if not isinstance(impl_name, str) or not impl_name:
                return False, "config 'implementation' must be a non-empty string"

            # 2. Discover plugins (if configured)
            plugin_dirs = config.get("plugin_dirs", [])
            if isinstance(plugin_dirs, str):
                plugin_dirs = [plugin_dirs]
            for plugin_dir in plugin_dirs:
                try:
                    discovered = discover_pcr_plugins(plugin_dir)
                    logger.info(f"Discovered PCR plugins from '{plugin_dir}': {discovered}")
                except Exception as e:
                    logger.warning(f"Plugin discovery failed for '{plugin_dir}': {e}")

            # 3. Check if primary is registered
            if not is_registered(impl_name):
                available = list(_PCR_REGISTRY.keys())
                return False, (
                    f"Primary PCR implementation '{impl_name}' is not registered. "
                    f"Available: {available}. "
                    f"Check plugin_dirs or call register_pcr() explicitly."
                )

            # 4. Warm-up primary PCR
            impl_config = config.get("impl_config", {})
            self._primary = create_pcr(impl_name, impl_config)
            logger.info(f"Primary PCR warmed up: '{impl_name}' v{self._primary.version}")

            # 5. Create fallback engine
            fallback_cfg = FallbackConfig(
                strategy=config.get("fallback_strategy", "conservative"),
                fallback_chain=config.get("fallback_chain", []),
                max_retry=config.get("max_retry", 1),
                retry_delay_ms=config.get("retry_delay_ms", 100.0),
                log_errors=config.get("log_errors", True),
                expose_errors_to_user=config.get("expose_errors_to_user", False),
            )
            valid, err = fallback_cfg.validate()
            if not valid:
                return False, f"FallbackConfig invalid: {err}"

            self._fallback_engine = FallbackEngine(
                primary=self._primary,
                registry=_PCR_REGISTRY,
                config=fallback_cfg,
            )
            logger.info(
                f"Fallback engine created: strategy={fallback_cfg.strategy}, "
                f"chain={fallback_cfg.fallback_chain}"
            )

            # 6. Start background health check thread
            self._health_check_interval_sec = config.get(
                "health_check_interval_sec", 60.0
            )
            self._running = True
            self._health_thread = threading.Thread(
                target=self._health_check_loop, daemon=True, name="PCR-HealthCheck"
            )
            self._health_thread.start()
            logger.info(
                f"Health check thread started (interval={self._health_check_interval_sec}s)"
            )

            return True, None

        except Exception as e:
            logger.error(f"PCR lifecycle initialization failed: {e}", exc_info=True)
            return False, f"PCR initialization failed: {e}"

    # ── Core evaluation ────────────────────────────────────────────────────

    def evaluate(self, input_data: PCRInput_v1) -> PCROutput_v1:
        """
        Thread-safe evaluation entry point with modality-aware routing.

        Routes by modality:
            TEXT        → standard pipeline (noise + complexity + cognitive profile)
            STRUCTURED  → fast path (bypass text noise estimation, direct intent classification)
            IMAGE/AUDIO/MULTIMODAL → preprocessing required (currently degraded to TEXT fallback)
        """
        if not self._fallback_engine:
            logger.warning("PCR not initialized — returning default fallback")
            return PCROutput_v1.default_fallback("PCR subsystem not initialized")

        with self._lock:
            modality = input_data.modality
            if modality == Modality.TEXT:
                return self._fallback_engine.evaluate(input_data)
            elif modality == Modality.STRUCTURED:
                return self._evaluate_structured(input_data)
            elif modality in (Modality.IMAGE, Modality.AUDIO, Modality.MULTIMODAL):
                return self._evaluate_with_preprocessing(input_data)
            else:
                logger.warning(f"Unsupported modality: {modality} — falling back to TEXT pipeline")
                return self._fallback_engine.evaluate(input_data)

    def _evaluate_structured(self, input_data: PCRInput_v1) -> PCROutput_v1:
        """
        Structured data fast path: bypass text noise/complexity estimation,
        direct intent classification.

        TODO: Implement structured data fast mapping when structured input schema
        (shortcut commands, JSON payloads) is finalized.
        """
        logger.info("STRUCTURED modality fast path — using TEXT fallback for now")
        result = self._fallback_engine.evaluate(input_data)
        # Augment trace log to mark structured path
        trace = list(result.trace_log) + ["[LIFECYCLE] STRUCTURED fast path (degraded to TEXT fallback)"]
        return result

    def _evaluate_with_preprocessing(self, input_data: PCRInput_v1) -> PCROutput_v1:
        """
        Non-text modalities: call external preprocessor (OCR/ASR) then reconstruct
        as TEXT input.

        TODO: Preprocessor is an optional external service; when available,
        reconstruct PCRInput_v1(modality=TEXT, query=preprocessed_text, raw_payload=None).
        """
        logger.info(f"{input_data.modality.value} modality — preprocessing required, using TEXT fallback")
        result = self._fallback_engine.evaluate(input_data)
        trace = list(result.trace_log) + [
            f"[LIFECYCLE] {input_data.modality.value.upper()} preprocessing fallback"
        ]
        return result

    # ── Telemetry & health ─────────────────────────────────────────────────

    def get_telemetry(self) -> Dict[str, Any]:
        """Aggregate telemetry from primary + fallback engine."""
        if not self._fallback_engine:
            return {"status": "not_initialized", "error": "PCR subsystem not initialized"}
        return self._fallback_engine.get_telemetry()

    def get_health(self) -> PCRHealthStatus:
        """Aggregate health status."""
        if not self._fallback_engine:
            return PCRHealthStatus.UNHEALTHY
        return self._fallback_engine.get_health()

    def get_capabilities(self) -> Dict[str, Any]:
        """Return capabilities of the primary PCR."""
        if not self._primary:
            return {"error": "PCR not initialized"}
        return self._primary.get_capabilities()

    def list_available(self) -> Dict[str, Dict[str, Any]]:
        """List all registered PCR implementations and their capabilities."""
        return list_available_pcr()

    # ── Hot reload ──────────────────────────────────────────────────────────

    def hot_reload_config(self, new_config: Dict[str, Any]) -> bool:
        """
        Attempt hot-reload of the primary PCR configuration.

        If the primary PCR supports hot_reload, updates its config.
        Otherwise, returns False (requires restart).

        Args:
            new_config: New configuration dict (same schema as initialize).

        Returns:
            True if hot-reload succeeded, False if restart is required.
        """
        if not self._primary:
            logger.warning("Cannot hot-reload: PCR not initialized")
            return False

        try:
            impl_config = new_config.get("impl_config", {})
            result = self._primary.reload_config(impl_config)
            if result:
                logger.info(f"Hot-reload succeeded for '{self._primary.name}'")
                self._config.update(new_config)
            else:
                logger.info(f"Hot-reload not supported by '{self._primary.name}' — restart required")
            return result
        except Exception as e:
            logger.error(f"Hot-reload failed for '{self._primary.name}': {e}")
            return False

    # ── Shutdown ──────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Graceful shutdown. Idempotent."""
        if not self._running:
            return

        logger.info("PCR lifecycle shutdown initiated...")
        self._running = False

        # Stop background thread
        if self._health_thread and self._health_thread.is_alive():
            # Daemon thread will exit automatically when main exits,
            # but we can join with a timeout for cleanliness
            self._health_thread.join(timeout=2.0)
            if self._health_thread.is_alive():
                logger.warning("Health check thread did not exit within 2s")

        # Shutdown primary
        if self._primary:
            try:
                self._primary.shutdown()
                logger.info(f"Primary PCR '{self._primary.name}' shut down")
            except Exception as e:
                logger.error(f"Error shutting down primary PCR: {e}")
            self._primary = None

        # Shutdown fallback instances
        if self._fallback_engine:
            for name, inst in getattr(self._fallback_engine, "_fallback_instances", {}).items():
                try:
                    inst.shutdown()
                    logger.info(f"Fallback PCR '{name}' shut down")
                except Exception as e:
                    logger.error(f"Error shutting down fallback PCR '{name}': {e}")
            self._fallback_engine = None

        logger.info("PCR lifecycle shutdown complete")

    # ── Background health check ────────────────────────────────────────────

    def _health_check_loop(self) -> None:
        """Background thread: periodic health checks and hot-reload detection."""
        while self._running:
            try:
                time.sleep(self._health_check_interval_sec)

                if not self._running:
                    break

                if not self._primary:
                    continue

                health = self._primary.get_health()
                if health == PCRHealthStatus.UNHEALTHY:
                    logger.error(
                        f"Primary PCR '{self._primary.name}' is UNHEALTHY. "
                        f"Fallback engine will be used for subsequent calls."
                    )
                elif health == PCRHealthStatus.DEGRADED:
                    logger.warning(
                        f"Primary PCR '{self._primary.name}' is DEGRADED."
                    )

                # Telemetry logging (debug level)
                telemetry = self.get_telemetry()
                logger.debug(f"PCR telemetry: {telemetry}")

            except Exception as e:
                logger.error(f"Health check loop error: {e}", exc_info=True)
