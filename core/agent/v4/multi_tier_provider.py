"""MultiTierLLMProvider: wraps multiple LLM providers as pipeline tiers."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any

from core.agent.v4.tiered_pipeline import Tier, MultiTierPipeline

logger = logging.getLogger(__name__)


@dataclass
class LLMResult:
    content: str = ""; confidence: float = 0.5
    provider_name: str = ""; latency_ms: float = 0.0


class MultiTierLLMProvider:
    """Multi-tier LLM provider with automatic fallback."""
    def __init__(self, providers: list[dict], registry=None):
        tiers = []
        for i, p in enumerate(providers):
            def make_process(provider):
                def process(prompt: str, _ctx: dict) -> LLMResult:
                    start = __import__("time").perf_counter()
                    try:
                        if callable(provider.get("call")):
                            return LLMResult(content=provider["call"](prompt),
                                             confidence=0.9, provider_name=provider.get("name", ""))
                    except Exception:
                        logger.warning("Provider %s failed", provider.get("name", ""))
                    return LLMResult(content="", confidence=0.0, provider_name=provider.get("name", ""))
                return process
            tier = Tier(level=i, name=p.get("name", f"tier{i}"),
                        process=make_process(p), confidence_threshold=0.7,
                        time_budget_ms=p.get("timeout_ms", 5000))
            tiers.append(tier)
        self._pipeline = MultiTierPipeline(tiers, name="llm_provider")

    def complete(self, prompt: str) -> str:
        result = self._pipeline.execute(prompt)
        val = result.value
        return val.content if isinstance(val, LLMResult) else str(val)

    def stats(self) -> dict:
        return self._pipeline.stats()
