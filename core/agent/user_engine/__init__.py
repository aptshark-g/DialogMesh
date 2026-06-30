# core/agent/user_engine/__init__.py
"""用户引擎 —— 从对话中提取用户画像、管理用户身份、跨会话聚合。

核心能力（Phase 2）：
- 用户画像提取（技术水平、领域、风格、工具偏好、耐心水平、纠错频率）
- 用户画像管理（SQLite 持久化、跨会话自动加载）
- 结构化上下文注入（JSON 格式 system context，取代字符串拼接）
- 统计追踪（话题切换率、意图连续性、注意力跨度）
- 增量更新（每轮对话后自动更新画像）
"""

from __future__ import annotations

from core.agent.user_engine.user_profile import UserProfile
from core.agent.user_engine.user_manager import UserManager
from core.agent.user_engine.user_extractor import UserExtractor

__all__ = [
    "UserProfile",
    "UserManager",
    "UserExtractor",
]