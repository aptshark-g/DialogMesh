# -*- coding: utf-8 -*-
"""
core/agent/llm_providers/provider_factory.py
──────────────────────────────────────────────
Provider 工厂与配置加载（v2.4 新增）。

支持从 YAML 配置加载 Provider，或代码中直接注册。
默认提供 "simple_local" 预设（适合开发）。
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from core.agent.llm_providers.base import LLMProvider
from core.agent.llm_providers.openai_provider import OpenAIProvider
from core.agent.llm_providers.local_provider import LocalProvider
from core.agent.llm_providers.hybrid_router import HybridRouter
from core.agent.llm_providers.mock_provider import MockProvider


class ProviderFactory:
    """
    Provider 工厂：从配置字典构建 Provider 实例。
    支持单 Provider 或 HybridRouter。
    """

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> LLMProvider:
        """
        根据配置构建 Provider。
        配置格式：
          {
            "type": "hybrid" | "openai" | "local" | "mock",
            "name": "my-router",
            ...  # 具体参数
          }
        """
        ptype = config.get("type", "hybrid")
        name = config.get("name", "default")

        if ptype == "hybrid":
            return HybridRouter(name, config)
        elif ptype == "openai":
            return OpenAIProvider(name, config)
        elif ptype == "local":
            return LocalProvider(name, config)
        elif ptype == "mock":
            return MockProvider(name, config)
        else:
            raise ValueError(f"Unknown provider type: {ptype}")

    @classmethod
    def from_yaml(cls, path: Optional[str] = None) -> LLMProvider:
        """从 YAML 配置文件加载。"""
        import yaml
        path = path or os.path.join(
            os.path.dirname(__file__), "..", "..", "config", "llm_providers.yaml"
        )
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return cls.from_config(config)


# ── 默认预设 ───────────────────────────────────────────────────────

def get_default_router() -> HybridRouter:
    """
    返回默认 HybridRouter 预设。
    适合开发环境：优先 Mock（如果配置），否则本地 Ollama，最后云端。
    """
    config = {
        "name": "default-hybrid",
        "type": "hybrid",
        "default_strategy": "latency",
        "fallback_chain": ["local-1.5b", "local-7b", "cloud-api"],
        "providers": [
            {
                "id": "local-1.5b",
                "type": "local",
                "backend": "ollama",
                "model_path": "qwen2.5:1.5b",
            },
            {
                "id": "local-7b",
                "type": "local",
                "backend": "ollama",
                "model_path": "qwen2.5:7b",
            },
            {
                "id": "cloud-api",
                "type": "openai",
                "model": "gpt-4o-mini",
                "api_key": os.environ.get("OPENAI_API_KEY", ""),
                "base_url": "https://api.openai.com/v1",
            },
        ],
    }
    return HybridRouter("default-hybrid", config)
