"""Isolated E2E test: DeepSeek LLM Provider + CrossDomainContextIR.to_prompt().

Bypasses the full engine import chain (which has SQLite/numpy issues in this env).
Directly tests:
  1. DeepSeek API connectivity
  2. CrossDomainContextIR serialization
  3. Prompt construction and LLM response

Usage:
    py tests/test_e2e_deepseek_isolated.py
"""
from __future__ import annotations
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_e2e")


def test_deepseek_provider():
    """Test 1: Direct DeepSeek API call."""
    from core.agent.llm_providers.openai_provider import OpenAIProvider
    from core.agent.llm_providers.base import GenerateRequest

    api_key = "YOUR_DEEPSEEK_API_KEY"

    provider = OpenAIProvider("deepseek", {
        "api_key": api_key,
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "timeout_s": 60,
    })

    logger.info("=" * 60)
    logger.info("Test 1: DeepSeek Provider Health Check")
    healthy = provider.health_check()
    logger.info("Health: %s", healthy)

    logger.info("=" * 60)
    logger.info("Test 2: Direct LLM Call")
    request = GenerateRequest(
        prompt="你好，请用一句话介绍自己。",
        system_prompt="你是一个有帮助的AI助手。",
        max_tokens=100,
        temperature=0.7,
        timeout_ms=30000,
    )
    result = provider.generate(request)
    logger.info("Success: %s", result.metrics.success)
    logger.info("Response: %s", result.text[:200])
    logger.info("Latency: %.0f ms", result.metrics.latency_ms)
    logger.info("Input tokens: %d", result.metrics.input_tokens)
    logger.info("Output tokens: %d", result.metrics.output_tokens)
    logger.info("Model: %s", result.metrics.model_id)

    return provider, result


def test_cross_domain_ir_to_prompt():
    """Test 2: CrossDomainContextIR serialization."""
    from core.agent.context.cross_domain_ir import (
        CrossDomainContextIR, IntentCategory, DomainAllocation, DomainRole,
        IREntry, CrossRef, CompileStrategy,
    )

    logger.info("=" * 60)
    logger.info("Test 3: CrossDomainContextIR.to_prompt()")

    ir = CrossDomainContextIR(
        intent_category=IntentCategory.QUERY,
        domain_allocation=[
            DomainAllocation(domain="knowledge", role=DomainRole.PRIMARY, budget_pct=0.6, budget_tokens=180),
            DomainAllocation(domain="world", role=DomainRole.AUXILIARY, budget_pct=0.25, budget_tokens=75),
            DomainAllocation(domain="skill", role=DomainRole.ANCHOR, budget_pct=0.15, budget_tokens=45),
        ],
        entries=[
            IREntry(
                domain="knowledge",
                type="HYPOTHESIS",
                content="Context Engineering improves LLM reasoning by structuring domain knowledge",
                cross_refs=[CrossRef(target_domain="world", target_event_id="evt_001", note="related module")],
                source_events=["evt_001"],
                confidence=0.92,
                estimated_tokens=45,
            ),
            IREntry(
                domain="world",
                type="MODULE",
                content="StructuralContextCompiler compiles subgraphs from World Model",
                cross_refs=[],
                source_events=["evt_002"],
                confidence=0.85,
                estimated_tokens=35,
            ),
            IREntry(
                domain="skill",
                type="PATTERN",
                content="4-round trim + 3-step landing for subgraph pruning",
                cross_refs=[CrossRef(target_domain="knowledge", target_event_id="evt_003", note="design doc ref")],
                source_events=["evt_003"],
                confidence=0.78,
                estimated_tokens=30,
            ),
        ],
        compile_strategy=CompileStrategy.BALANCED,
    )
    ir.recalc_total()

    prompt = ir.to_prompt(
        system_instruction="You are DialogMesh, a context-aware AI assistant.",
        max_tokens=500,
    )
    logger.info("Generated prompt (%d chars):", len(prompt))
    logger.info("\n%s", prompt)

    return ir, prompt


def test_full_pipeline(provider):
    """Test 3: Full pipeline — IR → prompt → DeepSeek → response."""
    from core.agent.llm_providers.base import GenerateRequest
    from core.agent.context.cross_domain_ir import (
        CrossDomainContextIR, IntentCategory, DomainAllocation, DomainRole,
        IREntry, CrossRef, CompileStrategy,
    )

    logger.info("=" * 60)
    logger.info("Test 4: Full Pipeline — IR → Prompt → DeepSeek → Response")

    # Build a realistic IR
    ir = CrossDomainContextIR(
        intent_category=IntentCategory.QUERY,
        domain_allocation=[
            DomainAllocation(domain="knowledge", role=DomainRole.PRIMARY, budget_pct=0.6, budget_tokens=180),
            DomainAllocation(domain="world", role=DomainRole.AUXILIARY, budget_pct=0.25, budget_tokens=75),
        ],
        entries=[
            IREntry(
                domain="knowledge",
                type="CONCEPT",
                content="DialogMesh v4 implements Context Engineering — compiling multi-domain knowledge into structured IR before sending to LLM",
                confidence=0.95,
                estimated_tokens=50,
            ),
            IREntry(
                domain="world",
                type="COMPONENT",
                content="CrossDomainContextIR is the unified intermediate representation with domain allocation, cross-references, and budget-aware entries",
                confidence=0.90,
                estimated_tokens=45,
            ),
            IREntry(
                domain="knowledge",
                type="FEATURE",
                content="to_prompt() serializes IR into Transformer-ready string with domain markers, cross-ref annotations, and token truncation",
                confidence=0.88,
                estimated_tokens=40,
            ),
        ],
        compile_strategy=CompileStrategy.BALANCED,
    )
    ir.recalc_total()

    # Build prompt
    system_instruction = "You are DialogMesh, a context-aware AI assistant. You receive structured context from multiple knowledge domains. Respond based on the provided context."
    prompt = ir.to_prompt(system_instruction=system_instruction, max_tokens=500)
    prompt += "\n[User]\n请根据上面的上下文，简要解释 DialogMesh v4 的 Context Engineering 设计。\n"

    logger.info("Prompt length: %d chars", len(prompt))

    # Call DeepSeek
    request = GenerateRequest(
        prompt=prompt,
        system_prompt=system_instruction,
        max_tokens=512,
        temperature=0.7,
        timeout_ms=30000,
    )
    result = provider.generate(request)

    logger.info("=" * 60)
    logger.info("LLM Response:")
    logger.info("%s", result.text)
    logger.info("=" * 60)
    logger.info("Metrics:")
    logger.info("  Success: %s", result.metrics.success)
    logger.info("  Latency: %.0f ms", result.metrics.latency_ms)
    logger.info("  Input tokens: %d", result.metrics.input_tokens)
    logger.info("  Output tokens: %d", result.metrics.output_tokens)
    logger.info("  Model: %s", result.metrics.model_id)

    return result


def main():
    logger.info("DialogMesh v4 E2E Test with DeepSeek")
    logger.info("=" * 60)

    # Test 1 & 2: Provider
    provider, _ = test_deepseek_provider()

    # Test 3: IR serialization
    _, prompt = test_cross_domain_ir_to_prompt()

    # Test 4: Full pipeline
    result = test_full_pipeline(provider)

    if result.metrics.success:
        logger.info("=" * 60)
        logger.info("✅ ALL TESTS PASSED")
        return 0
    else:
        logger.error("=" * 60)
        logger.error("❌ LLM CALL FAILED: %s", result.metrics.error_type)
        return 1


if __name__ == "__main__":
    sys.exit(main())
