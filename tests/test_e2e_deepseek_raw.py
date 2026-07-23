"""Isolated E2E test: DeepSeek API via raw HTTP (urllib).

Bypasses ALL Python library dependencies (openai, numpy, sqlite3).
Directly tests:
  1. DeepSeek API connectivity via urllib
  2. CrossDomainContextIR serialization (pure Python)
  3. Prompt construction and LLM response

Usage:
    set DEEPSEEK_API_KEY=your_key_here
    py tests/test_e2e_deepseek_raw.py
"""
from __future__ import annotations
import json
import os
import sys
import logging
import urllib.request
import urllib.error
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_e2e")

BASE_URL = "https://api.deepseek.com/v1"
MODEL = "deepseek-chat"


def get_api_key():
    """Get API key from environment."""
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        logger.error("DEEPSEEK_API_KEY not set. Export it first:")
        logger.error("  set DEEPSEEK_API_KEY=your_key_here")
    return key


def deepseek_chat(api_key, messages, max_tokens=512, temperature=0.7, timeout=30):
    """Call DeepSeek API via raw urllib."""
    url = f"{BASE_URL}/chat/completions"
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            latency_ms = (time.time() - start) * 1000

            choice = body["choices"][0]
            text = choice["message"].get("content", "")
            usage = body.get("usage", {})

            return {
                "success": True,
                "text": text,
                "latency_ms": latency_ms,
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "model": body.get("model", MODEL),
                "raw": body,
            }
    except urllib.error.HTTPError as e:
        latency_ms = (time.time() - start) * 1000
        error_body = e.read().decode("utf-8") if e.fp else ""
        return {
            "success": False,
            "error": f"HTTP {e.code}: {error_body}",
            "latency_ms": latency_ms,
        }
    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        return {
            "success": False,
            "error": str(e),
            "latency_ms": latency_ms,
        }


def test_api_connectivity(api_key):
    """Test 1: Simple API call."""
    logger.info("=" * 60)
    logger.info("Test 1: DeepSeek API Connectivity")

    result = deepseek_chat(
        api_key=api_key,
        messages=[
            {"role": "system", "content": "你是一个有帮助的AI助手。"},
            {"role": "user", "content": "你好，请用一句话介绍自己。"},
        ],
        max_tokens=100,
    )

    logger.info("Success: %s", result["success"])
    if result["success"]:
        logger.info("Response: %s", result["text"][:200])
        logger.info("Latency: %.0f ms", result["latency_ms"])
        logger.info("Input tokens: %d", result["input_tokens"])
        logger.info("Output tokens: %d", result["output_tokens"])
        logger.info("Model: %s", result["model"])
    else:
        logger.error("Error: %s", result.get("error", "Unknown"))

    return result


def test_ir_serialization():
    """Test 2: CrossDomainContextIR.to_prompt() (pure Python)."""
    logger.info("=" * 60)
    logger.info("Test 2: CrossDomainContextIR.to_prompt()")

    # Manually import only the IR module (no numpy/sqlite dependencies)
    from core.agent.context.cross_domain_ir import (
        CrossDomainContextIR, IntentCategory, DomainAllocation, DomainRole,
        IREntry, CrossRef, CompileStrategy,
    )

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
                type="CONCEPT",
                content="DialogMesh v4 implements Context Engineering — compiling multi-domain knowledge into structured IR before sending to LLM",
                cross_refs=[CrossRef(target_domain="world", target_event_id="evt_001", note="related module")],
                source_events=["evt_001"],
                confidence=0.95,
                estimated_tokens=50,
            ),
            IREntry(
                domain="world",
                type="COMPONENT",
                content="CrossDomainContextIR is the unified intermediate representation with domain allocation, cross-references, and budget-aware entries",
                cross_refs=[],
                source_events=["evt_002"],
                confidence=0.90,
                estimated_tokens=45,
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


def test_full_pipeline(api_key):
    """Test 3: Full pipeline — IR → prompt → DeepSeek → response."""
    from core.agent.context.cross_domain_ir import (
        CrossDomainContextIR, IntentCategory, DomainAllocation, DomainRole,
        IREntry, CrossRef, CompileStrategy,
    )

    logger.info("=" * 60)
    logger.info("Test 3: Full Pipeline — IR → Prompt → DeepSeek → Response")

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
                content="DialogMesh v4 的核心设计是 Context Engineering：在进入 LLM 之前，将多域知识（工程链、对话树、用户画像、行为链、因果链）编译为带跨域引用的统一中间表示（CrossDomainContextIR）。",
                confidence=0.95,
                estimated_tokens=60,
            ),
            IREntry(
                domain="world",
                type="COMPONENT",
                content="CognitiveRuntimeEngine 是 v4 的编排器，管理四条认知路径（Fast/Async/Slow/Deep），集成 PathAwareScheduler、BayesianOptimizer 和 LLM Provider。",
                confidence=0.90,
                estimated_tokens=55,
            ),
            IREntry(
                domain="knowledge",
                type="FEATURE",
                content="to_prompt() 方法将 CrossDomainContextIR 序列化为 Transformer-ready 的 prompt 字符串，包含 domain 标记、cross_ref 注释和 token 预算截断。",
                confidence=0.88,
                estimated_tokens=50,
            ),
        ],
        compile_strategy=CompileStrategy.BALANCED,
    )
    ir.recalc_total()

    system_instruction = (
        "You are DialogMesh, a context-aware AI assistant. "
        "You receive structured context from multiple knowledge domains. "
        "Respond based on the provided context, not general knowledge."
    )
    context_prompt = ir.to_prompt(system_instruction=system_instruction, max_tokens=500)
    user_message = "请根据上面的上下文，简要解释 DialogMesh v4 的 Context Engineering 设计。"

    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": context_prompt + "\n[User]\n" + user_message},
    ]

    logger.info("Prompt length: %d chars", len(messages[1]["content"]))

    result = deepseek_chat(api_key, messages, max_tokens=512, temperature=0.7)

    logger.info("=" * 60)
    logger.info("LLM Response:")
    logger.info("%s", result.get("text", "[No response]"))
    logger.info("=" * 60)
    logger.info("Metrics:")
    logger.info("  Success: %s", result["success"])
    logger.info("  Latency: %.0f ms", result["latency_ms"])
    logger.info("  Input tokens: %d", result.get("input_tokens", 0))
    logger.info("  Output tokens: %d", result.get("output_tokens", 0))
    logger.info("  Model: %s", result.get("model", "unknown"))

    return result


def main():
    logger.info("DialogMesh v4 E2E Test with DeepSeek (Raw HTTP)")
    logger.info("=" * 60)

    api_key = get_api_key()
    if not api_key:
        return 1

    # Test 1: API connectivity
    r1 = test_api_connectivity(api_key)
    if not r1["success"]:
        logger.error("❌ API connectivity failed. Aborting.")
        return 1

    # Test 2: IR serialization
    test_ir_serialization()

    # Test 3: Full pipeline
    r3 = test_full_pipeline(api_key)

    if r3["success"]:
        logger.info("=" * 60)
        logger.info("✅ ALL TESTS PASSED")
        return 0
    else:
        logger.error("=" * 60)
        logger.error("❌ PIPELINE FAILED: %s", r3.get("error", "Unknown"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
