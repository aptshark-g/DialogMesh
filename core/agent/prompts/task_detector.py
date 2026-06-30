# core/agent/prompts/task_detector.py
"""任务检测 Prompt —— 从对话中识别用户是否开启了新任务。

任务：检测对话中的任务类型和状态。
输出：JSON 格式

任务类型：
- code: 编写代码
- debug: 调试问题
- analyze: 分析/解释
- search: 搜索/查找
- learn: 学习/教程
- discuss: 讨论/交流
- implement: 实现功能
- review: 审查/评估
- plan: 计划/规划
- none: 无明确任务

任务状态：
- started: 新任务开始
- continued: 任务继续
- switched: 切换到新任务
- completed: 任务完成
- paused: 任务暂停

优化点：
- 单轮检测即可，无需历史（上下文由 DiscoursePipeline 提供）
- 结构化输出，方便 TaskManager 处理
"""

from __future__ import annotations

import json
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

TASK_DETECT_PROMPT = """判断用户输入是否开启了新任务或改变了任务状态。仅输出 JSON。

可选 type：code, debug, analyze, search, learn, discuss, implement, review, plan, none
可选 status：started, continued, switched, completed, paused

示例1：
输入："帮我写一个快速排序"
输出：{{"task_type": "code", "status": "started", "confidence": 0.95}}

示例2：
输入："不对，刚才那个排序有问题，帮我 debug 一下"
输出：{{"task_type": "debug", "status": "switched", "confidence": 0.92}}

示例3：
输入："好的，谢谢"
输出：{{"task_type": "none", "status": "continued", "confidence": 0.6}}

---
输入："{query}"
输出："""


def task_detect_prompt(query: str) -> str:
    """生成任务检测 prompt。

    Args:
        query: 用户输入（截断到 100 字）

    Returns:
        prompt 字符串
    """
    q = query[:100] if len(query) > 100 else query
    return TASK_DETECT_PROMPT.format(query=q)


def parse_task_result(result: str) -> Optional[Tuple[str, str, float]]:
    """解析任务检测结果。

    Returns:
        (task_type, status, confidence) 或 None
    """
    if not result:
        return None
    try:
        start = result.find("{")
        end = result.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(result[start:end + 1])
            task_type = data.get("task_type", "none")
            status = data.get("status", "continued")
            confidence = float(data.get("confidence", 0.5))
            return task_type, status, min(1.0, max(0.0, confidence))
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Task parse failed: {e}, result={result[:100]}")

    # 回退：关键词匹配
    result_lower = result.lower()
    for task_type in ["code", "debug", "analyze", "search", "learn", "discuss", "implement", "review", "plan"]:
        if task_type in result_lower:
            return task_type, "started", 0.6
    return "none", "continued", 0.3
