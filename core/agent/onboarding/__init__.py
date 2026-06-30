# core/agent/onboarding/__init__.py
"""Onboarding Agent — 引导系统。

帮助用户快速了解 Discourse Block Tree 系统，
提供系统介绍、健康检查、配置指导、模型下载和使用示例。

用法：
    from core.agent.onboarding import OnboardingAgent

    agent = OnboardingAgent()
    print(agent.greet())
    print(agent.respond("怎么下载模型？"))
"""

from __future__ import annotations

try:
    from core.agent.onboarding.agent import OnboardingAgent
except ImportError:
    from .agent import OnboardingAgent  # type: ignore

__all__ = ["OnboardingAgent"]
