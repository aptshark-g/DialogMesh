# -*- coding: utf-8 -*-
from __future__ import annotations
from core.agent.v3_0.cognitive_tree.models import CogType
from core.agent.v3_0.llm_providers.llm_instances.llm_engine import LLMEngine

_PROMPT = """你是一位规划师，负责根据意图和可用工具生成任务计划。

意图：{intent}
上下文：{context}
可用 Skill：{available_skills}

请输出 JSON，包含 strategy、reasoning、steps、confidence、fallback_strategy 字段。仅输出 JSON。"""

class PlanningLLM(LLMEngine):
    def __init__(self, provider=None, temperature=0.4):
        super().__init__("Planning-LLM", provider, CogType.PLANNING, _PROMPT, temperature, 1024)
    def _build_prompt(self, ctx):
        return _PROMPT
    def _parse_response(self, text):
        p = self._try_parse_json(text)
        if p: return p
        return {"confidence": 0.3}
