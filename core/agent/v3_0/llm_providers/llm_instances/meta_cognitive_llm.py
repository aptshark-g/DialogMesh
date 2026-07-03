# -*- coding: utf-8 -*-
from __future__ import annotations
from core.agent.v3_0.cognitive_tree.models import CogType
from core.agent.v3_0.llm_providers.llm_instances.llm_engine import LLMEngine

_PROMPT = """你是一位元认知监督者，负责验证节点的推理质量。

节点内容：{node_content}
节点类型：{node_type}
来源 LLM：{source_llm}
证据节点：{evidence_nodes}

请输出 JSON 包含 factual_check、consistency_check、reasonableness_check、hallucination_risk、overall_validation 和 confidence。仅输出 JSON。"""

class MetaCognitiveLLM(LLMEngine):
    def __init__(self, provider=None, temperature=0.2):
        super().__init__("Meta-Cognitive-LLM", provider, CogType.META_COGNITIVE, _PROMPT, temperature, 768)
    def _build_prompt(self, ctx):
        return _PROMPT
    def _parse_response(self, text):
        p = self._try_parse_json(text)
        if p: return p
        return {"confidence": 0.3}
