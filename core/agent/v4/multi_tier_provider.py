"""MultiTierLLMProvider: wraps multiple LLM providers as pipeline tiers."""
from __future__ import annotations
import logging, time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple, Union

from core.agent.v4.tiered_pipeline import Tier, MultiTierPipeline

logger = logging.getLogger(__name__)


@dataclass
class LLMResult:
    content: str = ""; confidence: float = 0.5
    provider_name: str = ""; latency_ms: float = 0.0


ProviderSpec = Union[Tuple[str, Callable, dict], Dict[str, Any]]


class MultiTierLLMProvider:

    def __init__(self, providers: List[ProviderSpec], registry=None):
        tiers = []
        for i, spec in enumerate(providers):
            if isinstance(spec, dict):
                name = spec.get("name", f"tier{i}")
                call = spec.get("call")
                timeout = spec.get("timeout_ms", 5000)
            else:
                name, call, opts = spec
                timeout = opts.get("timeout_ms", 5000) if opts else 5000

            tier = Tier(level=i, name=name,
                        process=self._make_process(name, call),
                        confidence_threshold=0.7, time_budget_ms=timeout)
            tiers.append(tier)
        self._pipeline = MultiTierPipeline(tiers, name="llm_provider")

    @staticmethod
    def _make_process(name, call):
        def process(prompt, ctx):
            try:
                kw = ctx.get("kwargs", {}) if ctx else {}
                result = call(prompt, **kw) if kw else call(prompt)
                return LLMResult(content=str(result), confidence=0.9, provider_name=name)
            except Exception:
                logger.warning("Provider %s failed", name)
                return LLMResult(content="", confidence=0.0, provider_name=name)
        return process

    def complete(self, prompt: str, **kwargs) -> str:
        ctx = {"kwargs": kwargs} if kwargs else {}
        result = self._pipeline.execute(prompt, ctx)
        val = result.value
        return val.content if isinstance(val, LLMResult) else str(val)

    def generate(self, prompt: str, **kwargs) -> str:
        return self.complete(prompt, **kwargs)

    def stats(self) -> dict:
        return self._pipeline.stats()
