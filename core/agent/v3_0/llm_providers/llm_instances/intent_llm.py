# -*- coding: utf-8 -*-
from __future__ import annotations
from core.agent.v3_0.cognitive_tree.models import CogType
from core.agent.v3_0.llm_providers.llm_instances.llm_engine import LLMEngine

_PROMPT = """你是一位意图分析师，负责从用户输入中提取深层意图和隐含实体。

输入：{user_input}
实体：{entities}
历史：{history}

请输出 JSON，包含 intent_inference（primary_intent/confidence/implied_entities/ambiguity_assessment）和 confidence 字段。仅输出 JSON。"""

class IntentLLM(LLMEngine):
    def __init__(self, provider=None, temperature=0.3):
        super().__init__("Intent-LLM", provider, CogType.REASONING, _PROMPT, temperature, 512)
    def _build_prompt(self, ctx):
        return _PROMPT
    def _parse_response(self, text):
        p = self._try_parse_json(text)
        if p: return p
        return {"confidence": 0.3}
