# -*- coding: utf-8 -*-
from __future__ import annotations
from core.agent.v3_0.cognitive_tree.models import CogType
from core.agent.v3_0.llm_providers.llm_instances.llm_engine import LLMEngine

_PROMPT = """你是一位认知分析师，负责分析用户输入的语义特征。

输入：{user_input}
上下文：{context}

请输出 JSON，包含 noise_analysis、expectation_inference、cognitive_snapshot 和 confidence 字段。仅输出 JSON。"""

class PCRLLM(LLMEngine):
    def __init__(self, provider=None, temperature=0.3):
        super().__init__("PCR-LLM", provider, CogType.PERCEPTION, _PROMPT, temperature, 512)
    def _build_prompt(self, ctx):
        return _PROMPT
    def _parse_response(self, text):
        p = self._try_parse_json(text)
        if p: return p
        return {"confidence": 0.3}
