# -*- coding: utf-8 -*-
from __future__ import annotations
from core.agent.v3_0.cognitive_tree.models import CogType
from core.agent.v3_0.llm_providers.llm_instances.llm_engine import LLMEngine

_PROMPT = """你是一位系统复盘师，负责分析 Cognitive Tree 的长期模式并生成改进策略。

会话范围：{session_range}
Tree 统计：{tree_stats}
已检测偏见：{biases}

请输出 JSON 包含 tree_health、bias_analysis、learning_strategies 和 confidence。仅输出 JSON。"""

class ReflectiveLLM(LLMEngine):
    def __init__(self, provider=None, temperature=0.3):
        super().__init__("Reflective-LLM", provider, CogType.REFLECTIVE, _PROMPT, temperature, 1024)
    def _build_prompt(self, ctx):
        return _PROMPT
    def _parse_response(self, text):
        p = self._try_parse_json(text)
        if p: return p
        return {"confidence": 0.3}
