# -*- coding: utf-8 -*-
"""
core/agent/llm_providers/__init__.py
──────────────────────────────────────
LLM Provider 包入口（v2.4 新增）。
"""

from __future__ import annotations

from core.agent.llm_providers.base import (
    LLMProvider,
    GenerateRequest,
    GenerateResult,
    LLMCallMetrics,
)
from core.agent.llm_providers.openai_provider import OpenAIProvider
from core.agent.llm_providers.local_provider import LocalProvider
from core.agent.llm_providers.hybrid_router import HybridRouter
from core.agent.llm_providers.mock_provider import MockProvider
from core.agent.llm_providers.provider_factory import ProviderFactory, get_default_router

__all__ = [
    "LLMProvider",
    "GenerateRequest",
    "GenerateResult",
    "LLMCallMetrics",
    "OpenAIProvider",
    "LocalProvider",
    "HybridRouter",
    "MockProvider",
    "ProviderFactory",
    "get_default_router",
]
