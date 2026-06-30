# core/agent/prompts/__init__.py
"""小模型 Prompt 模板库 —— 专为 Qwen2.5-1.5B/3B 等小模型优化。

设计原则：
- 简洁：单个 prompt < 200 tokens（小模型上下文窗口有限）
- 结构化：明确输出格式（JSON/标记/选项），减少解析错误
- Few-shot：1-2 个例子，帮助小模型理解任务
- 中文：中文 prompt 对小模型效果更好
- 确定性：低温度（0.1-0.3），短输出（max_tokens=50-100）

使用方式：
    from core.agent.prompts import boundary_judge_prompt
    prompt = boundary_judge_prompt("文本A", "文本B")
    result = small_model.invoke(prompt)
"""

from __future__ import annotations

from core.agent.prompts.boundary_judge import boundary_judge_prompt, parse_boundary_result
from core.agent.prompts.intent_classifier import intent_classify_prompt, parse_intent_result
from core.agent.prompts.summarizer import v3_summarize_prompt, parse_v3_summary
from core.agent.prompts.user_profiler import user_profile_extract_prompt, parse_user_profile
from core.agent.prompts.task_detector import task_detect_prompt, parse_task_result

__all__ = [
    "boundary_judge_prompt",
    "parse_boundary_result",
    "intent_classify_prompt",
    "parse_intent_result",
    "v3_summarize_prompt",
    "parse_v3_summary",
    "user_profile_extract_prompt",
    "parse_user_profile",
    "task_detect_prompt",
    "parse_task_result",
]
