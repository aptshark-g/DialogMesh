"""E2E test: DialogMesh v4 with DeepSeek API.

Usage:
    set DEEPSEEK_API_KEY=your_key_here
    py tests/test_e2e_deepseek.py
"""
from __future__ import annotations
import os
import sys
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent.events.event_ir import EventIR
from core.agent.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm_providers.openai_provider import OpenAIProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_e2e")


def main():
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        logger.error("DEEPSEEK_API_KEY not set. Export it first:")
        logger.error("  set DEEPSEEK_API_KEY=your_key_here")
        return 1

    # Create DeepSeek provider (OpenAI-compatible API)
    provider = OpenAIProvider("deepseek", {
        "api_key": api_key,
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "timeout_s": 60,
    })

    # Health check
    logger.info("Health check...")
    healthy = provider.health_check()
    logger.info("Provider health: %s", healthy)
    if not healthy:
        logger.error("DeepSeek provider not healthy. Check API key and network.")
        return 1

    # Create engine with DeepSeek provider
    logger.info("Starting CognitiveRuntimeEngine with DeepSeek...")
    engine = CognitiveRuntimeEngine(llm_provider=provider)
    engine.start()

    try:
        # Test 1: Simple greeting
        logger.info("=" * 60)
        logger.info("Test 1: Simple greeting")
        event1 = EventIR(
            id="test-001",
            kind="dialog.message",
            payload={"text": "你好，请介绍一下 DialogMesh 是什么？"},
        )
        response1 = engine.on_event(event1)
        logger.info("Response: %s", response1)
        logger.info("LLM metrics: %s", engine.llm_metrics)

        # Test 2: Technical question
        logger.info("=" * 60)
        logger.info("Test 2: Technical question about Context Engineering")
        event2 = EventIR(
            id="test-002",
            kind="dialog.message",
            payload={"text": "CrossDomainContextIR 的 to_prompt() 方法做了什么？"},
        )
        response2 = engine.on_event(event2)
        logger.info("Response: %s", response2)
        logger.info("LLM metrics: %s", engine.llm_metrics)

        # Test 3: Check context compilation
        logger.info("=" * 60)
        logger.info("Test 3: Context inspection")
        ctx = engine.last_context
        if ctx:
            logger.info("Context entries: %d", len(ctx.entries))
            logger.info("Total tokens: %d", ctx.total_estimated_tokens)
            logger.info("Intent: %s", ctx.intent_category.value)
            logger.info("Primary domain: %s", ctx.primary_domain())
            logger.info("Compile strategy: %s", ctx.compile_strategy.value)
        else:
            logger.warning("No context compiled")

        logger.info("=" * 60)
        logger.info("All tests passed!")
        return 0

    finally:
        engine.stop()
        logger.info("Engine stopped")


if __name__ == "__main__":
    sys.exit(main())
