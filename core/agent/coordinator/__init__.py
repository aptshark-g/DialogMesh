# core/agent/coordinator/__init__.py
"""多级协同协调器 —— 规则 → 本地小模型 → 远程大模型 三级决策架构。"""

from __future__ import annotations

from core.agent.coordinator.small_model_client import (
    SmallModelClient,
    get_small_model_client,
    reset_small_model_client,
)
from core.agent.coordinator.complexity_evaluator import (
    ComplexityEvaluator,
    ComplexityScore,
)
from core.agent.coordinator.mode_router import (
    ModeRouter,
    ProcessingMode,
)

# 多层 LLM 客户端（新增）
from core.agent.coordinator.multi_tier_llm_client import (
    MultiTierLLMClient,
    get_multi_tier_client,
    reset_multi_tier_client,
    invoke_llm,
    LLMProvider,
    TASK_TIER_MAP,
)

__all__ = [
    "SmallModelClient",
    "get_small_model_client",
    "reset_small_model_client",
    "ComplexityEvaluator",
    "ComplexityScore",
    "ModeRouter",
    "ProcessingMode",
    # 多层客户端
    "MultiTierLLMClient",
    "get_multi_tier_client",
    "reset_multi_tier_client",
    "invoke_llm",
    "LLMProvider",
    "TASK_TIER_MAP",
]