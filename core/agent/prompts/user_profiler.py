# core/agent/prompts/user_profiler.py
"""用户特征提取 Prompt —— 从对话中自动提取用户画像。

任务：从用户输入中提取技术水平、领域偏好、关注实体。
输出：JSON 格式

优化点：
- 结构化输出，方便存入 UserProfile
- 增量更新：只提取本轮新增信息
- 小模型 lightweight：单个 prompt < 150 tokens
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

USER_PROFILE_EXTRACT_PROMPT = """从用户对话中提取以下信息。仅输出 JSON。

字段：
- tech_level: beginner/intermediate/expert/unknown
- domains: 领域偏好列表（如 ["Python", "机器学习"]）
- entities: 用户关注的实体列表
- style: concise/detailed/tutorial/unknown

示例1：
输入："我是 Python 新手，想学机器学习"
输出：{{"tech_level": "beginner", "domains": ["Python", "机器学习"], "entities": ["Python", "机器学习"], "style": "tutorial"}}

示例2：
输入："这个算法的时间复杂度怎么分析？"
输出：{{"tech_level": "intermediate", "domains": ["算法"], "entities": ["时间复杂度"], "style": "concise"}}

---
输入："{query}"
输出："""


def user_profile_extract_prompt(query: str) -> str:
    """生成用户特征提取 prompt。

    Args:
        query: 用户输入（截断到 100 字）

    Returns:
        prompt 字符串
    """
    q = query[:100] if len(query) > 100 else query
    return USER_PROFILE_EXTRACT_PROMPT.format(query=q)


def parse_user_profile(result: str) -> Optional[Dict]:
    """解析用户特征提取结果。

    Returns:
        {"tech_level": ..., "domains": [...], "entities": [...], "style": ...}
    """
    if not result:
        return None
    try:
        start = result.find("{")
        end = result.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(result[start:end + 1])
            return {
                "tech_level": data.get("tech_level", "unknown"),
                "domains": data.get("domains", []) or [],
                "entities": data.get("entities", []) or [],
                "style": data.get("style", "unknown"),
            }
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"User profile parse failed: {e}, result={result[:100]}")
    return None
