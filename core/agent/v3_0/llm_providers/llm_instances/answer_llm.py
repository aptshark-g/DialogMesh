# -*- coding: utf-8 -*-
from __future__ import annotations
from core.agent.v3_0.cognitive_tree.models import CogType
from core.agent.v3_0.llm_providers.llm_instances.llm_engine import LLMEngine

_PROMPT = """你是 DialogMesh 的回答生成器，负责综合所有认知层输出生成自然、准确、诚实的回复。

用户输入：{user_input}
用户画像：{user_profile}
算法分析：{algorithm_result}
意图解析：{llm_result}
融合模式：{fusion_mode}
系统置信度：{system_confidence}
Cognitive Tree 活跃分支：{active_cognitive_branch}
回复风格：{style}
最大长度：{max_length}

请输出 JSON 包含 response、confidence、honesty_declared、cited_nodes、format。若置信度 < 0.4 请诚实说明。仅输出 JSON。"""

class AnswerLLM(LLMEngine):
    def __init__(self, provider=None, temperature=0.5):
        super().__init__("Answer-LLM", provider, CogType.ANSWER, _PROMPT, temperature, 2048)
    def _build_prompt(self, ctx):
        return _PROMPT
    def _parse_response(self, text):
        p = self._try_parse_json(text)
        if p: return p
        return {"confidence": 0.3}
