# core/agent/prompts/summarizer.py
"""v3 摘要生成 Prompt —— 规则模板信息熵低，小模型生成高质量主题摘要。

任务：从多轮对话中生成一句话主题描述，包含主题 + 核心行为 + 结论。
输出格式："主题: ... | 行为: ... | 结论: ..."

优化点：
- 极简输出（一句话），避免 token 浪费
- 中文输出，保持语义密度
- 与规则摘要互补：规则提供结构，小模型提供语义
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

V3_SUMMARIZE_PROMPT = """从以下对话中提炼一句话摘要。格式：主题|行为|结论

示例：
对话：
1. 用户：Python 的列表推导式怎么用？
2. 用户：那字典推导式呢？
3. 用户：帮我写个快速排序
摘要：主题:Python数据结构 | 行为:推导式学习→代码实现 | 结论:快速排序已完成

---
对话：
{conversation_text}
摘要："""


def v3_summarize_prompt(conversation_text: str, max_lines: int = 5) -> str:
    """生成 v3 摘要 prompt。

    Args:
        conversation_text: 多轮对话文本（已格式化）
        max_lines: 最多保留的对话轮数（截断到最近 N 轮）

    Returns:
        prompt 字符串
    """
    lines = conversation_text.strip().split("\n")
    # 保留最近 N 轮
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    truncated = "\n".join(lines)
    # 整体截断到 300 字
    if len(truncated) > 300:
        truncated = truncated[:297] + "..."
    return V3_SUMMARIZE_PROMPT.format(conversation_text=truncated)


def parse_v3_summary(result: str) -> Optional[str]:
    """解析 v3 摘要结果。

    Returns:
        清理后的摘要字符串，或 None
    """
    if not result:
        return None
    result = result.strip()
    # 移除前缀词
    for prefix in ["摘要：", "摘要:", "Summary:", "结果：", "→"]:
        if result.startswith(prefix):
            result = result[len(prefix):].strip()
    # 移除多余换行
    result = result.replace("\n", " ").strip()
    if len(result) < 5:
        return None
    return result
