# core/agent/prompts/boundary_judge.py
"""边界判断 Prompt —— 当规则粘合度在灰色区域时，小模型仲裁是否切分。

任务：判断两段对话是否属于同一话题。
输出：SAME（同一话题）或 DIFF（不同话题）

优化点：
- 极简 prompt（<100 tokens）
- 仅输出两个词之一，无多余解释
- 小模型 Qwen2.5-1.5B 在 CPU 上 < 20ms
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


BOUNDARY_JUDGE_PROMPT = """判断以下两段对话是否属于同一话题。仅回答：SAME 或 DIFF

示例1：
文本A: "Python 的列表推导式怎么用？"
文本B: "那字典推导式呢？"
→ SAME

示例2：
文本A: "Python 的列表推导式怎么用？"
文本B: "今天天气怎么样？"
→ DIFF

---
文本A: "{text_a}"
文本B: "{text_b}"
→ """


def boundary_judge_prompt(text_a: str, text_b: str) -> str:
    """生成边界判断 prompt。

    Args:
        text_a: 前一段文本（已截断到 50 字以内）
        text_b: 当前文本（已截断到 50 字以内）

    Returns:
        可直接发送给小模型的 prompt 字符串
    """
    # 截断，保持 prompt 简洁
    a = text_a[:50] if len(text_a) > 50 else text_a
    b = text_b[:50] if len(text_b) > 50 else text_b
    return BOUNDARY_JUDGE_PROMPT.format(text_a=a, text_b=b)


def parse_boundary_result(result: str) -> Optional[bool]:
    """解析边界判断结果。

    Args:
        result: 小模型输出字符串

    Returns:
        True: 同一话题（SAME）
        False: 不同话题（DIFF）
        None: 解析失败
    """
    if not result:
        return None
    result_upper = result.strip().upper()
    if "SAME" in result_upper and "DIFF" not in result_upper:
        return True
    if "DIFF" in result_upper:
        return False
    # 模糊匹配：根据常见表达
    if result_upper in ("是", "YES", "Y", "TRUE", "T"):
        return True
    if result_upper in ("否", "NO", "N", "FALSE", "F"):
        return False
    logger.warning(f"Boundary parse ambiguous: {result!r}")
    return None
