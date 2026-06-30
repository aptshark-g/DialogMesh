# -*- coding: utf-8 -*-
"""
core/agent/pcr/tests/mock_pcr.py
────────────────────────────────
Mock PCR implementation for testing.

Provides configurable IPCRRouter implementations that can be used for:
  - Unit testing (deterministic, pre-defined outputs)
  - Integration testing (controlled latency / error injection)
  - Benchmarking (stress testing with configurable throughput)
  - Adversarial testing (simulating edge cases without side effects)

All implementations are zero-dependency (stdlib only).
"""

from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field

from core.agent.pcr.interface import IPCRRouter, PCRHealthStatus
from core.agent.pcr.datacontract import PCRInput_v1, PCROutput_v1, CognitiveProfile_v1


@dataclass
class MockConfig:
    """Configuration for a Mock PCR instance."""
    # Output control
    fixed_expectation: Optional[str] = None
    fixed_noise: Optional[float] = None
    fixed_complexity: Optional[float] = None
    fixed_execution_mode: Optional[str] = None

    # Latency simulation (seconds)
    min_latency: float = 0.0
    max_latency: float = 0.0
    latency_jitter: float = 0.0

    # Error injection
    error_rate: float = 0.0           # Probability of raising exception
    error_type: type = RuntimeError
    error_message: str = "Mock injected error"
    error_after_n_calls: int = 0      # Start erroring after N successful calls

    # Health simulation
    healthy: bool = True
    health_message: str = "Mock healthy"

    # Telemetry tracking
    track_calls: bool = True


class StaticMockPCR(IPCRRouter):
    """
    Mock PCR that returns pre-defined static outputs.

    Useful for unit tests where the caller needs exact, predictable results.
    """

    def __init__(self, config: Optional[MockConfig] = None):
        self._cfg = config or MockConfig()
        self._calls: List[Dict[str, Any]] = []
        self._call_count = 0

    @property
    def name(self) -> str:
        return "static_mock"

    @property
    def version(self) -> str:
        return "1.0.0"

    def warm_up(self, config: Dict[str, Any]) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def evaluate(self, input_data: PCRInput_v1) -> PCROutput_v1:
        self._call_count += 1
        start = time.perf_counter()

        # Latency simulation
        if self._cfg.max_latency > 0:
            latency = random.uniform(self._cfg.min_latency, self._cfg.max_latency)
            if self._cfg.latency_jitter > 0:
                latency += random.gauss(0, self._cfg.latency_jitter)
                latency = max(0, latency)
            time.sleep(latency)

        # Error injection
        if self._cfg.error_rate > 0 and self._call_count > self._cfg.error_after_n_calls:
            if random.random() < self._cfg.error_rate:
                raise self._cfg.error_type(self._cfg.error_message)

        result = PCROutput_v1(
            expectation=self._cfg.fixed_expectation or "MOCK_STATIC",
            noise_level=self._cfg.fixed_noise if self._cfg.fixed_noise is not None else 0.0,
            complexity_level=self._cfg.fixed_complexity if self._cfg.fixed_complexity is not None else 0.0,
            cognitive_profile=CognitiveProfile_v1(),
            execution_mode=self._cfg.fixed_execution_mode or "BALANCED",
            prompt_style="MOCK",
            ambiguity_strategy="MOCK",
            parser_config_overrides={},
        )

        elapsed = time.perf_counter() - start
        if self._cfg.track_calls:
            self._calls.append({
                "input": input_data.to_dict(),
                "output": result.to_dict(),
                "latency_ms": round(elapsed * 1000, 3),
                "call_number": self._call_count,
            })
        return result

    def get_health(self) -> PCRHealthStatus:
        if self._cfg.healthy:
            return PCRHealthStatus.HEALTHY
        return PCRHealthStatus.UNHEALTHY

    def get_telemetry(self) -> Dict[str, Any]:
        return {
            "call_count": self._call_count,
            "avg_latency_ms": sum(c["latency_ms"] for c in self._calls) / max(1, len(self._calls)),
            "calls": self._calls,
        }

    def get_capabilities(self) -> Dict[str, Any]:
        return {"supports_mock": True, "supports_error_injection": True}

    def get_schema(self) -> Dict[str, Any]:
        return {"version": "v1_mock", "type": "static"}

    def reload_config(self, config: Dict[str, Any]) -> bool:
        if "fixed_expectation" in config:
            self._cfg.fixed_expectation = config["fixed_expectation"]
        if "fixed_noise" in config:
            self._cfg.fixed_noise = config["fixed_noise"]
        if "error_rate" in config:
            self._cfg.error_rate = config["error_rate"]
        return True


class SequenceMockPCR(IPCRRouter):
    """
    Mock PCR that returns a pre-defined sequence of outputs, cycling through them.

    Useful for testing fallback behavior, where different calls must return
    different results (e.g., first call fails, second succeeds).
    """

    def __init__(self, outputs: Optional[List[PCROutput_v1]] = None, exceptions: Optional[List[Exception]] = None):
        self._outputs = outputs or []
        self._exceptions = exceptions or []
        self._index = 0
        self._call_count = 0
        self._calls: List[Dict[str, Any]] = []
        self._healthy = True

    @property
    def name(self) -> str:
        return "sequence_mock"

    @property
    def version(self) -> str:
        return "1.0.0"

    def warm_up(self, config: Dict[str, Any]) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def evaluate(self, input_data: PCRInput_v1) -> PCROutput_v1:
        self._call_count += 1
        total = len(self._outputs) + len(self._exceptions)
        if total == 0:
            return PCROutput_v1.default_fallback("empty_sequence")

        idx = (self._index) % total
        self._index += 1

        # Interleave: outputs at even indices, exceptions at odd indices
        if idx % 2 == 0 and idx // 2 < len(self._outputs):
            result = self._outputs[idx // 2]
        elif idx % 2 == 1 and idx // 2 < len(self._exceptions):
            raise self._exceptions[idx // 2]
        else:
            result = self._outputs[idx % len(self._outputs)] if self._outputs else PCROutput_v1.default_fallback("overflow")

        self._calls.append({
            "input": input_data.to_dict(),
            "output": result.to_dict() if not isinstance(result, Exception) else str(result),
            "call_number": self._call_count,
        })
        return result

    def get_health(self) -> PCRHealthStatus:
        if self._healthy:
            return PCRHealthStatus.HEALTHY
        return PCRHealthStatus.UNHEALTHY

    def get_telemetry(self) -> Dict[str, Any]:
        return {"call_count": self._call_count, "sequence_index": self._index}

    def get_capabilities(self) -> Dict[str, Any]:
        return {"supports_sequence": True}

    def get_schema(self) -> Dict[str, Any]:
        return {"version": "v1_mock", "type": "sequence"}


class RecordedMockPCR(IPCRRouter):
    """
    Mock PCR that records all inputs and delegates to a real implementation.

    Useful for "replay" testing: record once, then replay without side effects.
    """

    def __init__(self, delegate: Optional[IPCRRouter] = None):
        self._delegate = delegate
        self._records: List[Dict[str, Any]] = []
        self._call_count = 0

    @property
    def name(self) -> str:
        return "recorded_mock"

    @property
    def version(self) -> str:
        return "1.0.0"

    def warm_up(self, config: Dict[str, Any]) -> None:
        if self._delegate:
            self._delegate.warm_up(config)

    def shutdown(self) -> None:
        if self._delegate:
            self._delegate.shutdown()

    def evaluate(self, input_data: PCRInput_v1) -> PCROutput_v1:
        self._call_count += 1
        start = time.perf_counter()

        if self._delegate:
            result = self._delegate.evaluate(input_data)
        else:
            result = PCROutput_v1.default_fallback("no_delegate")

        elapsed = time.perf_counter() - start
        self._records.append({
            "input": input_data.to_dict(),
            "output": result.to_dict(),
            "latency_ms": round(elapsed * 1000, 3),
            "call_number": self._call_count,
        })
        return result

    def get_health(self) -> PCRHealthStatus:
        if self._delegate:
            return self._delegate.get_health()
        return PCRHealthStatus.HEALTHY

    def get_telemetry(self) -> Dict[str, Any]:
        return {"record_count": len(self._records), "records": self._records}

    def get_capabilities(self) -> Dict[str, Any]:
        return {"supports_recording": True}

    def get_schema(self) -> Dict[str, Any]:
        return {"version": "v1_mock", "type": "recorded"}


class CounterMockPCR(IPCRRouter):
    """
    Mock PCR that counts calls per expectation type and returns configurable outputs.

    Useful for load testing and verifying that the router is called with correct inputs.
    """

    def __init__(self, return_factory: Optional[Callable[[PCRInput_v1], PCROutput_v1]] = None):
        self._factory = return_factory
        self._counters: Dict[str, int] = {}
        self._total = 0

    @property
    def name(self) -> str:
        return "counter_mock"

    @property
    def version(self) -> str:
        return "1.0.0"

    def warm_up(self, config: Dict[str, Any]) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def evaluate(self, input_data: PCRInput_v1) -> PCROutput_v1:
        self._total += 1
        exp = input_data.query or "UNKNOWN"
        self._counters[exp] = self._counters.get(exp, 0) + 1

        if self._factory:
            return self._factory(input_data)
        return PCROutput_v1(
            expectation=exp,
            noise_level=0.0,
            complexity_level=0.0,
            cognitive_profile=CognitiveProfile_v1(),
            execution_mode="BALANCED",
        )

    def get_health(self) -> PCRHealthStatus:
        return PCRHealthStatus.HEALTHY

    def get_telemetry(self) -> Dict[str, Any]:
        return {"total": self._total, "counters": self._counters.copy()}

    def get_capabilities(self) -> Dict[str, Any]:
        return {"supports_counting": True}

    def get_schema(self) -> Dict[str, Any]:
        return {"version": "v1_mock", "type": "counter"}

    def get_counts(self) -> Dict[str, int]:
        return self._counters.copy()

    def reset(self) -> None:
        self._counters.clear()
        self._total = 0


# ───────────────────────────────────────────────────────────────────────────────
# Factory helpers
# ───────────────────────────────────────────────────────────────────────────────

def create_failing_mock(error_after: int = 3, error_type: type = RuntimeError) -> SequenceMockPCR:
    """Create a mock that fails after N successful calls, then succeeds again."""
    outputs = [PCROutput_v1(expectation="SUCCESS", noise_level=0.0, complexity_level=0.0, cognitive_profile=CognitiveProfile_v1())]
    exceptions = [error_type("Injected failure")]
    return SequenceMockPCR(outputs=outputs, exceptions=exceptions)


def create_flaky_mock(success_rate: float = 0.7) -> StaticMockPCR:
    """Create a mock that fails randomly with a given probability."""
    return StaticMockPCR(MockConfig(error_rate=1.0 - success_rate, error_type=RuntimeError, error_message="Flaky failure"))


def create_slow_mock(latency_ms: float = 100, jitter_ms: float = 20) -> StaticMockPCR:
    """Create a mock that simulates consistent latency."""
    return StaticMockPCR(MockConfig(
        min_latency=latency_ms / 1000,
        max_latency=latency_ms / 1000,
        latency_jitter=jitter_ms / 1000,
    ))


def create_degraded_mock(primary_healthy: bool = False) -> StaticMockPCR:
    """Create a mock that reports degraded health."""
    return StaticMockPCR(MockConfig(
        healthy=primary_healthy,
        health_message="Degraded mock" if not primary_healthy else "Healthy mock",
    ))
