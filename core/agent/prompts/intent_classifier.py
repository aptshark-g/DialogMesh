# core/agent/prompts/intent_classifier.py
"""意图分类 Prompt —— 规则只能分 statement/question/imperative，小模型分更细意图。

任务：将用户输入分类为预定义意图类别。
输出：JSON 格式 {"intent": "...", "confidence": 0.0-1.0}

意图类别：
- chat: 闲聊/问候
- question: 简单询问
- analyze: 分析/解释
- compare: 对比/比较
- apply: 应用/实践
- evaluate: 评估/评价
- recommend: 推荐/建议
- plan: 计划/规划
- debug: 调试/排查
- refactor: 重构/优化
- code: 编写代码
- search: 搜索/查找
- summarize: 总结/概括
- statement: 陈述/说明
- imperative: 命令/请求
- unclear: 意图不明确

优化点：
- JSON 输出格式，方便解析
- 16 个类别覆盖常见对话场景
- 低温度确保一致性
"""

from __future__ import annotations

import json
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

INTENT_CLASSIFY_PROMPT = """将用户输入分类为以下意图之一。仅输出 JSON。

可选意图：chat, question, analyze, compare, apply, evaluate, recommend, plan, debug, refactor, code, search, summarize, statement, imperative, unclear

示例1：
输入："Python 的列表推导式怎么用？"
输出：{{"intent": "question", "confidence": 0.95}}

示例2：
输入："帮我对比 Flask 和 FastAPI 的优缺点"
输出：{{"intent": "compare", "confidence": 0.92}}

示例3：
输入："写一个快速排序的代码"
输出：{{"intent": "code", "confidence": 0.98}}

---
输入："{query}"
输出："""


def intent_classify_prompt(query: str) -> str:
    """生成意图分类 prompt。

    Args:
        query: 用户输入（截断到 100 字）

    Returns:
        prompt 字符串
    """
    q = query[:100] if len(query) > 100 else query
    return INTENT_CLASSIFY_PROMPT.format(query=q)


def parse_intent_result(result: str) -> Optional[Tuple[str, float]]:
    """解析意图分类结果。

    Returns:
        (intent_label, confidence) 或 None
    """
    if not result:
        return None
    try:
        # 尝试提取 JSON 部分
        start = result.find("{")
        end = result.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(result[start:end + 1])
            intent = data.get("intent", "unclear")
            confidence = float(data.get("confidence", 0.5))
            return intent, min(1.0, max(0.0, confidence))
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Intent JSON parse failed: {e}, result={result[:100]}")

    # 回退：关键词匹配
    result_lower = result.lower()
    for intent in [
        "chat", "question", "analyze", "compare", "apply", "evaluate",
        "recommend", "plan", "debug", "refactor", "code", "search",
        "summarize", "statement", "imperative", "unclear",
    ]:
        if intent in result_lower:
            return intent, 0.7

    return "unclear", 0.3
