# -*- coding: utf-8 -*-
"""
core/agent/pcr/tests/test_datacontract.py
─────────────────────────────────────────
Unit tests for PCR data contracts, interfaces, registry, fallback, lifecycle,
config, and telemetry.

Run: python -m unittest core.agent.pcr.tests.test_datacontract -v
"""

from __future__ import annotations

import unittest
import os
import tempfile
import json
from typing import Any, Dict

from core.agent.pcr.datacontract import (
    PCRInput_v1, PCROutput_v1, CognitiveProfile_v1, HistoryEntry, PCRVersion,
)
from core.agent.pcr.interface import IPCRRouter, PCRHealthStatus
from core.agent.pcr.registry import (
    register_pcr, unregister_pcr, is_registered, create_pcr,
    list_available_pcr, clear_registry,
)
from core.agent.pcr.fallback import FallbackEngine, FallbackConfig
from core.agent.pcr.lifecycle import PCRLifecycleManager
from core.agent.pcr.config import ConfigManager
from core.agent.pcr.telemetry import TelemetryCollector


# ──────────────────────────────────────────────────────────────────────────────
# Data Contract Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestPCRInput_v1(unittest.TestCase):

    def test_minimal_construction(self):
        inp = PCRInput_v1(query="scan")
        self.assertEqual(inp.query, "scan")
        self.assertEqual(inp.session_history, [])
        self.assertEqual(inp.metadata, {})

    def test_full_construction(self):
        hist = [HistoryEntry(role="user", content="hello", metadata={})]
        inp = PCRInput_v1(query="scan", session_history=hist, metadata={"key": "val"})
        self.assertEqual(len(inp.session_history), 1)
        self.assertEqual(inp.metadata["key"], "val")

    def test_to_dict(self):
        inp = PCRInput_v1(query="test")
        d = inp.to_dict()
        self.assertEqual(d["query"], "test")
        self.assertEqual(d["version"], "1.0")

    def test_from_dict(self):
        d = {"query": "test", "session_history": [], "metadata": {"a": 1}, "version": "1.0"}
        inp = PCRInput_v1.from_dict(d)
        self.assertEqual(inp.query, "test")
        self.assertEqual(inp.metadata["a"], 1)

    def test_from_dict_missing_fields(self):
        d = {"query": "test"}
        inp = PCRInput_v1.from_dict(d)
        self.assertEqual(inp.query, "test")
        self.assertEqual(inp.session_history, [])

    def test_invalid_none_query(self):
        with self.assertRaises(ValueError):
            PCRInput_v1(query=None)

    def test_invalid_type_query(self):
        with self.assertRaises(TypeError):
            PCRInput_v1(query=123)


class TestPCROutput_v1(unittest.TestCase):

    def test_default_construction(self):
        out = PCROutput_v1()
        self.assertEqual(out.expectation, "UNKNOWN")
        self.assertEqual(out.noise_level, 0.0)
        self.assertEqual(out.complexity_level, 0.0)
        self.assertEqual(out.execution_mode, "BALANCED")

    def test_full_construction(self):
        cog = CognitiveProfile_v1()
        out = PCROutput_v1(
            expectation="SCAN",
            noise_level=0.2,
            complexity_level=0.8,
            cognitive_profile=cog,
            execution_mode="CONVERGENT",
            parser_config_overrides={"max_tokens": 100},
        )
        self.assertEqual(out.expectation, "SCAN")
        self.assertEqual(out.noise_level, 0.2)
        self.assertEqual(out.execution_mode, "CONVERGENT")
        self.assertEqual(out.parser_config_overrides["max_tokens"], 100)

    def test_to_dict(self):
        out = PCROutput_v1(expectation="SCAN")
        d = out.to_dict()
        self.assertEqual(d["expectation"], "SCAN")
        self.assertEqual(d["version"], "1.0")

    def test_from_dict(self):
        d = {
            "expectation": "SCAN",
            "noise_level": 0.1,
            "complexity_level": 0.5,
            "cognitive_profile": {"metacognitive_level": 0.0, "divergence_ratio": 0.5, "tracking_depth": 0, "description_stability": 1.0},
            "execution_mode": "BALANCED",
            "prompt_style": "BALANCED",
            "ambiguity_strategy": "BALANCED",
            "parser_config_overrides": {},
            "version": "1.0",
        }
        out = PCROutput_v1.from_dict(d)
        self.assertEqual(out.expectation, "SCAN")
        self.assertEqual(out.noise_level, 0.1)

    def test_default_fallback(self):
        out = PCROutput_v1.default_fallback("test_reason")
        self.assertEqual(out.expectation, "UNKNOWN")
        self.assertEqual(out.noise_level, 0.5)
        self.assertEqual(out.complexity_level, 0.5)
        self.assertEqual(out.execution_mode, "CLARIFICATION")
        self.assertEqual(out.prompt_style, "BALANCED")
        self.assertEqual(out.ambiguity_strategy, "CONSERVATIVE_ASK")
        self.assertTrue(out.is_fallback)

    def test_invalid_noise_range(self):
        with self.assertRaises(ValueError):
            PCROutput_v1(noise_level=1.5)
        with self.assertRaises(ValueError):
            PCROutput_v1(noise_level=-0.1)

    def test_invalid_complexity_range(self):
        with self.assertRaises(ValueError):
            PCROutput_v1(complexity_level=1.5)

    def test_frozen_immutable(self):
        out = PCROutput_v1(expectation="SCAN")
        with self.assertRaises(Exception):
            out.expectation = "PATCH"


class TestCognitiveProfile_v1(unittest.TestCase):

    def test_defaults(self):
        cog = CognitiveProfile_v1()
        self.assertEqual(cog.metacognition, 0.0)
        self.assertEqual(cog.divergence, 0.0)
        self.assertEqual(cog.tracking_depth, 0.0)
        self.assertEqual(cog.stability, 0.0)
        self.assertEqual(cog.confidence, 0.0)

    def test_validation_ranges(self):
        with self.assertRaises(ValueError):
            CognitiveProfile_v1(metacognition=1.5)
        with self.assertRaises(ValueError):
            CognitiveProfile_v1(divergence=-0.1)
        with self.assertRaises(ValueError):
            CognitiveProfile_v1(tracking_depth=-1)

    def test_to_dict(self):
        cog = CognitiveProfile_v1(metacognition=0.5)
        d = cog.to_dict()
        self.assertEqual(d["metacognition"], 0.5)

    def test_from_dict(self):
        d = {"metacognition": 0.3, "divergence": 0.7, "tracking_depth": 0.2, "stability": 0.9, "confidence": 0.8}
        cog = CognitiveProfile_v1.from_dict(d)
        self.assertEqual(cog.metacognition, 0.3)
        self.assertEqual(cog.tracking_depth, 0.2)


class TestHistoryEntry(unittest.TestCase):

    def test_construction(self):
        h = HistoryEntry(role="user", content="test", metadata={"ts": 1})
        self.assertEqual(h.role, "user")
        self.assertEqual(h.content, "test")

    def test_to_dict(self):
        h = HistoryEntry(role="assistant", content="ok")
        d = h.to_dict()
        self.assertEqual(d["role"], "assistant")
        self.assertEqual(d["content"], "ok")

    def test_from_dict(self):
        d = {"role": "user", "content": "hi", "metadata": {}}
        h = HistoryEntry.from_dict(d)
        self.assertEqual(h.role, "user")


class TestPCRVersion(unittest.TestCase):

    def test_current_version(self):
        self.assertEqual(PCRVersion.current(), "1.0")

    def test_is_compatible(self):
        self.assertTrue(PCRVersion.is_compatible("1.0", "1.0"))
        self.assertFalse(PCRVersion.is_compatible("1.0", "2.0"))
        self.assertFalse(PCRVersion.is_compatible("1.0", "0.9"))

    def test_validate(self):
        PCRVersion.validate("1.0")  # should not raise
        with self.assertRaises(ValueError):
            PCRVersion.validate("2.0")


# ──────────────────────────────────────────────────────────────────────────────
# Interface Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestIPCRRouter(unittest.TestCase):

    def test_cannot_instantiate_abstract(self):
        with self.assertRaises(TypeError):
            IPCRRouter()

    def test_reload_config_default(self):
        # Create a minimal concrete subclass
        class DummyRouter(IPCRRouter):
            @property
            def name(self): return "dummy"
            @property
            def version(self): return "1.0.0"
            def warm_up(self, config): pass
            def shutdown(self): pass
            def evaluate(self, inp): return PCROutput_v1()
            def get_health(self): return PCRHealthStatus.HEALTHY
            def get_telemetry(self): return {}
            def get_capabilities(self): return {}
            def get_schema(self): return {}

        router = DummyRouter()
        self.assertFalse(router.reload_config({}))


# ──────────────────────────────────────────────────────────────────────────────
# Registry Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestPCRRegistry(unittest.TestCase):

    def setUp(self):
        clear_registry()

    def tearDown(self):
        clear_registry()

    def test_register_and_get(self):
        class DummyRouter(IPCRRouter):
            @property
            def name(self): return "dummy"
            @property
            def version(self): return "1.0.0"
            def warm_up(self, config): pass
            def shutdown(self): pass
            def evaluate(self, inp): return PCROutput_v1()
            def get_health(self): return PCRHealthStatus()
            def get_telemetry(self): return {}
            def get_capabilities(self): return {}
            def get_schema(self): return {}

        register_pcr("dummy", DummyRouter)
        available = list_available_pcr()
        self.assertIn("dummy", available)
        self.assertTrue(is_registered("dummy"))

        router = create_pcr("dummy")
        self.assertEqual(router.name, "dummy")

    def test_duplicate_registration(self):
        class R1(IPCRRouter):
            @property
            def name(self): return "r1"
            @property
            def version(self): return "1.0.0"
            def warm_up(self, c): pass
            def shutdown(self): pass
            def evaluate(self, i): return PCROutput_v1()
            def get_health(self): return PCRHealthStatus()
            def get_telemetry(self): return {}
            def get_capabilities(self): return {}
            def get_schema(self): return {}

        register_pcr("dup", R1)
        with self.assertRaises(ValueError):
            register_pcr("dup", R1)

    def test_unregister(self):
        class R2(IPCRRouter):
            @property
            def name(self): return "r2"
            @property
            def version(self): return "1.0.0"
            def warm_up(self, c): pass
            def shutdown(self): pass
            def evaluate(self, i): return PCROutput_v1()
            def get_health(self): return PCRHealthStatus()
            def get_telemetry(self): return {}
            def get_capabilities(self): return {}
            def get_schema(self): return {}

        register_pcr("r2", R2)
        unregister_pcr("r2")
        self.assertFalse(is_registered("r2"))

    def test_create_unknown(self):
        with self.assertRaises(ValueError):
            create_pcr("nonexistent")

    def test_factory_helper(self):
        from core.agent.pcr.tests.mock_pcr import StaticMockPCR, MockConfig
        router = StaticMockPCR(MockConfig(fixed_expectation="TEST"))
        self.assertEqual(router.name, "static_mock")
        out = router.evaluate(PCRInput_v1(query="anything"))
        self.assertEqual(out.expectation, "TEST")


# ──────────────────────────────────────────────────────────────────────────────
# Fallback Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestFallbackEngine(unittest.TestCase):

    def setUp(self):
        from core.agent.pcr.tests.mock_pcr import StaticMockPCR, MockConfig

        class FallbackMockPCR(StaticMockPCR):
            def __init__(self):
                super().__init__(MockConfig(fixed_expectation="FALLBACK"))

        self.FallbackMockPCR = FallbackMockPCR

    def test_successful_primary(self):
        from core.agent.pcr.tests.mock_pcr import StaticMockPCR, MockConfig

        primary = StaticMockPCR(MockConfig(fixed_expectation="PRIMARY"))
        engine = FallbackEngine(primary, {}, FallbackConfig())

        out = engine.evaluate(PCRInput_v1(query="test"))
        self.assertEqual(out.expectation, "PRIMARY")

    def test_fallback_on_failure(self):
        from core.agent.pcr.tests.mock_pcr import StaticMockPCR, MockConfig

        primary = StaticMockPCR(MockConfig(error_rate=1.0, error_type=RuntimeError, error_message="fail"))
        engine = FallbackEngine(primary, {"fallback_mock": self.FallbackMockPCR}, FallbackConfig(strategy="degraded", fallback_chain=["fallback_mock"]))

        out = engine.evaluate(PCRInput_v1(query="test"))
        self.assertEqual(out.expectation, "FALLBACK")

    def test_default_fallback_on_both_failure(self):
        from core.agent.pcr.tests.mock_pcr import StaticMockPCR, MockConfig

        primary = StaticMockPCR(MockConfig(error_rate=1.0))
        engine = FallbackEngine(primary, {}, FallbackConfig(strategy="conservative"))

        out = engine.evaluate(PCRInput_v1(query="test"))
        self.assertEqual(out.expectation, "UNKNOWN")
        self.assertEqual(out.execution_mode, "CLARIFICATION")

    def test_degraded_mode(self):
        from core.agent.pcr.tests.mock_pcr import StaticMockPCR, MockConfig

        primary = StaticMockPCR(MockConfig(error_rate=1.0, error_type=RuntimeError, error_message="down"))
        engine = FallbackEngine(primary, {"fallback_mock": self.FallbackMockPCR}, FallbackConfig(strategy="degraded", fallback_chain=["fallback_mock"]))

        out = engine.evaluate(PCRInput_v1(query="test"))
        self.assertEqual(out.expectation, "FALLBACK")

    def test_health_check(self):
        from core.agent.pcr.tests.mock_pcr import StaticMockPCR, MockConfig

        healthy = StaticMockPCR(MockConfig(healthy=True))
        unhealthy = StaticMockPCR(MockConfig(healthy=False))
        engine = FallbackEngine(healthy, {}, FallbackConfig())
        self.assertEqual(engine.get_health(), PCRHealthStatus.HEALTHY)

        engine2 = FallbackEngine(unhealthy, {}, FallbackConfig())
        self.assertEqual(engine2.get_health(), PCRHealthStatus.UNHEALTHY)


# ──────────────────────────────────────────────────────────────────────────────
# Lifecycle Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestLifecycleManager(unittest.TestCase):

    def setUp(self):
        from core.agent.pcr.tests.mock_pcr import StaticMockPCR
        register_pcr("static_mock", StaticMockPCR)

    def tearDown(self):
        clear_registry()

    def test_initialize_success(self):
        lm = PCRLifecycleManager()
        ok, err = lm.initialize({
            "implementation": "static_mock",
            "fallback_strategy": "conservative",
            "fallback_chain": [],
            "health_check_interval_sec": 999,
        })
        self.assertTrue(ok)
        self.assertIsNone(err)
        lm.shutdown()

    def test_initialize_failure_unknown_impl(self):
        lm = PCRLifecycleManager()
        ok, err = lm.initialize({
            "implementation": "nonexistent",
            "fallback_strategy": "conservative",
        })
        self.assertFalse(ok)
        self.assertIn("not registered", err)

    def test_evaluate_after_init(self):
        lm = PCRLifecycleManager()
        lm.initialize({
            "implementation": "static_mock",
            "fallback_strategy": "conservative",
            "fallback_chain": [],
            "health_check_interval_sec": 999,
        })
        out = lm.evaluate(PCRInput_v1(query="test"))
        self.assertEqual(out.expectation, "MOCK_STATIC")
        lm.shutdown()

    def test_evaluate_before_init(self):
        lm = PCRLifecycleManager()
        out = lm.evaluate(PCRInput_v1(query="test"))
        self.assertEqual(out.expectation, "UNKNOWN")

    def test_health(self):
        lm = PCRLifecycleManager()
        lm.initialize({
            "implementation": "static_mock",
            "fallback_strategy": "conservative",
            "fallback_chain": [],
            "health_check_interval_sec": 999,
        })
        health = lm.get_health()
        self.assertEqual(health, PCRHealthStatus.HEALTHY)
        lm.shutdown()

    def test_health_before_init(self):
        lm = PCRLifecycleManager()
        health = lm.get_health()
        self.assertEqual(health, PCRHealthStatus.UNHEALTHY)

    def test_telemetry(self):
        lm = PCRLifecycleManager()
        lm.initialize({
            "implementation": "static_mock",
            "fallback_strategy": "conservative",
            "fallback_chain": [],
            "health_check_interval_sec": 999,
        })
        lm.evaluate(PCRInput_v1(query="test"))
        telem = lm.get_telemetry()
        self.assertIn("call_count", telem)
        lm.shutdown()

    def test_hot_reload(self):
        lm = PCRLifecycleManager()
        lm.initialize({
            "implementation": "static_mock",
            "fallback_strategy": "conservative",
            "fallback_chain": [],
            "health_check_interval_sec": 999,
        })
        result = lm.hot_reload_config({"impl_config": {"fixed_expectation": "RELOADED"}})
        self.assertTrue(result)
        lm.shutdown()


# ──────────────────────────────────────────────────────────────────────────────
# Config Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestConfigManager(unittest.TestCase):

    def test_yaml_load(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not available")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"implementation": "rule_based", "max_retry": 3, "fallback_strategy": "conservative"}, f)
            path = f.name
        try:
            cm = ConfigManager(path)
            cfg = cm.get_global()
            self.assertEqual(cfg.implementation, "rule_based")
            self.assertEqual(cfg.max_retry, 3)
            self.assertEqual(cfg.fallback_strategy, "conservative")
        finally:
            os.unlink(path)

    def test_json_load(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"implementation": "mock", "max_retry": 5}, f)
            path = f.name
        try:
            cm = ConfigManager(path)
            cfg = cm.get_global()
            self.assertEqual(cfg.implementation, "mock")
            self.assertEqual(cfg.max_retry, 5)
        finally:
            os.unlink(path)

    def test_env_override(self):
        os.environ["PCR_MAX_RETRY"] = "7"
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump({"implementation": "rule_based", "max_retry": 1}, f)
                path = f.name
            try:
                cm = ConfigManager(path)
                cfg = cm.get_global()
                self.assertEqual(cfg.max_retry, 7)
            finally:
                os.unlink(path)
        finally:
            del os.environ["PCR_MAX_RETRY"]

    def test_hot_reload_no_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"implementation": "rule_based"}, f)
            path = f.name
        try:
            cm = ConfigManager(path)
            changed = cm.check_hot_reload()
            self.assertEqual(changed, [])
        finally:
            os.unlink(path)

    def test_invalid_config(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"implementation": "", "fallback_strategy": "invalid"}, f)
            path = f.name
        try:
            cm = ConfigManager(path)
            cfg = cm.get_global()
            ok, err = cfg.validate()
            self.assertFalse(ok)
            self.assertIn("implementation", err)
        finally:
            os.unlink(path)


# ──────────────────────────────────────────────────────────────────────────────
# Telemetry Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestTelemetryCollector(unittest.TestCase):

    def test_record_and_stats(self):
        tc = TelemetryCollector(max_records=5)
        tc.record(latency_ms=10)
        tc.record(latency_ms=20)
        tc.record(latency_ms=30)
        stats = tc.get_stats()
        self.assertEqual(stats["call_count"], 3)
        self.assertEqual(stats["avg_latency_ms"], 20.0)
        self.assertEqual(stats["max_latency_ms"], 30.0)

    def test_window_overflow(self):
        tc = TelemetryCollector(max_records=3)
        tc.record(latency_ms=10)
        tc.record(latency_ms=20)
        tc.record(latency_ms=30)
        tc.record(latency_ms=40)
        stats = tc.get_stats()
        self.assertEqual(stats["call_count"], 3)
        self.assertEqual(stats["max_latency_ms"], 40.0)

    def test_empty_stats(self):
        tc = TelemetryCollector()
        stats = tc.get_stats()
        self.assertEqual(stats["call_count"], 0)
        self.assertEqual(stats["avg_latency_ms"], 0.0)

    def test_latency_distribution(self):
        tc = TelemetryCollector(max_records=10)
        for i in range(10):
            tc.record(latency_ms=float(i))
        stats = tc.get_stats()
        self.assertEqual(stats["p50_latency_ms"], 5.0)
        self.assertEqual(stats["p99_latency_ms"], 9.0)


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    unittest.main()
