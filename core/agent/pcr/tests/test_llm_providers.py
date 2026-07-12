# -*- coding: utf-8 -*-
"""
core/agent/pcr/tests/test_llm_providers.py
──────────────────────────────────────────
LLM Provider 架构单元测试（v2.4 新增）。

覆盖：
  - MockProvider 固定响应 / 错误模拟 / 延迟
  - OpenAIProvider 初始化（无 API 时不实际调用）
  - LocalProvider 预估延迟
  - HybridRouter 路由策略（latency / privacy / cost / quality）
  - ProviderFactory 配置解析
  - 与现有编排门控集成：使用 MockProvider 替换 Router LLM
"""

from __future__ import annotations

import unittest
import time
import json
from unittest.mock import MagicMock, patch

from core.agent.llm_providers import (
    MockProvider, OpenAIProvider, LocalProvider,
    HybridRouter, ProviderFactory,
    GenerateRequest, GenerateResult, LLMCallMetrics,
)


class TestMockProvider(unittest.TestCase):
    """验证 MockProvider 行为。"""

    def test_fixed_text_response(self):
        p = MockProvider("mock", {"response_text": "hello world"})
        req = GenerateRequest(prompt="test")
        res = p.generate(req)
        self.assertTrue(res.metrics.success)
        self.assertEqual(res.text, "hello world")
        self.assertLess(res.metrics.latency_ms, 50)

    def test_fixed_json_response(self):
        p = MockProvider("mock", {
            "response_json": {"blueprint_id": "RULE_FAST_PATH", "reason": "test"}
        })
        req = GenerateRequest(prompt="test", response_format="json")
        res = p.generate(req)
        self.assertTrue(res.metrics.success)
        self.assertEqual(res.text, '{"blueprint_id": "RULE_FAST_PATH", "reason": "test"}')
        self.assertIsNotNone(res.structured)
        self.assertEqual(res.structured.get("blueprint_id"), "RULE_FAST_PATH")

    def test_simulate_error(self):
        p = MockProvider("mock", {"simulate_error": "timeout"})
        req = GenerateRequest(prompt="test")
        res = p.generate(req)
        self.assertFalse(res.metrics.success)
        self.assertEqual(res.metrics.error_type, "timeout")
        self.assertEqual(res.text, "")

    def test_simulate_latency(self):
        p = MockProvider("mock", {"response_text": "delayed", "latency_ms": 100})
        req = GenerateRequest(prompt="test")
        start = time.time() * 1000
        res = p.generate(req)
        elapsed = (time.time() * 1000) - start
        self.assertTrue(res.metrics.success)
        self.assertGreaterEqual(elapsed, 80)  # 允许 20ms 误差

    def test_health(self):
        p = MockProvider("mock", {"health": True})
        self.assertTrue(p.health_check())
        p2 = MockProvider("mock2", {"health": False})
        self.assertFalse(p2.health_check())

    def test_estimate_latency(self):
        p = MockProvider("mock", {"latency_ms": 42})
        self.assertEqual(p.estimate_latency_ms(100, 100), 42.0)


class TestLocalProviderEstimate(unittest.TestCase):
    """验证 LocalProvider 延迟预估公式。"""

    def test_ollama_small_model(self):
        p = LocalProvider("local", {
            "backend": "ollama", "model_path": "qwen2.5:1.5b"
        })
        est = p.estimate_latency_ms(256, 128)
        self.assertGreater(est, 0)
        # 1.5B 模型应该更快（基准 50+12*384 - 修正 15+5*384）
        self.assertLess(est, 5000)

    def test_vllm_estimate(self):
        p = LocalProvider("local", {
            "backend": "vllm", "model_path": "qwen2.5-7b"
        })
        est = p.estimate_latency_ms(256, 128)
        self.assertGreater(est, 0)
        # vLLM 应该比 transformers 快
        p_slow = LocalProvider("local2", {
            "backend": "transformers", "model_path": "qwen2.5-7b"
        })
        est_slow = p_slow.estimate_latency_ms(256, 128)
        self.assertLess(est, est_slow)


class TestHybridRouter(unittest.TestCase):
    """验证 HybridRouter 路由策略。"""

    def setUp(self):
        # 创建两个 MockProvider：一个快（本地），一个慢（云端）
        self.fast_local = MockProvider("fast", {
            "response_text": "local", "latency_ms": 20, "health": True,
        })
        self.slow_cloud = MockProvider("slow", {
            "response_text": "cloud", "latency_ms": 200, "health": True,
        })
        self.unhealthy = MockProvider("dead", {
            "response_text": "dead", "health": False,
        })

    def test_latency_strategy(self):
        router = HybridRouter("router", {
            "default_strategy": "latency",
            "providers": [],
        })
        router.register_provider("local", self.fast_local)
        router.register_provider("cloud", self.slow_cloud)

        # 延迟预算 50ms → 只能选 local
        req = GenerateRequest(prompt="test", metadata={"latency_budget_ms": 50})
        res = router.generate(req)
        self.assertEqual(res.text, "local")

        # 延迟预算 500ms → 选 local（更快）
        req2 = GenerateRequest(prompt="test", metadata={"latency_budget_ms": 500})
        res2 = router.generate(req2)
        self.assertEqual(res2.text, "local")

    def test_privacy_strategy(self):
        router = HybridRouter("router", {
            "default_strategy": "privacy",
            "providers": [],
        })
        router.register_provider("local", self.fast_local)
        router.register_provider("cloud", self.slow_cloud)

        # 隐私敏感 → 强制本地
        req = GenerateRequest(prompt="test", metadata={"privacy_sensitive": True})
        res = router.generate(req)
        self.assertEqual(res.text, "local")

    def test_fallback_on_failure(self):
        router = HybridRouter("router", {
            "default_strategy": "latency",
            "providers": [],
        })
        # 本地模拟失败
        failing_local = MockProvider("fail", {
            "response_text": "", "simulate_error": "timeout", "health": True,
        })
        router.register_provider("local", failing_local)
        router.register_provider("cloud", self.slow_cloud)

        req = GenerateRequest(prompt="test")
        res = router.generate(req)
        # 本地失败后 fallback 到云端
        self.assertEqual(res.text, "cloud")
        self.assertTrue(res.metrics.success)
        self.assertIn("cloud", res.metrics.provider_name)

    def test_all_providers_unhealthy(self):
        router = HybridRouter("router", {
            "default_strategy": "latency",
            "providers": [],
        })
        router.register_provider("dead", self.unhealthy)
        req = GenerateRequest(prompt="test")
        res = router.generate(req)
        self.assertFalse(res.metrics.success)
        self.assertIn("all_providers_failed", res.metrics.error_type)

    def test_health_check_any(self):
        router = HybridRouter("router", {
            "default_strategy": "latency",
            "providers": [],
        })
        router.register_provider("dead", self.unhealthy)
        self.assertFalse(router.health_check())
        router.register_provider("live", self.fast_local)
        self.assertTrue(router.health_check())

    def test_stats(self):
        router = HybridRouter("router", {
            "default_strategy": "latency",
            "providers": [],
        })
        router.register_provider("local", self.fast_local)
        # 先调用一次，记录 metrics
        req = GenerateRequest(prompt="test")
        router.generate(req)
        stats = router.get_provider_stats()
        self.assertIn("local", stats)
        self.assertTrue(stats["local"]["health"])


class TestProviderFactory(unittest.TestCase):
    """验证 ProviderFactory 配置解析。"""

    def test_from_config_mock(self):
        config = {"type": "mock", "name": "test-mock", "response_text": "factory"}
        p = ProviderFactory.from_config(config)
        self.assertIsInstance(p, MockProvider)
        self.assertEqual(p.name, "test-mock")
        res = p.generate(GenerateRequest(prompt="t"))
        self.assertEqual(res.text, "factory")

    def test_from_config_local(self):
        config = {
            "type": "local", "name": "test-local",
            "backend": "ollama", "model_path": "qwen2.5:1.5b",
        }
        p = ProviderFactory.from_config(config)
        self.assertIsInstance(p, LocalProvider)
        self.assertEqual(p.backend, "ollama")

    def test_from_config_hybrid(self):
        config = {
            "type": "hybrid", "name": "test-hybrid",
            "default_strategy": "latency",
            "providers": [
                {"id": "m1", "type": "mock", "response_text": "a", "latency_ms": 10, "health": True},
                {"id": "m2", "type": "mock", "response_text": "b", "latency_ms": 100, "health": True},
            ],
        }
        p = ProviderFactory.from_config(config)
        self.assertIsInstance(p, HybridRouter)
        res = p.generate(GenerateRequest(prompt="t"))
        self.assertEqual(res.text, "a")  # 延迟策略选 m1

    def test_from_config_unknown_type(self):
        with self.assertRaises(ValueError):
            ProviderFactory.from_config({"type": "unknown"})


class TestIntegrationWithOrchestration(unittest.TestCase):
    """验证与现有编排门控集成。"""

    def test_orchestrator_with_mock_llm(self):
        """使用 MockProvider 作为 Router LLM，验证端到端流程。"""
        from core.agent.v3_common.gates import DualTrackOrchestrator, OrchestrationGate

        # Mock PCR：UNKNOWN 高噪声，触发 Gate-2
        mock_pcr_out = MagicMock()
        mock_pcr_out.expectation = "UNKNOWN"
        mock_pcr_out.noise_level = 0.9
        mock_pcr_out.complexity_level = 0.2
        mock_pcr_out.cognitive_profile = MagicMock()
        mock_pcr_out.cognitive_profile.confidence = 0.5
        mock_pcr_out.cognitive_profile.metacognition = 0.5

        pcr_instance = MagicMock()
        pcr_instance.evaluate = MagicMock(return_value=mock_pcr_out)
        parser = MagicMock()

        # 创建 MockProvider 作为 Router LLM
        router_llm = MockProvider("router-llm", {
            "response_json": {
                "selected_blueprint": "RULE_FAST_PATH",
                "reason_code": "UNKNOWN_FALLBACK",
            },
            "latency_ms": 10,
        })

        def router_fn(router_input):
            req = GenerateRequest(
                prompt=json.dumps(router_input),
                response_format="json",
            )
            res = router_llm.generate(req)
            return res.text

        orch = DualTrackOrchestrator(pcr_instance, parser, router_llm_fn=router_fn)
        result = orch.process("那个东西", [])
        self.assertEqual(result.blueprint_id, "RULE_FAST_PATH")

    def test_llm_generate_explanation_with_mock(self):
        """验证 CognitiveTools.llm_generate_explanation 使用 Provider。"""
        from core.agent.tools.cognitive_tools import CognitiveTools, ExecutionContext

        provider = MockProvider("explainer", {
            "response_text": "这是扫描内存的操作说明...",
            "latency_ms": 5,
        })

        ctx = ExecutionContext(
            raw_input="scan memory",
            llm_provider=provider,
        )
        state = {"pcr_evaluate": MagicMock(expectation="TOOL", noise_level=0.1, complexity_level=0.3)}
        text = CognitiveTools.llm_generate_explanation(ctx, state)
        self.assertIn("扫描内存", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
